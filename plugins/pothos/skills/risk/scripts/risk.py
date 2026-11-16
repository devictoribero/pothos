#!/usr/bin/env python3
"""Assess how risky a branch is to merge, for the Risk section of its pull request.

Usage:
  risk.py assess [--base REF] [--json]

It compares merge-base(base, HEAD)..HEAD. The base is --base, else the contract's pr.base (the newer of the local
branch and its origin/ copy), else origin/HEAD. Uncommitted changes are not assessed; stderr says so when the tree
is dirty. Every changed path is classified, first match wins: generated (pr.risk.generated and the usual
lockfiles), test (verify's rule), docs (*.md, docs/), source. From those it reports the door (one-way when a path
matches pr.risk.one_way, default **/migrations/**), the blast radius (areas, pr.risk.contract surfaces,
pr.risk.core areas), the complexity of the source change and the evidence behind HEAD (verify's full and mutation
receipts, the test lines changed, the branch's evidence folder), then a suggested Risk and the highest Confidence
that evidence allows. Levels are Low, Medium or High, never percentages.

Rules:
  blast radius  narrow: one area, no contract surface, no core area; wide: three or more areas, or a contract
                surface and a core area together; medium otherwise. Areas are the run.apps an edited source file
                sits in, else its first folder.
  complexity    Low: at most 150 source lines (added plus removed) and 5 source files; High: more than 600 lines
                or more than 20 files; Medium otherwise.
  risk          High: a one-way door with a core area or a wide radius, or a core area with High complexity.
                Medium: a one-way door, a core area, a wide radius or High complexity. Low otherwise.
  confidence    the ceiling is Low without a passing full receipt for HEAD (on a clean tree); Medium when source
                changed with no test lines changed, with new mutation survivors, or with High complexity; High
                otherwise.

The default output is a markdown section ready for a pull request body; --json prints every signal instead.
It is advisory: it never blocks anything.

Exit codes: 0 assessed, 2 no contract (or an unreadable one), 3 no base found or no commit yet, 64 usage
(an unknown option or a --base that does not resolve).
"""
import json
import os
import sys

SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
sys.path.insert(0, os.path.realpath(SHARED))
import contract  # noqa: E402
import paths  # noqa: E402
import ui_check  # noqa: E402

LOCKFILES = ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "poetry.lock", "Cargo.lock", "go.sum")
DOCS = ("**/*.md", "docs")
DEFAULT_ONE_WAY = [{"why": "database migration", "paths": ["**/migrations/**"]}]
# Complexity bands, on source files only.
LOW_MAX_LINES = 150
LOW_MAX_FILES = 5
HIGH_ABOVE_LINES = 600
HIGH_ABOVE_FILES = 20
# Areas from which a change counts as a wide blast radius on its own.
WIDE_AREAS = 3
SHORT_SHA = 12
# Paths named per one-way reason before the rest is counted.
NAMED_PATHS = 3


class Usage(Exception):
    pass


class Unusable(Exception):
    pass


# Inputs: the contract, the base, the diff.

def load_contract(root):
    path = contract.locate(root)
    if not path:
        print("no pothos contract for this repository; run /pothos:plant", file=sys.stderr)
        sys.exit(2)
    try:
        return contract.load(path)
    except json.JSONDecodeError as exc:
        print(f"the contract at {path} is not valid JSON ({exc}); run /pothos:plant", file=sys.stderr)
        sys.exit(2)


def merge_base(root, ref):
    return contract.git(["merge-base", ref, "HEAD"], root)


def resolve_base(root, data, explicit):
    """(the base as named, the merge-base commit). --base must resolve; pr.base falls back to origin/HEAD."""
    if explicit:
        commit = merge_base(root, explicit)
        if not commit:
            raise Usage(f"base '{explicit}' not found")
        return explicit, commit
    configured = (data.get("pr") or {}).get("base")
    if configured:
        try:
            return configured, ui_check.base_ref(root, data, configured)
        except ValueError:
            pass
    commit = merge_base(root, "origin/HEAD")
    if not commit:
        raise Unusable("no base found: the contract has no pr.base that resolves and there is no origin/HEAD; pass --base")
    return "origin/HEAD", commit


def changed_files(root, base):
    """[{path, added, removed}] between base and HEAD; a binary file counts as zero lines."""
    out = contract.git(["-c", "core.quotepath=off", "diff", "--numstat", "--no-renames", base, "HEAD"], root) or ""
    files = []
    for line in out.splitlines():
        added, removed, path = line.split("\t", 2)
        files.append({"path": path, "added": int(added) if added.isdigit() else 0,
                      "removed": int(removed) if removed.isdigit() else 0})
    return files


def is_dirty(root):
    return bool(contract.git(["status", "--porcelain", "--untracked-files=normal"], root))


# Signals.

def classify(path, risk):
    if os.path.basename(path) in LOCKFILES or paths.matches_any(path, risk.get("generated") or []):
        return "generated"
    if paths.is_test_file(path):
        return "test"
    if paths.matches_any(path, DOCS):
        return "docs"
    return "source"


def matching(entries, key, files):
    """The entries whose globs match at least one of the files, with the paths each one matched."""
    found = []
    for entry in entries:
        hits = [f["path"] for f in files if paths.matches_any(f["path"], entry["paths"])]
        if hits:
            found.append({key: entry[key], "paths": hits})
    return found


def door(files, risk):
    reasons = matching(risk.get("one_way") or DEFAULT_ONE_WAY, "why", files)
    return {"kind": "one-way" if reasons else "two-way", "reasons": reasons,
            "default": not risk.get("one_way")}


def area_of(path, apps):
    for app in apps:
        folder = app["path"].rstrip("/")
        if path == folder or path.startswith(folder + "/"):
            return app["name"]
    return path.split("/", 1)[0] if "/" in path else "(root)"


def blast_radius(files, data, risk):
    apps = (data.get("run") or {}).get("apps") or []
    source = [f for f in files if f["class"] == "source"]
    reach = [f for f in files if f["class"] in ("source", "generated")]
    areas = sorted({area_of(f["path"], apps) for f in source})
    surfaces = matching(risk.get("contract") or [], "name", reach)
    core = matching(risk.get("core") or [], "name", reach)
    if len(areas) >= WIDE_AREAS or (surfaces and core):
        radius = "wide"
    elif len(areas) <= 1 and not surfaces and not core:
        radius = "narrow"
    else:
        radius = "medium"
    return {"radius": radius, "areas": areas, "contract": surfaces, "core": core,
            "core_declared": bool(risk.get("core"))}


def complexity(files):
    source = [f for f in files if f["class"] == "source"]
    added = sum(f["added"] for f in source)
    removed = sum(f["removed"] for f in source)
    lines = added + removed
    if lines > HIGH_ABOVE_LINES or len(source) > HIGH_ABOVE_FILES:
        level = "High"
    elif lines <= LOW_MAX_LINES and len(source) <= LOW_MAX_FILES:
        level = "Low"
    else:
        level = "Medium"
    folders = {os.path.dirname(f["path"]) or "." for f in source}
    return {"level": level, "files": len(source), "added": added, "removed": removed, "lines": lines,
            "folders": len(folders)}


def tests(files):
    changed = [f for f in files if f["class"] == "test"]
    return {"files": len(changed), "added": sum(f["added"] for f in changed), "removed": sum(f["removed"] for f in changed)}


def read_receipt(root, commit, level):
    try:
        with open(os.path.join(paths.receipt_dir(root, commit), f"{level}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def full_status(receipt):
    """passed, failed, dirty (passed on uncommitted changes, which never counts) or none."""
    if not receipt:
        return "none"
    if receipt.get("status") == "passed":
        return "dirty" if receipt.get("dirty") else "passed"
    return receipt.get("status") or "none"


def mutation_status(receipt):
    if not receipt:
        return {"status": "none", "new_survivors": None}
    new = [f for f in receipt.get("findings") or [] if f.get("kind") == "new"]
    counted = receipt.get("status") in ("clean", "findings")
    return {"status": receipt.get("status") or "none", "new_survivors": len(new) if counted else None}


def evidence(root, head):
    folder = paths.evidence_dir(root)
    captured = os.path.isdir(folder) and any(os.scandir(folder))
    return {"full": full_status(read_receipt(root, head, "full")),
            "mutation": mutation_status(read_receipt(root, head, "mutation")),
            "evidence_folder": captured}


# Suggestions.

def suggested_risk(door_, radius, size):
    """The level and the reasons behind it."""
    one_way, core, wide, big = door_["kind"] == "one-way", bool(radius["core"]), radius["radius"] == "wide", size["level"] == "High"
    if one_way and core:
        return "High", ["one-way door and a core area touched"]
    if one_way and wide:
        return "High", ["one-way door with a wide blast radius"]
    if core and big:
        return "High", ["high complexity in a core area"]
    reasons = [why for flag, why in ((one_way, "one-way door"), (core, "core area touched"),
                                     (wide, "wide blast radius"), (big, "high complexity")) if flag]
    return ("Medium", reasons) if reasons else ("Low", [])


def confidence_ceiling(signals, size, tested):
    """The highest confidence the evidence allows, and what holds it down."""
    if signals["full"] != "passed":
        return "Low", [{"none": "no full verify receipt for HEAD", "failed": "full verify failed on HEAD",
                        "dirty": "full verify ran on uncommitted changes"}.get(signals["full"], f"full verify {signals['full']}")]
    reasons = []
    if size["files"] and not (tested["added"] or tested["removed"]):
        reasons.append("source changed with no test lines changed")
    if signals["mutation"]["new_survivors"]:
        reasons.append(f"{signals['mutation']['new_survivors']} new mutation survivor(s)")
    if size["level"] == "High":
        reasons.append("high complexity")
    return ("Medium", reasons) if reasons else ("High", [])


def assess(root, data, explicit):
    head = contract.git(["rev-parse", "HEAD"], root)
    if not head:
        raise Unusable("no commit yet")
    risk = (data.get("pr") or {}).get("risk") or {}
    base, base_commit = resolve_base(root, data, explicit)
    files = changed_files(root, base_commit)
    for f in files:
        f["class"] = classify(f["path"], risk)
    door_, radius, size, tested = door(files, risk), blast_radius(files, data, risk), complexity(files), tests(files)
    signals = evidence(root, head)
    level, why = suggested_risk(door_, radius, size)
    ceiling, held = confidence_ceiling(signals, size, tested)
    return {"base": base, "merge_base": base_commit, "head": head, "dirty": is_dirty(root), "files": files,
            "door": door_, "blast_radius": radius, "complexity": size, "tests": tested, "evidence": signals,
            "suggested": {"risk": level, "risk_reasons": why, "confidence_ceiling": ceiling, "ceiling_reasons": held}}


# Output.

def door_line(door_):
    if door_["kind"] == "two-way":
        return "two-way."
    return "one-way: " + "; ".join(f"{r['why']} ({named(r['paths'])})" for r in door_["reasons"]) + "."


def named(found):
    shown = ", ".join(f"`{p}`" for p in found[:NAMED_PATHS])
    return shown + (f" and {len(found) - NAMED_PATHS} more" if len(found) > NAMED_PATHS else "")


def radius_line(radius):
    areas = ", ".join(radius["areas"]) or "no source files"
    surfaces = "".join(f"; {s['name']} changed" for s in radius["contract"])
    return f"{radius['radius']}: {areas}{surfaces}."


def core_line(radius):
    if not radius["core_declared"]:
        return "none declared in the contract."
    return (", ".join(c["name"] for c in radius["core"]) or "none touched") + "."


def size_line(size, tested):
    folders = f" in {size['folders']} folder{'s' if size['folders'] != 1 else ''}" if size["files"] else ""
    test_part = f"tests +{tested['added']} / -{tested['removed']}" if tested["files"] else "no test changes"
    return (f"{size['files']} source file{'s' if size['files'] != 1 else ''}, +{size['added']} / -{size['removed']}"
            f"{folders}; {test_part}.")


def evidence_line(signals, head):
    full = {"passed": f"full verify passed on {head[:SHORT_SHA]}", "failed": f"full verify failed on {head[:SHORT_SHA]}",
            "dirty": f"full verify ran on uncommitted changes at {head[:SHORT_SHA]}",
            "none": f"no full verify for {head[:SHORT_SHA]}"}.get(signals["full"], f"full verify {signals['full']}")
    mutation = signals["mutation"]
    if mutation["new_survivors"] is not None:
        mutation_part = f"mutation: {mutation['new_survivors']} new survivor{'s' if mutation['new_survivors'] != 1 else ''}"
    else:
        mutation_part = f"mutation: {mutation['status']}"
    return f"{full}; {mutation_part}; evidence: {'captured' if signals['evidence_folder'] else 'none'}."


def markdown(result):
    s = result["suggested"]
    ceiling = s["confidence_ceiling"]
    held = "; ".join(s["ceiling_reasons"]) or "nothing in the evidence holds it down"
    return "\n".join([
        "## Risk",
        "",
        f"**Risk:** {s['risk']} · **Complexity:** {result['complexity']['level']} · **Confidence:** {ceiling}",
        "",
        f"- **Door:** {door_line(result['door'])}",
        f"- **Blast radius:** {radius_line(result['blast_radius'])}",
        f"- **Core:** {core_line(result['blast_radius'])}",
        f"- **Size:** {size_line(result['complexity'], result['tests'])}",
        f"- **Evidence:** {evidence_line(result['evidence'], result['head'])}",
        "",
        f"<!-- Confidence ceiling {ceiling}: {held}. Replace with two lines: why it is not higher, and what would raise it. -->",
    ])


def notes(result):
    """What the reader of the output should know that does not belong in the pull request body."""
    lines = []
    if result["dirty"]:
        lines.append("risk: the working tree has uncommitted changes; they are not assessed, commit them first")
    if not result["blast_radius"]["core_declared"]:
        lines.append("risk: the contract declares no core areas; add pr.risk.core with /pothos:plant audit")
    if result["door"]["kind"] == "one-way" and result["door"]["default"]:
        lines.append("risk: one-way door from the default rule (**/migrations/**); pr.risk.one_way replaces it")
    return lines


def parse_assess(args):
    explicit, as_json, i = None, False, 0
    while i < len(args):
        if args[i] == "--json":
            as_json = True
        elif args[i] == "--base" and i + 1 < len(args):
            explicit = args[i + 1]
            i += 1
        else:
            raise Usage(f"unknown option '{args[i]}'")
        i += 1
    return explicit, as_json


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 64
    try:
        if argv[0] != "assess":
            raise Usage(f"unknown command '{argv[0]}'")
        explicit, as_json = parse_assess(argv[1:])
        root = contract.repo_root(os.getcwd())
        data = load_contract(root)
        result = assess(root, data, explicit)
    except Usage as exc:
        print(f"{exc}\nusage: risk.py assess [--base REF] [--json]", file=sys.stderr)
        return 64
    except Unusable as exc:
        print(str(exc), file=sys.stderr)
        return 3
    for line in notes(result):
        print(line, file=sys.stderr)
    print(json.dumps(result, indent=2) if as_json else markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
