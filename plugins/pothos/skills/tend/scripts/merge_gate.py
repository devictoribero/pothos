#!/usr/bin/env python3
"""Decide whether a pull request may merge itself, and merge it when it may.

Usage:
  merge_gate.py status    [PR] [--repo DIR]   print the pull request's state and the verdict; changes nothing
  merge_gate.py merge     [PR] [--repo DIR]   merge when the verdict is ready, then delete the remote branch
  merge_gate.py authorize [PR] (--quote TEXT | --ticket FILE) [--repo DIR]
                                              add the contract's label for a person who authorized this pull
                                              request, and say who did in a comment on it

PR is a number; without it, the pull request of the current branch. Run it from inside the repository.

A pull request is a candidate only when the contract has `pr.auto_merge` and the pull request carries its
label: the label is a person's decision about that pull request. `authorize` adds it on their behalf, with
their own words (`--quote`, which the PreToolUse hook checks against what the person typed in the session)
or a ticket that carries a `Merge: auto` line above its first section (`--ticket`). A candidate
is ready when, on its head commit, every check finished green (or, in a repository whose workflows never
run on pull requests, a passing verify receipt exists), no person's review asks for changes, no review thread
is open and GitHub can merge it. A commit that reports no checks while a workflow in `.github/workflows` of
this checkout runs on pushes or pull requests is treated as checks not reported yet, never as a repository
without checks. `merge` then runs `gh pr merge --<method> --match-head-commit <sha>`, so a push between the
check and the merge makes GitHub refuse it, and deletes the head branch on the remote when GitHub did not.

Exit codes: 0 ready (status), merged (merge) or labelled (authorize), 1 waiting (checks running, review pending, branch behind),
2 no contract, 3 not a candidate (or nothing to authorize with), 4 needs a person (changes requested, conflicts with the base),
5 gh is missing or failed, 64 usage. Standard library only.
"""
import json
import os
import re
import subprocess
import sys

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
sys.path.insert(0, os.path.realpath(SHARED))
import contract  # noqa: E402

READY, WAITING, NO_CONTRACT, NOT_CANDIDATE, NEEDS_PERSON, GH_FAILED, USAGE = 0, 1, 2, 3, 4, 5, 64
VERDICTS = {READY: "ready", WAITING: "waiting", NOT_CANDIDATE: "not a candidate", NEEDS_PERSON: "needs a person"}
METHODS = ("squash", "rebase", "merge")
PR_FIELDS = ("number,url,state,isDraft,baseRefName,headRefName,headRefOid,isCrossRepository,labels,"
             "mergeable,mergeStateStatus,latestReviews,statusCheckRollup")
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}
WORKFLOWS = os.path.join(".github", "workflows")
# The top-level `on:` key of a workflow (also written `"on":`): what follows on the same line, and the
# indented block under it.
ON_BLOCK = re.compile(r'^"?on"?:[ \t]*([^\n]*)\n((?:[ \t]+[^\n]*\n|[ \t]*\n)*)', re.M)
EVENTS = re.compile(r"\b(?:push|pull_request|pull_request_target)\b")
NESTED_EVENT = re.compile(r"^[ \t]+(?:push|pull_request|pull_request_target)[ \t]*:", re.M)
# A ticket authorizes its pull request with this line in its header, above the first `## ` section, so a
# comment appended at the bottom cannot add it.
TICKET_AUTO = re.compile(r"^merge:[ \t]*auto[ \t]*$", re.I)
REVIEW_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) {
    reviewThreads(first: 100) { pageInfo { hasNextPage } nodes { isResolved } }
    latestOpinionatedReviews(first: 100) { nodes { state author { login __typename } } } } } }"""


class GhError(Exception):
    pass


def gh(args, root):
    try:
        out = subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True)
    except FileNotFoundError:
        raise GhError("gh is not installed")
    if out.returncode != 0:
        raise GhError((out.stderr or out.stdout).strip().splitlines()[-1] if (out.stderr or out.stdout).strip()
                      else f"gh {' '.join(args[:2])} exited {out.returncode}")
    return out.stdout


def owner_repo(url):
    match = re.match(r"^https?://[^/]+/([^/]+)/([^/]+)/pull/\d+", url or "")
    if not match:
        raise GhError(f"cannot read owner and repository from {url!r}")
    return match.group(1), match.group(2)


def fetch(root, number):
    pr = json.loads(gh(["pr", "view", *([number] if number else []), "--json", PR_FIELDS], root))
    owner, name = owner_repo(pr.get("url"))
    out = json.loads(gh(["api", "graphql", "-f", f"query={REVIEW_QUERY}", "-F", f"owner={owner}",
                         "-F", f"name={name}", "-F", f"number={pr['number']}"], root))
    node = (((out.get("data") or {}).get("repository") or {}).get("pullRequest") or {})
    threads = node.get("reviewThreads") or {}
    pr["unresolvedThreads"] = sum(1 for n in threads.get("nodes") or [] if not n.get("isResolved"))
    pr["moreThreads"] = bool((threads.get("pageInfo") or {}).get("hasNextPage"))
    reviews = (node.get("latestOpinionatedReviews") or {}).get("nodes") or []
    pr["botReviewers"] = sorted({(r.get("author") or {}).get("login") for r in reviews
                                 if (r.get("author") or {}).get("__typename") == "Bot"} - {None})
    pr["nameWithOwner"] = f"{owner}/{name}"
    return pr


def check_state(item):
    """passed, pending or failed, for one entry of statusCheckRollup (a check run or a commit status)."""
    if item.get("__typename") == "StatusContext" or "context" in item:
        state = (item.get("state") or "").upper()
        return "passed" if state == "SUCCESS" else "pending" if state in ("PENDING", "EXPECTED") else "failed"
    if (item.get("status") or "").upper() != "COMPLETED":
        return "pending"
    return "passed" if (item.get("conclusion") or "").upper() in GREEN else "failed"


def check_name(item):
    return item.get("name") or item.get("context") or "?"


def receipt_passed(root, data, commit):
    """A passing, clean verify receipt for this commit: full, and e2e when the contract configures it."""
    folder = os.path.join(contract.pothos_home(), "receipts", contract.key_for(root, "receipts"), commit)
    levels = ["full"]
    if (data.get("verify") or {}).get("e2e") or any(e.get("e2e") for e in ((data.get("run") or {}).get("environments") or [])):
        levels.append("e2e")
    for level in levels:
        try:
            with open(os.path.join(folder, f"{level}.json"), encoding="utf-8") as fh:
                receipt = json.load(fh)
        except (OSError, ValueError):
            return False
        if receipt.get("status") != "passed" or receipt.get("dirty"):
            return False
    return True


def runs_on_pushes(text):
    """True when a workflow file triggers on push, pull_request or pull_request_target: `on: push`,
    `on: [push, pull_request]`, `on: {push: {}, ...}`, or those keys indented under `on:`. A job or step
    named `push` outside the `on:` block does not count."""
    match = ON_BLOCK.search(text.replace("\r\n", "\n") + "\n")
    if not match:
        return False
    inline = match.group(1).split("#", 1)[0]
    if inline.strip():
        return bool(EVENTS.search(inline))
    return bool(NESTED_EVENT.search(match.group(2)))


def expects_checks(root):
    """True when the checkout has a workflow that runs on pushes or pull requests, so a commit without checks
    is one whose checks have not been reported yet. A workflow whose branch or path filters leave this pull
    request out still counts: the gate then waits, and a person merges."""
    folder = os.path.join(root, WORKFLOWS)
    if not os.path.isdir(folder):
        return False
    for name in sorted(os.listdir(folder)):
        if name.endswith((".yml", ".yaml")):
            try:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as fh:
                    if runs_on_pushes(fh.read()):
                        return True
            except OSError:
                continue
    return False


def evaluate(pr, data, receipt_ok, checks_expected=False):
    """The verdict and the facts behind it. Pure: everything it needs comes in as arguments.
    checks_expected: the repository has workflows that run on this pull request, so no checks means not yet."""
    auto = ((data.get("pr") or {}).get("auto_merge")) or {}
    label = auto.get("label")
    base = (data.get("pr") or {}).get("base") or "main"
    labels = {(l.get("name") or "").casefold() for l in pr.get("labels") or []}  # GitHub matches labels regardless of case
    checks = pr.get("statusCheckRollup") or []
    states = [(check_name(c), check_state(c)) for c in checks]
    failed = [n for n, s in states if s == "failed"]
    pending = [n for n, s in states if s == "pending"]
    bots = set(pr.get("botReviewers") or [])
    changes = sorted({(r.get("author") or {}).get("login", "?") for r in pr.get("latestReviews") or []
                      if (r.get("state") or "").upper() == "CHANGES_REQUESTED"
                      and (r.get("author") or {}).get("login") not in bots})
    threads = pr.get("unresolvedThreads", 0)
    more_threads = pr.get("moreThreads", False)
    mergeable = (pr.get("mergeable") or "UNKNOWN").upper()
    merge_state = (pr.get("mergeStateStatus") or "UNKNOWN").upper()

    facts = [f"pr #{pr.get('number')} ({pr.get('headRefName')} -> {pr.get('baseRefName')}) at {(pr.get('headRefOid') or '')[:12]}"
             + (" from a fork" if pr.get("isCrossRepository") else "")]
    if not checks and checks_expected:
        facts.append("checks: none reported yet on this commit (the repository has workflows that run on it)")
    elif not checks:
        facts.append("checks: none on this commit; verify receipt " + ("passed" if receipt_ok else "missing or not passing"))
    else:
        passed = len(states) - len(failed) - len(pending)
        facts.append(f"checks: {passed} passed, {len(pending)} running, {len(failed)} failed"
                     + (f" ({', '.join(failed)})" if failed else ""))
    facts.append("reviews: " + (f"changes requested by {', '.join(changes)}" if changes else "none asking for changes"))
    facts.append(f"threads: {threads} unresolved" + (" of the first 100; there are more" if more_threads else ""))
    facts.append(f"mergeable: {mergeable.lower()}, merge state: {merge_state.lower()}")

    not_candidate = []
    if not label:
        not_candidate.append("the contract has no pr.auto_merge")
    elif label.casefold() not in labels:
        not_candidate.append(f"the pull request does not carry the label {label!r}")
    if (pr.get("state") or "").upper() != "OPEN":
        not_candidate.append(f"the pull request is {(pr.get('state') or 'unknown').lower()}")
    if pr.get("isDraft"):
        not_candidate.append("the pull request is a draft")
    if pr.get("baseRefName") != base:
        not_candidate.append(f"it targets {pr.get('baseRefName')!r}, not the contract's base {base!r}")
    facts.append("candidate: " + ("yes, label " + repr(label) if not not_candidate else "no, " + "; ".join(not_candidate)))

    person, waiting = [], []
    if changes:
        person.append(f"changes requested by {', '.join(changes)}")
    if mergeable == "CONFLICTING" or merge_state == "DIRTY":
        person.append("the branch conflicts with the base")
    if failed:
        waiting.append(f"failed checks: {', '.join(failed)}")
    if pending:
        waiting.append(f"checks still running: {', '.join(pending)}")
    if not checks and checks_expected:
        waiting.append("the workflows have not reported on this commit yet")
    elif not checks and not receipt_ok:
        waiting.append("no checks on this commit and no passing verify receipt")
    if threads:
        waiting.append(f"{threads} unresolved review thread(s)")
    if more_threads:
        waiting.append("more than 100 review threads: cannot tell they are all resolved")
    if merge_state == "BEHIND":
        waiting.append(f"the branch is behind {pr.get('baseRefName')}: update it")
    if mergeable == "UNKNOWN" or merge_state == "UNKNOWN":
        waiting.append("GitHub is still computing mergeability")
    if merge_state == "BLOCKED" and not (failed or pending or changes or threads):
        waiting.append("GitHub's branch rules block the merge (a required review or check)")

    if not_candidate:
        otherwise = person + waiting
        return NOT_CANDIDATE, facts, not_candidate + [
            ("otherwise needs a person: " if person else "otherwise waiting: ") + "; ".join(otherwise) if otherwise
            else "otherwise ready"]
    if person:
        return NEEDS_PERSON, facts, person + waiting
    if waiting:
        return WAITING, facts, waiting
    return READY, facts, []


def report(verdict, facts, reasons):
    for line in facts:
        print(line)
    print(f"verdict: {VERDICTS[verdict]}" + (f": {'; '.join(reasons)}" if reasons else ""))


def delete_remote_branch(root, pr):
    branch = pr["headRefName"]
    if pr.get("isCrossRepository"):
        return f"kept {branch}: it lives in a fork"
    dependants = json.loads(gh(["pr", "list", "--base", branch, "--state", "open", "--json", "number"], root) or "[]")
    if dependants:
        return f"kept {branch}: open pull requests target it ({', '.join('#' + str(d['number']) for d in dependants)})"
    try:
        gh(["api", f"repos/{pr['nameWithOwner']}/git/ref/heads/{branch}"], root)
    except GhError as exc:
        if "404" in str(exc) or "Not Found" in str(exc):
            return f"{branch} already deleted on the remote"
        return f"kept {branch}: could not read it on the remote ({exc})"
    gh(["api", "-X", "DELETE", f"repos/{pr['nameWithOwner']}/git/refs/heads/{branch}"], root)
    return f"deleted {branch} on the remote"


def ticket_authorizes(path):
    """True when the ticket's header (the lines above its first `## ` section) has a `Merge: auto` line."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("## "):
                    return False
                if TICKET_AUTO.match(line.strip()):
                    return True
    except OSError:
        return False
    return False


def authorize(root, data, number, quote, ticket):
    label = ((data.get("pr") or {}).get("auto_merge") or {}).get("label")
    if not label:
        print("cannot authorize: the contract has no pr.auto_merge", file=sys.stderr)
        return NOT_CANDIDATE
    if ticket and not ticket_authorizes(ticket):
        print(f"cannot authorize: {ticket} has no `Merge: auto` line above its first section", file=sys.stderr)
        return NOT_CANDIDATE
    pr = json.loads(gh(["pr", "view", *([number] if number else []), "--json", "number,labels"], root))
    if label.casefold() in {(l.get("name") or "").casefold() for l in pr.get("labels") or []}:
        print(f"#{pr['number']} already carries {label!r}")
        return READY
    source = (f"the person, in their own words:\n\n> {quote}" if quote
              else f"the ticket `{ticket}`, which carries `Merge: auto`.")
    body = (f"Auto-merge authorized by {source}\n\n`tend` merges this pull request through its merge gate once every "
            f"check is green, no review asks for changes and no thread is open. Remove the label `{label}` to stop it.")
    gh(["pr", "edit", str(pr["number"]), "--add-label", label], root)
    gh(["pr", "comment", str(pr["number"]), "--body", body], root)
    print(f"authorized: #{pr['number']} carries {label!r}")
    return READY


def take(args, flag):
    """Remove `flag VALUE` from args and return VALUE; None when absent, False when the value is missing."""
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args):
        return False
    value = args[i + 1]
    del args[i:i + 2]
    return value


def usage_error(args, repo, quote, ticket):
    if False in (repo, quote, ticket) or not args or args[0] not in ("status", "merge", "authorize"):
        return True
    if len(args) > 2 or (len(args) == 2 and not args[1].isdigit()):
        return True
    if args[0] != "authorize":
        return quote is not None or ticket is not None
    return (quote is None) == (ticket is None) or (quote is not None and not quote.strip())


def main(argv):
    args = list(argv)
    repo, quote, ticket = take(args, "--repo"), take(args, "--quote"), take(args, "--ticket")
    if usage_error(args, repo, quote, ticket):
        print(__doc__, file=sys.stderr)
        return USAGE
    command, number = args[0], (args[1] if len(args) == 2 else None)
    root = contract.repo_root(repo or os.getcwd())
    path = contract.locate(root)
    if not path:
        print("no pothos contract for this repository; run /pothos:plant", file=sys.stderr)
        return NO_CONTRACT
    data = contract.load(path)
    if command == "authorize":
        try:
            return authorize(root, data, number, quote and quote.strip(), ticket)
        except GhError as exc:
            print(f"gh failed: {exc}", file=sys.stderr)
            return GH_FAILED
    method = ((data.get("pr") or {}).get("auto_merge") or {}).get("method") or "squash"
    if method not in METHODS:
        print(f"pr.auto_merge.method {method!r} is not one of {', '.join(METHODS)}", file=sys.stderr)
        return USAGE
    try:
        pr = fetch(root, number)
        checks = pr.get("statusCheckRollup") or []
        expected = not checks and expects_checks(root)
        receipt_ok = not checks and not expected and receipt_passed(root, data, pr.get("headRefOid") or "")
        verdict, facts, reasons = evaluate(pr, data, receipt_ok, expected)
        report(verdict, facts, reasons)
        if command == "status" or verdict != READY:
            return verdict
        gh(["pr", "merge", str(pr["number"]), f"--{method}", "--match-head-commit", pr["headRefOid"]], root)
        print(f"merged: #{pr['number']} into {pr['baseRefName']} with {method} at {pr['headRefOid'][:12]}")
        print(delete_remote_branch(root, pr))
        return READY
    except GhError as exc:
        print(f"gh failed: {exc}", file=sys.stderr)
        return GH_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
