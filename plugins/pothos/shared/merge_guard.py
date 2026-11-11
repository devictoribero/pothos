#!/usr/bin/env python3
"""PreToolUse hook: keep agents from merging pull requests into the base branch and from adding the auto-merge label.

Merging into the base branch is a person's decision (PRINCIPLES.md). An agent carries it out only through
tend's merge gate, for a pull request a person authorized. The agent runs gh as its owner, so GitHub cannot
tell who added the label: this hook blocks the Bash commands that would let an agent decide for itself.
A merge into any other branch (a stack of ticket pull requests, `feature/<slug>`) is not that decision, so
`gh pr merge` passes when gh says the pull request's base is not the base branch of its repository's contract
(`main` without one). It blocks when it cannot read the base, and it always blocks the REST and GraphQL merge
calls, whose target the command does not name.
The one way an agent adds the label is `merge_gate.py authorize`. With `--quote`, this hook lets it through
only when the quote appears in a message the person typed in this session (read from the transcript, leaving
out tool results, skill text, pasted content and harness notes), so a ticket, a pull request comment or a
log cannot authorize anything by asking. It blocks when it cannot read the transcript. `--ticket` passes:
the gate checks the ticket's `Merge: auto` line.

It reads the hook input on stdin and exits 2, with the reason on stderr, to block the command; it exits 0
for everything else, including any error of its own, so a bug here never stops other work.
It covers the direct commands: `gh pr merge` into the base branch, the REST and GraphQL merge calls through
`gh api` or any HTTP client, a `gh alias` that would hide them, a `git push` into the contract's base branch,
and the label flags and endpoints. It matches the text of the command, so a wrapper (a script, a query read
from a file, a Python one-liner) gets past it: it stops the usual commands, not an agent determined to get
around it. A `gh pr merge` it cannot read as a command of its own (inside a quoted string, a heredoc or a
grep) is blocked; that costs a rephrase and never a merge.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract  # noqa: E402

PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
# Merge calls whose target the command text does not name, so they are blocked whatever the base.
MERGE_CALL = re.compile(r"\bgh\s+api\b.*(?:/pulls/[^/\s\"']+/merge\b|mergePullRequest|enablePullRequestAutoMerge)"
                        r"|api\.github\.com/repos/\S+/pulls/[^/\s\"']+/merge\b"
                        r"|\bgh\s+alias\s+set\b.*\bmerge\b", re.S)
# Shell punctuation: a newline is one too, so a command on the next line starts a step of its own.
PUNCTUATION = "();<>|&\n"
STEP_BREAKS = set(";&|\n()")
# Flags of `gh pr merge` that take a value, which is never the pull request.
VALUE_FLAGS = {"-b", "--body", "-F", "--body-file", "-t", "--subject", "--match-head-commit", "-A",
               "--author-email", "-R", "--repo"}
# Every gh call the hook makes shares this budget, under the hook's own timeout in hooks.json.
GH_BUDGET_SECONDS = 10
LABELLING = re.compile(r"\bgh\b.*(--add-label|--label\b|/labels\b)", re.S)
PUSH = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?push\b([^;&|\n]*)")
AUTHORIZE = re.compile(r"\bmerge_gate\.py\b.*\bauthorize\b", re.S)
# Text a user message carries that the person did not type: pasted material and notes from the harness.
NOT_TYPED = re.compile(r"<(pasted_content|system-reminder|system_instruction)\b[^>]*>.*?</\1>", re.S)
DEFAULT_LABEL = "auto-merge"
DEFAULT_BASE = "main"


def contract_data(cwd):
    path = contract.locate(contract.repo_root(cwd))
    return contract.load(path) if path else {}


def contract_base(key):
    """The base branch in the contract of the repository host/owner/repo, `main` without a contract."""
    folder = os.path.realpath(os.path.join(contract.pothos_home(), "contracts"))
    path = os.path.realpath(os.path.join(folder, key + ".json"))
    if path.startswith(folder + os.sep) and os.path.isfile(path):
        return (contract.load(path).get("pr") or {}).get("base") or DEFAULT_BASE
    return DEFAULT_BASE


def shell_words(command):
    """The command split into words and punctuation the way a shell reads it; None when it cannot be split."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def is_punctuation(word):
    return bool(word) and all(c in PUNCTUATION for c in word)


def merge_target(args):
    """The pull request and the --repo a `gh pr merge` names (None for each it leaves out)."""
    number = repo = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in VALUE_FLAGS:
            if arg in ("-R", "--repo") and i + 1 < len(args):
                repo = args[i + 1]
            i += 2
            continue
        if arg.startswith("--repo="):
            repo = arg.split("=", 1)[1]
        elif not arg.startswith("-") and number is None:
            number = arg
        i += 1
    return number, repo


def merge_commands(command, cwd):
    """Each `gh pr merge` in the command as (folder, pull request, repo), following a `cd` that opens a step.
    None when the command cannot be split, or quotes the words where no shell would run them as a command."""
    words = shell_words(command)
    if words is None:
        return None
    found, step_start, i = [], True, 0
    while i < len(words):
        word = words[i]
        if is_punctuation(word):
            step_start = step_start or any(c in STEP_BREAKS for c in word)
            i += 1
            continue
        if step_start and word == "cd" and i + 1 < len(words) and not is_punctuation(words[i + 1]):
            cwd = os.path.join(cwd, os.path.expanduser(words[i + 1]))
            i += 2
            continue
        step_start = False
        if words[i:i + 3] == ["gh", "pr", "merge"]:
            end = i + 3
            while end < len(words) and not is_punctuation(words[end]):
                end += 1
            found.append((cwd, *merge_target(words[i + 3:end])))
            i = end
            continue
        i += 1
    return found if len(found) == len(PR_MERGE.findall(command)) else None


def pull_request_base(cwd, number, repo, deadline):
    """(base branch, host/owner/repo) of the pull request gh would merge; None when gh cannot say in time."""
    left = deadline - time.monotonic()
    if left <= 0:
        return None
    args = ["gh", "pr", "view", *([number] if number else []), *(["--repo", repo] if repo else []),
            "--json", "baseRefName,url"]
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=left, env=contract.gh_env(cwd))
        data = json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    match = re.match(r"^(https?://[^/]+/[^/]+/[^/]+)/pull/\d+", (data or {}).get("url") or "")
    key = contract.remote_key(match.group(1)) if match else None
    base = (data or {}).get("baseRefName")
    return (base, key) if base and key else None


def merge_reason(command, cwd):
    if MERGE_CALL.search(command):
        return ("Blocked by pothos: a merge through the GitHub API never passes, because the command does not say which "
                "branch it merges into. Into the base branch, a person merges, or /pothos:tend's merge gate merges a "
                "pull request a person gave the auto-merge label; into any other branch, run `gh pr merge <n>`.")
    if not PR_MERGE.search(command):
        return None
    commands = merge_commands(command, cwd)
    if commands is None:
        return ("Blocked by pothos: this command quotes `gh pr merge` where it cannot tell which pull request it "
                "merges (a quoted string, a heredoc, a grep, a wrapper). If it only quotes the words, write the text "
                "with the Write tool or reword it; nothing was merged. To merge, run `gh pr merge <n>` as a command "
                "of its own.")
    deadline = time.monotonic() + GH_BUDGET_SECONDS
    for folder, number, repo in commands:
        target = pull_request_base(folder, number, repo, deadline)
        if target is None:
            return ("Blocked by pothos: cannot read the base branch of the pull request "
                    + (f"{number} " if number else "of the current branch ")
                    + "with `gh pr view`, so it may be the base branch. Check that gh can see it, or ask the user.")
        base, key = target
        if base == contract_base(key):
            return (f"Blocked by pothos: agents never merge a pull request into the base branch ({base}). A person "
                    "merges, or /pothos:tend's merge gate merges a pull request a person gave the auto-merge label. "
                    "The user can run it with `! gh pr merge <n>`.")
    return None


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


def normalize(text):
    return " ".join(text.split()).casefold()


def typed_by_person(transcript):
    """What the person typed in this session: user messages without tool results, skill text or pasted content,
    and the messages they typed while the agent was busy (queued, and shown to the agent inside a tool result)."""
    typed = []
    with open(transcript, encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "queue-operation" and entry.get("operation") == "enqueue":
                if isinstance(entry.get("content"), str):
                    typed.append(normalize(NOT_TYPED.sub(" ", entry["content"])))
                continue
            if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
                continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, list):
                if any(isinstance(i, dict) and i.get("type") == "tool_result" for i in content):
                    continue
                content = "\n".join(i.get("text") or "" for i in content if isinstance(i, dict) and i.get("type") == "text")
            if isinstance(content, str):
                typed.append(normalize(NOT_TYPED.sub(" ", content)))
    return typed


def quotes(command):
    """Every value given to --quote in the command; None when the command cannot be parsed."""
    try:  # punctuation_chars keeps a `;` or `&&` after the closing quote out of the quoted word
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return None
    return [words[i + 1] for i, w in enumerate(words[:-1]) if w == "--quote"]


def authorize_reason(command, transcript):
    found = quotes(command)
    if found is None:
        return "Blocked by pothos: cannot read the --quote of merge_gate.py authorize; pass it as one quoted argument."
    if not found:
        return None  # --ticket: the gate checks the ticket's Merge: auto line
    try:
        typed = typed_by_person(transcript) if transcript else None
    except Exception:  # unlike the rest of this hook, an unreadable transcript blocks: nothing confirms the words
        typed = None
    if typed is None:
        return ("Blocked by pothos: cannot read this session's transcript to confirm the person's words. "
                "Ask the user to add the auto-merge label.")
    for quote in found:
        if not normalize(quote) or not any(normalize(quote) in text for text in typed):
            return ("Blocked by pothos: the quote is not in any message the person typed in this session, so it "
                    "cannot authorize the auto-merge label. Quote their words exactly, or ask them to add the label.")
    return None


def reason(command, cwd, transcript=None):
    why = merge_reason(command, cwd)
    if why:
        return why
    pr = contract_data(cwd).get("pr") or {}
    if "push" in command and pushes_base(command, cwd, pr.get("base") or DEFAULT_BASE):
        return ("Blocked by pothos: agents never push to the base branch; a pull request merges it, by a person or "
                "through /pothos:tend's merge gate. The user can run it with `! git push ...`.")
    if LABELLING.search(command):
        labels = {DEFAULT_LABEL, (pr.get("auto_merge") or {}).get("label")} - {None}
        if any(re.search(r"(?<![\w-])" + re.escape(l) + r"(?![\w-])", command, re.I) for l in labels):
            return ("Blocked by pothos: the auto-merge label is the person's decision to let the pull request merge "
                    "itself. When they authorized this pull request, add it with tend's `merge_gate.py authorize`; "
                    "otherwise ask the user to add it.")
    if AUTHORIZE.search(command):
        return authorize_reason(command, transcript)
    return None


def main():
    try:
        event = json.load(sys.stdin)
        command = (event.get("tool_input") or {}).get("command") or ""
        if not any(word in command for word in ("gh", "push", "api.github.com", "merge_gate")):
            return 0
        why = reason(command, event.get("cwd") or os.getcwd(), event.get("transcript_path"))
    except Exception:  # never block work because of a bug here
        return 0
    if why:
        print(why, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
