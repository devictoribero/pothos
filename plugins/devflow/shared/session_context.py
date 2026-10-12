#!/usr/bin/env python3
"""SessionStart adapter: hand the repository's private contract to every skill as context.

Matt Pocock's skills expect "the issue tracker should have been provided to you"; his setup skill
writes that configuration into the repository. devflow keeps it in the private contract instead, and
this hook prints it as session context, so his skills run unchanged and the repository stays untouched.

Usage: session_context.py [DIR]   (DIR defaults to the cwd in the hook's stdin event, then the process cwd)
Prints a SessionStart hook JSON object, or nothing outside a git repository. Never fails the session:
any error becomes a one-line note in the context and exit code 0.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract  # noqa: E402

TEMPLATES = os.path.join(HERE, "vendor", "pocock-setup")
PLUGIN = os.path.dirname(HERE)
ROLES = ["needs-triage", "needs-info", "ready-for-agent", "ready-for-human", "wontfix"]
COMPETING_SKILLS = ("grill-with-docs, to-spec, to-tickets, wayfinder, triage, implement, implement-spec, code-review, pr, "
                    "verify, evidence")
CYCLE_SKILLS = ("grilling, grill-with-docs, to-spec, to-tickets, wayfinder, triage, implement, implement-spec, "
                "tdd, code-review, pr, prototype, diagnosing-bugs, retro, verify, evidence")


def template(name):
    """A Pocock setup template without its own top heading; this context supplies the heading."""
    with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
        lines = fh.read().strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def demote(markdown, levels=1):
    """Push headings down so templates nest under this context's own headings."""
    return "\n".join("#" * levels + line if line.startswith("#") else line for line in markdown.splitlines())


def main_checkout(start):
    """The main working tree, shared by every worktree of the repository."""
    common = contract.git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start)
    return os.path.dirname(common) if common and os.path.basename(common) == ".git" else contract.repo_root(start)


def tracker_section(data, start):
    tracker = data.get("tracker") or {"kind": "none"}
    kind = tracker.get("kind", "none")
    skill = tracker.get("skill")
    if kind in ("none", "local"):
        path = tracker.get("path") or ".scratch"
        body = template("issue-tracker-local.md").replace(".scratch/", path.rstrip("/") + "/").replace("`.scratch`", f"`{path}`")
        note = "" if kind == "local" else ("The contract names no tracker, so specs and tickets go to local markdown as described here. "
                                           "Mention it once when you first write there.\n\n")
        absolute = os.path.join(main_checkout(start), path)
        text = note + demote(body, 2) + (
            f"\n\nThe tracker folder is shared by every worktree: read and update tickets at `{absolute}/`, "
            "never in a worktree's own copy, and never commit it from a worktree.")
    elif kind in ("github", "gitlab"):
        text = demote(template(f"issue-tracker-{kind}.md"), 2)
    else:
        project = f" project `{tracker['project']}`" if tracker.get("project") else ""
        text = f"Issues and specs live in {kind.capitalize()}{project}."
        if not skill:
            text += (f" No repository skill is configured for {kind.capitalize()}: before writing to it, tell the user "
                     "what you would create and ask how to reach the tracker.")
    if skill:
        text += f"\n\nEvery tracker operation (publish, fetch, comment, label, close) goes through the repository skill `{skill}`."
    return "### Issue tracker\n\n" + text


def labels_section(data):
    labels = ((data.get("tracker") or {}).get("labels")) or {}
    rows = "\n".join(f"| `{role}` | `{labels.get(role, role)}` |" for role in ROLES)
    return ("### Triage labels\n\nWhen a skill names a triage role, use this repository's label for it.\n\n"
            "| Role | Label here |\n|---|---|\n" + rows)


def domain_section(data):
    docs = data.get("docs") or {}
    glossary, decisions = docs.get("glossary"), docs.get("decisions")
    lines = []
    if glossary and glossary != "GLOSSARY.md":
        lines.append(f"- The glossary is `{glossary}`: read it wherever the text below says `GLOSSARY.md`.")
    if decisions and decisions.rstrip("/") != "docs/adr":
        lines.append(f"- Decision records live in `{decisions}`: read them wherever the text below says `docs/adr/`.")
    if docs.get("specs"):
        lines.append(f"- Existing specs and product docs live in `{docs['specs']}`.")
    prefix = ("In this repository:\n" + "\n".join(lines) + "\n\n") if lines else ""
    return "### Domain docs\n\n" + prefix + demote(template("domain.md"), 2)


def verify_section(data):
    verify = data.get("verify") or {}
    rows = [f"- `{level}`: `{verify[level]}`" for level in ("fast", "full", "e2e") if verify.get(level)]
    text = ("### Verification\n\nRun `/devflow:verify` before merging anything into an integration or feature branch and "
            "before a pull request leaves draft; it runs these commands and records a receipt for the commit. "
            "With `implement-spec`, the merger subagent runs `verify run all` on the integration branch after each merge and "
            "hands a red result back to an implementer instead of moving on. "
            "Run the `fast` command yourself while working. Run `full` and `e2e` only through verify, in the foreground: "
            "a background command dies when your turn or subagent ends and nobody is notified. verify keeps slow checks "
            "alive in a detached process; when it exits 4 they are still going, so run `verify.py wait` until it returns "
            "another code.\n\n" + "\n".join(rows))
    if not verify.get("e2e"):
        text += "\n\nThis repository has no end-to-end command; skip that step and say so in the pull request."
    return text


def run_section(data):
    run = data.get("run") or {}
    if not run:
        return None
    lines = []
    if run.get("setup"):
        lines.append(f"- In a fresh clone or worktree, run `{run['setup']}` before anything else, including verify. "
                     "Tell every implementer subagent to do the same in its own worktree.")
    if run.get("dev"):
        mocked = " (mocked backend, no credentials needed)" if run.get("mocked") else ""
        lines.append(f"- Start the app: `{run['dev']}`{mocked}" + (f", served at {run['url']}" if run.get("url") else ""))
    if run.get("login"):
        lines.append(f"- How to log in: see `{run['login']}`")
    envs = run.get("environments") or []
    if envs:
        lines.append("- Backend environments (ask the user which one to use at the start of a feature; never pick one yourself):")
        for env in envs:
            extra = f"; end-to-end: `{env['e2e']}`" if env.get("e2e") else ""
            note = f" ({env['note']})" if env.get("note") else ""
            lines.append(f"  - `{env['name']}`: `{env['dev']}`{extra}{note}")
    return "### Running the app\n\n" + "\n".join(lines) if lines else None


def standards_section(data, repo_workflow=False):
    repo_files = [] if repo_workflow else list(((data.get("review") or {}).get("standards")) or [])
    personal = sorted(glob.glob(os.path.join(PLUGIN, "standards", "*.md")))
    personal += sorted(glob.glob(os.path.join(contract.devflow_home(), "standards", "*.md")))
    build_skills = [] if repo_workflow else list(((data.get("build") or {}).get("skills")) or [])
    if repo_workflow:
        intro = ("The owner's personal coding standards still apply when you write code here, below everything the "
                 "repository documents: where they disagree with the repository's conventions or skills, the repository wins.")
    else:
        intro = ("Read these before writing code and follow them while you write it: `implement`, `implement-spec`'s "
                 "implementers and `tdd` read them first. `code-review` checks the diff against them afterwards, together with "
                 "whatever the repository documents. When a repository file and a personal file disagree, the repository wins.")
    lines = ["### Coding standards", "", intro]
    if repo_files:
        lines += ["", "Repository:"] + [f"- `{path}`" for path in repo_files]
    if personal:
        lines += ["", "Personal (outside the repository):"] + [f"- `{path}`" for path in personal]
    lines += ["", "Before writing code that creates or changes UI components, load the `component-design` skill"
              + (" and follow it unless the repository's own component skills say otherwise." if repo_workflow else ".")]
    if build_skills:
        lines += ["Also load these repository skills before writing code: " + ", ".join(f"`{s}`" for s in build_skills) + "."]
    return "\n".join(lines)


def review_section(data):
    skills = ((data.get("review") or {}).get("skills")) or []
    if not skills:
        return None
    return ("### Repository review skills\n\nAfter `code-review`, also run these repository skills on the same diff and merge "
            "their findings into the report: " + ", ".join(f"`{s}`" for s in skills) + ".")


def pr_section(data):
    pr = data.get("pr") or {}
    lines = ["### Pull requests", "", f"- Base branch: `{pr.get('base', 'main')}`. A whole spec is built on an integration branch "
             "named `feature/<spec-slug>`; only its final pull request into the base branch is for the user to review and merge."]
    if pr.get("template"):
        lines.append(f"- The repository's template `{pr['template']}` wins over the `pr` skill's template; put the evidence "
                     "from `/devflow:evidence` in it.")
    if pr.get("evidence"):
        lines.append(f"- Upload screenshots with `{pr['evidence']}`; it prints markdown to embed.")
    lines.append("- Never merge into the base branch yourself.")
    return "\n".join(lines)


def build(start):
    if not contract.git(["rev-parse", "--git-dir"], start):
        return None
    try:
        path = contract.locate(start)
    except ValueError as exc:
        return f"## devflow\n\nCould not resolve this repository's contract: {exc}"
    if not path:
        return ("## devflow\n\nThis repository has no devflow contract yet. Skills that need an issue tracker, verify commands "
                "or a run command (" + CYCLE_SKILLS + ") should run `/devflow:onboard` first (it shows the draft contract to the user before saving). "
                "Never run `/setup-matt-pocock-skills`: devflow keeps that configuration out of the repository.")
    try:
        data = contract.load(path)
    except (OSError, json.JSONDecodeError) as exc:
        return f"## devflow\n\nThe contract at `{path}` could not be read ({exc}). Suggest `/devflow:onboard` to repair it."
    if data.get("workflow") == "repo":
        return ("## devflow\n\nThis repository follows its own development workflow: its own skills, CLAUDE.md and conventions. "
                "Do not use the devflow skills that would compete with it (" + COMPETING_SKILLS + ") unless the user names one "
                "explicitly; use the repository's own skills for tickets, implementation, verification, review and pull requests. "
                "Skills that do not own a step of the workflow are fine: grilling, diagnosing-bugs, prototype, tdd, codebase-design, "
                "domain-modeling, component-design, retro, explain and archify.\n\n" + standards_section(data, repo_workflow=True))
    errors = contract.check(data, start, strict=False)
    sections = [
        "## devflow: this repository's contract",
        f"The configuration below comes from the private contract `{path}`, which lives outside the repository. "
        "It is the configuration Matt Pocock's skills expect to be provided: never run `/setup-matt-pocock-skills`, "
        "and never write `docs/agents/` files or an `## Agent skills` block into the repository.",
    ]
    if errors:
        sections.append("The contract has problems; mention them and suggest `/devflow:onboard`:\n" + "\n".join(f"- {e}" for e in errors))
    sections.append(tracker_section(data, start))
    for part in (labels_section, domain_section, verify_section, run_section,
                 standards_section, review_section, pr_section):
        text = part(data)
        if text:
            sections.append(text)
    return "\n\n".join(sections)


def hook_cwd():
    """The hook receives its event as JSON on stdin; its cwd field is the session's directory."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    try:
        return json.loads(sys.stdin.read() or "{}").get("cwd")
    except (ValueError, AttributeError):
        return None


def main(argv):
    start = argv[0] if argv else (hook_cwd() or os.getcwd())
    try:
        text = build(start)
    except Exception as exc:  # the hook must never break a session
        text = f"## devflow\n\nThe contract adapter failed ({type(exc).__name__}: {exc}); continue without it."
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
