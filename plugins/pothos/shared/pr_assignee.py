#!/usr/bin/env python3
"""PostToolUse adapter: assign every pull request a session opens to the person who opened it.

`gh pr create` leaves a pull request unassigned unless the command remembers `--assignee @me`, and an
agent forgets often enough. This hook runs after each Bash call: when the command ran `gh pr create`, it
takes every pull request URL the command printed on a line of its own (what `gh pr create` prints) and
runs `gh pr edit <url> --add-assignee @me`. `@me` is the GitHub user `gh` is logged in as, the one who
opened the pull request. Adding an assignee that is already there changes nothing.

Usage: pr_assignee.py   (reads the hook event as JSON on stdin)
Prints a PostToolUse hook JSON object when it acted, nothing otherwise. Never fails the session: a
failed assignment becomes a note asking the agent to assign the pull request itself, and exit code 0.
"""
import json
import re
import subprocess
import sys

CREATE = re.compile(r"\bgh\s+pr\s+create\b")
PR_URL = re.compile(r"^\s*(https://[^\s/]+/[^\s/]+/[^\s/]+/pull/\d+)\s*$", re.MULTILINE)


def created_urls(event):
    """Pull request URLs printed by a Bash call that ran `gh pr create`, in order and without repeats."""
    if event.get("tool_name") != "Bash":
        return []
    command = (event.get("tool_input") or {}).get("command") or ""
    if not CREATE.search(command):
        return []
    response = event.get("tool_response")
    stdout = (response.get("stdout") or "") if isinstance(response, dict) else str(response or "")
    return list(dict.fromkeys(PR_URL.findall(stdout)))


def assign(url):
    """None when `url` is assigned to `@me`, otherwise why it is not."""
    try:
        result = subprocess.run(["gh", "pr", "edit", url, "--add-assignee", "@me"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None if result.returncode == 0 else (result.stderr.strip() or f"gh exited {result.returncode}")


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        urls = created_urls(event) if isinstance(event, dict) else []
        notes = []
        for url in urls:
            error = assign(url)
            notes.append(f"Assigned {url} to the GitHub user who opened it (@me)." if error is None else
                         f"Could not assign {url} to @me ({error}); run `gh pr edit {url} --add-assignee @me`.")
    except Exception as exc:  # the hook must never break a session
        notes = [f"The pull request assignee hook failed ({type(exc).__name__}: {exc}); assign the pull request "
                 "with `gh pr edit <url> --add-assignee @me`."]
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": " ".join(notes)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
