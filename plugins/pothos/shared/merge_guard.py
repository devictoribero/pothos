#!/usr/bin/env python3
"""PreToolUse hook: keep agents from merging pull requests and from adding the auto-merge label.

Merging into the base branch is a person's decision (PRINCIPLES.md). An agent carries it out only through
tend's merge gate, for a pull request a person authorized. The agent runs gh as its owner, so GitHub cannot
tell who added the label: this hook blocks the Bash commands that would let an agent decide for itself.
The one way an agent adds the label is `merge_gate.py authorize`. With `--quote`, this hook lets it through
only when the quote appears in a message the person typed in this session (read from the transcript, leaving
out tool results, skill text, pasted content and harness notes), so a ticket, a pull request comment or a
log cannot authorize anything by asking. It blocks when it cannot read the transcript. `--ticket` passes:
the gate checks the ticket's `Merge: auto` line.

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
import shlex
import subprocess
import sys

MERGE = re.compile(r"\bgh\s+pr\s+merge\b"
                   r"|\bgh\s+api\b.*(?:/pulls/[^/\s\"']+/merge\b|mergePullRequest|enablePullRequestAutoMerge)"
                   r"|api\.github\.com/repos/\S+/pulls/[^/\s\"']+/merge\b"
                   r"|\bgh\s+alias\s+set\b.*\bmerge\b", re.S)
LABELLING = re.compile(r"\bgh\b.*(--add-label|--label\b|/labels\b)", re.S)
PUSH = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?push\b([^;&|\n]*)")
AUTHORIZE = re.compile(r"\bmerge_gate\.py\b.*\bauthorize\b", re.S)
# Text a user message carries that the person did not type: pasted material and notes from the harness.
NOT_TYPED = re.compile(r"<(pasted_content|system-reminder|system_instruction)\b[^>]*>.*?</\1>", re.S)
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


def normalize(text):
    return " ".join(text.split()).casefold()


def typed_by_person(transcript):
    """What the person typed in this session: user messages without tool results, skill text or pasted content."""
    typed = []
    with open(transcript, encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
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
