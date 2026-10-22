# Pothos

A portable development workflow for Claude Code. It carries how you work from repository to repository: specify, implement, verify, review and ship. Each repository describes itself in a small contract, so the same skills work in any codebase.

> Status: early. Version 0.2.0 runs the whole cycle: Matt Pocock's skills for specifying, planning, building and reviewing, plus Pothos's own contract, verification, evidence and explanations.

## Install

```
/plugin marketplace add devictoribero/pothos
/plugin install pothos@devictoribero
```

Then, in each repository:

```
/pothos:plant
```

## How it fits together

```
plugin (how you work)  ──reads──▶  private contract  ──points to──▶  repository (the project)
```

- **The plugin** holds skills, standards and four hooks, none of which mention a specific project. Most cycle skills are [Matt Pocock's](https://github.com/mattpocock/skills), vendored unchanged at a pinned commit.
- **The hooks:** the first runs at session start, reads the contract and hands it to every skill as context. Pocock's skills expect their configuration (issue tracker, labels, domain docs) "to have been provided"; his setup skill writes it into the repository, Pothos provides it from the contract instead. The second runs before every shell command and blocks the direct commands that merge a pull request, push to the base branch or add the auto-merge label: merging is a person's decision, carried out only by `tend`'s merge gate. The third runs after every `gh pr create` and assigns the new pull request to the GitHub user who opened it (`@me`). The fourth keeps a plugin you load in place from a git checkout (a marketplace added from a local directory) current: at session start it fetches in the background and fast-forwards the checkout when it is on the remote's default branch, so a merged pull request reaches every repository from the next session without a manual pull. It never touches another branch, a local commit or an uncommitted change the update would overwrite.
- **Verification has two tiers.** The session context tells every skill that edits code to run the repository's fast check after each coherent edit and before each commit (a root `check:fast` script, else the contract's `verify.fast`, else each package's lint, unit tests and type-check), and to run the full gate through `verify` once before a push. The command lives in the repository; the plugin only finds and calls it.
- **The contract** is a short JSON file per repository, kept privately in `~/.config/pothos/contracts/<host>/<owner>/<repo>.json`, never inside the repository. Every clone and worktree of a repository shares it. It says how to verify a change, how to run the app, where the domain docs live, where tickets go and how pull requests are made.
- **The repository** keeps everything project-specific: its scripts, its docs, its conventions and its own skills.

## The contract

```json
{
  "$schema": "https://raw.githubusercontent.com/devictoribero/pothos/main/plugins/pothos/shared/contract.schema.json",
  "version": 1,
  "verify": {
    "fast": "pnpm run type-check && pnpm run lint",
    "full": "pnpm run validate",
    "e2e": "pnpm run e2e"
  },
  "run": { "dev": "pnpm run dev:mock", "url": "http://localhost:3000", "mocked": true },
  "docs": { "glossary": "GLOSSARY.md", "decisions": "docs/decisions", "prd": "docs/prd" },
  "tracker": { "kind": "local", "path": ".scratch" },
  "review": { "skills": ["i18n-review"] },
  "pr": { "base": "main", "template": ".github/pull_request_template.md" }
}
```

Only `version` and `verify.full` are required. The schema documents every field, and editors that read `$schema` autocomplete it.

## Skills

| Step | Skill | From | What it does |
|---|---|---|---|
| Connect a repo | `plant` | Pothos | Writes or audits the private contract and reports what blocks autonomous work. |
| Define | `grilling`, `grill-with-docs` | Pocock | Interview until a plan has no open questions; the second also writes the glossary and decision records. |
| Specify | `to-spec` | Pocock | Turns the conversation into a spec in the tracker. |
| Plan | `to-tickets`, `wayfinder` | Pocock | Tracer-bullet tickets with blocking edges; a decision map for work bigger than one session. |
| Build | `implement`, `implement-spec`, `tdd`, `prototype` | Pocock | One ticket, or a whole spec on an integration branch with implementer subagents in worktrees. |
| Verify | `verify` | Pothos | Runs the contract's checks and keeps a receipt per commit; the merge gate. |
| Prove | `evidence` | Pothos | Screenshots and before/after output for the pull request, stored outside the repo. |
| Review | `code-review` | Pocock | Standards and spec review in parallel subagents. Reads Pothos's standards too. |
| Ship | `pr` | Pocock | Pull request body with summary, evidence and merge danger. |
| Tend | `tend` | Pothos | Babysits a ready pull request: answers review comments, fixes red checks and, when a person authorized it (the auto-merge label, "and merge it", or a `Merge: auto` ticket), merges through a gate once everything is green. |
| Learn | `diagnosing-bugs`, `retro` | Pocock | Find the cause of a bug; look back at a session. |
| Design | `component-design` | Pothos | UI component APIs: composition, naming, accessibility, tests. |
| Design | `codebase-design`, `domain-modeling`, `improve-codebase-architecture` | Pocock | Deep modules, glossary and decision records, architecture improvements. |
| Explain | `explain`, `archify` | Pothos, tt-a1i | Local HTML explanations with diagrams, indexed for later sessions. |
| Other | `triage`, `handoff`, `writing-for-agents` | Pocock | Issue triage, session handoff, writing skills and agent docs. |

## Running unattended

```bash
cd your-repo
python3 ~/path/to/pothos/plugins/pothos/scripts/pothos-run.py spec .scratch/<feature>/issues          # whole spec
python3 ~/path/to/pothos/plugins/pothos/scripts/pothos-run.py ticket .scratch/<feature>/issues/01-x.md  # one ticket
python3 ~/path/to/pothos/plugins/pothos/scripts/pothos-run.py status
```

Each run gets a worktree and branch next to the repository, runs the contract's `run.setup`, and starts a headless session that builds, verifies, reviews and writes the pull request body. Logs and results go to `~/.config/pothos/runs/`. Add `--open-pr` to let it push and open a draft pull request; nothing ever merges into the base branch.

## Standards

`plugins/pothos/standards/` holds personal coding standards that `code-review`, `tdd` and `implement` read through the session context. A repository's own documented standards win on conflict.

- `testing.md`: what makes a test trustworthy, kept to the rules that measurably changed results.
- `review.md`: what blocks a merge and what is only recommended, distilled from past reviews.

Add your own in `~/.config/pothos/standards/*.md`; the hook lists them too.

## Developing

```bash
claude --plugin-dir plugins/pothos      # try changes without reinstalling
python3 -m unittest discover -s tests              # script tests
python3 scripts/lint_skills.py                     # skill checks
python3 scripts/vendor_sync.py check               # pinned third-party skills behind upstream?
claude plugin validate plugins/pothos    # manifest checks
claude plugin eval plugins/pothos --scaffold --allow-tools Bash Write Edit   # evals, costs tokens
```

[PRINCIPLES.md](PRINCIPLES.md) explains the rules every change follows. [docs/work-model.md](docs/work-model.md) explains the artifacts (spec, plan, ticket), the outer and inner loops, and who orchestrates them.

## License

MIT
