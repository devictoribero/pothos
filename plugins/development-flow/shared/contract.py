#!/usr/bin/env python3
"""Locate, read and validate a development-flow agent contract.

Usage:
  contract.py locate [--repo DIR]           print the contract path
  contract.py get KEY [--repo DIR]          print one value, KEY is dotted (verify.fast)
  contract.py validate [FILE] [--strict]    check the contract against the schema;
                                            --strict also checks that referenced paths exist

Exit codes: 0 ok, 1 invalid contract, 2 no contract found, 3 key not set, 64 usage error.
Standard library only, so it runs anywhere python3 does.
"""
import json
import os
import subprocess
import sys

CONTRACT_RELATIVE_PATH = os.path.join(".agents", "contract.json")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contract.schema.json")
PATH_FIELDS = ("docs.glossary", "tracker.path", "docs.decisions", "docs.specs", "docs.prd", "run.login", "pr.template")

EXIT_OK, EXIT_INVALID, EXIT_MISSING, EXIT_UNSET, EXIT_USAGE = 0, 1, 2, 3, 64


def repo_root(start):
    try:
        out = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.path.abspath(start)


def locate(start):
    path = os.path.join(repo_root(start), CONTRACT_RELATIVE_PATH)
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
        py_type = TYPES[expected]
        ok = isinstance(value, py_type) and not (expected == "integer" and isinstance(value, bool))
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
            errors.append(f"contract.{field}: path '{rel}' does not exist")
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


def main(argv):
    args = list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return EXIT_OK if args else EXIT_USAGE
    command = args.pop(0)
    try:
        repo = parse_flag(args, "--repo") or os.getcwd()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return EXIT_USAGE

    if command == "locate":
        path = locate(repo)
        if not path:
            print(f"no contract at {CONTRACT_RELATIVE_PATH}", file=sys.stderr)
            return EXIT_MISSING
        print(path)
        return EXIT_OK

    if command == "get":
        if len(args) != 1:
            print("usage: contract.py get KEY", file=sys.stderr)
            return EXIT_USAGE
        path = locate(repo)
        if not path:
            print(f"no contract at {CONTRACT_RELATIVE_PATH}", file=sys.stderr)
            return EXIT_MISSING
        value = lookup(load(path), args[0])
        if value is None:
            return EXIT_UNSET
        print(value if isinstance(value, str) else json.dumps(value))
        return EXIT_OK

    if command == "validate":
        strict = "--strict" in args
        args = [a for a in args if a != "--strict"]
        path = args[0] if args else locate(repo)
        if not path or not os.path.isfile(path):
            print(f"no contract at {path or CONTRACT_RELATIVE_PATH}", file=sys.stderr)
            return EXIT_MISSING
        try:
            data = load(path)
        except json.JSONDecodeError as exc:
            print(f"contract: not valid JSON ({exc})")
            return EXIT_INVALID
        errors = schema_errors(data, load(SCHEMA_PATH))
        if strict:
            root = os.path.dirname(os.path.dirname(os.path.abspath(path)))
            errors.extend(path_errors(data, root))
        for error in errors:
            print(error)
        if not errors:
            print(f"ok: {path}")
        return EXIT_INVALID if errors else EXIT_OK

    print(f"unknown command '{command}'", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
