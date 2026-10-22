#!/usr/bin/env python3
"""Score rubric criterion 12, reuse of what exists, for an eval that ran inside a fixture project.

Usage: reuse_check.py <eval-id> <project-dir> [--evals evals.json] [--json]
       reuse_check.py <fixture-dir> <project-dir> --components Button,TextField [--hooks useControllableState]
                      [--ui src/ui] [--hooks-dir src/hooks] [--json]

With an eval id, the fixture and the `reuse` entry (components and hooks the task calls for, and optionally
`ui` and `hooks_dir`, the shared folders from the project root; `src/ui` and `src/hooks` otherwise) come from
evals.json; the flags override them. A shared folder is matched from the project root, so a feature's own
`ui/` subfolder is not the shared one. Compares the agent's copy of the project with the fixture it started
from and reports:
  - the files the run added, and the fixture files it changed or removed;
  - which named components and hooks the code the run wrote uses, file by file: a component counts when
    one file imports it from the shared UI folder (by name, `import { Button } from '…/ui'`, or through a
    namespace, `import * as UI` then `<UI.Button>`) and renders it; a hook counts when one file imports it
    from the shared hooks folder and calls it. A relative import is resolved against the importing file, so
    `'../Button/Button'` from inside the shared folder counts. The code the run wrote is every new code
    file plus the code added to a fixture file, compared token by token so a reformat adds nothing however
    the lines are split;
    tests, previews, stories and example consumers are left out, the last by folder (`examples/`, `demo/`,
    `preview/`), by prefix (`preview*`, `example*`) or by suffix (`.example.tsx`, `*Example.tsx`, `*Demo.tsx`,
    `*Usage.tsx`), never by substring, so `ProjectNamePreview.tsx` is code; comments and string contents are
    ignored (an apostrophe inside a word, `Couldn't`, is not a quote), and a default import does not count;
  - raw controls (`<button`, `<input`, `<select`, `<textarea`) in that code that stand in for a named
    component, outside the shared UI folder (an additive change to a primitive touches its own element);
  - second copies: a new file under the shared UI or hooks folder named like a named component or
    hook (`IconButton`, `useControllableValue`), or a new file anywhere whose name is exactly one of them.

Score: 2 when every named component and hook is used, no raw control stands in for one and there is no
second copy; 1 when some are reused and the rest rebuilt or left out; 0 when none are reused. A run that
wrote no code the script scores (only tests, previews or files it skips) scores 0 and says so on stderr.
A hook or second-copy finding is a fact for the reviewer to confirm (rubric, criterion 12); raw controls
inside previews and example consumers, and ARIA roles on plain elements, are left to the reviewer too.
Exit 0 after scoring, 2 on a usage error (also -h).
"""
import argparse, difflib, json, os, posixpath, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"node_modules", ".vite-cache", ".git", "dist", "build", ".next"}
CONSUMER_DIRS = {"example", "examples", "demo", "demos", "preview", "previews", "stories", "__tests__"}
TEST_FILE = re.compile(r"\.(test|spec|stories)\.[jt]sx?$")
CONSUMER_FILE = re.compile(r"(\.(preview|example)|(^|/|[a-z0-9])(Example|Demo|Usage))\.[jt]sx?$")
TOKEN = re.compile(r"\w+|[^\w\s]")
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


def strip_noise(text, strings=True):
    """The text without comments, and without the contents of string and template literals when `strings`
    (import specifiers stay readable when it is False). A quote closes at the end of its line, so an
    apostrophe in JSX text costs at most that line."""
    out, i, n = [], 0, len(text)
    while i < n:
        c, nxt = text[i], text[i + 1:i + 2]
        if c == "/" and nxt == "/":
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif c == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif c in "'\"`" and not (c == "'" and i and (text[i - 1].isalnum() or text[i - 1] == "_")):
            end = i + 1
            while end < n and text[end] != c and (c == "`" or text[end] != "\n"):
                end += 2 if text[end] == "\\" else 1
            out.append(c + ("" if strings else text[i + 1:end]) + c)
            i = end + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


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
    """Whether `path` (from the project root) is `folder` or lies under it. A path that starts with `/` came
    from an aliased import (`@/ui`, `~/ui`) and is compared against the folder without its first segment
    (`src/ui` → `ui`), since an alias usually maps to `src/`."""
    if path.startswith("/"):
        path, folder = path[1:], folder.split("/", 1)[-1]
    return path == folder or path.startswith(folder + "/")


def module_path(specifier, importer):
    """Where an import points: a path from the project root for a relative specifier; `/`-prefixed for an
    aliased one (`@/ui`, `~/ui`, `@ui` → `/ui`); a package specifier as it is, which no project folder matches."""
    if specifier.startswith("."):
        return posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
    if specifier.startswith(("@/", "~/", "~")) or (specifier.startswith("@") and "/" not in specifier):
        return "/" + specifier.lstrip("@~/")
    return specifier


def local_names(text, name, folder, importer):
    """The identifiers `name` is bound to in this file when imported from a module under `folder`: its own
    name or an alias for a named import, `Alias.name` for a namespace import."""
    names = set()
    for match in IMPORT.finditer(text):
        if not in_folder(module_path(match.group(2), importer), folder):
            continue
        for item in match.group(1).split(","):
            item = item.strip()
            if item.startswith("type "):
                continue
            imported, _, alias = item.partition(" as ")
            if imported.strip() == name:
                names.add((alias or imported).strip())
    for match in NS_IMPORT.finditer(text):
        alias, specifier = match.groups()
        if in_folder(module_path(specifier, importer), folder):
            names.add(f"{alias}.{name}")
    return names


def spaced(name):
    """`name` as a pattern that tolerates the spaces token-joined code puts around dots."""
    return r"\s*\.\s*".join(re.escape(part) for part in name.split("."))


def renders(text, local):
    return re.search(rf"<\s*{spaced(local)}(?![\w.])", text) is not None


def calls(text, local):
    return re.search(rf"(?<![\w.]){spaced(local)}\s*\(", text) is not None


def camel_words(name):
    return re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)


def added_code(before, after):
    """The code `after` has that `before` had not, as tokens joined by spaces, one line per inserted run.
    Comments and strings are stripped first, then the two token sequences are compared, so neither
    indentation nor where a line breaks changes what counts: a reformat adds nothing, and a `<Button …>`
    spread over five lines is one insertion."""
    old, new = TOKEN.findall(strip_noise(before)), TOKEN.findall(strip_noise(after))
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return "\n".join(" ".join(new[j1:j2]) for tag, _, _, j1, j2 in matcher.get_opcodes() if tag in ("insert", "replace"))


def second_copy(rel, components, hooks, ui, hooks_dir):
    parts = rel.split("/")
    base = os.path.splitext(parts[-1])[0]
    if base in components or base in hooks:
        return True
    if not (in_folder(rel, ui) or in_folder(rel, hooks_dir)):
        return False
    if any(base == c or base.endswith(c) or base.endswith(camel_words(c)[-1]) for c in components):
        return True
    return any(camel_words(h[3:] if h.startswith("use") else h)[0] in base for h in hooks)


def resolve(a):
    """The fixture folder, components and hooks: from evals.json when the first argument is an eval id."""
    if os.path.isdir(a.target):
        return a.target, a.components, a.hooks, None, a.ui or "src/ui", a.hooks_dir or "src/hooks"
    with open(a.evals, encoding="utf-8") as fh:
        evals = {e["id"]: e for e in json.load(fh)["evals"]}
    ev = evals.get(a.target)
    if not ev:
        return None, None, None, f"no folder or eval named {a.target!r} (evals: {a.evals})", None, None
    if not ev.get("fixture"):
        return None, None, None, f"eval {a.target!r} has no fixture", None, None
    fixture = os.path.join(os.path.dirname(os.path.abspath(a.evals)), ev["fixture"])
    reuse = ev.get("reuse") or {}
    return (fixture, a.components or ",".join(reuse.get("components") or []), a.hooks or ",".join(reuse.get("hooks") or []),
            None, a.ui or reuse.get("ui") or "src/ui", a.hooks_dir or reuse.get("hooks_dir") or "src/hooks")


def score_file(rel, whole, written, components, hooks, ui, hooks_dir):
    """What one file reuses: imports read from the whole file (a fixture file may already import the
    primitive), renders and calls read from the code the run wrote in it."""
    imports = strip_noise(whole, strings=False)
    code = strip_noise(written)
    used = {c for c in components if any(renders(code, local) for local in local_names(imports, c, ui, rel))}
    hooks_used = {h for h in hooks if any(calls(code, local) for local in local_names(imports, h, hooks_dir, rel))}
    raw = {}
    if not in_folder(rel, ui):
        for tag, keys in RAW_TAGS.items():
            if any(key in c for c in components for key in keys):
                count = len(re.findall(rf"<\s*{tag}\b", code))
                if count:
                    raw[tag] = count
    return used, hooks_used, raw


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("target", nargs="?")
    ap.add_argument("project", nargs="?")
    ap.add_argument("--evals", default=os.path.join(HERE, "evals.json"))
    ap.add_argument("--components", default="")
    ap.add_argument("--hooks", default="")
    ap.add_argument("--ui", default="")
    ap.add_argument("--hooks-dir", default="")
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
    fixture, components, hooks, error, ui, hooks_dir = resolve(a)
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
    changed_code = []
    uses = {c: [] for c in components}
    hook_uses = {h: [] for h in hooks}
    raw = {}
    for rel in code + [f for f in changed if is_code(f)]:
        whole = text_of(os.path.join(a.project, rel))
        if rel in code:
            written = whole
        else:
            written = added_code(text_of(os.path.join(fixture, rel)), whole)
            if not written.strip():
                continue  # a reformat, or a change in comments, strings or whitespace only
            changed_code.append(rel)
        used, hooks_used, raw_here = score_file(rel, whole, written, components, hooks, ui, hooks_dir)
        for c in used:
            uses[c].append(rel)
        for h in hooks_used:
            hook_uses[h].append(rel)
        for tag, count in raw_here.items():
            raw[tag] = raw.get(tag, 0) + count
    copies = [f for f in new if second_copy(f, components, hooks, ui, hooks_dir)]
    scored = bool(code or changed_code)

    reused = sum(1 for v in uses.values() if v) + sum(1 for v in hook_uses.values() if v)
    wanted = len(components) + len(hooks)
    if reused == wanted and not raw and not copies:
        score = 2
    elif reused:
        score = 1
    else:
        score = 0
    if not scored:
        print("reuse_check.py: no code to score: the run wrote only tests, previews, examples or files outside "
              ".ts/.tsx; check new_files before trusting the 0", file=sys.stderr)

    result = dict(score=score, scored=scored,
                  components={c: bool(v) for c, v in uses.items()}, hooks={h: bool(v) for h, v in hook_uses.items()},
                  used_in={**{c: v for c, v in uses.items() if v}, **{h: v for h, v in hook_uses.items() if v}},
                  raw_controls=raw, second_copies=copies, code_files=code, changed_code_files=changed_code,
                  new_files=new, changed_fixture_files=changed, removed_fixture_files=removed)
    if a.json:
        print(json.dumps(result, indent=1))
        return 0
    print(f"Reuse: {score}")
    for c, where in uses.items():
        print(f"  {c}: " + (f"rendered in {', '.join(where)}" if where else f"not imported from {ui} and rendered"))
    for h, where in hook_uses.items():
        print(f"  {h}: " + (f"called in {', '.join(where)}" if where else f"not imported from {hooks_dir} and called"))
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
