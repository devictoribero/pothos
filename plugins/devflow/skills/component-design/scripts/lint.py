#!/usr/bin/env python3
"""Lint a component folder for the two conventions code review misses most: dependency direction
and naming.

Usage: lint.py <src-dir> [--business-words price,listing,...] [--primitives ui,primitives,design-system,ds]
                         [--features features] [--all]

Boundaries (screens -> features -> primitives -> platform):
  1. A primitive (a file under a primitives folder) never imports a feature, a domain or data module,
     a DTO or API package, a store, or a screen.
  2. A feature reaches another feature only through its public entry (`features/<name>` or its
     `index`), never its internals.
  3. With --business-words, a primitive's props and types never use those words: primitives speak
     product and UI language (`media`, `title`, `meta`), not one business (`listing`, `price`).

Names (references/naming.md):
  isOpen-style names for states the platform names, defaultIs*/initial*, onSelect, selectedId-style
  selection, `default`/`normal`/`regular`/`base` as union values, `id` as an item's identity,
  non-native file names, onChangeText on a field-like part, $transient props, onTap.
  Tests and consumer folders (example, demo, app, preview, stories) are skipped unless --all;
  local variable declarations without JSX are never flagged.

Imports are resolved for relative paths and the `@/`, `~/` and `src/` aliases (all mean <src-dir>).
Silence a deliberate exception with a trailing `// lint-ok: <reason>`.
Exit code 1 when something is found.
"""
import argparse, os, re, sys

# ---------------------------------------------------------------- boundaries
IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|require\s*\(\s*|export\s[^'"]*?from\s*)['"]([^'"]+)['"]""")
BUSINESS_SEGMENTS = {"features", "feature", "domain", "data", "api", "apis", "dto", "dtos", "services", "store", "stores",
                     "screens", "pages", "routes", "app"}
BUSINESS_PACKAGE = re.compile(r"(^|[/@-])(dto|dtos|api-client|api)([/-]|$)", re.I)

# ---------------------------------------------------------------- names
NAME_RULES = [
    (r"\b(isOpen|isChecked|isSelected|isPressed|isDisabled|isRequired|isReadOnly|isHidden)\b\s*[?:=]",
     "the platform has a word for this state: open, checked, selected, pressed, disabled, required, readOnly, hidden"),
    (r"\bdefaultIs[A-Z]\w*", "uncontrolled defaults drop the `is`: defaultOpen, not defaultIsOpen"),
    (r"\binitial[A-Z]\w*\s*\??:", "uncontrolled initial values are default<Name>"),
    (r"\bonSelect\s*[?:=]", "onSelect is ambiguous: onValueChange for a selection, onClick/onAction/an outcome for an action"),
    (r"\b(selectedId|onSelectedIdChange|selectedValue|onSelectedValueChange|defaultSelectedValue)\b",
     "a single selection is value + defaultValue + onValueChange"),
    (r"""(['"])(default|normal|regular|base)\1\s*\||\|\s*(['"])(default|normal|regular|base)\3""",
     "a union value names what it is, never its role (default, normal, regular, base)"),
    (r"<\w+\.(Item|Tab|Option|Step|Panel|Trigger|Row)\b[^>]*\sid=", "an item's identity is `value`; `id` is the DOM id"),
    (r"\b(isMulti|acceptedFileTypes|allowsMultiple)\b", "use the native names: multiple, accept, or a selectionMode union"),
    (r"\bonChangeText\b", "a field-like part reports its value with onValueChange (onChangeText only on a raw React Native TextInput)"),
    (r"\$[a-z]\w*\??\s*:\s*\w+", "a styling library's transient prop ($prop) is not public API"),
    (r"\bonTap\b", "the platform event is onClick (web) or onPress (React Native)"),
]
CONSUMER_DIRS = {"example", "examples", "demo", "demos", "app", "preview", "stories", "__tests__"}
TEST_FILE = re.compile(r"\.(test|spec|stories)\.[jt]sx?$")

def segments(path):
    return [s for s in path.replace("\\", "/").split("/") if s and s != "."]

def resolve(spec, file_path, src):
    if spec.startswith("."):
        return os.path.normpath(os.path.join(os.path.dirname(file_path), spec))
    for alias in ("@/", "~/", "src/"):
        if spec.startswith(alias):
            return os.path.normpath(os.path.join(src, spec[len(alias):]))
    return None  # a package

def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("src"); ap.add_argument("--primitives", default="ui,primitives,design-system,ds")
    ap.add_argument("--features", default="features"); ap.add_argument("--business-words", default="")
    ap.add_argument("--all", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        print(__doc__); return 2
    src = os.path.abspath(a.src)
    prim_dirs = set(a.primitives.split(",")); feat_dir = a.features
    words = [w.strip() for w in a.business_words.split(",") if w.strip()]
    boundaries, names = [], []
    for d, _, fs in os.walk(src):
        if "node_modules" in d: continue
        for f in fs:
            if not f.endswith((".ts", ".tsx", ".js", ".jsx")): continue
            path = os.path.join(d, f); rel = os.path.relpath(path, src); segs = segments(rel)
            is_test = bool(TEST_FILE.search(f))
            is_consumer = is_test or bool(set(segs[:-1]) & CONSUMER_DIRS)
            is_prim = bool(set(segs[:-1]) & prim_dirs)
            feat = segs[segs.index(feat_dir) + 1] if feat_dir in segs[:-1] else None
            for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
                if "lint-ok:" in line: continue
                if not is_test:
                    for spec in IMPORT.findall(line):
                        target = resolve(spec, path, src)
                        tsegs = segments(os.path.relpath(target, src)) if target else []
                        if is_prim:
                            if target and set(tsegs) & BUSINESS_SEGMENTS and not set(tsegs) & prim_dirs:
                                boundaries.append((rel, n, f"primitive imports business code '{spec}'"))
                            elif not target and BUSINESS_PACKAGE.search(spec):
                                boundaries.append((rel, n, f"primitive imports a DTO or API package '{spec}'"))
                        if feat and target and feat_dir in tsegs:
                            i = tsegs.index(feat_dir)
                            other = tsegs[i + 1] if len(tsegs) > i + 1 else None
                            deep = tsegs[i + 2:] if len(tsegs) > i + 2 else []
                            if other and other != feat and deep and deep != ["index"]:
                                boundaries.append((rel, n, f"feature '{feat}' reaches into '{other}' internals '{spec}'; import its public entry"))
                    if is_prim and words:
                        for w in words:
                            if re.search(rf"\b{re.escape(w)}\w*\??\s*:|\b{re.escape(w)}\w*=", line, re.I):
                                boundaries.append((rel, n, f"primitive uses business word '{w}': name it in product/UI language"))
                if (a.all or not is_consumer) and not (re.match(r"\s*(export\s+)?(const|let|var)\s", line) and "<" not in line):
                    for pattern, why in NAME_RULES:
                        if re.search(pattern, line):
                            names.append((rel, n, why))
    for title, items in (("Boundaries", boundaries), ("Names", names)):
        print(f"{title}: {len(items)} finding(s)")
        for rel, n, why in items:
            print(f"  {rel}:{n}: {why}")
    total = len(boundaries) + len(names)
    print(f"{total} finding(s)")
    return 1 if total else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
