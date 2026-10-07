#!/usr/bin/env python3
"""Inspect a repository and print what onboard needs to draft a contract, as JSON.

Usage: detect.py [REPO_DIR]

Only reports facts found on disk. It never guesses a command that is not declared
somewhere, so the model drafting the contract cannot invent one either.
Standard library only.
"""
import json
import os
import re
import subprocess
import sys

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
}

DOC_CANDIDATES = {
    "context": ["CONTEXT.md", "docs/CONTEXT.md", "docs/glossary.md", "GLOSSARY.md"],
    "decisions": ["docs/decisions", "docs/adr", "docs/adrs", "docs/architecture/decisions", "adr"],
    "specs": ["docs/specs", "specs"],
    "prd": ["docs/prd", "docs/prds", "prd"],
}

PR_TEMPLATES = [
    ".github/pull_request_template.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/pull_request_template.md",
    "pull_request_template.md",
]

E2E_CONFIGS = {
    "cypress": ["cypress.config.ts", "cypress.config.js", "cypress.config.mjs", "cypress.json"],
    "playwright": ["playwright.config.ts", "playwright.config.js", "playwright.config.mjs"],
    "maestro": [".maestro"],
    "detox": [".detoxrc.js", ".detoxrc.json", "detox.config.js"],
}

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


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def runner_prefix(pm):
    return {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn", "bun": "bun run"}.get(pm, "npm run")


def detect(root):
    root = os.path.abspath(root)
    exists = lambda rel: os.path.exists(os.path.join(root, rel))
    report = {"root": root}

    pm = next((name for lock, name in LOCKFILES if exists(lock)), None)
    pkg_text = read(os.path.join(root, "package.json"))
    pkg = json.loads(pkg_text) if pkg_text else None
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
    report["other_build_files"] = [f for f in ["Makefile", "justfile", "Taskfile.yml", "pyproject.toml", "go.mod", "Cargo.toml"] if exists(f)]

    report["agent_files"] = {
        name: {"exists": exists(name), "symlink_to": os.readlink(os.path.join(root, name)) if os.path.islink(os.path.join(root, name)) else None}
        for name in ["AGENTS.md", "CLAUDE.md"]
    }
    report["docs"] = {key: [p for p in paths if exists(p)] for key, paths in DOC_CANDIDATES.items()}
    report["pr_template"] = next((p for p in PR_TEMPLATES if exists(p)), None)
    report["e2e_tools"] = [tool for tool, files in E2E_CONFIGS.items() if any(exists(f) for f in files)]

    workflows_dir = os.path.join(root, ".github", "workflows")
    ci = []
    if os.path.isdir(workflows_dir):
        for name in sorted(os.listdir(workflows_dir)):
            if name.endswith((".yml", ".yaml")):
                text = read(os.path.join(workflows_dir, name)) or ""
                positions = {}
                for script in scripts:
                    match = re.search(rf"(run|yarn|pnpm|npm run|bun run)\s+{re.escape(script)}(\s|$|\")", text)
                    if match:
                        positions[script] = match.start()
                used = sorted(positions, key=positions.get)
                ci.append({"file": f".github/workflows/{name}", "scripts_used_in_order": used})
    report["ci"] = ci

    # Word hits only: "we do not use Jira" also matches. The model reads the files to decide.
    hint_text = "\n".join(filter(None, [read(os.path.join(root, f)) for f in ["AGENTS.md", "CLAUDE.md", "README.md"]]))
    trackers = [kind for kind, pattern in TRACKER_PATTERNS.items() if pattern.search(hint_text)]
    report["tracker_hints"] = {
        "words_found": trackers,
        "issue_keys": sorted({m for m in JIRA_KEY.findall(hint_text) if m not in {"UTF", "ISO", "RFC", "HTTP", "SHA"}})[:5],
        "git_remote": run(["git", "remote", "get-url", "origin"], root),
    }
    head = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    report["default_branch"] = head.split("/", 1)[1] if head and "/" in head else run(["git", "branch", "--show-current"], root)

    contract = os.path.join(root, ".agents", "contract.json")
    report["existing_contract"] = ".agents/contract.json" if os.path.isfile(contract) else None
    return report


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    if not os.path.isdir(target):
        print(f"not a directory: {target}", file=sys.stderr)
        sys.exit(64)
    print(json.dumps(detect(target), indent=2))
