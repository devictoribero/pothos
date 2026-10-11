#!/usr/bin/env python3
"""Run the contract's checks and keep a receipt per commit, outside the repository.

Usage:
  verify.py run LEVEL [--env NAME]   LEVEL is fast, full, e2e or all (full, then e2e when configured)
  verify.py check [--no-e2e]         exit 0 when HEAD has a passing full receipt (and e2e, when configured)
  verify.py show                     print HEAD's receipts as JSON

Receipts live in $DEVFLOW_HOME/receipts/<host>/<owner>/<repo>/<commit>/<level>.json with the full log next
to them. A run on a dirty working tree is recorded but never counts as a pass: commit first.

Exit codes: 0 passed (or skipped because the level is not configured), 1 failed or no valid receipt,
2 no contract, 3 the contract or the environment is unusable, 64 usage.
"""
import datetime
import json
import os
import subprocess
import sys
import time

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
sys.path.insert(0, os.path.realpath(SHARED))
import contract  # noqa: E402

LEVELS = ("fast", "full", "e2e")
TAIL = 60


def head(root):
    return contract.git(["rev-parse", "HEAD"], root)


def dirty(root, data=None):
    """Uncommitted changes, ignoring the local tracker folder: tickets change while code is verified."""
    out = contract.git(["status", "--porcelain", "--untracked-files=normal"], root) or ""
    tracker = ((data or {}).get("tracker") or {})
    ignored = (tracker.get("path") or ".scratch").rstrip("/") + "/" if tracker.get("kind", "none") in ("none", "local") else None
    changed = [line[3:].strip('"') for line in out.splitlines() if line.strip()]
    return any(not (ignored and (path == ignored.rstrip("/") or path.startswith(ignored))) for path in changed)


def receipt_dir(root, commit):
    key = contract.key_for(root, "receipts")
    return os.path.join(contract.devflow_home(), "receipts", key, commit)


def load_contract(root):
    path = contract.locate(root)
    if not path:
        print("no devflow contract for this repository; run /devflow:onboard", file=sys.stderr)
        sys.exit(2)
    data = contract.load(path)
    if data.get("workflow") == "repo":
        print("this repository follows its own workflow (contract workflow: repo); use its own checks", file=sys.stderr)
        sys.exit(3)
    return data


def command_for(data, level, env_name):
    verify = data.get("verify") or {}
    if level != "e2e":
        return verify.get(level), None
    envs = {e["name"]: e for e in ((data.get("run") or {}).get("environments") or [])}
    if env_name:
        if env_name not in envs:
            print(f"unknown environment '{env_name}'; the contract lists: {', '.join(envs) or 'none'}", file=sys.stderr)
            sys.exit(3)
        return envs[env_name].get("e2e") or verify.get("e2e"), env_name
    if verify.get("e2e") is None and any(e.get("e2e") for e in envs.values()):
        print("end-to-end runs per environment here; pass --env with one of: " + ", ".join(envs), file=sys.stderr)
        sys.exit(3)
    return verify.get("e2e"), None


def write_receipt(folder, level, receipt):
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, f".{level}.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, os.path.join(folder, f"{level}.json"))


def run_level(root, data, level, env_name):
    command, env = command_for(data, level, env_name)
    commit = head(root)
    if not commit:
        print("no commit yet; commit before verifying", file=sys.stderr)
        sys.exit(3)
    folder = receipt_dir(root, commit)
    base = {"commit": commit, "level": level, "env": env, "command": command,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if not command:
        write_receipt(folder, level, {**base, "status": "skipped", "dirty": dirty(root, data)})
        print(f"{level}: skipped (the contract has no {level} command)")
        return 0
    was_dirty = dirty(root, data)
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, f"{level}.log")
    print(f"{level}: {command}" + (f"  [env {env}]" if env else ""), flush=True)
    started = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(command, shell=True, cwd=root, stdout=log, stderr=subprocess.STDOUT, text=True)
    seconds = round(time.monotonic() - started, 1)
    status = "passed" if proc.returncode == 0 else "failed"
    write_receipt(folder, level, {**base, "status": status, "exit": proc.returncode, "seconds": seconds,
                                  "dirty": was_dirty or dirty(root, data), "log": log_path})
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    if status == "failed":
        print("\n".join(lines[-TAIL:]))
    print(f"{level}: {status} in {seconds}s (exit {proc.returncode}); log {log_path}")
    if was_dirty:
        print(f"{level}: the working tree had uncommitted changes, so this receipt does not count; commit and run again")
    return 0 if status == "passed" else 1


def receipts(root):
    commit = head(root)
    if not commit:
        return None, {}
    folder = receipt_dir(root, commit)
    found = {}
    for level in LEVELS:
        path = os.path.join(folder, f"{level}.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                found[level] = json.load(fh)
    return commit, found


def check(root, data, need_e2e):
    commit, found = receipts(root)
    if not commit:
        print("no commit yet", file=sys.stderr)
        return 1
    problems = []
    if dirty(root, data):
        problems.append("the working tree has uncommitted changes")
    wanted = ["full"] + (["e2e"] if need_e2e and command_for_any_e2e(data) else [])
    for level in wanted:
        r = found.get(level)
        if not r:
            problems.append(f"no {level} receipt for {commit[:12]}")
        elif r["status"] != "passed":
            problems.append(f"{level} {r['status']} on {commit[:12]}")
        elif r.get("dirty"):
            problems.append(f"{level} ran on a dirty tree")
    if problems:
        print("not verified: " + "; ".join(problems))
        return 1
    print(f"verified: {', '.join(wanted)} passed on {commit[:12]}")
    return 0


def command_for_any_e2e(data):
    if (data.get("verify") or {}).get("e2e"):
        return True
    return any(e.get("e2e") for e in ((data.get("run") or {}).get("environments") or []))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 64
    root = contract.repo_root(os.getcwd())
    cmd = argv[0]
    if cmd == "run":
        if len(argv) < 2 or argv[1] not in LEVELS + ("all",):
            print("usage: verify.py run fast|full|e2e|all [--env NAME]", file=sys.stderr)
            return 64
        env = argv[argv.index("--env") + 1] if "--env" in argv and argv.index("--env") + 1 < len(argv) else None
        data = load_contract(root)
        if argv[1] != "all":
            return run_level(root, data, argv[1], env)
        status = run_level(root, data, "full", env)
        if status:
            return status
        if command_for_any_e2e(data):
            return run_level(root, data, "e2e", env)
        print("e2e: skipped (not configured)")
        return 0
    if cmd == "check":
        data = load_contract(root)
        return check(root, data, "--no-e2e" not in argv)
    if cmd == "show":
        commit, found = receipts(root)
        print(json.dumps({"commit": commit, "receipts": found}, indent=2))
        return 0
    print(f"unknown command '{cmd}'", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
