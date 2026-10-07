#!/usr/bin/env python3
"""Check and update the third-party skills pinned in plugins/devflow/vendor.json.

Usage:
  vendor_sync.py check            compare each pinned commit with upstream HEAD
  vendor_sync.py update [NAME...] copy upstream HEAD over the local folder and record the new commit

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
PLUGIN = os.path.join(ROOT, "plugins", "devflow")
MANIFEST = os.path.join(PLUGIN, "vendor.json")


def load():
    with open(MANIFEST, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}, data


def path_changes(entry):
    """Commits on upstream HEAD since the pinned one that touch the vendored folder (newest first)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", entry["source"], tmp], check=True)
        head = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        log = subprocess.run(["git", "-C", tmp, "log", "--format=%H %s", f"{entry['commit']}..{head}", "--", entry["upstream_path"]],
                             capture_output=True, text=True, check=True).stdout.strip()
    return head, [line for line in log.splitlines() if line]


def check():
    entries, _ = load()
    stale = False
    for name, entry in entries.items():
        head, commits = path_changes(entry)
        if not commits:
            print(f"{name}: current (no change to {entry['upstream_path']} since {entry['commit'][:12]})")
            continue
        stale = True
        print(f"{name}: {len(commits)} upstream commit(s) touch {entry['upstream_path']} since {entry['commit'][:12]}")
        for line in commits[:20]:
            print(f"  - {line[:12]} {line[41:]}")
        print(f"  {entry['source']}/compare/{entry['commit'][:12]}...{head[:12]}")
    return 10 if stale else 0


def update(names):
    entries, raw = load()
    targets = names or list(entries)
    for name in targets:
        entry = entries[name]
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "clone", "-q", "--depth", "1", entry["source"], tmp], check=True)
            head = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            src = os.path.join(tmp, entry["upstream_path"]) + "/"
            dst = os.path.join(PLUGIN, entry["local_path"]) + "/"
            excludes = [arg for pattern in entry.get("exclude", []) for arg in ("--exclude", pattern)]
            subprocess.run(["rsync", "-a", "--delete", *excludes, src, dst], check=True)
            license_src = os.path.join(tmp, "LICENSE")
            if not os.path.exists(os.path.join(dst, "LICENSE")) and os.path.exists(license_src):
                shutil.copy(license_src, os.path.join(dst, "LICENSE"))
        old = entry["commit"]
        raw[name]["commit"] = head
        print(f"{name}: {old[:12]} -> {head[:12]}")
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
    print(f"unknown command '{args[0]}'", file=sys.stderr)
    sys.exit(64)
