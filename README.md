# development-flow

A portable development workflow for Claude Code. It carries how you work from repository to repository: specify, implement, verify, review and ship. Each repository describes itself in a small contract, so the same skills work in any codebase.

> Status: early. Version 0.1.0 ships the contract and the `onboard` skill. The rest of the cycle is in progress.

## Install

```
/plugin marketplace add devictoribero/development-flow
/plugin install development-flow@devictoribero
```

Then, in each repository:

```
/development-flow:onboard
```

## How it fits together

```
plugin (how you work)  ──reads──▶  .agents/contract.json  ──points to──▶  repository (the project)
```

- **The plugin** holds skills, agents and hooks that never mention a specific project.
- **The contract** is a short JSON file in each repository. It says how to verify a change, how to run the app, where the domain docs live, where tickets go and how pull requests are made.
- **The repository** keeps everything project-specific: its scripts, its docs, its conventions and its own skills.

## The contract

```json
{
  "$schema": "https://raw.githubusercontent.com/devictoribero/development-flow/main/plugins/development-flow/shared/contract.schema.json",
  "version": 1,
  "verify": {
    "fast": "pnpm run type-check && pnpm run lint",
    "full": "pnpm run validate",
    "e2e": "pnpm run e2e"
  },
  "run": { "dev": "pnpm run dev:mock", "url": "http://localhost:3000", "mocked": true },
  "docs": { "context": "CONTEXT.md", "decisions": "docs/decisions", "prd": "docs/prd" },
  "tracker": { "kind": "none" },
  "review": { "skills": ["i18n-review"] },
  "pr": { "base": "main", "template": ".github/pull_request_template.md" }
}
```

Only `version` and `verify.full` are required. The schema documents every field, and editors that read `$schema` autocomplete it.

## Skills

| Skill | Status | What it does |
|---|---|---|
| `onboard` | available | Writes or audits the repository's contract and reports what blocks autonomous work. |
| `grill` | planned | Interviews you until a task has no open questions. |
| `distill` | planned | Turns a conversation, thread or note into tickets or a PRD with checkable acceptance criteria. |
| `domain-model` | planned | Keeps the ubiquitous-language glossary and decision records. |
| `implement` | planned | Builds a defined task with tests. |
| `diagnose` | planned | Finds the cause of a bug by building a feedback loop first. |
| `verify` | planned | Runs the contract's checks and records a receipt for the commit. |
| `evidence` | planned | Runs the app and captures proof that a change works. |
| `review` | planned | Reviews a diff with fresh-context agents and validates each finding. |
| `pull-request` | planned | Opens a pull request once verify and evidence hold for the current commit. |
| `address-review` | planned | Applies, declines or escalates each review comment. |
| `component-design`, `testing`, `codebase-design`, `improve-architecture`, `writing` | planned | Knowledge skills that apply automatically. |

## Developing

```bash
claude --plugin-dir plugins/development-flow      # try changes without reinstalling
python3 -m unittest discover -s tests              # script tests
python3 scripts/lint_skills.py                     # skill checks
claude plugin validate plugins/development-flow    # manifest checks
claude plugin eval plugins/development-flow --scaffold   # evals, costs tokens
```

[PRINCIPLES.md](PRINCIPLES.md) explains the rules every change follows.

## License

MIT
