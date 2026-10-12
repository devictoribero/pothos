#!/usr/bin/env python3
"""Check and update the third-party skills pinned in plugins/pothos/vendor.json.

Usage:
  vendor_sync.py check            compare each pinned commit with upstream HEAD
  vendor_sync.py update [NAME...] copy upstream HEAD over the local folder and record the new commit
  vendor_sync.py overrides        re-apply the frontmatter overrides to the local copies

Two optional fields per entry adjust the copy's frontmatter after every update, and nothing else:
"model_invocable": true removes disable-model-invocation, so the skill also starts from plain language,
and "triggers" appends a sentence to the description saying when to use it.

check exits 0 when everything is current and 10 when an update is available, so a scheduled job can
decide whether to run update and open a pull request. update never runs on its own in a session:
a person reviews the resulting diff and the evals before merging. Needs git and rsync.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "pothos")
MANIFEST = os.path.join(PLUGIN, "vendor.json")


def load():
    with open(MANIFEST, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}, data


class Clones:
    """One clone per upstream source for the whole run; several entries often share a source."""

    def __init__(self, full):
        self.full = full
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = {}

    def get(self, source):
        if source not in self.paths:
            path = os.path.join(self.tmp.name, str(len(self.paths)))
            args = ["--filter=blob:none", "--no-checkout"] if not self.full else ["--depth", "1"]
            subprocess.run(["git", "clone", "-q", *args, source, path], check=True)
            self.paths[source] = path
        return self.paths[source]

    def head(self, source):
        return subprocess.run(["git", "-C", self.get(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

    def close(self):
        self.tmp.cleanup()


def path_changes(clones, entry):
    """Commits on upstream HEAD since the pinned one that touch the vendored folder (newest first)."""
    repo = clones.get(entry["source"])
    head = clones.head(entry["source"])
    excluded = [f":(exclude){entry['upstream_path']}/{pattern}" for pattern in entry.get("exclude", [])]
    log = subprocess.run(["git", "-C", repo, "log", "--format=%H %s", f"{entry['commit']}..{head}", "--", entry["upstream_path"], *excluded],
                         capture_output=True, text=True, check=True).stdout.strip()
    return head, [line for line in log.splitlines() if line]


def apply_overrides(skill_md, entry):
    """Apply the entry's frontmatter overrides to a vendored SKILL.md; the body is never touched."""
    if not (entry.get("model_invocable") or entry.get("triggers")) or not os.path.isfile(skill_md):
        return False
    with open(skill_md, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---\n"):
        return False
    end = text.index("\n---", 4)
    lines = text[4:end].split("\n")
    if entry.get("model_invocable"):
        lines = [line for line in lines if not line.startswith("disable-model-invocation:")]
    if entry.get("triggers"):
        for i, line in enumerate(lines):
            if line.startswith("description:"):
                value = line[len("description:"):].strip()
                if entry["triggers"] in value:
                    break
                if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[:-1].rstrip() + " " + entry["triggers"] + value[-1]
                else:
                    value = value + " " + entry["triggers"]
                lines[i] = "description: " + value
                break
    with open(skill_md, "w", encoding="utf-8") as fh:
        fh.write("---\n" + "\n".join(lines) + text[end:])
    return True


def check():
    entries, _ = load()
    stale = False
    clones = Clones(full=False)
    for name, entry in entries.items():
        head, commits = path_changes(clones, entry)
        if not commits:
            print(f"{name}: current (no change to {entry['upstream_path']} since {entry['commit'][:12]})")
            continue
        stale = True
        print(f"{name}: {len(commits)} upstream commit(s) touch {entry['upstream_path']} since {entry['commit'][:12]}")
        for line in commits[:20]:
            print(f"  - {line[:12]} {line[41:]}")
        print(f"  {entry['source']}/compare/{entry['commit'][:12]}...{head[:12]}")
    clones.close()
    return 10 if stale else 0


def update(names):
    entries, raw = load()
    unknown = [n for n in names if n not in entries]
    if unknown:
        print(f"unknown entry: {', '.join(unknown)}", file=sys.stderr)
        return 64
    targets = names or list(entries)
    clones = Clones(full=True)
    for name in targets:
        entry = entries[name]
        tmp = clones.get(entry["source"])
        head = clones.head(entry["source"])
        src = os.path.join(tmp, entry["upstream_path"]) + "/"
        dst = os.path.join(PLUGIN, entry["local_path"]) + "/"
        os.makedirs(dst, exist_ok=True)
        excludes = [arg for pattern in entry.get("exclude", []) for arg in ("--exclude", pattern)]
        subprocess.run(["rsync", "-a", "--delete", "--exclude", "LICENSE", *excludes, src, dst], check=True)
        license_src = os.path.join(tmp, "LICENSE")
        if os.path.exists(license_src):
            shutil.copy(license_src, os.path.join(dst, "LICENSE"))
        apply_overrides(os.path.join(dst, "SKILL.md"), entry)
        old = entry["commit"]
        raw[name]["commit"] = head
        print(f"{name}: {old[:12] or 'new'} -> {head[:12]}")
    clones.close()
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if args else 64)
    if args[0] == "check":
        sys.exit(check())
    if args[0] == "update":
        sys.exit(update(args[1:]))
    if args[0] == "overrides":
        entries, _ = load()
        for name, entry in entries.items():
            if apply_overrides(os.path.join(PLUGIN, entry["local_path"], "SKILL.md"), entry):
                print(f"{name}: overrides applied")
        sys.exit(0)
    print(f"unknown command '{args[0]}'", file=sys.stderr)
    sys.exit(64)
