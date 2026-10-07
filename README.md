# devflow

A portable development workflow for Claude Code. It carries how you work from repository to repository: specify, implement, verify, review and ship. Each repository describes itself in a small contract, so the same skills work in any codebase.

> Status: early. Version 0.1.0 ships the private contract and three skills: `onboard`, `explain` and the bundled `archify`. The rest of the cycle, agents and hooks are planned.

## Install

```
/plugin marketplace add devictoribero/devflow
/plugin install devflow@devictoribero
```

Then, in each repository:

```
/devflow:onboard
```

## How it fits together

```
plugin (how you work)  ──reads──▶  private contract  ──points to──▶  repository (the project)
```

- **The plugin** holds skills (and, later, agents and hooks) that never mention a specific project.
- **The contract** is a short JSON file per repository, kept privately in `~/.config/devflow/contracts/<host>/<owner>/<repo>.json`, never inside the repository. Every clone and worktree of a repository shares it. It says how to verify a change, how to run the app, where the domain docs live, where tickets go and how pull requests are made.
- **The repository** keeps everything project-specific: its scripts, its docs, its conventions and its own skills.

## The contract

```json
{
  "$schema": "https://raw.githubusercontent.com/devictoribero/devflow/main/plugins/devflow/shared/contract.schema.json",
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

| Skill | Status | What it does |
|---|---|---|
| `onboard` | available | Writes or audits the repository's contract and reports what blocks autonomous work. |
| `explain` | available | Explains a flow, architecture or concept as a local HTML page with archify diagrams, opened in the browser and indexed so later sessions can find it. |
| `archify` | available, third-party | Draws validated, explorable architecture, workflow, sequence, data-flow and lifecycle diagrams. Pinned copy of [tt-a1i/archify](https://github.com/tt-a1i/archify); explain uses it. |
| `grill` | planned | Interviews you until a task has no open questions. |
| `distill` | planned | Turns a conversation, thread or note into tickets or a PRD with checkable acceptance criteria. |
| `domain-model` | planned | Keeps the ubiquitous-language glossary and decision records. |
| `implement` | planned | Takes one ticket or a whole feature. For a feature it creates the feature branch and works through the ticket graph, running the inner loop for every unblocked ticket. |
| `code` | planned | Writes the code and tests for one ticket. The inner loop runs it; you rarely type it. |
| `diagnose` | planned | Finds the cause of a bug by building a feedback loop first. |
| `verify` | planned | Runs the contract's checks and records a receipt for the commit. |
| `evidence` | planned | Runs the app and captures proof that a change works. |
| `review` | planned | Reviews a diff with fresh-context agents and validates each finding. |
| `pull-request` | planned | Opens a pull request once verify and evidence hold for the current commit. |
| `address-review` | planned | Applies, declines or escalates each review comment. |
| `component-design`, `testing`, `codebase-design`, `improve-architecture`, `writing` | planned | Knowledge skills that apply automatically. |

## Developing

```bash
claude --plugin-dir plugins/devflow      # try changes without reinstalling
python3 -m unittest discover -s tests              # script tests
python3 scripts/lint_skills.py                     # skill checks
claude plugin validate plugins/devflow    # manifest checks
claude plugin eval plugins/devflow --scaffold   # evals, costs tokens
```

[PRINCIPLES.md](PRINCIPLES.md) explains the rules every change follows. [docs/work-model.md](docs/work-model.md) explains the artifacts (spec, plan, ticket), the outer and inner loops, and who orchestrates them.

## License

MIT
