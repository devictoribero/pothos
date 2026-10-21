#!/usr/bin/env python3
"""Run the contract's checks and keep a receipt per commit, outside the repository.

Usage:
  verify.py run LEVEL [--env NAME] [--wait SECONDS]
                                     LEVEL is fast, full, e2e or all (full, then e2e when configured)
  verify.py wait [--wait SECONDS]    keep waiting for HEAD's run that is still going
  verify.py check [--no-e2e]         exit 0 when HEAD has a passing full receipt (and e2e, when configured)
  verify.py show                     print HEAD's receipts as JSON

Receipts live in $POTHOS_HOME/receipts/<host>/<owner>/<repo>/<commit>/<level>.json with the full log next
to them. A run on a dirty working tree is recorded but never counts as a pass: commit first.
After full, the contract's ui check runs on the branch's added lines and writes ui.json. It is advisory:
it never changes an exit code, and check only mentions it.

The checks run in a detached process, so a slow suite outlives the caller. `run` waits up to --wait
seconds (default 540, under an agent's ten-minute command limit) and exits 4 when the run is still
going; `wait` picks it up again. Starting `run` while one is going for the same commit attaches to it.

Exit codes: 0 passed (or skipped because the level is not configured), 1 failed or no valid receipt,
2 no contract, 3 the contract or the environment is unusable, 4 still running, 64 usage.
"""
import datetime
import fnmatch
import json
import os
import shlex
import subprocess
import sys
import time

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
sys.path.insert(0, os.path.realpath(SHARED))
import contract  # noqa: E402
import ui_check  # noqa: E402

LEVELS = ("fast", "full", "e2e")
ADVISORY = ("ui", "mutation")
# The files Stryker's default mutate option leaves out; an explicit --mutate replaces those defaults.
TEST_FILE_GLOBS = ("*.test.*", "*.spec.*")
TEST_FOLDERS = ("__tests__", "tests")
TAIL = 60
WAIT = 540


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
    return os.path.join(contract.pothos_home(), "receipts", key, commit)


def load_contract(root):
    path = contract.locate(root)
    if not path:
        print("no pothos contract for this repository; run /pothos:plant", file=sys.stderr)
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
    for level in LEVELS + ADVISORY:
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
    ui = found.get("ui") or {}
    note = f"; ui: {len(ui['findings'])} advisory finding(s), see `verify.py show`" if ui.get("status") == "findings" else ""
    print(f"verified: {', '.join(wanted)} passed on {commit[:12]}{note}")
    return 0


def command_for_any_e2e(data):
    if (data.get("verify") or {}).get("e2e"):
        return True
    return any(e.get("e2e") for e in ((data.get("run") or {}).get("environments") or []))


def option(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def budget(argv):
    value = option(argv, "--wait")
    return float(value) if value else WAIT


def ui_level(root, data):
    """Advisory: the UI check on the branch's added lines. Recorded in the receipt, never changes the exit code."""
    commit = head(root)
    receipt = {"commit": commit, "level": "ui", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    try:
        base = ui_check.base_ref(root, data, None)
        result = ui_check.findings(root, data, base)
    except Exception as exc:  # an advisory check must never break verification
        write_receipt(receipt_dir(root, commit), "ui", {**receipt, "status": "error", "error": str(exc)})
        print(f"ui: could not run ({exc}); advisory only")
        return
    if result is None:
        write_receipt(receipt_dir(root, commit), "ui", {**receipt, "status": "skipped"})
        print("ui: skipped (the contract's ui sets neither tokens nor icons)")
        return
    active, found = result
    write_receipt(receipt_dir(root, commit), "ui", {**receipt, "status": "findings" if found else "clean",
                                                    "rules": active, "findings": found})
    if found:
        print("\n".join(found[:TAIL]))
        print(f"ui: {len(found)} finding(s), advisory, does not block. {ui_check.HINT}")
    else:
        print("ui: clean")


def is_test_file(path):
    name = os.path.basename(path)
    return (any(fnmatch.fnmatch(name, glob) for glob in TEST_FILE_GLOBS)
            or any(part in TEST_FOLDERS for part in path.split("/")[:-1])
            or (name.startswith("test_") and name.endswith(".py")))


def changed_source_files(root, base, exclude):
    """Repository-relative files added or modified between base and HEAD, without tests and the contract's exclude globs."""
    out = contract.git(["-c", "core.quotepath=off", "diff", "--name-only", "--diff-filter=AM", base, "HEAD"], root) or ""
    return [path for path in out.splitlines()
            if path and not is_test_file(path) and not any(fnmatch.fnmatch(path, glob) for glob in exclude)]


def mutation_level(root, data):
    """Advisory: the contract's mutation command on the source files the branch changed. Exit 1 only on error."""
    commit = head(root)
    folder = receipt_dir(root, commit)
    settings = (data.get("verify") or {}).get("mutation") or {}
    receipt = {"commit": commit, "level": "mutation", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if not settings.get("command"):
        write_receipt(folder, "mutation", {**receipt, "status": "skipped", "reason": "no mutation command"})
        print("mutation: skipped (the contract has no mutation command)")
        return 0
    base = ui_check.base_ref(root, data, None)
    if not base:
        write_receipt(folder, "mutation", {**receipt, "status": "error", "error": "no base branch found"})
        print("mutation: no base branch found")
        return 1
    files = changed_source_files(root, base, settings.get("exclude") or [])
    if not files:
        write_receipt(folder, "mutation", {**receipt, "status": "skipped", "reason": "no source files changed"})
        print("mutation: skipped (no source files changed)")
        return 0
    return 0


def execute(root, data, level, env):
    """The checks themselves, run inside the detached process."""
    if level == "mutation":
        return mutation_level(root, data)
    if level == "full":
        status = run_level(root, data, "full", env)
        ui_level(root, data)
        return status
    if level != "all":
        return run_level(root, data, level, env)
    status = run_level(root, data, "full", env)
    ui_level(root, data)
    if status:
        return status
    if command_for_any_e2e(data):
        return run_level(root, data, "e2e", env)
    print("e2e: skipped (not configured)")
    return 0


def marker_paths(root):
    folder = receipt_dir(root, head(root))
    return folder, os.path.join(folder, "run.json")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def mutation_allowed(found):
    """HEAD has a fast or full receipt that passed on a clean tree: never mutate red or uncommitted work."""
    return any(r.get("status") == "passed" and not r.get("dirty") for r in (found.get("fast"), found.get("full")) if r)


def start(root, data, level, env, seconds):
    commit = head(root)
    if not commit:
        print("no commit yet; commit before verifying", file=sys.stderr)
        return 3
    if level == "mutation":
        if not mutation_allowed(receipts(root)[1]):
            print("mutation: run fast or full first")
            return 1
    for one in {"all": ("full", "e2e"), "mutation": ()}.get(level, (level,)):
        if one != "e2e" or level == "e2e" or command_for_any_e2e(data):
            command_for(data, one, env)  # exits 3 on an unusable environment, before anything starts
    folder, marker = marker_paths(root)
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8") as fh:
            running = json.load(fh)
        if alive(running["pid"]):
            print(f"a {running['level']} run is already going for {commit[:12]}; waiting for it", flush=True)
            return attach(root, None, seconds)
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "run.out")
    args = [sys.executable, os.path.abspath(__file__), "_exec", level] + (["--env", env] if env else [])
    script = (f"{' '.join(shlex.quote(a) for a in args)} > {shlex.quote(out)} 2>&1; "
              f"echo $? > {shlex.quote(os.path.join(folder, 'run.exit'))}; rm -f {shlex.quote(marker)}")
    for stale in ("run.exit",):
        if os.path.exists(os.path.join(folder, stale)):
            os.remove(os.path.join(folder, stale))
    proc = subprocess.Popen(["/bin/sh", "-c", script], cwd=root, start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"pid": proc.pid, "level": level, "env": env, "out": out}, fh)
    return attach(root, proc, seconds)


def attach(root, proc, seconds):
    folder, marker = marker_paths(root)
    exit_path = os.path.join(folder, "run.exit")
    if not os.path.isfile(marker) and not os.path.isfile(exit_path):
        print("no run for this commit; start one with run")
        return 1
    pid = None
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8") as fh:
            pid = json.load(fh)["pid"]
    deadline = time.monotonic() + seconds
    while True:
        if proc is not None:
            done = proc.poll() is not None
        else:
            done = not os.path.isfile(marker) or not alive(pid)
        if done:
            break
        if time.monotonic() >= deadline:
            print(f"still running (pid {pid}); output so far in {os.path.join(folder, 'run.out')}. "
                  "Run `verify.py wait` to keep waiting. Do not start another run.")
            return 4
        time.sleep(1)
    out = os.path.join(folder, "run.out")
    if os.path.isfile(out):
        with open(out, encoding="utf-8", errors="replace") as fh:
            sys.stdout.write(fh.read())
    if not os.path.isfile(exit_path):
        print("the run stopped without finishing; start it again")
        if os.path.isfile(marker):
            os.remove(marker)
        return 1
    with open(exit_path, encoding="utf-8") as fh:
        return int(fh.read().strip() or 1)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 64
    root = contract.repo_root(os.getcwd())
    cmd = argv[0]
    if cmd == "run":
        if len(argv) < 2 or argv[1] not in LEVELS + ("all", "mutation"):
            print("usage: verify.py run fast|full|e2e|all|mutation [--env NAME] [--wait SECONDS]", file=sys.stderr)
            return 64
        data = load_contract(root)
        return start(root, data, argv[1], option(argv, "--env"), budget(argv))
    if cmd == "_exec":
        data = load_contract(root)
        return execute(root, data, argv[1], option(argv, "--env"))
    if cmd == "wait":
        load_contract(root)
        return attach(root, None, budget(argv))
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
