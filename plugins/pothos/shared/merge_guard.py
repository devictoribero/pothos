#!/usr/bin/env python3
"""PreToolUse hook: keep agents from merging pull requests and from adding the auto-merge label.

Merging into the base branch is a person's decision (PRINCIPLES.md). An agent carries it out only through
tend's merge gate, for a pull request a person labelled. The agent runs gh as its owner, so GitHub cannot
tell who added the label: this hook blocks the Bash commands that would let an agent decide for itself.

It reads the hook input on stdin and exits 2, with the reason on stderr, to block the command; it exits 0
for everything else, including any error of its own, so a bug here never stops other work.
It covers the usual commands (`gh pr merge`, the REST and GraphQL merge calls through `gh api`, and the
label flags and endpoints), not an agent determined to get around it.
"""
import json
import os
import re
import sys

MERGE = re.compile(r"\bgh\s+pr\s+merge\b"
                   r"|\bgh\s+api\b.*(?:/pulls/\d+/merge\b|mergePullRequest|enablePullRequestAutoMerge)", re.S)
LABELLING = re.compile(r"\bgh\b.*(--add-label|--label\b|/labels\b)", re.S)
DEFAULT_LABEL = "auto-merge"


def contract_label(cwd):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import contract
    path = contract.locate(contract.repo_root(cwd))
    data = contract.load(path) if path else {}
    return (((data.get("pr") or {}).get("auto_merge")) or {}).get("label")


def reason(command, cwd):
    if MERGE.search(command):
        return ("Blocked by pothos: agents never merge a pull request. A person merges, or /pothos:tend's merge gate merges "
                "a pull request a person gave the auto-merge label. The user can run it with `! gh pr merge <n>`.")
    if LABELLING.search(command):
        labels = {DEFAULT_LABEL, contract_label(cwd)} - {None}
        if any(re.search(r"(?<![\w-])" + re.escape(l) + r"(?![\w-])", command) for l in labels):
            return ("Blocked by pothos: only a person adds the auto-merge label; it is their decision to let the "
                    "pull request merge itself. Ask the user to add it.")
    return None


def main():
    try:
        event = json.load(sys.stdin)
        command = (event.get("tool_input") or {}).get("command") or ""
        if "gh" not in command:
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
