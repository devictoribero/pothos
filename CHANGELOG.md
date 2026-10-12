# Changelog

## Unreleased

- `onboard` is now `plant` (`/pothos:plant`); asking to onboard a repository still starts it.
- Renamed from devflow to Pothos: commands are `/pothos:<skill>`, the home folder is `~/.config/pothos` (`POTHOS_HOME`), the contract's default workflow value is `pothos`, and the unattended runner is `pothos-run.py`.
- Every step of the cycle starts from plain language: `vendor.json` can mark a vendored skill `model_invocable` and append `triggers` to its description, re-applied on every update.
- Coding standards are read before writing code, not only in review; UI work loads `component-design` first; the contract's new `build.skills` lists repository skills to load before writing code.
- Repositories with `workflow: repo` still get the owner's personal standards, below the repository's own, and only the skills that compete with their workflow are off limits.
- `onboard` asks which screenshots each app supports (`run.screenshots`: web, iOS simulator or none) and maps monorepo apps to `run.apps`; `evidence.py plan` reads both, so evidence never retries screenshots an app cannot take.
- `verify` runs slow checks detached (exit 4, `verify wait`); `pothos-run.py` resumes headless sessions until they write `report.md`.

## 0.2.0

- Pothos now runs the cycle with Matt Pocock's skills, vendored unchanged at a pinned commit: `grilling`, `grill-with-docs`, `to-spec`, `to-tickets`, `wayfinder`, `triage`, `implement`, `implement-spec`, `tdd`, `code-review`, `pr`, `prototype`, `diagnosing-bugs`, `retro`, `domain-modeling`, `codebase-design`, `improve-codebase-architecture`, `handoff`, `writing-for-agents`. His setup skill is left out because it writes into the repository; its templates are kept as shared data.
- SessionStart hook (`shared/session_context.py`): hands the private contract to every skill as context (tracker, triage labels, domain docs, verify commands, environments, standards, review skills, pull request rules). Repositories with `workflow: repo` get a note that keeps the cycle skills out.
- `verify` skill: runs the contract's checks and keeps a receipt per commit outside the repository; `check` is the merge gate.
- `evidence` skill: starts the app, takes headless or simulator screenshots into a per-branch folder outside the repository, and guides before/after proof for the pull request.
- `component-design` skill moves into the plugin.
- Standards read by `code-review`, `tdd` and `implement`: `standards/testing.md` (replaces a testing skill that measured no better than no skill at twice the cost) and `standards/review.md` (28 rules distilled from 260 past review comments). Personal standards can also live in `~/.config/pothos/standards/`.
- Contract: `tracker.kind` `gitlab`, `tracker.labels` and `review.standards`.
- `onboard` can start on its own and reads existing Pocock setup files. The side-effects principle now gates the publishing step, not the skill.
- `vendor_sync.py` clones each source once per run and rejects unknown entry names.

## 0.1.0

- Plugin and marketplace skeleton.
- Agent contract v1: JSON schema and `shared/contract.py` to locate, read, write and validate it. Contracts are private, stored in `~/.config/pothos/contracts/<host>/<owner>/<repo>.json` and shared by every clone and worktree of a repository; nothing is written inside the repository.
- Contract fields `docs.glossary` (GLOSSARY.md, or CONTEXT.md in older repos) and tracker kind `local` for markdown tickets under `.scratch/`.
- Contract `workflow: repo` to make Pothos stand aside in a repository that follows its own process, and `run.environments` for repos that run against several backends.
- `archify` skill: pinned copy of tt-a1i/archify (MIT), with `vendor.json`, `scripts/vendor_sync.py` and a weekly workflow that opens a pull request when upstream moves.
- `explain` investigates code questions with a pinned copy of poteto/how (MIT): simple questions use one explainer, complex ones fan out to parallel Explore agents and a synthesis, and "critique" adds read-only critics on different models. `references/codebase-questions.md` adapts it from Cursor to Claude Code and sends the result to the page instead of the chat. New evals for a complex flow and a critique.
- `explain` sidebar: every page loads a shared `nav.js` listing all pages of the repository, children nested under their parent (`--parent`, `artifact.py parent`), and the current page's sections and diagrams; `register` rebuilds it so older pages stay current.
- `explain` skill: local HTML explanations with light theme by default, dark toggle and archify diagrams, stored privately under `~/.config/pothos/artifacts/` with a `summary.md` per page and an `INDEX.md` per repository, opened in Brave.
- `docs/work-model.md`: spec, plan and ticket; the outer and inner loops; sessions and orchestration.
- `onboard` skill: detects a repository's scripts, docs, CI and tracker, saves the private contract and reports readiness gaps. Includes an audit mode.
