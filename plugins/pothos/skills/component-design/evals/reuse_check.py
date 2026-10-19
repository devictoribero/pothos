#!/usr/bin/env python3
"""Score rubric criterion 12, reuse of what exists, for an eval that ran inside a fixture project.

Usage: reuse_check.py <fixture-dir> <project-dir> --components Button,TextField [--hooks useControllableState]
                      [--ui ui] [--hooks-dir hooks] [--json]

Compares the agent's copy of the project with the fixture it started from and reports:
  - the files the run added, and the fixture files it changed or removed;
  - which named components the new code imports by name (`import { Button } from '…/ui'`) from the
    shared UI folder, and which named hooks from the hooks folder; tests, previews and example
    consumers are left out, and a default or namespace import does not count;
  - raw controls (`<button`, `<input`, `<select`, `<textarea`) in that code that stand in for a
    named component;
  - second copies: a new file under the shared UI or hooks folder named like a named component or
    hook, or a new file anywhere whose name is exactly one of them.

Score: 2 when every named component is imported, no raw control stands in for one and there is no
second copy; 1 when some components are reused and the rest rebuilt; 0 when none are reused. Hooks
are reported for the reviewer, since a run needs them only where its state calls for them, but a
second copy of one counts against the score. Exit 0 after scoring, 2 on a usage error (also -h).
"""
import argparse, json, os, re, sys

SKIP_DIRS = {"node_modules", ".vite-cache", ".git", "dist", "build", ".next"}
CONSUMER_DIRS = {"example", "examples", "demo", "demos", "app", "preview", "stories", "__tests__"}
TEST_FILE = re.compile(r"\.(test|spec|stories)\.[jt]sx?$")
IMPORT = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['\"]([^'\"]+)['\"]")
RAW_TAGS = {"button": ("Button",), "input": ("Field", "Input", "Checkbox", "Radio", "Switch"),
            "select": ("Select",), "textarea": ("TextArea", "Textarea")}


def files(root):
    out = set()
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            out.add(os.path.relpath(os.path.join(base, name), root).replace("\\", "/"))
    return out


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def is_code(rel):
    parts = rel.split("/")
    if not rel.endswith((".ts", ".tsx")) or rel.endswith(".d.ts") or TEST_FILE.search(rel):
        return False
    if any(p in CONSUMER_DIRS for p in parts[:-1]):
        return False
    name = parts[-1].lower()
    return "preview" not in name and "example" not in name


def imported_from(text, name, folder):
    """True when `name` is imported from a module path that has `folder` as a segment."""
    for match in IMPORT.finditer(text):
        names = [n.strip().split(" as ")[0].replace("type ", "").strip() for n in match.group(1).split(",")]
        if name in names and re.search(rf"(^|/){re.escape(folder)}(/|$)", match.group(2)):
            return True
    return False


def camel_words(name):
    return re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("fixture", nargs="?")
    ap.add_argument("project", nargs="?")
    ap.add_argument("--components", default="")
    ap.add_argument("--hooks", default="")
    ap.add_argument("--ui", default="ui")
    ap.add_argument("--hooks-dir", default="hooks")
    ap.add_argument("--json", action="store_true")
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 2
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        a = None
    if a is None or not a.fixture or not a.project:
        print(__doc__)
        return 2
    components = [c for c in a.components.split(",") if c]
    hooks = [h for h in a.hooks.split(",") if h]
    if not components:
        print("reuse_check.py: --components names at least one component", file=sys.stderr)
        return 2
    if not os.path.isdir(a.fixture) or not os.path.isdir(a.project):
        print("reuse_check.py: fixture and project must be folders", file=sys.stderr)
        return 2

    fixture, project = files(a.fixture), files(a.project)
    new = sorted(project - fixture)
    removed = sorted(fixture - project)
    changed = sorted(f for f in fixture & project
                     if read(os.path.join(a.fixture, f)) != read(os.path.join(a.project, f)))
    code = [f for f in new if is_code(f)]
    text = "\n".join(read(os.path.join(a.project, f)).decode("utf-8", "replace") for f in code)

    uses = {c: imported_from(text, c, a.ui) for c in components}
    hook_uses = {h: imported_from(text, h, a.hooks_dir) for h in hooks}
    raw = {}
    for tag, keys in RAW_TAGS.items():
        if any(key in c for c in components for key in keys):
            count = len(re.findall(rf"<{tag}\b", text))
            if count:
                raw[tag] = count
    tokens = set()
    for c in components:
        tokens.update((c, camel_words(c)[-1]))
    for h in hooks:
        bare = h[3:] if h.startswith("use") else h
        tokens.update((bare, camel_words(bare)[0]))
    copies = []
    for f in new:
        parts = f.split("/")
        base = os.path.splitext(parts[-1])[0]
        in_shared = any(p in (a.ui, a.hooks_dir) for p in parts[:-1])
        if (in_shared and any(t in base for t in tokens)) or base in components or base in hooks:
            copies.append(f)

    reused = sum(uses.values())
    if reused == len(components) and not raw and not copies:
        score = 2
    elif reused:
        score = 1
    else:
        score = 0

    result = dict(score=score, components=uses, hooks=hook_uses, raw_controls=raw, second_copies=copies,
                  code_files=code, new_files=new, changed_fixture_files=changed, removed_fixture_files=removed)
    if a.json:
        print(json.dumps(result, indent=1))
        return 0
    print(f"Reuse: {score}")
    for c, used in uses.items():
        print(f"  {c}: {'imported from ' + a.ui if used else 'not imported from ' + a.ui}")
    for h, used in hook_uses.items():
        print(f"  {h}: {'imported from ' + a.hooks_dir if used else 'not used (fine where no state calls for it)'}")
    for tag, count in raw.items():
        print(f"  raw <{tag}>: {count} in new feature code")
    for f in copies:
        print(f"  second copy: {f}")
    print(f"New files: {len(new)}" + (f" (scored: {', '.join(code)})" if code else ""))
    for f in changed:
        print(f"  changed fixture file: {f}")
    for f in removed:
        print(f"  removed fixture file: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
