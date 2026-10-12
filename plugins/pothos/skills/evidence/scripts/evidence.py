#!/usr/bin/env python3
"""Mechanics for capturing proof that a change works: start the app, take screenshots, stop it.

Usage:
  evidence.py dir                                  print (and create) this branch's evidence folder
  evidence.py plan [--base BRANCH]                 which apps the branch touches and which screenshots each allows
  evidence.py serve [--app NAME] [--env NAME] [--timeout SECS]
                                                   start the contract's dev command, wait for its URL
  evidence.py stop PID                             stop a server started by serve
  evidence.py shot URL NAME [--width W] [--height H] [--wait MS]
                                                   headless browser screenshot into the evidence folder
  evidence.py sim NAME                             screenshot of the booted iOS simulator

Evidence lives in $POTHOS_HOME/evidence/<host>/<owner>/<repo>/<branch>/, never in the repository.
Exit codes: 0 ok, 1 failed (server never answered, no browser, no simulator), 2 no contract,
3 nothing to run (no dev command or URL), 64 usage.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
sys.path.insert(0, os.path.realpath(SHARED))
import contract  # noqa: E402

BROWSERS = [
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "brave-browser", "google-chrome", "chromium", "chromium-browser",
]


def flag(args, name, default=None):
    if name in args and args.index(name) + 1 < len(args):
        return args[args.index(name) + 1]
    return default


def folder(root):
    branch = contract.git(["symbolic-ref", "--short", "-q", "HEAD"], root) or "detached"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "branch"
    path = os.path.join(contract.pothos_home(), "evidence", contract.key_for(root, "evidence"), slug)
    os.makedirs(path, exist_ok=True)
    return path


def load(root):
    path = contract.locate(root)
    if not path:
        print("no pothos contract for this repository; run /pothos:plant", file=sys.stderr)
        sys.exit(2)
    return contract.load(path)


def answers(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def changed_files(root, base):
    merge_base = contract.git(["merge-base", "HEAD", base], root) or contract.git(["merge-base", "HEAD", "origin/" + base], root)
    committed = contract.git(["diff", "--name-only", merge_base, "HEAD"], root) if merge_base else ""
    pending = subprocess.run(["git", "-C", root, "status", "--porcelain", "--untracked-files=all"],
                             capture_output=True, text=True).stdout
    files = set(filter(None, (committed or "").splitlines()))
    files |= {line[3:].split(" -> ")[-1] for line in pending.splitlines() if len(line) > 3}
    return files


def plan(root, args):
    """One line per app the branch touches: name, screenshots mode, start command and URL."""
    data = load(root)
    run = data.get("run") or {}
    base = flag(args, "--base") or (data.get("pr") or {}).get("base") or "main"
    apps = run.get("apps") or []
    if not apps:
        targets = [{"name": "(repository)", **run}]
    else:
        files = changed_files(root, base)
        targets = [a for a in apps if any(f == a["path"].rstrip("/") or f.startswith(a["path"].rstrip("/") + "/") for f in files)]
        if not targets:
            print(f"the branch touches no app listed in run.apps (compared with {base}); prove it with test output")
            return 0
    for app in targets:
        shots = app.get("screenshots") or "unknown"
        hint = "  (unset: try once; if it fails, suggest setting it with /pothos:plant audit)" if shots == "unknown" else ""
        print(f"app={app['name']} screenshots={shots} dev={app.get('dev') or '-'} url={app.get('url') or '-'}{hint}")
    return 0


def serve(root, args):
    data = load(root)
    run = data.get("run") or {}
    app_name = flag(args, "--app")
    if app_name:
        apps = {a["name"]: a for a in run.get("apps") or []}
        if app_name not in apps:
            print(f"unknown app '{app_name}'; the contract lists: {', '.join(apps) or 'none'}", file=sys.stderr)
            return 3
        run = {**run, "dev": apps[app_name].get("dev"), "url": apps[app_name].get("url")}
    env_name = flag(args, "--env")
    command = run.get("dev")
    if env_name:
        envs = {e["name"]: e for e in run.get("environments") or []}
        if env_name not in envs:
            print(f"unknown environment '{env_name}'; the contract lists: {', '.join(envs) or 'none'}", file=sys.stderr)
            return 3
        command = envs[env_name]["dev"]
    url = run.get("url")
    if not command or not url:
        print("the contract needs a dev command (run.dev, an environment or the app's dev) and its URL to serve the app", file=sys.stderr)
        return 3
    if answers(url):
        print(f"already-running url={url}")
        return 0
    log_path = os.path.join(folder(root), "server.log")
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(command, shell=True, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + float(flag(args, "--timeout", "180"))
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(f"the dev command exited with {proc.returncode} before {url} answered; log {log_path}", file=sys.stderr)
            return 1
        if answers(url):
            print(f"pid={proc.pid} url={url} log={log_path}")
            return 0
        time.sleep(1)
    os.killpg(proc.pid, signal.SIGTERM)
    print(f"{url} did not answer in time; stopped the server; log {log_path}", file=sys.stderr)
    return 1


def stop(pid):
    try:
        os.killpg(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        print(f"no process group {pid}")
        return 0
    print(f"stopped {pid}")
    return 0


def browser():
    for candidate in BROWSERS:
        path = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if path and os.path.exists(path):
            return path
    return None


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "shot"


def shot(root, args):
    url, name = args[0], safe_name(args[1])
    exe = browser()
    if not exe:
        print("no Chromium-based browser found for headless screenshots", file=sys.stderr)
        return 1
    out = os.path.join(folder(root), name + ".png")
    width, height = flag(args, "--width", "1280"), flag(args, "--height", "800")
    cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
           f"--virtual-time-budget={flag(args, '--wait', '4000')}", f"--screenshot={out}", url]
    subprocess.run(cmd, capture_output=True, timeout=120)
    if not os.path.isfile(out):
        print(f"the browser produced no screenshot for {url}", file=sys.stderr)
        return 1
    print(out)
    return 0


def sim(root, name):
    if not shutil.which("xcrun"):
        print("xcrun not found; simulator screenshots need Xcode", file=sys.stderr)
        return 1
    out = os.path.join(folder(root), safe_name(name) + ".png")
    result = subprocess.run(["xcrun", "simctl", "io", "booted", "screenshot", out], capture_output=True, text=True)
    if result.returncode or not os.path.isfile(out):
        print("no booted simulator answered: " + (result.stderr.strip() or "unknown error"), file=sys.stderr)
        return 1
    print(out)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 64
    root = contract.repo_root(os.getcwd())
    cmd, rest = argv[0], argv[1:]
    if cmd == "dir":
        print(folder(root))
        return 0
    if cmd == "plan":
        return plan(root, rest)
    if cmd == "serve":
        return serve(root, rest)
    if cmd == "stop" and len(rest) == 1 and rest[0].isdigit():
        return stop(rest[0])
    if cmd == "shot" and len(rest) >= 2:
        return shot(root, rest)
    if cmd == "sim" and len(rest) == 1:
        return sim(root, rest[0])
    print(f"usage error; run {os.path.basename(__file__)} --help", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
