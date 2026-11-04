#!/usr/bin/env python3
"""SessionStart adapter: ask every session to mark the comments it posts as an agent's, not the person's.

A comment posted with `gh` appears under the person's own account, indistinguishable from one they typed. This
context asks for a callout at the top of every comment and thread reply, naming the model and the account it
posts for. A rule, not a hook on the command: a comment without the callout is visible and editable, so the
first guard earns its place only if the rule proves not enough. This is a hook of its own, not a section of
session_context.py, for the reason retro_context.py gives: the contract's context already sits near the size
above which Claude Code moves it to a file.

Usage: comment_context.py [DIR]   (DIR defaults to the cwd in the hook's stdin event, then the process cwd)
Prints a SessionStart hook JSON object, or nothing outside a git repository or on any error.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract  # noqa: E402
from session_context import hook_cwd  # noqa: E402

CALLOUT = "> [!NOTE]\n> 🤖 **<model> responding on behalf of @<login>**"

TEXT = ("## Comments you post\n\n"
        "A comment or thread reply you post on a pull request or issue appears under the person's own account. "
        "Start every one with this callout, then a blank line, then the text:\n\n"
        f"```md\n{CALLOUT}\n```\n\n"
        "`<model>` is the model running this session (`Claude Fable 5.1`, or `Claude Code` when unsure); `<login>` comes "
        "from `gh api user --jq .login`. Add it even when the person dictated the words: it says who posted, not who chose "
        "the words. A skill's own disclaimer (triage's) goes below it. Commits and pull request bodies keep their own "
        "attribution and never get it.")


def build(start):
    if not contract.git(["rev-parse", "--git-dir"], start):
        return None
    return TEXT


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
