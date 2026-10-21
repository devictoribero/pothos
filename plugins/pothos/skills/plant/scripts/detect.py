#!/usr/bin/env python3
"""Inspect a repository and print what plant needs to draft a contract, as JSON.

Usage: detect.py [REPO_DIR]

Only reports facts found on disk, plus one bounded call to the origin remote for its default
branch when the clone does not know it. It never guesses a command that is not declared
somewhere, so the model drafting the contract cannot invent one either.
Standard library only.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared"))
import ui_check  # noqa: E402
from contract import PR_TEMPLATES  # noqa: E402

LOCKFILES = [
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("package-lock.json", "npm"),
]

# Script names grouped by role, most specific first. Matching is exact on the script name.
ROLES = {
    "aggregate": ["verify", "validate", "check", "ci", "precommit", "pre-commit"],
    "fast": ["verify:fast", "check:fast", "type-check:fast", "typecheck:fast"],
    "typecheck": ["type-check", "typecheck", "types:check", "check-types", "tsc", "types"],
    "lint": ["lint", "lint:check", "eslint"],
    "format": ["format:check", "pretty", "prettier:check", "format"],
    "test": ["test", "test:unit", "unit", "vitest", "jest"],
    "component": ["test:component", "test:components"],
    "e2e": ["e2e", "test:e2e", "e2e:smoke", "test:e2e:smoke", "cypress:run", "playwright"],
    "dev": ["dev", "start", "local:dev", "serve", "develop"],
    "dev_mocked": ["dev:mock", "dev:mocked", "local:mock", "dev:seeded", "mock"],
    "setup": ["setup", "bootstrap", "postinstall", "generate", "codegen", "db:generate", "prisma:generate"],
}

DOC_CANDIDATES = {
    "glossary": ["GLOSSARY.md", "docs/GLOSSARY.md", "docs/glossary.md", "CONTEXT.md", "docs/CONTEXT.md"],
    "decisions": ["docs/decisions", "docs/adr", "docs/adrs", "docs/architecture/decisions", "adr"],
    "specs": ["docs/specs", "specs"],
    "prd": ["docs/prd", "docs/prds", "prd"],
}


E2E_CONFIGS = {
    "cypress": ["cypress.config.ts", "cypress.config.js", "cypress.config.mjs", "cypress.json"],
    "playwright": ["playwright.config.ts", "playwright.config.js", "playwright.config.mjs"],
    "maestro": [".maestro"],
    "detox": [".detoxrc.js", ".detoxrc.json", "detox.config.js"],
}

# Mutation tools, by the config file that declares them, at the root or in a monorepo app.
MUTATION_CONFIGS = {
    "stryker": ["stryker.config.js", "stryker.config.mjs", "stryker.config.cjs", "stryker.config.json",
                "stryker.conf.js", "stryker.conf.json"],
    "cosmic-ray": ["cosmic-ray.toml", "cosmic-ray.conf"],
}
# Build files that load the PIT plugin, and the words that show it.
PIT_BUILD_FILES = {"pom.xml": re.compile(r"pitest-maven"), "build.gradle": re.compile(r"info\.solidsoft\.pitest|pitest"),
                   "build.gradle.kts": re.compile(r"info\.solidsoft\.pitest|pitest")}
STRYKER_PACKAGE = "@stryker-mutator/core"
# Section headers that configure mutmut: a table in the Python project file or a section in setup.cfg.
MUTMUT_SECTIONS = {"pyproject.toml": re.compile(r"^\[tool\.mutmut\]", re.M), "setup.cfg": re.compile(r"^\[mutmut\]", re.M)}

TRACKER_PATTERNS = {
    "jira": re.compile(r"atlassian\.net|\bjira\b", re.I),
    "linear": re.compile(r"linear\.app|\blinear\b", re.I),
}
JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b")


def run(cmd, cwd):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def run_remote(cmd, cwd):
    """The one command that leaves the disk: bounded, and never waiting for credentials at a terminal."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True, timeout=5,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def read(path):
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def find_upwards_of_depth(root, names, depth=2):
    """Relative paths of files or folders named in `names`, at most `depth` folders deep, skipping dependencies."""
    found = []
    for base, dirs, files in os.walk(root):
        rel = os.path.relpath(base, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git") and level < depth]
        for name in set(names) & (set(files) | set(dirs)):
            found.append(name if rel == "." else os.path.join(rel, name))
    return sorted(found)


def workspace_globs(root, pkg):
    globs = []
    text = read(os.path.join(root, "pnpm-workspace.yaml")) or ""
    in_packages = False
    for line in text.splitlines():
        if re.match(r"^packages:\s*$", line):
            in_packages = True
        elif in_packages and re.match(r"^\s*-\s*", line):
            globs.append(re.sub(r"^\s*-\s*", "", line).strip().strip("'\""))
        elif in_packages and line.strip() and not line.startswith(" "):
            in_packages = False
    workspaces = (pkg or {}).get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    globs += [g for g in workspaces or [] if isinstance(g, str)]
    return [g for g in globs if not g.startswith("!")]


def app_kind(manifest):
    """A hint for the screenshots question, from the app's dependencies. The user decides."""
    deps = {**(manifest.get("dependencies") or {}), **(manifest.get("devDependencies") or {})}
    if deps.keys() & {"expo", "react-native"}:
        return "mobile"
    if deps.keys() & {"next", "vite", "react-dom", "astro", "@remix-run/react", "nuxt", "@sveltejs/kit", "@angular/core"}:
        return "web"
    return "other"


def workspace_command(pm, name, rel, script):
    """A command run from the repository root that starts one workspace package's script."""
    return {"pnpm": f"pnpm --filter {name} {script}", "yarn": f"yarn workspace {name} {script}",
            "bun": f"bun run --filter {name} {script}"}.get(pm, f"npm run {script} --workspace {rel}")


def workspace_manifests(root, pkg):
    """(folder, package.json) of every workspace package."""
    found = []
    for pattern in workspace_globs(root, pkg):
        base = pattern.rstrip("/").removesuffix("/*").removesuffix("/**")
        folders = [base] if base == pattern.rstrip("/") else [
            os.path.join(base, d) for d in sorted(os.listdir(os.path.join(root, base))) if os.path.isdir(os.path.join(root, base, d))
        ] if os.path.isdir(os.path.join(root, base)) else []
        for rel in folders:
            text = read(os.path.join(root, rel, "package.json"))
            try:
                manifest = json.loads(text) if text else None
            except ValueError:
                manifest = None
            if isinstance(manifest, dict):
                found.append((rel, manifest))
    return found


def workspace_apps(root, pkg, pm):
    """Every workspace package with a package.json: its folder, name, start scripts and kind."""
    apps = []
    for rel, manifest in workspace_manifests(root, pkg):
        name = manifest.get("name") or os.path.basename(rel)
        scripts = manifest.get("scripts") or {}
        dev = [n for n in ROLES["dev_mocked"] + ROLES["dev"] if n in scripts]
        apps.append({"path": rel, "package": name, "kind": app_kind(manifest),
                     "dev_scripts": [{"script": n, "command": workspace_command(pm, name, rel, n), "body": scripts[n]} for n in dev]})
    return apps


SKIP_DIRS = {"__tests__", "__mocks__", "test-utils", "node_modules", ".git", "dist", "build", ".next", ".expo", "coverage", "storybook-static", "ios", "android", "vendor"}
COMPONENT_DIR_NAMES = {"components", "ui", "primitives", "design-system", "designsystem", "common"}
COMPONENT_EXTS = (".tsx", ".jsx", ".vue", ".svelte", ".astro")
TOKEN_FILE = re.compile(r"^(tokens?|design-tokens|theme|themes|variables|colors|palette)(\.[\w-]+)*\.(css|scss|ts|tsx|js|mjs|json)$|"
                        r"^tailwind\.config\.(js|cjs|mjs|ts)$|\.tokens\.json$", re.I)
ICON_PACKAGES = ui_check.ICON_PACKAGES
TOKEN_DIR_NAMES = {"tokens", "design-tokens", "theme", "themes"}
# A components folder below one of these belongs to one feature or route, not to the shared UI.
FEATURE_SCOPE = re.compile(r"(^|/)(features?|modules|domains|pages|routes|screens|views)/[^/]+/", re.I)
CUSTOM_PROPERTY = re.compile(r"^\s*--[\w-]+\s*:", re.M)


def declares_tokens(path):
    """A stylesheet that defines the theme: a Tailwind @theme block or at least ten custom properties."""
    text = read(path) or ""
    return "@theme" in text or len(CUSTOM_PROPERTY.findall(text)) >= 10


STORYBOOK_SCRIPTS = ["storybook", "storybook:dev", "dev:storybook", "sb"]
SOURCE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte")


def walk(root, depth):
    """(relative folder, dirs, files) up to `depth` folders deep, skipping dependencies and build output."""
    for base, dirs, files in os.walk(root):
        rel = os.path.relpath(base, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") or d == ".storybook")
        if level >= depth:
            dirs[:] = []
        yield ("" if rel == "." else rel), dirs, files


def ui_facts(root, pkg, pm):
    """Facts plant needs for the contract's ui section. Candidates only: the model and the user choose."""
    manifests = [("", pkg or {})] + (workspace_manifests(root, pkg) if pkg else [])
    folders, tokens, storybook_dirs, sources = [], [], [], []
    for rel, dirs, files in walk(root, 6):
        name = os.path.basename(rel).lower()
        if rel and name in COMPONENT_DIR_NAMES:
            count = sum(1 for _, _, fs in walk(os.path.join(root, rel), 3) for f in fs if f.endswith(COMPONENT_EXTS))
            if count:
                scoped = bool(FEATURE_SCOPE.search(rel))
                folders.append({"path": rel, "component_files": count, "feature_scoped": scoped})
        if rel and name in TOKEN_DIR_NAMES and any(f.endswith(SOURCE_EXTS + (".css", ".scss", ".json")) for _, _, fs in walk(os.path.join(root, rel), 2) for f in fs):
            tokens.append(rel)
        if os.path.basename(rel) == ".storybook":
            storybook_dirs.append(rel)
        for f in files:
            path = os.path.join(rel, f) if rel else f
            if TOKEN_FILE.search(f) or (f.endswith((".css", ".scss")) and declares_tokens(os.path.join(root, path))):
                tokens.append(path)
            if f.endswith(SOURCE_EXTS) and len(sources) < 5000:
                sources.append(path)
    declared = {}
    for rel, manifest in manifests:
        deps = {**(manifest.get("dependencies") or {}), **(manifest.get("devDependencies") or {})}
        for package in ICON_PACKAGES:
            if package in deps:
                declared.setdefault(package, []).append(rel or ".")
    imports = {package: 0 for package in declared}
    for path in sources:
        text = read(os.path.join(root, path)) or ""
        for package in declared:
            imports[package] += len(re.findall(r"""from\s+['"]""" + re.escape(package) + r"""(?:/[^'"]*)?['"]|require\(['"]""" + re.escape(package), text))
    preview = []
    for rel, manifest in manifests:
        scripts = manifest.get("scripts") or {}
        for script in STORYBOOK_SCRIPTS:
            if script in scripts:
                command = f"{runner_prefix(pm)} {script}" if not rel else workspace_command(pm, manifest.get("name") or os.path.basename(rel), rel, script)
                port = re.search(r"(?:-p|--port)[ =](\d+)", scripts[script])
                preview.append({"command": command, "body": scripts[script], "url": f"http://localhost:{port.group(1)}" if port else None})
                break
    return {
        "component_folders": sorted(folders, key=lambda f: (f["feature_scoped"], -f["component_files"])),
        "token_files": sorted(t for t in tokens if not any(t.startswith(other + "/") for other in tokens)),
        "icon_packages": [{"package": p, "declared_in": declared[p], "imports": imports[p]} for p in sorted(declared, key=lambda p: -imports[p])],
        "storybook_config": storybook_dirs,
        "preview_scripts": preview,
    }


def mutation_tools(root, pkg):
    """Mutation tools declared on disk, sorted. Only what a config file or manifest says; never a guess."""
    tools = {tool for tool, files in MUTATION_CONFIGS.items() if find_upwards_of_depth(root, files)}
    deps = {**((pkg or {}).get("dependencies") or {}), **((pkg or {}).get("devDependencies") or {})}
    if STRYKER_PACKAGE in deps:
        tools.add("stryker")
    if any(pattern.search(read(os.path.join(root, name)) or "") for name, pattern in MUTMUT_SECTIONS.items()):
        tools.add("mutmut")
    if any(pattern.search(read(os.path.join(root, name)) or "") for name, pattern in PIT_BUILD_FILES.items()):
        tools.add("pit")
    return sorted(tools)


def default_branch(root):
    head = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    if head and "/" in head:
        return head.split("/", 1)[1]
    symref = run_remote(["git", "ls-remote", "--symref", "origin", "HEAD"], root)
    match = re.search(r"ref: refs/heads/(\S+)\s+HEAD", symref or "")
    if match:
        return match.group(1)
    for name in ("main", "master"):
        if run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], root) is not None:
            return name
    current = run(["git", "symbolic-ref", "--short", "HEAD"], root)  # unborn branch in a repo with no commits
    return current if current in ("main", "master") else None


def runner_prefix(pm):
    return {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn", "bun": "bun run"}.get(pm, "npm run")


def detect(root):
    root = os.path.abspath(root)
    exists = lambda rel: os.path.exists(os.path.join(root, rel))
    report = {"root": root}

    pm = next((name for lock, name in LOCKFILES if exists(lock)), None)
    pkg_text = read(os.path.join(root, "package.json"))
    pkg = None
    if pkg_text:
        try:
            pkg = json.loads(pkg_text)
        except ValueError as exc:
            report["package_json_error"] = str(exc)
    if pkg and not pm:
        declared = str(pkg.get("packageManager", ""))
        pm = declared.split("@")[0] or "npm"
    report["package_manager"] = pm
    report["monorepo"] = bool(exists("pnpm-workspace.yaml") or (pkg and pkg.get("workspaces")))

    scripts = (pkg or {}).get("scripts", {})
    report["scripts"] = scripts
    prefix = runner_prefix(pm)
    candidates = {}
    for role, names in ROLES.items():
        found = [n for n in names if n in scripts]
        if found:
            candidates[role] = [{"script": n, "command": f"{prefix} {n}", "body": scripts[n]} for n in found]
    report["candidates"] = candidates
    # Same app started against different backends: local:dev, local:demo, start:staging...
    env_scripts = [n for n in scripts if re.match(r"^(local|dev|start|serve):[a-z][\w-]*$", n) and not re.search(r"mock|seed", n)]
    report["apps"] = workspace_apps(root, pkg, pm) if report["monorepo"] else []
    report["environment_variants"] = [{"script": n, "name": n.split(":", 1)[1], "command": f"{prefix} {n}"} for n in env_scripts]
    report["other_build_files"] = [f for f in ["Makefile", "justfile", "Taskfile.yml", "pyproject.toml", "go.mod", "Cargo.toml"] if exists(f)]

    report["agent_files"] = {
        name: {"exists": exists(name), "symlink_to": os.readlink(os.path.join(root, name)) if os.path.islink(os.path.join(root, name)) else None}
        for name in ["AGENTS.md", "CLAUDE.md"]
    }
    report["docs"] = {key: [p for p in paths if exists(p)] for key, paths in DOC_CANDIDATES.items()}
    report["pr_template"] = next((p for p in PR_TEMPLATES if exists(p)), None)
    e2e_found = {tool: find_upwards_of_depth(root, files) for tool, files in E2E_CONFIGS.items()}
    report["e2e_tools"] = [tool for tool, paths in e2e_found.items() if paths]
    report["e2e_config_paths"] = sorted(p for paths in e2e_found.values() for p in paths)
    report["mutation_tools"] = mutation_tools(root, pkg)
    report["mutation_temp_ignored"] = None

    workflows_dir = os.path.join(root, ".github", "workflows")
    ci = []
    if os.path.isdir(workflows_dir):
        for name in sorted(os.listdir(workflows_dir)):
            if name.endswith((".yml", ".yaml")):
                text = read(os.path.join(workflows_dir, name)) or ""
                positions = {}
                for script in scripts:
                    if script in ("test", "start"):  # npm test / npm start need no "run"
                        pattern = rf"(?:\brun:|&&|;)?\s*(?:npm(?:\s+run)?|pnpm(?:\s+run)?|yarn|bun\s+run)\s+{script}(\s|$|\")"
                    else:
                        pattern = rf"(?:npm\s+run|pnpm(?:\s+run)?|yarn|bun\s+run)\s+{re.escape(script)}(\s|$|\")"
                    match = re.search(pattern, text)
                    if match:
                        positions[script] = match.start()
                used = sorted(positions, key=positions.get)
                first_check = min(positions.values()) if positions else len(text)
                # Steps CI runs before its first check: installs and code generation a fresh checkout needs.
                setup = [m.group(1).strip() for m in re.finditer(r"^\s*-?\s*run:\s*(.+)$", text[:first_check], re.M)
                         if re.search(r"install|\bci\b|generate|codegen|prisma|build:types", m.group(1))]
                ci.append({"file": f".github/workflows/{name}", "scripts_used_in_order": used, "setup_steps": setup})
    report["ci"] = ci

    # Word hits only: "we do not use Jira" also matches. The model reads the files to decide.
    hint_text = "\n".join(filter(None, [read(os.path.join(root, f)) for f in ["AGENTS.md", "CLAUDE.md", "README.md"]]))
    trackers = [kind for kind, pattern in TRACKER_PATTERNS.items() if pattern.search(hint_text)]
    report["tracker_hints"] = {
        "words_found": trackers,
        "issue_keys": sorted({m for m in JIRA_KEY.findall(hint_text) if m not in {"UTF", "ISO", "RFC", "HTTP", "SHA"}})[:5],
        "git_remote": run(["git", "remote", "get-url", "origin"], root),
        "local_dir": next((d for d in [".scratch", "docs/plans"] if exists(d)), None),
    }
    report["ui"] = ui_facts(root, pkg, pm)
    report["default_branch"] = default_branch(root)

    contract_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared", "contract.py")
    path = run([sys.executable, contract_script, "path", "--repo", root], root)
    report["contract_path"] = path
    report["existing_contract"] = path if path and os.path.isfile(path) else None
    return report


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    if not os.path.isdir(target):
        print(f"not a directory: {target}", file=sys.stderr)
        sys.exit(64)
    print(json.dumps(detect(target), indent=2))
