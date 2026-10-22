#!/usr/bin/env python3
"""Check the lines a branch adds against the contract's ui section.

Usage: ui_check.py [--base REF] [--repo DIR]

Looks only at added lines (committed on the branch, uncommitted and untracked), so
existing code never fails it. Works on any stack: the rules are text patterns that
hold for CSS, Sass, Tailwind classes, CSS-in-JS, React Native styles, Vue and Svelte.

Rules, each applied only where the contract gives it a meaning:
  raw-color   a hex, rgb() or hsl() color outside ui.tokens        (needs ui.tokens)
  font        a new font family or font loader outside ui.tokens     (needs ui.tokens)
  icon-set    an import of an icon package other than ui.icons       (needs ui.icons)

A line containing "ui-ok" is skipped: write why next to it.
Exit codes: 0 clean or nothing to check, 1 findings, 2 no contract, 64 usage.
Standard library only.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract  # noqa: E402

ICON_PACKAGES = [
    "lucide-react", "lucide-react-native", "lucide-vue-next", "lucide-svelte", "@heroicons/react", "@heroicons/vue",
    "react-icons", "@tabler/icons-react", "@tabler/icons-vue", "@phosphor-icons/react", "phosphor-react-native",
    "@radix-ui/react-icons", "@expo/vector-icons", "react-native-vector-icons", "@mui/icons-material",
    "@fortawesome/react-fontawesome", "@fortawesome/fontawesome-svg-core", "@iconify/react", "@iconify/vue",
    "react-feather", "@remixicon/react", "@primer/octicons-react", "@carbon/icons-react", "ionicons",
    "@fortawesome/react-native-fontawesome", "@fortawesome/free-solid-svg-icons", "@fortawesome/free-regular-svg-icons",
]
CHECKED_EXTS = (".css", ".scss", ".sass", ".less", ".styl", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                ".vue", ".svelte", ".astro", ".html")
SKIPPED_PATH = re.compile(r"(^|/)(__tests__|__mocks__|__snapshots__|test|tests|e2e|cypress|docs?)/|\.(test|spec|stories|story|snap)\.", re.I)
# A `*` line is a block comment only when text, `*/` or nothing follows: `* {`, `*, *::before`, `*::before`,
# `* + *` and `*:not(.a)` are CSS selectors.
COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*(?:\s+[\w@`'\"(-]|\s*$|/)|<!--|\{/\*)")

HEX = re.compile(r"(?<![\w.&#/-])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")
FUNC_COLOR = re.compile(r"\b(rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(\s*[\d.]")
COLOR_CONTEXT = re.compile(r"""[:'"`\[(,=]\s*$""")
FONT = [
    re.compile(r"font-family\s*:\s*(?!\s*(inherit|initial|unset|revert|var\(|theme\(|\$|@))", re.I),
    re.compile(r"""fontFamily\s*:\s*['"`]"""),
    re.compile(r"@font-face", re.I),
    re.compile(r"fonts\.googleapis\.com|fonts\.bunny\.net|use\.typekit\.net"),
    re.compile(r"""['"](next/font/(google|local)|@fontsource(-variable)?/[^'"]+|expo-font)['"]"""),
    re.compile(r"\buseFonts\(|\bFont\.loadAsync\("),
    re.compile(r"""\bfont-\[['"]?[A-Z]"""),
]


def git(args, cwd):
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def base_ref(root, data, explicit):
    """The merge-base of HEAD with the base branch, as a commit.

    The local branch and its `origin/` copy are both tried and the newer merge-base wins: a worktree's local `main`
    often sits weeks behind the remote (every file since then would count as changed), and a `main` with unpushed
    commits sits ahead of it.
    """
    candidates = [explicit] if explicit else [((data.get("pr") or {}).get("base")), "main", "master"]
    for ref in filter(None, candidates):
        bases = [base for base in ((git(["merge-base", name, "HEAD"], root) or "").strip() for name in (ref, f"origin/{ref}"))
                 if base]
        if bases:
            return newest(root, bases)
    if explicit:
        raise ValueError(f"base '{explicit}' not found")
    return None


def newest(root, commits):
    """The commit no other one in the list descends from; the first one when they are unrelated."""
    chosen = commits[0]
    for commit in commits[1:]:
        if subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", chosen, commit], capture_output=True).returncode == 0:
            chosen = commit
    return chosen


def added_lines(root, base):
    """{path: [(line number, text)]} for every line added since base, including uncommitted and untracked files."""
    added = {}
    # Explicit prefixes: a user's diff.noprefix=true would otherwise shift every path by two characters.
    options = ["diff", "--unified=0", "--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/"]
    diff = git(options + [base if base else "HEAD"], root) or ""
    path, number = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = None if line[4:] == "/dev/null" else line[6:]
        elif line.startswith("@@"):
            number = int(re.match(r"@@ -\S+ \+(\d+)", line).group(1))
        elif line.startswith("+") and path:
            added.setdefault(path, []).append((number, line[1:]))
            number += 1
    untracked = git(["ls-files", "--others", "--exclude-standard"], root) or ""
    for rel in untracked.splitlines():
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                added[rel] = list(enumerate(fh.read().splitlines(), 1))
        except (OSError, UnicodeDecodeError):
            continue
    return added


def scopes(data):
    """(path prefix, ui) pairs, most specific first; the top-level ui applies to everything else."""
    pairs = [(app["path"].rstrip("/") + "/", app["ui"]) for app in ((data.get("run") or {}).get("apps") or [])
             if isinstance(app, dict) and app.get("ui") and app.get("path")]
    pairs.sort(key=lambda pair: -len(pair[0]))
    if data.get("ui"):
        pairs.append(("", data["ui"]))
    return pairs


def ui_for(path, pairs):
    return next((ui for prefix, ui in pairs if path.startswith(prefix)), None)


def inside(path, roots):
    return any(path == r.rstrip("/") or path.startswith(r.rstrip("/") + "/") for r in roots)


def is_color(text, match):
    value = match.group(1)
    if any(c.isdigit() for c in value) and len(value) in (6, 8):
        return True
    return bool(COLOR_CONTEXT.search(text[:match.start()]))


IMPORT = re.compile(r"""(?:\bfrom\s+|\brequire\(\s*|\bimport\s*\(\s*|^\s*import\s+)['"]([^'"./~#][^'"]*)['"]""")
ICON_NAME = re.compile(r"icon|fontawesome|lucide|feather", re.I)


def package_name(specifier):
    """The npm package an import specifier names, or None for path aliases such as @/x."""
    parts = specifier.split("/")
    if specifier.startswith("@"):
        return "/".join(parts[:2]) if len(parts) > 1 and len(parts[0]) > 1 else None
    return parts[0]


def is_icon_package(name):
    return name in ICON_PACKAGES or bool(ICON_NAME.search(name))


def same_set(name, configured):
    """One icon set can span packages of one scope: @fortawesome/react-fontawesome with @fortawesome/pro-light-svg-icons."""
    scope = lambda n: n.split("/")[0] if n.startswith("@") else None
    return name == configured or (scope(name) is not None and scope(name) == scope(configured))


def icon_imports(text):
    for match in IMPORT.finditer(text):
        name = package_name(match.group(1))
        if name and is_icon_package(name):
            yield name


def check_line(path, text, ui):
    if "ui-ok" in text or COMMENT_LINE.match(text):
        return []
    found = []
    if ui.get("tokens"):
        for match in HEX.finditer(text):
            if is_color(text, match):
                found.append(("raw-color", match.group(0)))
        found += [("raw-color", m.group(0) + "…") for m in FUNC_COLOR.finditer(text)]
        found += [("font", m.group(0)) for pattern in FONT for m in [pattern.search(text)] if m]
    icons = ui.get("icons")
    if icons:
        found += [("icon-set", package) for package in icon_imports(text) if not same_set(package, icons)]
        if os.path.basename(path) == "package.json":
            dep = re.match(r'\s*"([^"]+)"\s*:\s*"', text)
            if dep and is_icon_package(dep.group(1)) and not same_set(dep.group(1), icons):
                found.append(("icon-set", dep.group(1)))
    return found


def findings(root, data, base):
    """(active rules, findings) for the lines added since base; None when the contract gives nothing to check."""
    pairs = scopes(data)
    active = sorted({rule for _, ui in pairs for rule, key in (("raw-color", "tokens"), ("font", "tokens"), ("icon-set", "icons")) if ui.get(key)})
    if not active:
        return None
    found = []
    for path, lines in sorted(added_lines(root, base).items()):
        ui = ui_for(path, pairs)
        is_manifest = os.path.basename(path) == "package.json"
        if not ui or not (path.endswith(CHECKED_EXTS) or is_manifest) or SKIPPED_PATH.search(path):
            continue
        if inside(path, ui.get("tokens") or []):
            continue
        for number, text in lines:
            for rule, snippet in check_line(path, text, ui):
                found.append(f"{path}:{number} {rule}: {snippet}")
    return active, found


HINT = "Use the tokens or the configured icon set, or add 'ui-ok: <why>' to the line when the raw value is intended."


def run(root, data, base):
    result = findings(root, data, base)
    if result is None:
        print("skipped: the contract's ui sets neither tokens nor icons; run /pothos:plant audit to add them")
        return 0
    active, found = result
    for line in found:
        print(line)
    print(f"ui-check: {len(found)} finding(s); rules: {', '.join(active)}. {HINT}")
    return 1 if found else 0


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        repo = argv[argv.index("--repo") + 1] if "--repo" in argv else os.getcwd()
        explicit = argv[argv.index("--base") + 1] if "--base" in argv else None
    except IndexError:
        print(__doc__, file=sys.stderr)
        return 64
    path = contract.locate(repo)
    if not path:
        print("no contract: run /pothos:plant", file=sys.stderr)
        return 2
    root = contract.repo_root(repo)
    try:
        data = contract.load(path)
    except json.JSONDecodeError as exc:
        print(f"the contract at {path} is not valid JSON ({exc}); run /pothos:plant", file=sys.stderr)
        return 2
    try:
        base = base_ref(root, data, explicit)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 64
    return run(root, data, base)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
