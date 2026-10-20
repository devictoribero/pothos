#!/usr/bin/env python3
"""Score rubric criterion 12, reuse of what exists, for an eval that ran inside a fixture project.

Usage: reuse_check.py <eval-id> <project-dir> [--evals evals.json] [--json]
       reuse_check.py <fixture-dir> <project-dir> --components Button,TextField [--hooks useControllableState]
                      [--ui ui] [--hooks-dir hooks] [--json]

With an eval id, the fixture and the `reuse` entry (components and hooks the task calls for) come from
evals.json; the flags override them. Compares the agent's copy of the project with the fixture it started
from and reports:
  - the files the run added, and the fixture files it changed or removed;
  - which named components and hooks the code the run wrote imports from the shared UI and hooks
    folders, by name (`import { Button } from '…/ui'`) or through a namespace (`import * as UI`, then
    `UI.Button`). The code the run wrote is every new code file plus the lines added to a fixture file;
    tests, previews, stories and example consumers are left out, and a default import does not count;
  - raw controls (`<button`, `<input`, `<select`, `<textarea`) in that code that stand in for a
    named component;
  - second copies: a new file under the shared UI or hooks folder named like a named component or
    hook (`IconButton`, `useControllableValue`), or a new file anywhere whose name is exactly one of them.

Score: 2 when every named component and hook is imported, no raw control stands in for one and there is
no second copy; 1 when some are reused and the rest rebuilt or left out; 0 when none are reused. The
`reuse` entry names only what the task's state calls for, so a missing hook costs the score. Raw controls
inside previews and example consumers, and ARIA roles on plain elements, are left to the reviewer.
Exit 0 after scoring, 2 on a usage error (also -h).
"""
import argparse, difflib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"node_modules", ".vite-cache", ".git", "dist", "build", ".next"}
CONSUMER_DIRS = {"example", "examples", "demo", "demos", "app", "preview", "stories", "__tests__"}
TEST_FILE = re.compile(r"\.(test|spec|stories)\.[jt]sx?$")
CONSUMER_FILE = re.compile(r"\.(preview|example)\.[jt]sx?$")
IMPORT = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['\"]([^'\"]+)['\"]")
NS_IMPORT = re.compile(r"import\s+\*\s+as\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]")
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


def text_of(path):
    return read(path).decode("utf-8", "replace")


def is_code(rel):
    """A file the run wrote as part of the feature: not a test, a story, a preview or an example consumer."""
    parts = rel.split("/")
    name = parts[-1].lower()
    if not rel.endswith((".ts", ".tsx")) or rel.endswith(".d.ts") or TEST_FILE.search(rel) or CONSUMER_FILE.search(rel):
        return False
    if any(p in CONSUMER_DIRS for p in parts[:-1]):
        return False
    return not name.startswith(("preview", "example"))


def in_folder(path, folder):
    return re.search(rf"(^|/){re.escape(folder)}(/|$)", path) is not None


def imported_from(text, name, folder):
    """True when `name` is imported from a module path that has `folder` as a segment, by name or
    through a namespace import that is then used as `Alias.name`."""
    for match in IMPORT.finditer(text):
        names = [n.strip().split(" as ")[0].replace("type ", "").strip() for n in match.group(1).split(",")]
        if name in names and in_folder(match.group(2), folder):
            return True
    for match in NS_IMPORT.finditer(text):
        alias, path = match.groups()
        if in_folder(path, folder) and (path.rstrip("/").endswith("/" + name)
                                        or re.search(rf"\b{re.escape(alias)}\.{re.escape(name)}\b", text)):
            return True
    return False


def camel_words(name):
    return re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)


def added_lines(before, after):
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    return [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]


def second_copy(rel, components, hooks, ui, hooks_dir):
    parts = rel.split("/")
    base = os.path.splitext(parts[-1])[0]
    if base in components or base in hooks:
        return True
    if not any(p in (ui, hooks_dir) for p in parts[:-1]):
        return False
    if any(base == c or base.endswith(c) or base.endswith(camel_words(c)[-1]) for c in components):
        return True
    return any(camel_words(h[3:] if h.startswith("use") else h)[0] in base for h in hooks)


def resolve(a):
    """The fixture folder, components and hooks: from evals.json when the first argument is an eval id."""
    if os.path.isdir(a.target):
        return a.target, a.components, a.hooks, None
    with open(a.evals, encoding="utf-8") as fh:
        evals = {e["id"]: e for e in json.load(fh)["evals"]}
    ev = evals.get(a.target)
    if not ev:
        return None, None, None, f"no folder or eval named {a.target!r} (evals: {a.evals})"
    if not ev.get("fixture"):
        return None, None, None, f"eval {a.target!r} has no fixture"
    fixture = os.path.join(os.path.dirname(os.path.abspath(a.evals)), ev["fixture"])
    reuse = ev.get("reuse") or {}
    return fixture, a.components or ",".join(reuse.get("components") or []), a.hooks or ",".join(reuse.get("hooks") or []), None


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("target", nargs="?")
    ap.add_argument("project", nargs="?")
    ap.add_argument("--evals", default=os.path.join(HERE, "evals.json"))
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
    if a is None or not a.target or not a.project:
        print(__doc__)
        return 2
    fixture, components, hooks, error = resolve(a)
    if error:
        print(f"reuse_check.py: {error}", file=sys.stderr)
        return 2
    components = [c for c in components.split(",") if c]
    hooks = [h for h in hooks.split(",") if h]
    if not components:
        print("reuse_check.py: name at least one component (--components, or the eval's `reuse.components`)", file=sys.stderr)
        return 2
    if not os.path.isdir(fixture) or not os.path.isdir(a.project):
        print("reuse_check.py: fixture and project must be folders", file=sys.stderr)
        return 2

    fixture_files, project_files = files(fixture), files(a.project)
    new = sorted(project_files - fixture_files)
    removed = sorted(fixture_files - project_files)
    changed = sorted(f for f in fixture_files & project_files
                     if read(os.path.join(fixture, f)) != read(os.path.join(a.project, f)))
    code = [f for f in new if is_code(f)]
    changed_code = [f for f in changed if is_code(f)]
    pieces = [text_of(os.path.join(a.project, f)) for f in code]
    for f in changed_code:
        pieces.append("\n".join(added_lines(text_of(os.path.join(fixture, f)), text_of(os.path.join(a.project, f)))))
    text = "\n".join(pieces)

    uses = {c: imported_from(text, c, a.ui) for c in components}
    hook_uses = {h: imported_from(text, h, a.hooks_dir) for h in hooks}
    raw = {}
    for tag, keys in RAW_TAGS.items():
        if any(key in c for c in components for key in keys):
            count = len(re.findall(rf"<{tag}\b", text))
            if count:
                raw[tag] = count
    copies = [f for f in new if second_copy(f, components, hooks, a.ui, a.hooks_dir)]

    reused = sum(uses.values()) + sum(hook_uses.values())
    wanted = len(components) + len(hooks)
    if reused == wanted and not raw and not copies:
        score = 2
    elif reused:
        score = 1
    else:
        score = 0

    result = dict(score=score, components=uses, hooks=hook_uses, raw_controls=raw, second_copies=copies,
                  code_files=code, changed_code_files=changed_code, new_files=new,
                  changed_fixture_files=changed, removed_fixture_files=removed)
    if a.json:
        print(json.dumps(result, indent=1))
        return 0
    print(f"Reuse: {score}")
    for c, used in uses.items():
        print(f"  {c}: {'imported from ' + a.ui if used else 'not imported from ' + a.ui}")
    for h, used in hook_uses.items():
        print(f"  {h}: {'imported from ' + a.hooks_dir if used else 'not imported from ' + a.hooks_dir}")
    for tag, count in raw.items():
        print(f"  raw <{tag}>: {count} in the code the run wrote")
    for f in copies:
        print(f"  second copy: {f}")
    print(f"New files: {len(new)}" + (f" (scored: {', '.join(code)})" if code else ""))
    for f in changed:
        print(f"  changed fixture file: {f}" + (" (added lines scored)" if f in changed_code else ""))
    for f in removed:
        print(f"  removed fixture file: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
