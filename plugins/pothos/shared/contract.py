#!/usr/bin/env python3
"""Locate, read, write and validate a pothos agent contract.

Contracts are private: they live outside the repository, under
$POTHOS_HOME (default $XDG_CONFIG_HOME/pothos, usually ~/.config/pothos)/contracts/, one file per repository,
keyed by the origin remote (host/owner/repo.json). Every worktree and clone of
the same repository shares one contract, and the repository itself is never
touched. A repository without a remote is keyed by the path of its main worktree.

Usage:
  contract.py path   [--repo DIR]           print where the contract for this repo lives
  contract.py locate [--repo DIR]           print the path only if the contract exists
  contract.py get KEY [--repo DIR]          print one value, KEY is dotted (verify.fast)
  contract.py show   [--repo DIR]           print the whole contract
  contract.py write  [--repo DIR]           read a contract as JSON on stdin, validate it
                                            with --strict, and save it (nothing saved if invalid)
  contract.py validate [FILE] [--strict] [--repo DIR]
                                            check against the schema; --strict also checks
                                            that referenced paths exist in the repository

Exit codes: 0 ok, 1 invalid contract, 2 no contract found, 3 key not set, 64 usage error.
Standard library only, so it runs anywhere python3 does.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contract.schema.json")
# Paths that must already exist in the repository.
PATH_FIELDS = ("docs.glossary", "docs.decisions", "docs.specs", "run.login", "pr.template")
# Folders a skill creates on first use: they must be relative and inside the repo, but may not exist yet.
CREATED_LATER_FIELDS = ("tracker.path", "docs.prd")
CASE_INSENSITIVE_HOSTS = ("github.com", "gitlab.com", "bitbucket.org")

EXIT_OK, EXIT_INVALID, EXIT_MISSING, EXIT_UNSET, EXIT_USAGE = 0, 1, 2, 3, 64


def git(args, cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True)
        return out.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def pothos_home():
    if os.environ.get("POTHOS_HOME"):
        return os.environ["POTHOS_HOME"]
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(config, "pothos")


PR_TEMPLATES = [
    ".github/pull_request_template.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/pull_request_template.md",
    "pull_request_template.md",
]


def repo_root(start):
    return git(["rev-parse", "--show-toplevel"], start) or os.path.abspath(start)


def is_path_remote(url):
    return url.startswith(("/", "./", "../", "~", "file://")) or re.match(r"^[A-Za-z]:[\\/]", url) is not None


def remote_key(url):
    """host/owner/repo from a network git remote URL; None for filesystem remotes or anything unsafe."""
    url = url.strip()
    if not url or is_path_remote(url):
        return None
    match = re.match(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?([^:/\s]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", url, re.I)
    if not match:
        return None
    host, path = match.group(1).lower(), match.group(2).strip("/")
    # ssh host aliases such as github.com-work point at github.com; github.company.com does not.
    host = re.sub(r"^((?:github|gitlab)\.com|bitbucket\.org)-[\w.-]+$", r"\1", host)
    parts = [p for p in path.split("/") if p]
    if not parts or any(p in (".", "..") or p.startswith(".") for p in parts):
        return None
    if host in CASE_INSENSITIVE_HOSTS:
        parts = [p.lower() for p in parts]
    return "/".join([host, *parts])


def local_identity(start, remote):
    """A stable folder for repos without a network remote, shared by clones and worktrees where possible."""
    root = repo_root(start)
    if remote and is_path_remote(remote):
        target = remote[len("file://"):] if remote.startswith("file://") else os.path.expanduser(remote)
        target = os.path.realpath(os.path.join(root, target))
        return os.path.basename(target.rstrip("/")).removesuffix(".git") or "repo", target
    common = git(["rev-parse", "--git-common-dir"], start)
    if common:
        common = os.path.realpath(os.path.join(start, common))
        if f"{os.sep}modules{os.sep}" not in common:  # submodules keep their git dir inside the parent
            main = os.path.dirname(common)
            return os.path.basename(main), main
    return os.path.basename(root), os.path.realpath(root)


def key_for(start, folder):
    remote = git(["remote", "get-url", "origin"], start)
    key = remote_key(remote) if remote else None
    if not key:
        name, identity = local_identity(start, remote)
        key = f"local/{name}-{hashlib.sha1(identity.encode()).hexdigest()[:8]}"
    base = os.path.realpath(os.path.join(pothos_home(), folder))
    path = os.path.realpath(os.path.join(base, key))
    if not path.startswith(base + os.sep):
        raise ValueError(f"refusing a repository key that leaves {base}: {key}")
    return key


def contract_path(start):
    return os.path.join(pothos_home(), "contracts", key_for(start, "contracts") + ".json")


def locate(start):
    path = contract_path(start)
    return path if os.path.isfile(path) else None


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lookup(data, dotted):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


TYPES = {"object": dict, "string": str, "integer": int, "boolean": bool, "array": list}


def schema_errors(value, schema, where="contract"):
    """Validate the JSON Schema subset the contract schema uses."""
    errors = []
    expected = schema.get("type")
    if expected:
        ok = isinstance(value, TYPES[expected]) and not (expected == "integer" and isinstance(value, bool))
        if not ok:
            return [f"{where}: expected {expected}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where}: must not be empty")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing required field '{key}'")
        for key, child in value.items():
            if key in props:
                errors.extend(schema_errors(child, props[key], f"{where}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{where}: unknown field '{key}'")
    if isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(schema_errors(item, item_schema, f"{where}[{i}]"))
        if schema.get("uniqueItems") and len(set(map(json.dumps, value))) != len(value):
            errors.append(f"{where}: items must be unique")
    return errors


def path_errors(data, root):
    errors = []
    real_root = os.path.realpath(root)
    checks = [(field, lookup(data, field)) for field in PATH_FIELDS + CREATED_LATER_FIELDS]
    standards = lookup(data, "review.standards")
    if isinstance(standards, list):
        checks += [(f"review.standards[{i}]", rel) for i, rel in enumerate(standards)]
    for key in ("ui.components", "ui.tokens", "ui.locales"):
        items = lookup(data, key)
        if isinstance(items, list):
            checks += [(f"{key}[{i}]", rel) for i, rel in enumerate(items)]
    apps = lookup(data, "run.apps")
    if isinstance(apps, list):
        checks += [(f"run.apps[{i}].path", app.get("path")) for i, app in enumerate(apps) if isinstance(app, dict)]
        for i, app in enumerate(apps):
            for key in ("components", "tokens", "locales"):
                items = lookup(app, f"ui.{key}") if isinstance(app, dict) else None
                if isinstance(items, list):
                    checks += [(f"run.apps[{i}].ui.{key}[{j}]", rel) for j, rel in enumerate(items)]
    for field, rel in checks:
        if not isinstance(rel, str):
            continue
        target = os.path.realpath(os.path.join(root, rel))
        if os.path.isabs(rel) or not (target == real_root or target.startswith(real_root + os.sep)):
            errors.append(f"contract.{field}: '{rel}' must be a path inside the repository")
        elif field not in CREATED_LATER_FIELDS and not os.path.exists(target):
            errors.append(f"contract.{field}: path '{rel}' does not exist in {root}")
    return errors


def check(data, repo, strict):
    errors = schema_errors(data, load(SCHEMA_PATH))
    if isinstance(data, dict) and data.get("workflow", "pothos") == "pothos" and "verify" not in data:
        errors.append("contract: missing required field 'verify' (only optional when workflow is repo)")
    if strict:
        errors.extend(path_errors(data, repo_root(repo)))
    return errors


def parse_flag(args, name):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise ValueError(f"{name} needs a value")
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return None


def missing(repo):
    print(f"no contract for this repository; expected at {contract_path(repo)}", file=sys.stderr)
    return EXIT_MISSING


def main(argv):
    args = list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return EXIT_OK if args else EXIT_USAGE
    command = args.pop(0)
    try:
        repo = os.path.abspath(parse_flag(args, "--repo") or os.getcwd())
        contract_path(repo)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return EXIT_USAGE

    if command == "path":
        print(contract_path(repo))
        return EXIT_OK

    if command == "locate":
        path = locate(repo)
        if not path:
            return missing(repo)
        print(path)
        return EXIT_OK

    if command in ("get", "show"):
        if command == "get" and len(args) != 1:
            print("usage: contract.py get KEY", file=sys.stderr)
            return EXIT_USAGE
        path = locate(repo)
        if not path:
            return missing(repo)
        data = load(path)
        if command == "show":
            print(json.dumps(data, indent=2))
            return EXIT_OK
        value = lookup(data, args[0])
        if value is None:
            return EXIT_UNSET
        print(value if isinstance(value, str) else json.dumps(value))
        return EXIT_OK

    if command == "write":
        try:
            data = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(f"contract: not valid JSON ({exc})")
            return EXIT_INVALID
        errors = check(data, repo, strict=True)
        for error in errors:
            print(error)
        if errors:
            print("nothing saved")
            return EXIT_INVALID
        path = contract_path(repo)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        print(f"ok: saved {path}")
        return EXIT_OK

    if command == "validate":
        strict = "--strict" in args
        args = [a for a in args if a != "--strict"]
        path = args[0] if args else locate(repo)
        if not path or not os.path.isfile(path):
            return missing(repo)
        try:
            data = load(path)
        except json.JSONDecodeError as exc:
            print(f"contract: not valid JSON ({exc})")
            return EXIT_INVALID
        errors = check(data, repo, strict)
        for error in errors:
            print(error)
        if not errors:
            print(f"ok: {path}")
        return EXIT_INVALID if errors else EXIT_OK

    print(f"unknown command '{command}'", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
