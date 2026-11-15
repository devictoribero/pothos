"""Path rules more than one script needs: repository-relative globs, test files, and the folders Pothos keeps per
commit and per branch outside the repository.

Standard library only. Import it the way the scripts import contract.py, from the plugin's shared folder.
"""
import fnmatch
import os
import re

import contract

LANG_TOKEN = "{lang}"
LANG_GROUP = r"(?P<lang>[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?)"
# The files Stryker's default mutate option leaves out (an explicit --mutate replaces those defaults).
TEST_FILE_GLOBS = ("*.test.*", "*.spec.*")
TEST_FOLDERS = ("__tests__",)


def glob_regex(pattern):
    """A repository-relative folder or glob as a regex over repository-relative paths: `**` crosses folders,
    `*` stays inside one, a folder matches everything under it, and `{lang}` is one language code, captured."""
    out = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith(LANG_TOKEN, i):
            out += LANG_GROUP
            i += len(LANG_TOKEN)
            continue
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if ch == "*":
            out += "[^/]*"
        elif ch == "?":
            out += "[^/]"
        else:
            out += re.escape(ch)
        i += 1
    has_extension = bool(re.search(r"\.[A-Za-z0-9]+$", pattern))
    tail = "" if has_extension else "(?:/.*)?"
    return re.compile("^" + out.rstrip("/") + tail + "$")


def matches_any(path, patterns):
    return any(glob_regex(p).match(path) for p in patterns)


def is_test_file(path):
    name = os.path.basename(path)
    return (any(fnmatch.fnmatch(name, glob) for glob in TEST_FILE_GLOBS)
            or any(part in TEST_FOLDERS for part in path.split("/")[:-1]))


def receipt_dir(root, commit):
    """Where verify keeps the receipts of one commit: $POTHOS_HOME/receipts/<host>/<owner>/<repo>/<commit>/."""
    return os.path.join(contract.pothos_home(), "receipts", contract.key_for(root, "receipts"), commit)


def evidence_dir(root):
    """Where evidence keeps the proof of the current branch: $POTHOS_HOME/evidence/<host>/<owner>/<repo>/<branch>/.
    The folder is not created here."""
    branch = contract.git(["symbolic-ref", "--short", "-q", "HEAD"], root) or "detached"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "branch"
    return os.path.join(contract.pothos_home(), "evidence", contract.key_for(root, "evidence"), slug)
