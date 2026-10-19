#!/usr/bin/env python3
"""PreToolUse hook: keep agents from merging pull requests and from adding the auto-merge label.

Merging into the base branch is a person's decision (PRINCIPLES.md). An agent carries it out only through
tend's merge gate, for a pull request a person labelled. The agent runs gh as its owner, so GitHub cannot
tell who added the label: this hook blocks the Bash commands that would let an agent decide for itself.

It reads the hook input on stdin and exits 2, with the reason on stderr, to block the command; it exits 0
for everything else, including any error of its own, so a bug here never stops other work.
It covers the direct commands: `gh pr merge`, the REST and GraphQL merge calls through `gh api` or any
HTTP client, a `gh alias` that would hide them, a `git push` into the contract's base branch, and the
label flags and endpoints. It matches the text of the command, so a wrapper (a script, a query read from a
file, a Python one-liner) gets past it: it stops the usual commands, not an agent determined to get around it.
It matches anywhere in the command, so a commit message or a grep that quotes `gh pr merge` is blocked too;
that costs a rephrase and never a merge.
"""
import json
import os
import re
import subprocess
import sys

MERGE = re.compile(r"\bgh\s+pr\s+merge\b"
                   r"|\bgh\s+api\b.*(?:/pulls/[^/\s\"']+/merge\b|mergePullRequest|enablePullRequestAutoMerge)"
                   r"|api\.github\.com/repos/\S+/pulls/[^/\s\"']+/merge\b"
                   r"|\bgh\s+alias\s+set\b.*\bmerge\b", re.S)
LABELLING = re.compile(r"\bgh\b.*(--add-label|--label\b|/labels\b)", re.S)
PUSH = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?push\b([^;&|\n]*)")
DEFAULT_LABEL = "auto-merge"
DEFAULT_BASE = "main"


def contract_data(cwd):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import contract
    path = contract.locate(contract.repo_root(cwd))
    return contract.load(path) if path else {}


def current_branch(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def pushes_base(command, cwd, base):
    """True when a `git push` in the command lands on the base branch: by refspec, or a bare push from it."""
    for match in PUSH.finditer(command):
        words = [w for w in match.group(1).split() if not w.startswith("-")]
        refspecs = words[1:]  # the first word names the remote
        for spec in refspecs:
            target = spec.split(":", 1)[1] if ":" in spec else spec
            if target in (base, "refs/heads/" + base):
                return True
        if not refspecs and current_branch(cwd) == base:
            return True
    return False


def reason(command, cwd):
    if MERGE.search(command):
        return ("Blocked by pothos: agents never merge a pull request. A person merges, or /pothos:tend's merge gate merges "
                "a pull request a person gave the auto-merge label. The user can run it with `! gh pr merge <n>`.")
    pr = contract_data(cwd).get("pr") or {}
    if "push" in command and pushes_base(command, cwd, pr.get("base") or DEFAULT_BASE):
        return ("Blocked by pothos: agents never push to the base branch; a pull request merges it, by a person or "
                "through /pothos:tend's merge gate. The user can run it with `! git push ...`.")
    if LABELLING.search(command):
        labels = {DEFAULT_LABEL, (pr.get("auto_merge") or {}).get("label")} - {None}
        if any(re.search(r"(?<![\w-])" + re.escape(l) + r"(?![\w-])", command, re.I) for l in labels):
            return ("Blocked by pothos: only a person adds the auto-merge label; it is their decision to let the "
                    "pull request merge itself. Ask the user to add it.")
    return None


def main():
    try:
        event = json.load(sys.stdin)
        command = (event.get("tool_input") or {}).get("command") or ""
        if "gh" not in command and "push" not in command and "api.github.com" not in command:
            return 0
        why = reason(command, event.get("cwd") or os.getcwd())
    except Exception:  # never block work because of a bug here
        return 0
    if why:
        print(why, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
