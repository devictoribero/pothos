#!/usr/bin/env python3
"""Run the contract's checks and keep a receipt per commit, outside the repository.

Usage:
  verify.py run LEVEL [--env NAME] [--wait SECONDS]
                                     LEVEL is fast, full, e2e, all (full, then e2e when configured)
                                     or mutation (the contract's mutation command on the changed files)
  verify.py wait [--wait SECONDS]    keep waiting for HEAD's run that is still going
  verify.py check [--no-e2e]         exit 0 when HEAD has a passing full receipt (and e2e, when configured)
  verify.py show                     print HEAD's receipts as JSON

Receipts live in $POTHOS_HOME/receipts/<host>/<owner>/<repo>/<commit>/<level>.json with the full log next
to them. A run on a dirty working tree is recorded but never counts as a pass: commit first.
After full, the contract's ui check runs on the branch's added lines and writes ui.json. It is advisory:
it never changes an exit code, and check only mentions it.
`run mutation` is advisory too and stays out of `run all`: it needs a passing clean fast or full receipt
for HEAD, runs the contract's mutation command on the source files added or modified since the merge-base
with the pull request base, and writes mutation.json. When the contract names a report and the command
wrote it, the receipt lists the surviving mutants in the changed files, `new` on a line the branch added
or `inherited`, and its status is clean or findings; otherwise ran, error or skipped. Only new findings
print, and check mentions them without failing.

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
import shutil
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
# Every status of the mutation-testing-report-schema: only the first kind is a finding.
MUTANT_STATUSES = {"Survived": "finding", "NoCoverage": "finding", "Killed": "killed", "Timeout": "killed",
                   "Ignored": "ignored", "CompileError": "noise", "RuntimeError": "noise", "Pending": "noise"}
MUTATION_CLOSING = ("mutation: {new} new surviving mutant(s) in {files} changed file(s); {inherited} inherited, "
                    "see verify.py show. Advisory, does not block. Each new one is a missing test or dead code.")
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
    new = [f for f in (found.get("mutation") or {}).get("findings") or [] if f["kind"] == "new"]
    if new:
        note += f"; mutation: {len(new)} new survivor(s), see verify.py show"
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
    """Repository-relative files added or modified between base and HEAD, without tests and the contract's exclude globs.

    Rename detection is off, so a file moved and edited on the branch counts as added under its new path.
    """
    out = contract.git(["-c", "core.quotepath=off", "diff", "--no-renames", "--name-only", "--diff-filter=AM", base, "HEAD"],
                       root) or ""
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
    receipt.update(run_mutation_with_cache(root, data, settings["command"], files, folder))
    if receipt["status"] == "ran" and settings.get("report"):
        receipt.update(read_mutation_report(root, base, settings["report"], receipt))
    write_receipt(folder, "mutation", receipt)
    print_mutation_result(receipt)
    return 1 if receipt["status"] == "error" else 0


def run_mutation_with_cache(root, data, command, files, folder):
    """Run the command on a private copy of the shared cache, publish the copy on exit 0, and return the receipt fields.

    `status` is ran or error. A cache step that fails sets `error`, and the shared folder stays as it was. The private
    copy is removed either way: it served this run only.
    """
    shared, private = mutation_cache_dir(root), os.path.join(folder, "mutation-cache")
    try:
        seed_mutation_cache(shared, private)
    except OSError as exc:  # verify's own handling never raises: the receipt says what broke
        return {"status": "error", "cache": shared, "error": f"could not prepare the cache ({exc})"}
    result = run_mutation_command(root, data, command, files, folder, env={"POTHOS_MUTATION_CACHE": private})
    fields = {**result, "cache": shared, "status": "ran" if result["exit"] == 0 else "error"}
    try:
        if fields["status"] == "ran":
            publish_mutation_cache(private, shared)
    except OSError as exc:
        fields.update(status="error", error=f"could not publish the cache ({exc})")
    finally:
        shutil.rmtree(private, ignore_errors=True)
    return fields


def read_mutation_report(root, base, report, receipt):
    """The receipt fields a report adds: its path, counts and findings, with status clean or findings.

    A report the command never wrote adds nothing, so the status stays at ran; one that cannot be read is an error.
    """
    path = os.path.join(root, expand_with(report, receipt["env"]))
    if not os.path.isfile(path):
        return {}
    try:
        parsed = report_findings(root, path, receipt["files"], ui_check.added_lines(root, base))
    except Exception as exc:  # an advisory level never raises: the receipt says what went wrong
        return {"status": "error", "error": f"could not read the report {path}: {exc}"}
    return {**parsed, "report": path, "status": "findings" if parsed["findings"] else "clean"}


def print_mutation_result(receipt):
    """The new findings one per line and the closing line; otherwise the error, or the log tail and the exit code."""
    status = receipt["status"]
    if status in ("clean", "findings"):
        new = [f for f in receipt["findings"] if f["kind"] == "new"]
        print("\n".join(describe_mutant(f) for f in new[:TAIL]))
        print(MUTATION_CLOSING.format(new=len(new), files=len(receipt["files"]), inherited=len(receipt["findings"]) - len(new)))
    elif "error" in receipt:
        print(f"mutation: {receipt['error']}")
    else:
        if status == "error":
            with open(receipt["log"], encoding="utf-8", errors="replace") as fh:
                print("\n".join(fh.read().splitlines()[-TAIL:]))
        print(f"mutation: {status} in {receipt['seconds']}s (exit {receipt['exit']}) on {len(receipt['files'])} changed file(s); "
              f"log {receipt['log']}. Advisory, does not block.")
    if receipt.get("dirty_after"):
        print("mutation: the working tree has uncommitted changes, already there before the command; look at them before committing"
              if receipt["dirty_before"] else
              "mutation: the command left changes in the working tree; look at them before committing")


def expand_with(path, env):
    """os.path.expandvars reads os.environ, so lend it the variables the command got for the call."""
    previous = {name: os.environ.get(name) for name in env}
    os.environ.update(env)
    try:
        return os.path.expandvars(path)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def report_findings(root, report, files, added):
    """Read a mutation-testing-report-schema file: counts per status and the findings in the changed files, new first.

    Keys are joined with the report's projectRoot and made relative to the repository; mutants elsewhere are dropped.
    A finding is a surviving or uncovered mutant; it is `new` when its line is one the branch added.
    """
    with open(report, encoding="utf-8") as fh:
        data = json.load(fh)
    project_root = data.get("projectRoot") or root
    added = {path: {number for number, _ in lines} for path, lines in added.items()}
    counts, findings = {}, []
    for key, entry in (data.get("files") or {}).items():
        path = os.path.relpath(os.path.realpath(os.path.join(project_root, key)), os.path.realpath(root))
        if path not in files:
            continue
        for mutant in entry.get("mutants") or []:
            status = mutant["status"]
            counts[status] = counts.get(status, 0) + 1
            if MUTANT_STATUSES.get(status) != "finding":
                continue
            line = mutant["location"]["start"]["line"]
            finding = {"file": path, "line": line, "kind": "new" if line in added.get(path, ()) else "inherited",
                       "mutator": mutant.get("mutatorName")}
            if entry.get("source") is not None:
                finding["original"] = slice_source(entry["source"], mutant["location"])
            if mutant.get("replacement") is not None:
                finding["replacement"] = mutant["replacement"]
            finding["status"] = status
            findings.append(finding)
    findings.sort(key=lambda f: f["kind"] != "new")
    return {"counts": counts, "findings": findings}


def slice_source(source, location):
    """The text at a location: lines and columns are 1-based, the end column exclusive."""
    lines = source.split("\n")
    start, end = location["start"], location["end"]
    if start["line"] == end["line"]:
        return lines[start["line"] - 1][start["column"] - 1:end["column"] - 1]
    middle = lines[start["line"]:end["line"] - 1]
    return "\n".join([lines[start["line"] - 1][start["column"] - 1:], *middle, lines[end["line"] - 1][:end["column"] - 1]])


def describe_mutant(finding):
    change = " -> ".join(finding[key] for key in ("original", "replacement") if key in finding)
    return f"{finding['file']}:{finding['line']} {finding['mutator']}{': ' + change if change else ''} ({finding['status']})"


def mutation_cache_dir(root):
    """The tool's cache, one folder per repository under the Pothos home, shared by every clone and worktree."""
    return os.path.join(contract.pothos_home(), "mutation", contract.key_for(root, "mutation"))


def seed_mutation_cache(shared, private):
    """Copy the shared cache into this run's private folder: the tool never reads or writes the shared one."""
    os.makedirs(shared, exist_ok=True)
    if os.path.isdir(private):
        shutil.rmtree(private)
    shutil.copytree(shared, private)


def publish_mutation_cache(private, shared):
    """Each file of the private copy replaces its counterpart in the shared folder: written under a temporary name
    in the same folder, then renamed over the target. Last writer wins between runs; a torn file is impossible."""
    for current, _, names in os.walk(private):
        target = os.path.normpath(os.path.join(shared, os.path.relpath(current, private)))
        os.makedirs(target, exist_ok=True)
        for name in names:
            tmp = os.path.join(target, f".{name}.{os.getpid()}.tmp")
            shutil.copyfile(os.path.join(current, name), tmp)
            os.replace(tmp, os.path.join(target, name))


def run_mutation_command(root, data, command, files, folder, env=None):
    """Run the mutation command once on the changed files and say what happened, without reading any report.

    This is the seam the next steps build on: a report parser reads the file the command wrote under the output
    folder after the run, and a cache step adds its own variable through `env` and publishes its copy on exit 0.
    Returns command (as run), files, env (the variables exported), exit, seconds, log, dirty_before, dirty_after.
    """
    exported = {"POTHOS_CHANGED_FILES": "\n".join(files), "POTHOS_MUTATION_OUT": folder, **(env or {})}
    command = command.replace("{files}", ",".join(shlex.quote(path) for path in files))
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, "mutation.log")
    dirty_before = dirty(root, data)
    print(f"mutation: {command}", flush=True)
    started = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(command, shell=True, cwd=root, stdout=log, stderr=subprocess.STDOUT, text=True,
                              env={**os.environ, **exported})
    return {"command": command, "files": files, "env": exported, "exit": proc.returncode,
            "seconds": round(time.monotonic() - started, 1), "log": log_path,
            "dirty_before": dirty_before, "dirty_after": dirty(root, data)}


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
