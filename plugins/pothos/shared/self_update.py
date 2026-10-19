#!/usr/bin/env python3
"""SessionStart adapter: keep a plugin that loads in place from a git checkout at its remote's default branch.

A marketplace added from a local directory loads the plugin straight from that checkout, so every
repository runs whatever the checkout holds. After a pull request merges on GitHub, the checkout stays
behind until someone pulls it. This hook does that pull at every session start, in a detached process
so the session never waits for the network; the new files apply from the next session or `/reload-plugins`.

It only ever fast-forwards, and only when all of these hold:
- the plugin's own manifest is tracked in a git checkout (a copy in the plugin cache is not, so installs
  from a git-hosted marketplace are left to Claude Code's own updates);
- the checkout is on the remote's default branch (`<remote>/HEAD`), under the same name and tracking it,
  so a feature branch checked out for work is never touched, even one started from `origin/main`;
- `git merge --ff-only` accepts it: a local commit on that branch, or an uncommitted change to a file the
  update touches, makes git refuse and leaves everything as it was.

Usage: self_update.py          (hook mode: starts `self_update.py --run` detached and returns at once)
       self_update.py --run    (does the update in the foreground)
Prints nothing and exits 0 in both modes: an update that cannot happen is skipped silently.
"""
import fcntl
import os
import subprocess
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(".claude-plugin", "plugin.json")
GIT_TIMEOUT = 60


def git(*args, cwd=PLUGIN):
    """stdout of a git command, stripped, or None when it fails. Never prompts for credentials."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def tracking_default_branch():
    """(remote, branch) when the checked-out branch is the remote's default branch and tracks it, else None."""
    if git("ls-files", "--error-unmatch", MANIFEST) is None:
        return None
    branch = git("symbolic-ref", "--short", "-q", "HEAD")
    remote = branch and git("config", f"branch.{branch}.remote")
    upstream = remote and git("rev-parse", "--abbrev-ref", "@{upstream}")
    default = remote and git("symbolic-ref", "--short", "-q", f"refs/remotes/{remote}/HEAD")
    if not upstream or upstream != default or upstream != f"{remote}/{branch}":
        return None
    return remote, branch


def update():
    target = tracking_default_branch()
    if target is None:
        return
    git_dir = git("rev-parse", "--absolute-git-dir")
    if not git_dir:
        return
    with open(os.path.join(git_dir, "pothos-self-update.lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # another session is already updating this checkout
        remote, branch = target
        if git("fetch", "--quiet", remote, branch) is not None:
            git("merge", "--ff-only", "--quiet", "@{upstream}")


def main(argv):
    try:
        if argv[1:] == ["--run"]:
            update()
        else:
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "--run"], cwd=PLUGIN,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:  # the hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
