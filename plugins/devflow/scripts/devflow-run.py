#!/usr/bin/env python3
"""Run devflow's inner loop unattended: one headless Claude Code session in a fresh worktree.

Usage:
  devflow-run.py spec TICKETS [--slug SLUG] [--base BRANCH] [--open-pr] [--model MODEL] [--dry-run]
      Build every ticket under TICKETS (a local tracker folder, or a tracker reference) with
      /devflow:implement-spec on a new integration branch feature/<slug>.
  devflow-run.py ticket TICKET [--slug SLUG] [--base BRANCH] [--open-pr] [--model MODEL] [--dry-run]
      Build one ticket with /devflow:implement on a new branch ticket/<slug>.
  devflow-run.py status
      List this repository's runs, newest first, with their state and final line.

Run it from inside the repository. Each run gets its own worktree next to the repository
(<repo>-devflow/<slug>), runs the contract's run.setup there, and logs to
$DEVFLOW_HOME/runs/<host>/<owner>/<repo>/<timestamp>-<slug>/ (session.jsonl, result.md, meta.json).

Without --open-pr the run never pushes: it writes the pull request body to result folder's
pr-body.md and stops. With --open-pr it pushes the branch and opens a draft pull request.
Nothing ever merges into the base branch.

Exit codes: 0 the session finished, 1 the session failed, 2 no contract, 3 contract or git state
unusable, 64 usage.
"""
import datetime
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "shared"))
import contract  # noqa: E402

PROMPTS = {
    "spec": (
        "/devflow:implement-spec Tickets: {target}. The integration branch already exists and is checked out in this "
        "worktree: {branch}, based on {base}; use it instead of creating another. Nobody is available to answer questions: "
        "make reasonable choices and record them on the tickets; a ticket that cannot be built as written gets "
        "needs-replan with what you found, and you carry on with the rest of the frontier. {publish}"
    ),
    "ticket": (
        "/devflow:implement {target}. Work on the branch checked out in this worktree, {branch}, based on {base}. "
        "Nobody is available to answer questions: make reasonable choices and record them on the ticket. "
        "When the work is committed, run /devflow:verify and fix until verify check passes. {publish}"
    ),
}
PUBLISH = {
    False: ("Do not push and do not open a pull request. When everything is merged, reviewed and verified, use the pr "
            "skill to write the pull request body, with evidence from /devflow:evidence, to {run}/pr-body.md. Then stop "
            "and report what you did, the commits, the verify line and anything you could not do."),
    True: ("When everything is merged, reviewed and verified, push {branch} and open a draft pull request into {base} "
           "with the pr skill's body and evidence from /devflow:evidence. Never mark it ready and never merge it. "
           "Then stop and report the pull request URL, the commits, the verify line and anything you could not do."),
}


def flag(args, name, default=None):
    if name in args and args.index(name) + 1 < len(args):
        return args[args.index(name) + 1]
    return default


def slugify(text):
    text = os.path.basename(text.rstrip("/")).lower()
    text = re.sub(r"\.md$", "", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48] or "work"


def runs_dir(root):
    return os.path.join(contract.devflow_home(), "runs", contract.key_for(root, "runs"))


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)


def start(kind, args):
    root = contract.repo_root(os.getcwd())
    path = contract.locate(root)
    if not path:
        print("no devflow contract for this repository; run /devflow:onboard first", file=sys.stderr)
        return 2
    data = contract.load(path)
    if data.get("workflow") == "repo":
        print("this repository follows its own workflow (contract workflow: repo)", file=sys.stderr)
        return 3
    target = args[0]
    if kind == "spec" and os.path.isdir(target):
        target = os.path.realpath(target)
    named = target.rstrip("/")
    if os.path.isdir(named) and os.path.basename(named) == "issues":
        named = os.path.dirname(named)  # .scratch/<feature>/issues names the feature, not "issues"
    slug = flag(args, "--slug") or slugify(named)
    base = flag(args, "--base") or (data.get("pr") or {}).get("base") or "main"
    branch = ("feature/" if kind == "spec" else "ticket/") + slug
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run = os.path.join(runs_dir(root), f"{stamp}-{slug}")
    worktree = os.path.join(os.path.dirname(root), os.path.basename(root) + "-devflow", slug)
    open_pr = "--open-pr" in args
    prompt = PROMPTS[kind].format(target=target, branch=branch, base=base,
                                  publish=PUBLISH[open_pr].format(run=run, branch=branch, base=base))
    command = ["claude", "-p", prompt, "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose"]
    if flag(args, "--model"):
        command += ["--model", flag(args, "--model")]
    setup = (data.get("run") or {}).get("setup")
    plan = {"kind": kind, "target": target, "branch": branch, "base": base, "worktree": worktree, "run": run,
            "setup": setup, "open_pr": open_pr, "command": " ".join(shlex.quote(c) for c in command)}
    if "--dry-run" in args:
        print(json.dumps(plan, indent=2))
        return 0
    if os.path.exists(worktree):
        print(f"{worktree} already exists; finish or remove that run first, or pass --slug", file=sys.stderr)
        return 3
    fetched = git(root, "fetch", "-q", "origin", base)
    start_point = f"origin/{base}" if fetched.returncode == 0 else base
    made = git(root, "worktree", "add", "-q", "-b", branch, worktree, start_point)
    if made.returncode:
        print(f"could not create the worktree: {made.stderr.strip()}", file=sys.stderr)
        return 3
    os.makedirs(run, exist_ok=True)
    meta = {**plan, "started": stamp, "state": "running", "pid": os.getpid()}
    write_meta(run, meta)
    print(f"run {run}\nworktree {worktree}\nbranch {branch}", flush=True)
    if setup:
        with open(os.path.join(run, "setup.log"), "w") as log:
            done = subprocess.run(setup, shell=True, cwd=worktree, stdout=log, stderr=subprocess.STDOUT)
        if done.returncode:
            write_meta(run, {**meta, "state": "setup-failed"})
            print(f"run.setup failed; see {run}/setup.log", file=sys.stderr)
            return 1
    with open(os.path.join(run, "session.jsonl"), "w") as out, open(os.path.join(run, "session.err"), "w") as err:
        session = subprocess.run(command, cwd=worktree, stdout=out, stderr=err)
    result, cost = final_result(os.path.join(run, "session.jsonl"))
    with open(os.path.join(run, "result.md"), "w", encoding="utf-8") as fh:
        fh.write(result or "(the session ended without a result message)\n")
    state = "done" if session.returncode == 0 and result else "failed"
    write_meta(run, {**meta, "state": state, "exit": session.returncode, "cost_usd": cost,
                     "finished": datetime.datetime.now().strftime("%Y%m%d-%H%M%S")})
    print(f"{state}: {run}/result.md")
    return 0 if state == "done" else 1


def write_meta(run, meta):
    with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")


def final_result(path):
    result, cost = None, None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                result, cost = event.get("result"), event.get("total_cost_usd")
    return result, cost


def status():
    root = contract.repo_root(os.getcwd())
    folder = runs_dir(root)
    if not os.path.isdir(folder):
        print("no runs yet")
        return 0
    for name in sorted(os.listdir(folder), reverse=True):
        meta_path = os.path.join(folder, name, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        last = ""
        result = os.path.join(folder, name, "result.md")
        if os.path.isfile(result):
            with open(result, encoding="utf-8") as fh:
                lines = [l.strip() for l in fh if l.strip()]
            last = lines[-1][:100] if lines else ""
        cost = f" ${meta['cost_usd']:.2f}" if meta.get("cost_usd") else ""
        print(f"{name}  {meta.get('state')}{cost}  {meta.get('branch')}  {last}")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 64
    if argv[0] == "status":
        return status()
    if argv[0] in PROMPTS and len(argv) >= 2:
        return start(argv[0], argv[1:])
    print(f"usage error; run {os.path.basename(__file__)} --help", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
