#!/usr/bin/env python3
"""Locate, read, write and validate a devflow agent contract.

Contracts are private: they live outside the repository, under
$DEVFLOW_HOME (default $XDG_CONFIG_HOME/devflow, usually ~/.config/devflow)/contracts/, one file per repository,
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
PATH_FIELDS = ("docs.glossary", "tracker.path", "docs.decisions", "docs.specs", "docs.prd", "run.login", "pr.template")

EXIT_OK, EXIT_INVALID, EXIT_MISSING, EXIT_UNSET, EXIT_USAGE = 0, 1, 2, 3, 64


def git(args, cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True)
        return out.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def devflow_home():
    if os.environ.get("DEVFLOW_HOME"):
        return os.environ["DEVFLOW_HOME"]
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(config, "devflow")


def repo_root(start):
    return git(["rev-parse", "--show-toplevel"], start) or os.path.abspath(start)


def remote_key(url):
    """host/owner/repo from any common git remote URL form."""
    url = url.strip()
    match = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^:/]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", url)
    if not match:
        return None
    host, path = match.group(1).lower(), match.group(2).strip("/")
    if host.startswith("github.com"):  # ssh host aliases such as github.com-work
        host = "github.com"
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    return "/".join([host, *parts])


def contract_path(start):
    remote = git(["remote", "get-url", "origin"], start)
    key = remote_key(remote) if remote else None
    if not key:
        common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start)
        main = os.path.dirname(common) if common else repo_root(start)
        digest = hashlib.sha1(main.encode()).hexdigest()[:8]
        key = f"local/{os.path.basename(main)}-{digest}"
    return os.path.join(devflow_home(), "contracts", key + ".json")


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
    for field in PATH_FIELDS:
        rel = lookup(data, field)
        if isinstance(rel, str) and not os.path.exists(os.path.join(root, rel)):
            errors.append(f"contract.{field}: path '{rel}' does not exist in {root}")
    return errors


def check(data, repo, strict):
    errors = schema_errors(data, load(SCHEMA_PATH))
    if isinstance(data, dict) and data.get("workflow", "devflow") == "devflow" and "verify" not in data:
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
