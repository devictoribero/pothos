#!/usr/bin/env python3
"""Create, register, list and open explanation artifacts.

Artifacts are private and persistent, like contracts: they live under
$POTHOS_HOME/artifacts/<host>/<owner>/<repo>/<YYYY-MM-DD>-<slug>/ (or artifacts/general/ outside a
git repository), never inside the repository. Each folder holds index.html, a diagrams/ folder
and summary.md. The repository folder keeps INDEX.md, one line per artifact, so any agent can find
earlier explanations by reading a few lines instead of the HTML.

Usage:
  artifact.py new --slug SLUG --title TITLE [--lang LANG] [--parent FOLDER] [--repo DIR]
                                                            create the folder from the page template; prints its path.
                                                            --parent nests the page under an earlier one in the sidebar
  artifact.py parent FOLDER PARENT|none                     change where a page sits in the sidebar
  artifact.py put FOLDER RELPATH                            write stdin to FOLDER/RELPATH (the only way skills write pages)
  artifact.py light FILE...                                 make archify diagrams open in the light theme by default
  artifact.py register DIR                                  add or refresh DIR's line in INDEX.md (needs summary.md),
                                                            drop archify's receipt files from DIR/diagrams, rebuild the
                                                            sidebar for every page of the repository, and point
                                                            <repo folder>/latest at this page
  artifact.py nav [--repo DIR]                              rebuild the sidebar (nav.js) for this repository
  artifact.py list [--repo DIR]                             print INDEX.md for this repository
  artifact.py open PATH                                     open in Brave, falling back to the default browser

Exit codes: 0 ok, 1 failure (including: nothing to patch, no browser), 64 usage error. Standard library only.
"""
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))
import contract  # noqa: E402  (shared location and repo-key logic)

TEMPLATE = os.path.join(HERE, "..", "assets", "page.html")
NAV_RUNTIME = os.path.join(HERE, "..", "assets", "nav-runtime.js")
NAV_TAG = '<script src="../nav.js"></script>'
ARCHIFY_FALLBACK = "window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'"
ARCHIFY_LIVE_OS = "apply(e.matches ? 'light' : 'dark');"


def repo_folder(start):
    root = contract.git(["rev-parse", "--show-toplevel"], start)
    if not root:
        return os.path.join(contract.pothos_home(), "artifacts", "general")
    key = os.path.relpath(contract.contract_path(start), os.path.join(contract.pothos_home(), "contracts"))
    return os.path.join(contract.pothos_home(), "artifacts", key[: -len(".json")])


def flag(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            print(f"{name} needs a value", file=sys.stderr)
            raise SystemExit(64)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return default


def cmd_new(args):
    slug = flag(args, "--slug")
    title = flag(args, "--title")
    lang = flag(args, "--lang", "en")
    parent = flag(args, "--parent")
    repo = os.path.abspath(flag(args, "--repo", os.getcwd()))
    if not slug or not title or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        print("usage: artifact.py new --slug kebab-case-slug --title 'Title'", file=sys.stderr)
        return 64
    base = repo_folder(repo)
    if parent and not os.path.isfile(os.path.join(base, parent, "meta.json")):
        print(f"--parent must be an existing page folder in {base}, such as 2026-01-31-some-topic", file=sys.stderr)
        return 64
    folder = os.path.join(base, f"{datetime.date.today().isoformat()}-{slug}")
    if os.path.exists(folder):
        print(folder)
        print("exists: update it instead of creating a duplicate", file=sys.stderr)
        return 0
    os.makedirs(os.path.join(folder, "diagrams"))
    with open(TEMPLATE, encoding="utf-8") as fh:
        page = fh.read().replace("{{TITLE}}", html.escape(title)).replace("{{LANG}}", html.escape(lang))
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    meta = {"title": title, "slug": slug, "created": datetime.date.today().isoformat(),
            "repo": contract.git(["remote", "get-url", "origin"], repo),
            "commit": contract.git(["rev-parse", "--short", "HEAD"], repo), "parent": parent}
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(folder)
    return 0


def cmd_put(args):
    """Artifact folders live outside the project, where file tools prompt or are denied; write through here."""
    if len(args) != 2:
        print("usage: artifact.py put FOLDER RELPATH < content", file=sys.stderr)
        return 64
    folder = os.path.realpath(args[0])
    artifacts = os.path.realpath(os.path.join(contract.pothos_home(), "artifacts"))
    target = os.path.realpath(os.path.join(folder, args[1]))
    is_artifact = folder.startswith(artifacts + os.sep) and os.path.isfile(os.path.join(folder, "meta.json"))
    if not is_artifact or not target.startswith(folder + os.sep):
        print("refused: put only writes inside a folder created by `artifact.py new`", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(sys.stdin.read())
    print(f"wrote {target}")
    return 0


def cmd_light(files):
    if not files:
        print("usage: artifact.py light FILE...", file=sys.stderr)
        return 64
    failed = False
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        patched = text.replace('data-theme="dark"', 'data-theme="light"', 1).replace(ARCHIFY_FALLBACK, "'light'").replace(ARCHIFY_LIVE_OS, "return;")
        if ARCHIFY_FALLBACK in text or 'data-theme="dark"' in text:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(patched)
            print(f"light by default: {path}")
        elif "'light'" in text and ARCHIFY_LIVE_OS not in text and "data-theme" in text:
            print(f"already light: {path}")
        else:
            failed = True
            print(f"not an archify page this script knows how to patch: {path}", file=sys.stderr)
    return 1 if failed else 0


def first_line(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip().lstrip("#").strip()
            if line:
                return line
    return ""


RECEIPT_SUFFIXES = (".finalize.json", ".finalize-summary.json", ".browser-check.json", ".delivery.json")
RECEIPT_FOLDERS = (".old-receipts",)


def clean_receipts(folder):
    """Remove archify's gate receipts under folder/diagrams. They are evidence for the run that produced a
    diagram, not part of the page, and they weigh more than the candidate JSON. Diagram HTML and candidates stay."""
    removed = 0
    diagrams = os.path.join(folder, "diagrams")
    for root, dirs, files in os.walk(diagrams):
        for name in list(dirs):
            if name in RECEIPT_FOLDERS:
                shutil.rmtree(os.path.join(root, name))
                dirs.remove(name)
                removed += 1
        for name in files:
            if name.endswith(RECEIPT_SUFFIXES):
                os.remove(os.path.join(root, name))
                removed += 1
    return removed


def cmd_register(args):
    if len(args) != 1:
        print("usage: artifact.py register DIR", file=sys.stderr)
        return 64
    folder = os.path.abspath(args[0])
    summary = os.path.join(folder, "summary.md")
    meta_path = os.path.join(folder, "meta.json")
    if not all(os.path.isfile(os.path.join(folder, f)) for f in ("summary.md", "meta.json", "index.html")):
        print(f"{folder} needs index.html, summary.md and meta.json", file=sys.stderr)
        return 1
    with open(os.path.join(folder, "index.html"), encoding="utf-8") as fh:
        if "data-pothos-placeholder" in fh.read():
            print("index.html still has the 'being written' notice; finish the page first", file=sys.stderr)
            return 1
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    index = os.path.join(os.path.dirname(folder), "INDEX.md")
    name = os.path.basename(folder)
    line = f"- [{meta['title']}]({name}/index.html) · {meta['created']} · commit {meta.get('commit') or 'n/a'} · {first_line(summary)} · summary: {name}/summary.md"
    lines = []
    if os.path.isfile(index):
        with open(index, encoding="utf-8") as fh:
            lines = [l.rstrip("\n") for l in fh if l.strip() and not l.startswith("# ") and f"]({name}/" not in l]
    date_of = lambda entry: entry.split("](", 1)[1][:10] if "](" in entry else ""
    # Newest date first; within a day, the page registered last goes first (sorted() is stable).
    lines = sorted([line] + lines, key=date_of, reverse=True)
    with open(index, "w", encoding="utf-8") as fh:
        fh.write("# Explanations\n\nNewest first. Read summary.md before opening the HTML.\n\n" + "\n".join(l for l in lines if l.startswith("- ")) + "\n")
    receipts = clean_receipts(folder)
    build_nav(os.path.dirname(folder))
    latest = os.path.join(os.path.dirname(folder), "latest")
    if os.path.islink(latest) or not os.path.exists(latest):
        tmp = latest + ".tmp"
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(name, tmp)
        os.replace(tmp, latest)
    print(f"registered in {index}" + (f"; removed {receipts} archify receipt file(s)" if receipts else ""))
    return 0


def pages_in(base):
    pages = []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        meta_path = os.path.join(base, name, "meta.json")
        if not os.path.islink(os.path.join(base, name)) and os.path.isfile(meta_path):
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
            pages.append({"folder": name, "title": meta.get("title", name), "created": meta.get("created", name[:10]), "parent": meta.get("parent")})
    return sorted(pages, key=lambda p: p["folder"], reverse=True)


def build_nav(base):
    """Write base/nav.js and make sure every page loads it. Returns the number of pages."""
    pages = pages_in(base)
    with open(NAV_RUNTIME, encoding="utf-8") as fh:
        runtime = fh.read()
    with open(os.path.join(base, "nav.js"), "w", encoding="utf-8") as fh:
        fh.write("window.POTHOS_NAV = " + json.dumps(pages, ensure_ascii=False, indent=1) + ";\n" + runtime)
    for page in pages:
        index = os.path.join(base, page["folder"], "index.html")
        if not os.path.isfile(index):
            continue
        with open(index, encoding="utf-8") as fh:
            text = fh.read()
        if NAV_TAG not in text and "</body>" in text:
            with open(index, "w", encoding="utf-8") as fh:
                fh.write(text.replace("</body>", NAV_TAG + "\n</body>", 1))
    return len(pages)


def cmd_nav(args):
    repo = os.path.abspath(flag(args, "--repo", os.getcwd()))
    base = repo_folder(repo)
    print(f"sidebar rebuilt for {build_nav(base)} page(s) in {base}")
    return 0


def cmd_parent(args):
    if len(args) != 2:
        print("usage: artifact.py parent FOLDER PARENT|none", file=sys.stderr)
        return 64
    folder = os.path.abspath(args[0])
    base, name = os.path.dirname(folder), os.path.basename(folder)
    parent = None if args[1] == "none" else os.path.basename(os.path.abspath(args[1]))
    meta_path = os.path.join(folder, "meta.json")
    if not os.path.isfile(meta_path) or (parent and not os.path.isfile(os.path.join(base, parent, "meta.json"))):
        print("both folders must be pages of the same repository", file=sys.stderr)
        return 64
    parents = {p["folder"]: p["parent"] for p in pages_in(base)}
    step = parent
    while step:
        if step == name:
            print("refused: that would make a page its own ancestor", file=sys.stderr)
            return 1
        step = parents.get(step)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["parent"] = parent
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    build_nav(base)
    print(f"{name}: parent is now {parent or 'none'}")
    return 0


def cmd_list(args):
    repo = os.path.abspath(flag(args, "--repo", os.getcwd()))
    index = os.path.join(repo_folder(repo), "INDEX.md")
    if not os.path.isfile(index):
        print(f"no explanations yet ({index})")
        return 0
    with open(index, encoding="utf-8") as fh:
        print(fh.read().rstrip())
    return 0


def cmd_open(args):
    if len(args) != 1:
        print("usage: artifact.py open PATH", file=sys.stderr)
        return 64
    path = os.path.abspath(args[0])
    if os.environ.get("POTHOS_NO_OPEN"):
        print(f"not opened (POTHOS_NO_OPEN): {path}")
        return 0
    attempts = [["open", "-a", "Brave Browser", path], ["open", path], ["xdg-open", path]]
    for cmd in attempts:
        if shutil.which(cmd[0]) and subprocess.run(cmd, capture_output=True).returncode == 0:
            print(f"opened with {' '.join(cmd[:-1])}: {path}")
            return 0
    print(f"could not open a browser; open it yourself: {path}")
    return 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 64
    command, args = argv[0], list(argv[1:])
    handlers = {"new": cmd_new, "put": cmd_put, "nav": cmd_nav, "parent": cmd_parent, "light": cmd_light, "register": cmd_register, "list": cmd_list, "open": cmd_open}
    if command not in handlers:
        print(f"unknown command '{command}'", file=sys.stderr)
        return 64
    return handlers[command](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
