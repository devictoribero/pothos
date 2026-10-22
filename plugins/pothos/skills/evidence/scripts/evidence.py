#!/usr/bin/env python3
"""Mechanics for capturing proof that a change works: start the app, take screenshots, stop it.

Usage:
  evidence.py dir                                  print (and create) this branch's evidence folder
  evidence.py plan [--base BRANCH]                 which apps the branch touches and which screenshots each allows
  evidence.py screens [--base BRANCH]              which screens the branch touches (from the contract's ui.screens, ui.components,
                                                   ui.tokens and ui.locales) and which languages to capture
  evidence.py capture SCREEN [SCREEN ...] [--lang es,ca] [--base BRANCH] [--app NAME]
                                                   run the contract's capture command and keep its images as after-…; with --base,
                                                   run it again in a worktree of that ref (after run.setup) and keep those as before-…
  evidence.py serve [--app NAME] [--env NAME] [--timeout SECS]
                                                   start the contract's dev command, wait for its URL
  evidence.py stop PID                             stop a server started by serve
  evidence.py shot URL NAME [--width W] [--height H] [--wait MS]
                                                   headless browser screenshot into the evidence folder
  evidence.py sim NAME                             screenshot of the booted iOS simulator
  evidence.py emu NAME                             screenshot of the running Android emulator (ANDROID_SERIAL picks one)
  evidence.py upload FILE [FILE ...]               upload to this month's pr-evidence release, print markdown

Evidence lives in $POTHOS_HOME/evidence/<host>/<owner>/<repo>/<branch>/, never in the repository.
upload needs pr.evidence set to github-release in the contract: it publishes the files as assets of a
prerelease named pr-evidence-YYYY-MM, one per month so no release reaches GitHub's 1000-asset limit.
Exit codes: 0 ok, 1 failed (server never answered, no browser, no simulator, upload failed), 2 no contract,
3 nothing to run (no dev command or URL, upload not enabled, no capture command), 64 usage.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
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
    try:
        return contract.load(path)
    except json.JSONDecodeError as exc:
        print(f"the contract at {path} is not valid JSON ({exc}); run /pothos:plant", file=sys.stderr)
        sys.exit(2)


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
        capture = f" capture={app['capture']['command']}" if (app.get("capture") or {}).get("command") else ""
        print(f"app={app['name']} screenshots={shots}{capture} dev={app.get('dev') or '-'} url={app.get('url') or '-'}{hint}")
    return 0


LANG_TOKEN = "{lang}"
LANG_GROUP = r"(?P<lang>[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?)"


def glob_regex(pattern):
    """A repository-relative folder or glob as a regex over repository-relative paths: `**` crosses folders,
    `*` stays inside one, a folder matches everything under it, and `{lang}` is one language code, captured."""
    out = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith(LANG_TOKEN, i):
            out += LANG_GROUP
            i += len(LANG_TOKEN)
            continue
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        else:
            out += re.escape(ch)
        i += 1
    has_extension = bool(re.search(r"\.[A-Za-z0-9]+$", pattern))
    tail = "" if has_extension else "(?:/.*)?"
    return re.compile("^" + out.rstrip("/") + tail + "$")


def matches_any(path, patterns):
    return any(glob_regex(p).match(path) for p in patterns)


def locale_language(path, patterns):
    """The language a copy file belongs to: the `{lang}` segment of the pattern that matches it
    (`locales/{lang}/*.json`, `values-{lang}/strings.xml`), else the file's name without its extension
    (`es.ts`, `ca.json`). None when no pattern matches."""
    for pattern in patterns:
        match = glob_regex(pattern).match(path)
        if match:
            return match.groupdict().get("lang") or re.sub(r"\..*$", "", os.path.basename(path))
    return None


def ui_sets(data, path):
    """The ui section that governs a repository-relative path: the app's own in a monorepo, the top level otherwise."""
    for app in (data.get("run") or {}).get("apps") or []:
        folder = app.get("path", "").rstrip("/")
        if folder and (path == folder or path.startswith(folder + "/")) and app.get("ui"):
            return app["ui"], app
    return data.get("ui") or {}, None


def screen_files(root, patterns):
    """Every file under the screen patterns, so importers can be looked up by name."""
    found = []
    for base, _, files in os.walk(root):
        if "/node_modules" in base or "/.git" in base:
            continue
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), root)
            if matches_any(rel, patterns):
                found.append(rel)
    return sorted(found)


def importers(root, screens, changed):
    """The screens whose source names the changed file's module (one grep level, by its stem)."""
    stem = re.sub(r"\.[^.]+$", "", os.path.basename(changed))
    stem = re.sub(r"\.(spec|test)$", "", stem)
    if stem in ("index", "") or changed in screens:
        return []
    needle = re.compile(r"(?:from|require\()\s*['\"][^'\"]*\b" + re.escape(stem) + r"['\"/]")
    hits = []
    for screen in screens:
        try:
            with open(os.path.join(root, screen), encoding="utf-8", errors="replace") as fh:
                if needle.search(fh.read()):
                    hits.append(screen)
        except OSError:
            continue
    return hits


def screens(root, args):
    """Which screens the branch touches, by the contract's ui.screens, ui.components, ui.tokens and ui.locales,
    and which languages to capture (ui.languages). Prints `none` when the branch reaches no screen."""
    data = load(root)
    base = flag(args, "--base") or (data.get("pr") or {}).get("base") or "main"
    changed = sorted(f for f in changed_files(root, base) if not re.search(r"\.(spec|test)\.[^./]+$", f))
    direct, via, copy_languages, languages, capture = [], {}, set(), [], {}
    seen_ui = []
    for path in changed:
        ui, app = ui_sets(data, path)
        if not ui.get("screens"):
            continue
        if ui not in seen_ui:
            seen_ui.append(ui)
            if ui.get("languages"):
                languages = ui["languages"]
            command = ((app or {}).get("capture") or (data.get("run") or {}).get("capture") or {}).get("command")
            if command:
                capture = {"command": command, "app": (app or {}).get("name")}
        if matches_any(path, ui["screens"]):
            direct.append(path)
        elif matches_any(path, ui.get("components") or []) or matches_any(path, ui.get("tokens") or []):
            via[path] = importers(root, screen_files(root, ui["screens"]), path)
        elif matches_any(path, ui.get("locales") or []):
            copy_languages.add(locale_language(path, ui["locales"]))
    if not direct and not via and not copy_languages:
        print(f"none: the branch touches no screen, shared component, token or copy (compared with {base})")
        return 0
    for path in direct:
        print(f"screen {path}")
    for path, hits in via.items():
        print(f"via {path}: " + (", ".join(hits) if hits else "no screen imports it directly; name the screens that use it"))
    if copy_languages:
        print("copy " + ", ".join(sorted(copy_languages)))
    if languages:
        chosen = [languages[0]] + ([l for l in languages[1:] if copy_languages] if len(languages) > 1 else [])
        print("languages " + ",".join(chosen) + (f" ({languages[0]} always; the rest because copy changed)" if len(chosen) > 1 else f" ({languages[0]} always)"))
    if capture.get("command"):
        print(f"capture {capture['command']}" + (f" (app {capture['app']})" if capture.get("app") else ""))
    else:
        print("capture none: no capture command in the contract; use the device, or list the screens to check by hand")
    return 0


def capture_command(data, app_name):
    run = data.get("run") or {}
    if app_name:
        apps = {a["name"]: a for a in run.get("apps") or []}
        if app_name not in apps:
            return None, f"unknown app '{app_name}'; the contract lists: {', '.join(apps) or 'none'}"
        command = (apps[app_name].get("capture") or {}).get("command")
    else:
        command = (run.get("capture") or {}).get("command")
        if not command:
            with_capture = [a for a in run.get("apps") or [] if (a.get("capture") or {}).get("command")]
            if len(with_capture) == 1:
                command = with_capture[0]["capture"]["command"]
            elif with_capture:
                return None, "several apps have a capture command; pass --app NAME"
    if not command:
        return None, "the contract has no capture command (run.capture or the app's capture); capture on a device instead"
    return command, None


def capture(root, args):
    """Runs the contract's capture command for each screen and keeps its images in the evidence folder as
    after-<screen>-<lang>.png. With --base, checks that ref out in a throwaway worktree, runs run.setup there
    and the same command again, and keeps those images as before-…; when that cannot be done, says why on
    stderr and keeps the after images alone."""
    data = load(root)
    command, error = capture_command(data, flag(args, "--app"))
    if error:
        print(error, file=sys.stderr)
        return 3
    names = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--lang", "--base", "--app"))]
    if not names:
        print("capture needs at least one screen name", file=sys.stderr)
        return 64
    out = folder(root)
    lang = ["--lang", flag(args, "--lang")] if flag(args, "--lang") else []
    after, error = run_capture(root, command, names, lang, out, out, "after-")
    if error:
        print(error, file=sys.stderr)
        return 1
    kept = list(after)
    base = flag(args, "--base")
    if base:
        before, error = capture_base(root, data, command, names, lang, out, base)
        if error:
            print(f"before: {error}; captured the new state only, say so in evidence.md", file=sys.stderr)
        kept += before
    print("\n".join(kept))
    return 0


def run_capture(cwd, command, names, lang, shots, out, prefix):
    """Runs `<command> <names> --out <shots> [--lang <codes>]` from cwd and moves every image it prints into out
    under the prefix. Returns (paths, None) or ([], why it failed)."""
    full = f"{command} {' '.join(names)} --out {shlex_quote(shots)} " + " ".join(lang)
    result = subprocess.run(full, shell=True, cwd=cwd, capture_output=True, text=True)
    sys.stderr.write(result.stderr)
    if result.returncode:
        return [], f"the capture command exited {result.returncode}: {full}"
    produced = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    kept = []
    for path in produced:
        if not os.path.isfile(path):
            return [], f"the capture command printed a path that does not exist: {path}"
        target = os.path.join(out, prefix + os.path.basename(path))
        if os.path.realpath(path) != os.path.realpath(target):
            shutil.move(path, target)
        kept.append(target)
    if not kept:
        return [], "the capture command printed no image path"
    return kept, None


def capture_base(root, data, command, names, lang, out, ref):
    """The base branch's images: a detached worktree of ref outside the repository, run.setup in it when the
    contract has one, then the same capture command from that worktree. The worktree is removed afterwards."""
    sha = contract.git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], root) \
        or contract.git(["rev-parse", "--verify", "--quiet", "origin/" + ref + "^{commit}"], root)
    if not sha:
        return [], f"no ref named {ref} (nor origin/{ref})"
    tmp = tempfile.mkdtemp(prefix="pothos-base-")
    worktree = os.path.join(tmp, "repo")
    shots = os.path.join(tmp, "shots")
    os.makedirs(shots)
    try:
        added = subprocess.run(["git", "-C", root, "worktree", "add", "--detach", worktree, sha],
                               capture_output=True, text=True)
        if added.returncode:
            return [], f"could not check {ref} out in a worktree: {added.stderr.strip().splitlines()[-1] if added.stderr.strip() else added.returncode}"
        setup = (data.get("run") or {}).get("setup")
        if setup:
            prepared = subprocess.run(setup, shell=True, cwd=worktree, capture_output=True, text=True)
            if prepared.returncode:
                tail = "\n".join((prepared.stderr or prepared.stdout).strip().splitlines()[-5:])
                return [], f"run.setup failed in the worktree of {ref} (exit {prepared.returncode}):\n{tail}"
        kept, error = run_capture(worktree, command, names, lang, shots, out, "before-")
        if error:
            return [], f"on {ref}, {error} (a base that predates the capture command cannot be captured)"
        return kept, None
    finally:
        subprocess.run(["git", "-C", root, "worktree", "remove", "--force", worktree], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def shlex_quote(value):
    import shlex
    return shlex.quote(value)


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
    log_path = os.path.join(folder(root), f"server-{safe_name(app_name or 'app')}.log")
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(command, shell=True, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    timeout = float(flag(args, "--timeout", "180"))
    deadline = time.monotonic() + timeout
    exited_clean = False
    while time.monotonic() < deadline:
        # A command that exits 0 may have started the server in the background (a daemon, a container):
        # keep waiting for the URL. A non-zero exit means it failed.
        if proc.poll() is not None and proc.returncode != 0:
            print(f"the dev command exited with {proc.returncode} before {url} answered; log {log_path}", file=sys.stderr)
            return 1
        if proc.poll() is not None and not exited_clean:
            exited_clean = True
            print(f"the dev command exited 0; waiting up to {timeout:.0f}s for {url} to answer", file=sys.stderr)
        if answers(url):
            print(f"pid={proc.pid} url={url} log={log_path}")
            return 0
        time.sleep(1)
    stop(proc.pid)
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
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"the browser did not finish {url} in 120 seconds", file=sys.stderr)
        return 1
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


def adb():
    found = shutil.which("adb")
    if found:
        return found
    for sdk in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                os.path.expanduser("~/Library/Android/sdk"), os.path.expanduser("~/Android/Sdk")):
        path = os.path.join(sdk, "platform-tools", "adb") if sdk else ""
        if path and os.path.isfile(path):
            return path
    return None


def emu(root, name):
    exe = adb()
    if not exe:
        print("adb not found; emulator screenshots need the Android SDK platform-tools", file=sys.stderr)
        return 1
    result = subprocess.run([exe, "exec-out", "screencap", "-p"], capture_output=True, timeout=60)
    if result.returncode or not result.stdout.startswith(b"\x89PNG"):
        reason = result.stderr.decode(errors="replace").strip() or "no PNG came back"
        print(f"no Android emulator answered (set ANDROID_SERIAL when several run): {reason}", file=sys.stderr)
        return 1
    out = os.path.join(folder(root), safe_name(name) + ".png")
    with open(out, "wb") as fh:
        fh.write(result.stdout)
    print(out)
    return 0


RELEASE_STORE = "github-release"
VIDEO = (".mp4", ".mov", ".webm")


def gh(args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def github_repo(root):
    """github.com/owner/repo for gh's -R, which also overrides a GH_HOST set to an ssh alias."""
    remote = contract.git(["remote", "get-url", "origin"], root)
    key = contract.remote_key(remote) if remote else None
    return key if key and key.startswith("github.com/") and key.count("/") == 2 else None


def asset_prefix(root, repo):
    """The pull request number once one exists, the branch before: the month's release is shared repo-wide."""
    branch = contract.git(["symbolic-ref", "--short", "-q", "HEAD"], root)
    if branch:
        number = gh(["pr", "view", branch, "-R", repo, "--json", "number", "--jq", ".number"]).stdout.strip()
        if number.isdigit():
            return "pr" + number
    return safe_name(branch or "detached")


def ensure_release(repo, tag, month):
    if gh(["release", "view", tag, "-R", repo]).returncode == 0:
        return True
    created = gh(["release", "create", tag, "-R", repo, "--prerelease", "--title", f"PR evidence {month}",
                  "--notes", "Screenshots embedded in this month's pull requests. Kept as their history; do not delete."])
    # Another upload may have created it between the view and the create.
    return created.returncode == 0 or gh(["release", "view", tag, "-R", repo]).returncode == 0


def upload(root, files):
    if ((load(root).get("pr") or {}).get("evidence")) != RELEASE_STORE:
        print(f"upload publishes files to GitHub; enable it with pr.evidence set to {RELEASE_STORE} in the contract",
              file=sys.stderr)
        return 3
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        print("no such file: " + ", ".join(missing), file=sys.stderr)
        return 1
    repo = github_repo(root)
    if not repo:
        print("upload needs an origin remote on github.com", file=sys.stderr)
        return 1
    month = time.strftime("%Y-%m")
    tag = f"pr-evidence-{month}"
    if not ensure_release(repo, tag, month):
        print(f"could not create the {tag} release on {repo}", file=sys.stderr)
        return 1
    prefix = asset_prefix(root, repo)
    with tempfile.TemporaryDirectory() as staging:
        for path in files:
            name = f"{prefix}-{safe_name(os.path.basename(path))}"
            staged = os.path.join(staging, name)
            shutil.copyfile(path, staged)
            result = gh(["release", "upload", tag, staged, "-R", repo, "--clobber"])
            if result.returncode:
                print(f"upload of {path} failed: {result.stderr.strip()}", file=sys.stderr)
                return 1
            url = f"https://{repo}/releases/download/{tag}/{name}"
            print(f"[{name}]({url})" if name.lower().endswith(VIDEO) else f"![{name}]({url})")
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
    if cmd == "screens":
        return screens(root, rest)
    if cmd == "capture" and rest:
        return capture(root, rest)
    if cmd == "serve":
        return serve(root, rest)
    if cmd == "stop" and len(rest) == 1 and rest[0].isdigit() and int(rest[0]) > 1:  # 0 and 1 would signal this shell
        return stop(rest[0])
    if cmd == "shot" and len(rest) >= 2:
        return shot(root, rest)
    if cmd == "sim" and len(rest) == 1:
        return sim(root, rest[0])
    if cmd == "emu" and len(rest) == 1:
        return emu(root, rest[0])
    if cmd == "upload" and rest:
        return upload(root, rest)
    print(f"usage error; run {os.path.basename(__file__)} --help", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
