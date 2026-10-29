#!/usr/bin/env python3
"""SessionStart adapter: tell every session where this repository's retro findings go and how many are open.

A retro finding is written when friction shows up, not when a skill asks, so every session in a git repository
needs the folder, with or without a contract. `retro` itself stays as upstream wrote it. This is a hook of its
own, not a section of session_context.py: Claude Code moves a hook's additionalContext to a file above about
10,000 characters, and the contract's context already sits near that limit.

Usage: retro_context.py [DIR]   (DIR defaults to the cwd in the hook's stdin event, then the process cwd)
Prints a SessionStart hook JSON object, or nothing outside a git repository or on any error.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract  # noqa: E402
from session_context import hook_cwd  # noqa: E402

FORMAT = os.path.join(HERE, "retro-findings.md")


def finding_status(path):
    """The `status:` field of a finding's frontmatter, or None when the file has none."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        key, _, value = line.partition(":")
        if key.strip() == "status":
            return value.split("#")[0].strip() or None
    return None


def build(start):
    if not contract.git(["rev-parse", "--git-dir"], start):
        return None
    home = os.path.join(contract.pothos_home(), "retros")
    folder = os.path.join(home, contract.key_for(start, "retros"))
    open_count = sum(1 for path in glob.glob(os.path.join(folder, "*.md")) if finding_status(path) == "open")
    return ("## Retro findings\n\n"
            "A change to the agent's environment worth making later (from `/pothos:retro`, or friction in this session) "
            f"is a retro finding: one file per finding, under `{folder}` when the fix lands in this repository, under the "
            f"same `<host>/<owner>/<repo>` key in `{home}` when it lands in another. Before writing one, look for a file on "
            f"the same finding and add an occurrence to it instead. Format and statuses: `{FORMAT}`. "
            f"Open findings for this repository: {open_count}.")


def main(argv):
    start = argv[0] if argv else (hook_cwd() or os.getcwd())
    try:
        text = build(start)
    except Exception:  # the hook must never break a session, and this context is optional
        return 0
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
