#!/usr/bin/env python3
"""Pick the repository's fast check: the command a session runs after every coherent edit.

The command lives in the repository; this script only finds it, in this order:
  1. a `check:fast` script in the root package.json (run with the repository's package manager);
  2. the contract's `verify.fast`;
  3. a fallback per package: its lint on the changed files, its unit tests (`--findRelatedTests` when the
     runner is jest) and its type-check, all three even after one fails.
A command the repository's CLAUDE.md names wins over all of these; the session reads CLAUDE.md itself.

Usage: fast_check.py [DIR]   prints the pick as JSON. The SessionStart hook turns it into context.
Standard library only.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract  # noqa: E402

LOCKFILES = [("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun"),
             ("package-lock.json", "npm")]
RUNNER = {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn", "bun": "bun run"}
FAST_SCRIPT = "check:fast"
LINT = ("lint", "lint:check", "eslint")
UNIT = ("test:unit", "test")
TYPECHECK = ("type-check", "typecheck", "types:check", "check-types", "tsc")


def read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def package_manager(root, pkg):
    for lock, name in LOCKFILES:
        if os.path.exists(os.path.join(root, lock)):
            return name
    declared = (pkg or {}).get("packageManager")
    if isinstance(declared, str) and declared:
        return declared.split("@")[0]
    return "pnpm" if os.path.exists(os.path.join(root, "pnpm-workspace.yaml")) else "npm"


def workspace_globs(root, pkg):
    globs = []
    try:
        with open(os.path.join(root, "pnpm-workspace.yaml"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    in_packages = False
    for line in lines:
        if line.rstrip() == "packages:":
            in_packages = True
        elif in_packages and line.lstrip().startswith("- "):
            globs.append(line.lstrip()[2:].strip().strip("'\""))
        elif in_packages and line.strip() and not line.startswith(" "):
            in_packages = False
    workspaces = (pkg or {}).get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    globs += [g for g in workspaces or [] if isinstance(g, str)]
    return [g for g in globs if not g.startswith("!")]


def workspace_manifests(root, pkg):
    """(relative folder, package.json) of every workspace package, root first."""
    found = [("", pkg or {})]
    for pattern in workspace_globs(root, pkg):
        pattern = pattern.rstrip("/")
        base = pattern.removesuffix("/*").removesuffix("/**")
        if base == pattern:
            folders = [base]
        elif os.path.isdir(os.path.join(root, base)):
            folders = [os.path.join(base, d) for d in sorted(os.listdir(os.path.join(root, base)))
                       if os.path.isdir(os.path.join(root, base, d))]
        else:
            folders = []
        for rel in folders:
            manifest = read_json(os.path.join(root, rel, "package.json"))
            if manifest and rel not in [r for r, _ in found]:
                found.append((rel, manifest))
    return found


def script_command(pm, rel, name, script):
    """How to run one package's script from the repository root."""
    if not rel:
        return f"{RUNNER.get(pm, 'npm run')} {script}"
    return {"pnpm": f"pnpm --filter {name} {script}", "yarn": f"yarn workspace {name} {script}",
            "bun": f"bun run --filter {name} {script}"}.get(pm, f"npm run {script} --workspace {rel}")


def uses_jest(manifest, script):
    deps = {**(manifest.get("dependencies") or {}), **(manifest.get("devDependencies") or {})}
    return "jest" in (manifest.get("scripts") or {}).get(script, "") or "jest" in deps


def fallback_steps(root, pkg, pm):
    steps = []
    for rel, manifest in workspace_manifests(root, pkg):
        scripts = manifest.get("scripts") or {}
        lint = next((s for s in LINT if s in scripts), None)
        unit = next((s for s in UNIT if s in scripts), None)
        typecheck = next((s for s in TYPECHECK if s in scripts), None)
        if not (lint or unit or typecheck):
            continue
        name = manifest.get("name") or os.path.basename(rel) or "root"
        command = lambda script: script_command(pm, rel, name, script) if script else None
        steps.append({"path": rel or ".", "name": name, "lint": command(lint), "unit": command(unit),
                      "jest": bool(unit and uses_jest(manifest, unit)), "typecheck": command(typecheck),
                      "scripts": [lint, unit, typecheck]})
    return steps


def discover(root, data):
    """The pick: `command` and `why`, or `fallback` steps per package, plus `drift` when the contract disagrees."""
    pkg = read_json(os.path.join(root, "package.json"))
    scripts = (pkg or {}).get("scripts") or {}
    pm = package_manager(root, pkg)
    contract_fast = ((data or {}).get("verify") or {}).get("fast")
    if FAST_SCRIPT in scripts:
        command = f"{RUNNER.get(pm, 'npm run')} {FAST_SCRIPT}"
        return {"command": command, "source": "script", "why": f"the root package.json declares `{FAST_SCRIPT}`",
                "drift": contract_fast if contract_fast and contract_fast != command else None, "fallback": []}
    if contract_fast:
        return {"command": contract_fast, "source": "contract", "why": "the contract's `verify.fast` names it",
                "drift": None, "fallback": []}
    steps = fallback_steps(root, pkg, pm)
    return {"command": None, "source": "fallback" if steps else "none", "why": None, "drift": None, "fallback": steps}


def step_line(paths, step):
    """One line for every package that shares this step's script names: the command is shown for the first."""
    parts = []
    if step["lint"]:
        parts.append(f"`{step['lint']} -- <files>`")
    if step["unit"]:
        parts.append(f"`{step['unit']} -- --findRelatedTests <files>` (jest)" if step["jest"]
                     else f"`{step['unit']}` (not jest: the package's unit suite)")
    if step["typecheck"]:
        parts.append(f"`{step['typecheck']}`")
    where = ", ".join(f"`{p}`" for p in paths)
    alike = f" (shown for `{paths[0]}`)" if len(paths) > 1 else ""
    return f"- {where}{alike}: " + "; ".join(parts)


def fallback_lines(steps):
    """The fallback as context: one line per shape of package, run for each package that holds a changed code file."""
    shape = lambda s: (tuple(s.get("scripts") or (s["lint"], s["unit"], s["typecheck"])), s["jest"])
    groups = []
    for step in steps:
        for paths, first in groups:
            if shape(first) == shape(step):
                paths.append(step["path"])
                break
        else:
            groups.append(([step["path"]], step))
    return (["Per package with a changed code file, all of these even after one fails:"]
            + [step_line(paths, first) for paths, first in groups])


def main(argv):
    root = contract.repo_root(argv[0] if argv else os.getcwd())
    path = contract.locate(root)
    data = contract.load(path) if path else {}
    print(json.dumps(discover(root, data), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
