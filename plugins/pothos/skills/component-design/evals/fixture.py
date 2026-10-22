#!/usr/bin/env python3
"""Prepare a run of an eval that has a fixture.

Usage: fixture.py <eval-id> <dest> [--evals evals.json]

Copies the eval's fixture project to <dest>, which must not exist yet, links the cached toolchain's
node_modules into it package by package (scripts/toolchain.sh installs the toolchain on first use;
COMPONENT_DESIGN_TOOLCHAIN overrides where it lives) and prints the eval's prompt with {project}
replaced by the copy's absolute path. Give that prompt to a fresh agent. Afterwards, score criterion 12
with `reuse_check.py <eval-id> <dest>`; the exact command is printed on stderr.
Exit 2 on a usage error (also -h), 1 when the toolchain cannot be installed or lacks a package the
fixture needs (the copy is removed, since its prompt promises a project that runs).
"""
import argparse, json, os, shlex, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLCHAIN = os.path.join(os.path.dirname(HERE), "scripts", "toolchain.sh")


def link_toolchain(toolchain, dest):
    source = os.path.join(toolchain, "node_modules")
    target = os.path.join(dest, "node_modules")
    os.makedirs(target)
    for name in os.listdir(source):  # packages, scopes and .bin
        os.symlink(os.path.join(source, name), os.path.join(target, name))


def missing_dependencies(dest):
    manifest = os.path.join(dest, "package.json")
    if not os.path.isfile(manifest):
        return []
    with open(manifest, encoding="utf-8") as fh:
        pkg = json.load(fh)
    wanted = list(pkg.get("dependencies") or {}) + list(pkg.get("devDependencies") or {})
    return [d for d in wanted if not os.path.exists(os.path.join(dest, "node_modules", d))]


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("eval_id", nargs="?")
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--evals", default=os.path.join(HERE, "evals.json"))
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 2
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        a = None
    if a is None or not a.eval_id or not a.dest:
        print(__doc__)
        return 2
    with open(a.evals, encoding="utf-8") as fh:
        evals = {e["id"]: e for e in json.load(fh)["evals"]}
    ev = evals.get(a.eval_id)
    if not ev:
        print(f"fixture.py: no eval named {a.eval_id!r} in {a.evals}", file=sys.stderr)
        return 2
    if not ev.get("fixture"):
        print(f"fixture.py: eval {a.eval_id!r} has no fixture", file=sys.stderr)
        return 2
    fixture = os.path.join(os.path.dirname(os.path.abspath(a.evals)), ev["fixture"])
    dest = os.path.abspath(a.dest)
    if os.path.exists(dest):
        print(f"fixture.py: {dest} exists; give a folder that does not", file=sys.stderr)
        return 2
    try:
        toolchain = subprocess.run(["bash", TOOLCHAIN], capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError as error:
        print(f"fixture.py: toolchain.sh failed:\n{error.stderr}", file=sys.stderr)
        return 1
    shutil.copytree(fixture, dest, ignore=shutil.ignore_patterns("node_modules", ".vite-cache"))
    link_toolchain(toolchain, dest)
    missing = missing_dependencies(dest)
    if missing:
        shutil.rmtree(dest)
        print(f"fixture.py: the toolchain at {toolchain} lacks {', '.join(missing)}; add them to scripts/toolchain.sh "
              "(it reinstalls when its package list changes) and run again", file=sys.stderr)
        return 1
    reuse = ev.get("reuse") or {}
    if reuse.get("components"):
        command = [os.path.join(HERE, "reuse_check.py"), a.eval_id, dest]
        if os.path.abspath(a.evals) != os.path.join(HERE, "evals.json"):
            command += ["--evals", os.path.abspath(a.evals)]
        print(f"Project ready at {dest}. Score criterion 12 afterwards with:\n  {shlex.join(command)}", file=sys.stderr)
    else:
        print(f"Project ready at {dest}. Eval {a.eval_id!r} names no `reuse.components`, so criterion 12 has "
              "nothing to score; add them to evals.json.", file=sys.stderr)
    print(ev["prompt"].replace("{project}", dest))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
