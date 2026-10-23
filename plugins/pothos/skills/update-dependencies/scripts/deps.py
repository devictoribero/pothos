#!/usr/bin/env python3
"""The deterministic half of update-dependencies: inventory, registry facts, drivers, targets, radius, policy,
reconciliation and the run record. The model adds only judgement on top: evidence for a bug or feature driver,
the changelog read against the symbols the repository imports, and the migration itself.

Usage:
  deps.py plan     [--only PKG ...] [--repo DIR] [--today YYYY-MM-DD]
                                        inventory every direct dependency, classify it and write the run record;
                                        prints the record path and one line per entry
  deps.py impact   PKG [--repo DIR]     the files that import PKG (anchored) and the test files that import them
  deps.py update   RECORD ID --status STATUS [--note TEXT] [--pr URL] [--set KEY=VALUE ...]
                                        record what happened to one entry (applied, in-progress, verified,
                                        failed, pr-opened, reported, superseded)
  deps.py summary  RECORD               one line per entry, holds and decisions reported once
  deps.py unlock   [--repo DIR]         remove a stale lock left by a run that died

Facts come from the npm registry (`npm view`), the package manager's audit (`npm audit --json` or
`pnpm audit --json`), the repository's open pull requests with the contract's label (`gh pr list`) and the
policy file the contract names (`deps.policy`). Every external fact carries its provenance in the record, and
a package whose registry data is missing fails explicitly instead of being classified with a gap. The record
lives at $POTHOS_HOME/deps/<host>/<owner>/<repo>/<date>.json, never in the repository, and `latest` next to it
points at the newest one. Only one run at a time per repository: a second `plan` sees the first one's lock and
stops.

Stand-ins for tests and evals: POTHOS_NPM, POTHOS_PNPM and POTHOS_GH name the binaries to call instead of
npm, pnpm and gh. Only the npm registry is known; other ecosystems need an adapter.

Exit codes: 0 ok, 1 at least one entry failed or the run could not classify (the record says what),
2 no contract, 3 nothing to do (no package.json, or every package excluded), 4 another run holds the lock,
64 usage. Standard library only.
"""
import datetime
import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
sys.path.insert(0, os.path.realpath(SHARED))
import contract  # noqa: E402

OK, FAILED, NO_CONTRACT, NOTHING, LOCKED, USAGE = 0, 1, 2, 3, 4, 64

DEFAULTS = {"cooling_off_days": 14, "dead_line_months": 12, "review_budget": 3, "label": "dependency-update"}
DRIVERS = ("security", "eol", "drift-exposed", "unblocks", "bug", "feature", "drift-safe")
ENTRY_STATUSES = ("candidate", "skipped", "failed", "applied", "in-progress", "verified", "pr-opened", "reported", "superseded")
LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun"), ("package-lock.json", "npm"))
SOURCE_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".astro")
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", ".next", "coverage", ".turbo", ".cache"}
TEST_MARKERS = (".test.", ".spec.", "/__tests__/", "/test/", "/tests/")
# A tool configured by a file and imported by nobody has the whole repository as its radius.
CONFIG_SURFACE = {
    "typescript": ["tsconfig*.json"], "eslint": ["eslint.config.*", ".eslintrc*"], "prettier": [".prettierrc*", "prettier.config.*"],
    "postcss": ["postcss.config.*"], "autoprefixer": ["postcss.config.*"], "vite": ["vite.config.*"], "vitest": ["vitest.config.*"],
    "jest": ["jest.config.*"], "babel": ["babel.config.*", ".babelrc*"], "@babel/core": ["babel.config.*", ".babelrc*"],
    "tailwindcss": ["tailwind.config.*"], "webpack": ["webpack.config.*"], "rollup": ["rollup.config.*"], "tsup": ["tsup.config.*"],
    "next": ["next.config.*"], "playwright": ["playwright.config.*"], "@playwright/test": ["playwright.config.*"],
    "cypress": ["cypress.config.*"], "knip": ["knip.json", "knip.config.*"], "stylelint": [".stylelintrc*", "stylelint.config.*"],
    "husky": [".husky"], "lint-staged": [".lintstagedrc*", "lint-staged.config.*"],
}
RADIUS = {0: "none", 1: "narrow", 2: "narrow", 3: "narrow"}
HOLD = re.compile(r"^- (?P<pkg>\S+) stays on (?P<major>\d+) until (?P<date>\d{4}-\d{2}-\d{2})(?::\s*(?P<why>.*))?$")
DECISION = re.compile(r"^- (?P<pkg>\S+): not before (?P<date>\d{4}-\d{2}-\d{2})(?::\s*(?P<why>.*))?$")
METADATA = re.compile(r"^Dependency-(Root|Target|Driver|Entry-Id):\s*(\S+)", re.M)
PRERELEASE_TAGS = ("alpha", "beta", "rc", "next", "canary", "dev", "nightly", "pre")


# ---------- small semver ----------

def parse(version):
    """(major, minor, patch, prerelease) or None. Build metadata is ignored."""
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$", version.strip())
    if not match:
        return None
    pre = match.group(4)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), tuple(pre.split(".")) if pre else None)


def is_prerelease(version):
    parsed = parse(version)
    return bool(parsed and parsed[3])


def key(version):
    """Sort key: a prerelease sorts before its release."""
    major, minor, patch, pre = parse(version)
    parts = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre) if pre else None
    return (major, minor, patch, 1 if pre is None else 0, parts or ())


def compare(a, b):
    ka, kb = key(a), key(b)
    return (ka > kb) - (ka < kb)


def _partial(text):
    """A possibly partial version (`18`, `1.2`, `1.x`) as (major, minor, patch) with None for the missing parts."""
    parts = [p for p in text.lstrip("v").split(".")]
    out = []
    for part in parts[:3]:
        if part in ("x", "X", "*", ""):
            break
        out.append(int(re.match(r"\d+", part).group(0)))
    while len(out) < 3:
        out.append(None)
    return tuple(out)


def _bounds(comparator):
    """A single npm comparator as (lower (inclusive), upper (exclusive)) version tuples, None for open ends."""
    text = comparator.strip()
    if text in ("", "*", "x", "X", "latest"):
        return None, None
    match = re.match(r"^(\^|~|>=|<=|>|<|=)?\s*v?([\dxX*][\w.*-]*)$", text)
    if not match:
        return None, None
    op, rest = match.group(1) or "", match.group(2)
    major, minor, patch = _partial(rest)
    low = (major or 0, minor or 0, patch or 0)
    if op == "^":
        if major:
            high = (major + 1, 0, 0)
        elif minor:
            high = (0, minor + 1, 0)
        else:
            high = (0, 0, (patch or 0) + 1)
        return low, high
    if op == "~":
        return low, (major, (minor or 0) + 1, 0) if minor is not None else (major + 1, 0, 0)
    if op in ("", "="):
        if minor is None:
            return low, (major + 1, 0, 0)
        if patch is None:
            return low, (major, minor + 1, 0)
        return low, (major, minor, patch + 1)
    if op == ">=":
        return low, None
    if op == ">":
        if patch is None:
            return ((major + 1, 0, 0) if minor is None else (major, minor + 1, 0)), None
        return (major, minor, patch + 1), None
    if op == "<":
        return None, low
    if op == "<=":
        if minor is None:
            return None, (major + 1, 0, 0)
        if patch is None:
            return None, (major, minor + 1, 0)
        return None, (major, minor, patch + 1)
    return None, None


def satisfies(version, range_text):
    """Does a version satisfy an npm range? Covers ^, ~, x, *, comparators, hyphen ranges and ||.
    Prereleases satisfy only an exact comparator that names them."""
    parsed = parse(version)
    if not parsed:
        return False
    triple = parsed[:3]
    for alternative in str(range_text).split("||"):
        alternative = alternative.strip()
        hyphen = re.match(r"^(\S+)\s+-\s+(\S+)$", alternative)
        if hyphen:
            lows, highs = [_bounds(">=" + hyphen.group(1))[0]], [_bounds("<=" + hyphen.group(2))[1]]
        else:
            comparators = alternative.split()
            if alternative.strip() in ("", "*"):
                return True
            if parsed[3] and alternative.lstrip("=") == version:
                return True
            pairs = [_bounds(c) for c in comparators]
            lows, highs = [p[0] for p in pairs], [p[1] for p in pairs]
        if parsed[3]:
            continue
        ok = all(triple >= low for low in lows if low) and all(triple < high for high in highs if high)
        if ok:
            return True
    return False


# ---------- repository ----------

def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def package_manager(root):
    return next((pm for lock, pm in LOCKFILES if os.path.exists(os.path.join(root, lock))), None)


def workspace_dirs(root, pkg):
    """The root and every workspace package folder, as repository-relative paths."""
    patterns = []
    workspaces = (pkg or {}).get("workspaces") or []
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages") or []
    patterns += [w for w in workspaces if isinstance(w, str)]
    yaml = os.path.join(root, "pnpm-workspace.yaml")
    if os.path.isfile(yaml):
        with open(yaml, encoding="utf-8") as fh:
            in_packages = False
            for line in fh:
                if re.match(r"^packages\s*:", line):
                    in_packages = True
                    continue
                if in_packages:
                    item = re.match(r"^\s+-\s*['\"]?([^'\"#]+?)['\"]?\s*$", line)
                    if item:
                        patterns.append(item.group(1).strip())
                    elif line.strip() and not line.startswith((" ", "\t")):
                        in_packages = False
    folders = ["."]
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        for match in sorted(glob.glob(os.path.join(root, pattern))):
            if os.path.isfile(os.path.join(match, "package.json")):
                folders.append(os.path.relpath(match, root))
    return folders


def installed_version(root, folder, name):
    """The version under the nearest node_modules, walking up from the package folder."""
    current = os.path.realpath(os.path.join(root, folder))
    top = os.path.realpath(root)
    while True:
        meta = read_json(os.path.join(current, "node_modules", name, "package.json"))
        if meta and meta.get("version"):
            return meta["version"], os.path.relpath(os.path.join(current, "node_modules", name), root)
        if current == top or not current.startswith(top):
            return None, None
        current = os.path.dirname(current)


def inventory(root, only=None, exclude=None):
    """Every direct dependency of every package in the repository, with its declared range and installed version.
    Packages outside `only` or matching `exclude` stay in the inventory, marked, so a candidate's peer range can be
    checked against what they will keep installed; they are never classified."""
    pkg = read_json(os.path.join(root, "package.json"))
    if pkg is None:
        return None
    entries = {}
    for folder in workspace_dirs(root, pkg):
        data = pkg if folder == "." else read_json(os.path.join(root, folder, "package.json"))
        if not data:
            continue
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            for name, spec in sorted((data.get(section) or {}).items()):
                if not isinstance(spec, str) or spec.startswith(("workspace:", "file:", "link:", "git", "http", "github:")):
                    continue
                version, where = installed_version(root, folder, name)
                entry = entries.setdefault(name, {"name": name, "declared": [], "installed": version, "installed_at": where,
                                                   "runtime": False, "selected": not only or name in only,
                                                   "excluded": any(fnmatch.fnmatch(name, p) for p in (exclude or [])) and not (only and name in only)})
                entry["declared"].append({"package": folder, "section": section, "range": spec})
                entry["runtime"] = entry["runtime"] or section == "dependencies"
                if entry["installed"] is None and version:
                    entry["installed"], entry["installed_at"] = version, where
    return entries


def lockfile_in_sync(root, pkg):
    """npm's lockfile records the root's declared ranges; a mismatch means someone edited package.json without
    installing, and a bump on top of that would mix two changes. Other lockfiles are not checked."""
    lock = read_json(os.path.join(root, "package-lock.json"))
    if not lock or "packages" not in lock:
        return True, None
    recorded = lock["packages"].get("", {})
    for section in ("dependencies", "devDependencies"):
        declared = pkg.get(section) or {}
        if declared != (recorded.get(section) or {}):
            return False, f"package-lock.json {section} differ from package.json; run the install first"
    return True, None


# ---------- external facts ----------

def binary(name):
    return os.environ.get("POTHOS_" + name.upper()) or name


def run(args, cwd, timeout=120):
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    return done, None


def registry(name, root):
    """Published versions with dates, the deprecation message and the peer ranges of the latest version."""
    done, error = run([binary("npm"), "view", name, "time", "deprecated", "dist-tags.latest", "--json"], root)
    if done is None or done.returncode != 0:
        return None, (error or done.stderr.strip() or f"npm view {name} failed").splitlines()[-1]
    try:
        data = json.loads(done.stdout or "{}")
    except ValueError:
        return None, f"npm view {name}: not JSON"
    times = data.get("time") if isinstance(data, dict) else None
    if not isinstance(times, dict):
        return None, f"npm view {name}: no publish dates"
    versions = {v: t for v, t in times.items() if parse(v)}
    if not versions:
        return None, f"npm view {name}: no parseable versions"
    return {"versions": versions, "deprecated": data.get("deprecated") or None, "latest": data.get("dist-tags.latest")}, None


def peers(name, version, root):
    done, error = run([binary("npm"), "view", f"{name}@{version}", "peerDependencies", "--json"], root)
    if done is None or done.returncode != 0:
        return None
    try:
        data = json.loads(done.stdout or "{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else {}


def advisories(root, pm):
    """Advisories per direct package, from the package manager's audit. npm's format (vulnerabilities) and the
    older one pnpm and yarn print (advisories) are both read."""
    if pm not in ("npm", "pnpm"):
        return None, f"advisories need npm or pnpm audit; {pm or 'no lockfile'} is not read"
    done, error = run([binary(pm), "audit", "--json"], root, timeout=300)
    if done is None:
        return None, error
    try:
        data = json.loads(done.stdout or "{}")
    except ValueError:
        return None, (done.stderr.strip() or "audit printed no JSON").splitlines()[-1]
    if not isinstance(data, dict) or (done.returncode != 0 and not (data.get("vulnerabilities") or data.get("advisories"))):
        # npm exits 1 when it found vulnerabilities, which is an answer; any other non-zero exit is a failure.
        if done.returncode != 0 and not data:
            return None, (done.stderr.strip() or f"{pm} audit exited {done.returncode}").splitlines()[-1]
        if not isinstance(data, dict):
            return None, f"{pm} audit printed something that is not an object"
    found = {}
    for name, item in (data.get("vulnerabilities") or {}).items():
        ids = []
        for via in item.get("via") or []:
            if isinstance(via, dict):
                ids.append({"id": via.get("url") or via.get("source") or via.get("name"), "severity": via.get("severity"),
                            "title": via.get("title"), "range": via.get("range")})
        found[name] = {"severity": item.get("severity"), "range": item.get("range"), "direct": bool(item.get("isDirect")),
                       "advisories": ids, "fix": item.get("fixAvailable")}
    for _, adv in (data.get("advisories") or {}).items():
        name = adv.get("module_name")
        if not name:
            continue
        entry = found.setdefault(name, {"severity": adv.get("severity"), "range": adv.get("vulnerable_versions"), "direct": False,
                                        "advisories": [], "fix": None})
        entry["advisories"].append({"id": adv.get("url") or adv.get("github_advisory_id") or str(adv.get("id")),
                                    "severity": adv.get("severity"), "title": adv.get("title"), "range": adv.get("vulnerable_versions")})
        entry["direct"] = entry["direct"] or any(len(f.get("paths") or []) and ">" not in f["paths"][0] for f in adv.get("findings") or [])
    return found, None


def open_pull_requests(root, label):
    done, error = run([binary("gh"), "pr", "list", "--state", "open", "--label", label, "--json",
                       "number,title,body,headRefName,author,isDraft", "--limit", "100"], root)
    if done is None or done.returncode != 0:
        return None, (error or done.stderr.strip() or "gh pr list failed").splitlines()[-1]
    try:
        items = json.loads(done.stdout or "[]")
    except ValueError:
        return None, "gh pr list: not JSON"
    out = []
    for item in items:
        meta = {k.lower(): v for k, v in METADATA.findall(item.get("body") or "")}
        out.append({"number": item.get("number"), "title": item.get("title"), "branch": item.get("headRefName"),
                    "author": ((item.get("author") or {}).get("login")), "draft": item.get("isDraft"),
                    "root": meta.get("root"), "target": meta.get("target"), "driver": meta.get("driver")})
    return out, None


def policy(root, path):
    """Holds (`- react stays on 18 until 2027-01-01: why`) and decisions (`- zod: not before 2026-12-01: why`)."""
    holds, decisions = [], []
    if not path:
        return holds, decisions, None
    full = os.path.join(root, path)
    if not os.path.isfile(full):
        return holds, decisions, f"policy file {path} does not exist; the run record is the only memory"
    with open(full, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip()
            hold = HOLD.match(line)
            if hold:
                holds.append({"package": hold["pkg"], "major": int(hold["major"]), "until": hold["date"], "why": (hold["why"] or "").strip()})
                continue
            decision = DECISION.match(line)
            if decision:
                decisions.append({"package": decision["pkg"], "until": decision["date"], "why": (decision["why"] or "").strip()})
    return holds, decisions, None


# ---------- classification ----------

def iso(date):
    return date.strftime("%Y-%m-%d")


def published(stamp):
    try:
        return datetime.datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").date()
    except (TypeError, ValueError):
        return None


def releases(reg):
    """(version, date) for every stable release, newest first."""
    out = [(v, published(t)) for v, t in reg["versions"].items() if not is_prerelease(v) and published(t)]
    return sorted(out, key=lambda item: key(item[0]), reverse=True)


def line_status(installed, reg, today, dead_after_days):
    """current: the installed major is the latest. backported: behind, but the installed line had a release within the
    window. dead: behind and the installed line has been silent longer than the window."""
    stable = releases(reg)
    if not stable or not parse(installed):
        return None, {}
    latest = stable[0][0]
    major = parse(installed)[0]
    if parse(latest)[0] <= major:
        return "current", {"latest": latest}
    on_line = [(v, d) for v, d in stable if parse(v)[0] == major]
    if not on_line:
        return "dead", {"latest": latest, "last_on_line": None, "silent_days": None}
    last_version, last_date = on_line[0]
    silent = (today - last_date).days
    return ("dead" if silent > dead_after_days else "backported"), {"latest": latest, "last_on_line": last_version,
                                                                    "last_on_line_date": iso(last_date), "silent_days": silent}


def matured_target(installed, reg, today, cooling_days):
    """The newest stable version that has been published at least cooling_days, if newer than the installed one."""
    for version, date in releases(reg):
        if (today - date).days >= cooling_days:
            if parse(installed) and compare(version, installed) <= 0:
                return None, "the newest matured version is already installed"
            return version, f"newest version published {cooling_days}+ days ago ({iso(date)})"
    return None, "no version has matured yet"


def patched_target(installed, reg, ranges):
    """The smallest version above the installed one that no advisory range covers."""
    for version, _ in sorted(releases(reg), key=lambda item: key(item[0])):
        if compare(version, installed) <= 0:
            continue
        if not any(satisfies(version, r) for r in ranges if r):
            return version
    return None


def erratic(reg, today):
    recent = {parse(v)[0] for v, d in releases(reg) if (today - d).days <= 30}
    return len(recent) > 1


def config_surface(root, name, scripts):
    for pattern in CONFIG_SURFACE.get(name, []):
        if glob.glob(os.path.join(root, pattern)):
            return f"configured by {pattern}"
    for script_name, body in scripts.items():
        if re.search(r"(^|[\s&|;])" + re.escape(name.split("/")[-1]) + r"(\s|$)", body or ""):
            return f"used by the `{script_name}` script"
    return None


def source_files(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for file in files:
            if file.endswith(SOURCE_EXTENSIONS):
                yield os.path.join(base, file)


def impact(root, name, scripts=None):
    """Files importing the package through an anchored specifier, the test files among them or importing them, and
    the radius bucket. Tooling configured by a file is wide whatever imports say."""
    pattern = re.compile(r"""(?:from\s*|import\s*|require\(\s*|import\(\s*)['"]""" + re.escape(name) + r"""(?:['"]|/)""")
    importers, tests = [], set()
    for path in source_files(root):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if pattern.search(text):
            rel = os.path.relpath(path, root)
            importers.append(rel)
            if any(marker in "/" + rel for marker in TEST_MARKERS):
                tests.add(rel)
    stems = {os.path.splitext(os.path.basename(p))[0] for p in importers}
    if stems:
        relative = re.compile(r"""from\s*['"]\.{1,2}/[^'"]*?/?(""" + "|".join(re.escape(s) for s in stems) + r""")(?:\.\w+)?['"]""")
        for path in source_files(root):
            rel = os.path.relpath(path, root)
            if not any(marker in "/" + rel for marker in TEST_MARKERS) or rel in tests:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    if relative.search(fh.read()):
                        tests.add(rel)
            except OSError:
                continue
    surface = config_surface(root, name, scripts or {})
    count = len([p for p in importers if p not in tests])
    bucket = "wide" if surface or count >= 4 else RADIUS[count]
    return {"importers": sorted(importers), "tests": sorted(tests), "count": count, "radius": bucket,
            "why": surface or f"{count} importing file(s)"}


def classify(entry, reg, audit, today, settings):
    """Driver, evidence, line status and target for one package. Returns the fields to merge into the entry."""
    out = {"driver": None, "evidence": None, "line": None, "line_facts": {}, "target": None, "target_why": None,
           "erratic": erratic(reg, today), "deprecated": reg.get("deprecated")}
    installed = entry["installed"]
    out["line"], out["line_facts"] = line_status(installed, reg, today, settings["dead_line_months"] * 30)
    vulnerable = audit.get(entry["name"]) if audit else None
    if vulnerable and vulnerable["advisories"] and any(satisfies(installed, a["range"] or vulnerable["range"] or "") for a in vulnerable["advisories"]):
        ranges = [a["range"] or vulnerable["range"] for a in vulnerable["advisories"]]
        out["driver"] = "security"
        out["evidence"] = {"advisories": vulnerable["advisories"], "severity": vulnerable["severity"],
                           "reaches": "runtime" if entry["runtime"] else "dev-only"}
        out["target"] = patched_target(installed, reg, ranges)
        out["target_why"] = "minimum version outside every advisory range, whatever its age" if out["target"] else None
        if not out["target"]:
            out["failure"] = "no published version escapes the advisory ranges"
        return out
    if reg.get("deprecated"):
        out["driver"], out["evidence"] = "eol", {"deprecated": reg["deprecated"]}
    elif out["line"] == "dead":
        out["driver"], out["evidence"] = "drift-exposed", dict(out["line_facts"])
    else:
        out["driver"], out["evidence"] = "drift-safe", None
    out["target"], out["target_why"] = matured_target(installed, reg, today, settings["cooling_off_days"])
    return out


def apply_policy(entry, holds, decisions, today, peer_ranges):
    """A hold blocks a package only when its target's peer range cannot keep the held major; a live decision
    silences everything but security and eol."""
    name, target = entry["name"], entry.get("target")
    for hold in holds:
        if hold["until"] < iso(today):
            continue
        if hold["package"] == name and target and parse(target) and parse(target)[0] != hold["major"]:
            return "held", f"{name} stays on {hold['major']} until {hold['until']}" + (f": {hold['why']}" if hold["why"] else "")
        if hold["package"] != name and peer_ranges and hold["package"] in peer_ranges:
            wanted = peer_ranges[hold["package"]]
            if not any(satisfies(f"{hold['major']}.{m}.0", wanted) for m in range(0, 50)):
                return "held", (f"{name}@{target} needs {hold['package']} {wanted}, and {hold['package']} stays on "
                                f"{hold['major']} until {hold['until']}")
    if entry.get("driver") not in ("security", "eol"):
        for decision in decisions:
            if decision["package"] == name and decision["until"] >= iso(today):
                return "decided", f"not before {decision['until']}" + (f": {decision['why']}" if decision["why"] else "")
    return None, None


def reconcile(entry, pulls):
    """An open pull request for the same target means skip; an older target means supersede after the new one exists;
    a person's pull request without metadata is never touched."""
    for pr in pulls or []:
        if pr.get("root") == entry["name"]:
            if pr.get("target") == entry.get("target"):
                return "existing-pr", pr["number"]
            return "supersede", pr["number"]
    stem = re.escape(entry["name"])
    for pr in pulls or []:
        if not pr.get("root") and re.search(r"\b" + stem + r"\b", pr.get("title") or ""):
            return "overlaps-person", pr["number"]
    return None, None


def peer_conflicts(entries):
    """A candidate whose target needs a peer at a version the run will not have (the peer's own target, or its installed
    version when it is not moving) fails with the conflict, never a blind resolution. Peers outside the inventory are
    transitive and left to the install."""
    failed = False
    for entry in entries.values():
        if entry["status"] != "candidate" or not entry.get("peers"):
            continue
        for peer, wanted in entry["peers"].items():
            other = entries.get(peer)
            if other is None:
                continue
            will_be = other["target"] if other["status"] == "candidate" and other.get("target") else other["installed"]
            if will_be and not satisfies(will_be, wanted):
                moving = "its target" if will_be == other.get("target") and other["status"] == "candidate" else "installed"
                entry.update(status="failed", reason=f"peer conflict: needs {peer} {wanted}, {peer} will be {will_be} ({moving})")
                failed = True
                break
    return failed


# ---------- the run record ----------

def deps_dir(root):
    return os.path.join(contract.pothos_home(), "deps", contract.key_for(root, "deps"))


def lock_path(root):
    return os.path.join(deps_dir(root), ".lock")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def take_lock(root):
    path = lock_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                pid = int(fh.read().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if pid and alive(pid):
            return False, pid
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    return True, None


def release_lock(root):
    try:
        os.remove(lock_path(root))
    except OSError:
        pass


def record_path(root, today):
    folder = deps_dir(root)
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, iso(today))
    path, n = base + ".json", 1
    while os.path.exists(path):
        n += 1
        path = f"{base}-{n}.json"
    return path


def environment(root, pm):
    env = {"package_manager": pm}
    for tool in ("node", pm or "npm"):
        done, _ = run([binary(tool) if tool != "node" else "node", "--version"], root, timeout=30)
        env[tool] = done.stdout.strip() if done and done.returncode == 0 else None
    for lock, name in LOCKFILES:
        path = os.path.join(root, lock)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                env["lockfile"] = {"file": lock, "sha1": hashlib.sha1(fh.read()).hexdigest()}
            break
    return env


def save(path, record):
    """Write the record atomically and point `latest` (next to it) at it, so evals and the next run find it by name."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    latest = os.path.join(os.path.dirname(path), "latest")
    try:
        if os.path.islink(latest) or os.path.exists(latest):
            os.remove(latest)
        os.symlink(os.path.basename(path), latest)
    except OSError:
        pass


def settings_from(data):
    deps = data.get("deps") or {}
    return {**DEFAULTS, **{k: v for k, v in deps.items() if k in DEFAULTS}, "exclude": deps.get("exclude") or [],
            "policy": deps.get("policy"), "gates": deps.get("gates") or {}}


def gates_for(name, gates):
    return [command for pattern, command in gates.items() if re.search(pattern, name)]


def plan(root, data, only, today):
    pkg = read_json(os.path.join(root, "package.json"))
    if pkg is None:
        print("no package.json at the repository root; only npm-style repositories are known", file=sys.stderr)
        return NOTHING
    settings = settings_from(data)
    entries = inventory(root, only, settings["exclude"])
    if not entries or not any(e["selected"] and not e["excluded"] for e in entries.values()):
        print("nothing to do: no direct dependency matches", file=sys.stderr)
        return NOTHING
    ok, pid = take_lock(root)
    if not ok:
        print(f"another update-dependencies run holds the lock (pid {pid}); wait for it or run deps.py unlock", file=sys.stderr)
        return LOCKED
    try:
        return _plan(root, data, pkg, entries, settings, today)
    finally:
        release_lock(root)


def _plan(root, data, pkg, entries, settings, today):
    pm = package_manager(root)
    record = {"date": iso(today), "repository": contract.key_for(root, "deps"), "settings": settings, "environment": environment(root, pm),
              "sources": {}, "holds": [], "decisions": [], "open_pull_requests": [], "entries": {}, "status": "planned"}
    path = record_path(root, today)
    in_sync, why = lockfile_in_sync(root, pkg)
    if not in_sync:
        record["status"], record["failure"] = "failed", why
        save(path, record)
        print(path)
        print(f"run failed before any bump: {why}")
        return FAILED
    holds, decisions, note = policy(root, settings["policy"])
    record["holds"], record["decisions"] = holds, decisions
    record["sources"]["policy"] = {"path": settings["policy"], "note": note}
    audit, audit_error = advisories(root, pm)
    record["sources"]["audit"] = {"command": f"{pm} audit --json" if pm else None, "error": audit_error, "packages": sorted(audit or {})}
    pulls, gh_error = open_pull_requests(root, settings["label"])
    record["sources"]["pull_requests"] = {"label": settings["label"], "error": gh_error, "count": len(pulls or [])}
    record["open_pull_requests"] = pulls or []
    scripts = pkg.get("scripts") or {}
    failed = False
    for name, entry in entries.items():
        entry.update({"status": "candidate", "reason": None, "gates": gates_for(name, settings["gates"]), "peers": None,
                      "related_pr": None, "provenance": {"registry": f"npm view {name} time deprecated dist-tags.latest --json",
                                                          "audit": record["sources"]["audit"]["command"], "today": iso(today)}})
        if entry["excluded"]:
            entry.update(status="skipped", reason="excluded")
            continue
        if not entry["selected"]:
            entry.update(status="skipped", reason="not-selected")
            continue
        if entry["installed"] is None:
            entry.update(status="failed", reason="installed version unknown: not under node_modules")
            failed = True
            continue
        reg, error = registry(name, root)
        if reg is None:
            entry.update(status="failed", reason=f"registry data missing: {error}")
            failed = True
            continue
        if audit is None:
            entry.update(status="failed", reason=f"advisories unknown: {audit_error}")
            failed = True
            continue
        entry.update(classify(entry, reg, audit, today, settings))
        if entry.get("failure"):
            entry.update(status="failed", reason=entry.pop("failure"))
            failed = True
            continue
        if entry["target"] is None:
            entry.update(status="skipped", reason="up-to-date" if entry["line"] == "current" or "already installed" in (entry["target_why"] or "")
                         else "no-safe-target", note=entry["target_why"])
            continue
        if is_prerelease(entry["target"]) and not is_prerelease(entry["installed"]):
            entry.update(status="skipped", reason="prerelease")
            continue
        entry["peers"] = peers(name, entry["target"], root)
        entry["impact"] = impact(root, name, scripts)
        skip, note = apply_policy(entry, holds, decisions, today, entry["peers"])
        if skip:
            entry.update(status="skipped", reason=skip, note=note)
            continue
        relation, number = reconcile(entry, pulls)
        if relation == "existing-pr":
            entry.update(status="skipped", reason="existing-pr", related_pr=number)
            continue
        if relation:
            entry["related_pr"], entry["reconciliation"] = number, relation
        entry["hint"] = ("hygiene batch, wide radius: read the changelog against the imported symbols before applying"
                         if entry["driver"] == "drift-safe" and entry["impact"]["radius"] == "wide" else None)
    failed = peer_conflicts(entries) or failed
    record["entries"] = entries
    record["status"] = "planned" if not failed else "planned-with-failures"
    save(path, record)
    print(path)
    print(summary_text(record))
    return FAILED if failed else OK


# ---------- reporting ----------

def entry_line(entry):
    name = entry["name"]
    if entry["status"] == "failed":
        return f"{name}: failed, {entry['reason']}"
    if entry["status"] == "skipped":
        extra = f" ({entry['note']})" if entry.get("note") and entry["reason"] not in ("held", "decided") else ""
        if entry["reason"] == "existing-pr":
            extra = f" (#{entry['related_pr']})"
        return f"{name}: skipped, {entry['reason']}{extra}"
    reach = "" if entry.get("driver") != "security" else f" ({entry['evidence']['reaches']})"
    line = f" line {entry['line']}" if entry.get("line") else ""
    radius = f", radius {entry['impact']['radius']}" if entry.get("impact") else ""
    target = f" {entry['installed']} -> {entry['target']}" if entry.get("target") else ""
    flags = "".join([", erratic versioning" if entry.get("erratic") else "", f", supersedes #{entry['related_pr']}" if entry.get("reconciliation") == "supersede" else "",
                     f", overlaps a person's #{entry['related_pr']}" if entry.get("reconciliation") == "overlaps-person" else ""])
    pr = f" {entry['pr']}" if entry.get("pr") else ""
    note = f": {entry['note']}" if entry.get("note") else ""
    return f"{name}: {entry['status']}{pr}, {entry.get('driver')}{reach}{line}{target}{radius}{flags}{note}"


def summary_text(record):
    lines = []
    if record.get("failure"):
        lines.append(f"run failed: {record['failure']}")
    order = {d: i for i, d in enumerate(DRIVERS)}
    entries = sorted(record["entries"].values(), key=lambda e: (e["status"] in ("skipped", "failed"), order.get(e.get("driver"), 9), e["name"]))
    held = [e for e in entries if e["status"] == "skipped" and e["reason"] == "held"]
    decided = [e for e in entries if e["status"] == "skipped" and e["reason"] == "decided"]
    excluded = [e["name"] for e in entries if e["status"] == "skipped" and e["reason"] == "excluded"]
    quiet = ("held", "decided", "excluded", "not-selected")
    lines += [entry_line(e) for e in entries if not (e["status"] == "skipped" and e["reason"] in quiet)]
    if excluded:
        lines.append(f"{len(excluded)} excluded by deps.exclude: " + ", ".join(excluded))
    for hold in record.get("holds") or []:
        frozen = [e["name"] for e in held if hold["package"] in (e.get("note") or "")]
        if frozen:
            lines.append(f"hold {hold['package']} stays on {hold['major']} until {hold['until']}: keeps {', '.join(frozen)} back")
    if decided:
        lines.append(f"{len(decided)} silenced by decisions until their review date: " + ", ".join(f"{e['name']} ({e['note']})" for e in decided))
    for source, facts in (record.get("sources") or {}).items():
        if facts.get("error") or facts.get("note"):
            lines.append(f"{source}: {facts.get('error') or facts.get('note')}")
    return "\n".join(lines)


def update(path, entry_id, status, note, pr, sets):
    record = read_json(path)
    if record is None:
        print(f"no record at {path}", file=sys.stderr)
        return USAGE
    entry = record["entries"].get(entry_id)
    if entry is None:
        print(f"no entry {entry_id} in {path}", file=sys.stderr)
        return USAGE
    if status not in ENTRY_STATUSES:
        print(f"status must be one of {', '.join(ENTRY_STATUSES)}", file=sys.stderr)
        return USAGE
    if status == "verified" and str(sets.get("verify_exit", "0")) != "0":
        print("verified needs verify_exit=0: exit 4 means the run is still going, record it as in-progress", file=sys.stderr)
        return USAGE
    entry["status"] = status
    if note is not None:
        entry["note"] = note
    if pr:
        entry["pr"] = pr
    for k, v in sets.items():
        entry[k] = v
    entry.setdefault("history", []).append({"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                            "status": status, "note": note})
    save(path, record)
    print(entry_line(entry))
    return OK


def take(args, flag, many=False):
    values = []
    while flag in args:
        i = args.index(flag)
        if i + 1 >= len(args):
            raise ValueError(f"{flag} needs a value")
        values.append(args[i + 1])
        del args[i:i + 2]
        if not many:
            break
    return values if many else (values[0] if values else None)


def main(argv):
    args = list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return OK if args else USAGE
    command = args.pop(0)
    try:
        repo = os.path.abspath(take(args, "--repo") or os.getcwd())
        today_text = take(args, "--today")
        today = datetime.date.fromisoformat(today_text) if today_text else datetime.date.today()
        if command == "plan":
            only = set(take(args, "--only", many=True))
            only |= {a for a in args if not a.startswith("--")}
            root = contract.repo_root(repo)
            path = contract.locate(root)
            if not path:
                print(f"no pothos contract for this repository; run /pothos:plant (expected at {contract.contract_path(root)})", file=sys.stderr)
                return NO_CONTRACT
            return plan(root, contract.load(path), only or None, today)
        if command == "impact":
            if len(args) != 1:
                print("usage: deps.py impact PKG [--repo DIR]", file=sys.stderr)
                return USAGE
            root = contract.repo_root(repo)
            scripts = (read_json(os.path.join(root, "package.json")) or {}).get("scripts") or {}
            print(json.dumps(impact(root, args[0], scripts), indent=2))
            return OK
        if command == "update":
            status, note, pr = take(args, "--status"), take(args, "--note"), take(args, "--pr")
            sets = dict(s.split("=", 1) for s in take(args, "--set", many=True) if "=" in s)
            if len(args) != 2 or not status:
                print("usage: deps.py update RECORD ID --status STATUS [--note TEXT] [--pr URL] [--set KEY=VALUE ...]", file=sys.stderr)
                return USAGE
            return update(args[0], args[1], status, note, pr, sets)
        if command == "summary":
            if len(args) != 1:
                print("usage: deps.py summary RECORD", file=sys.stderr)
                return USAGE
            record = read_json(args[0])
            if record is None:
                print(f"no record at {args[0]}", file=sys.stderr)
                return USAGE
            print(summary_text(record))
            return OK
        if command == "unlock":
            release_lock(contract.repo_root(repo))
            print("lock removed")
            return OK
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return USAGE
    print(f"unknown command '{command}'", file=sys.stderr)
    return USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
