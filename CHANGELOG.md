# Changelog

## 0.1.0

- Plugin and marketplace skeleton.
- Agent contract v1: JSON schema and `shared/contract.py` to locate, read, write and validate it. Contracts are private, stored in `~/.config/devflow/contracts/<host>/<owner>/<repo>.json` and shared by every clone and worktree of a repository; nothing is written inside the repository.
- Contract fields `docs.glossary` (GLOSSARY.md, or CONTEXT.md in older repos) and tracker kind `local` for markdown tickets under `.scratch/`.
- Contract `workflow: repo` to make devflow stand aside in a repository that follows its own process, and `run.environments` for repos that run against several backends.
- `archify` skill: pinned copy of tt-a1i/archify (MIT), with `vendor.json`, `scripts/vendor_sync.py` and a weekly workflow that opens a pull request when upstream moves.
- `explain` sidebar: every page loads a shared `nav.js` listing all pages of the repository, children nested under their parent (`--parent`, `artifact.py parent`), and the current page's sections and diagrams; `register` rebuilds it so older pages stay current.
- `explain` skill: local HTML explanations with light theme by default, dark toggle and archify diagrams, stored privately under `~/.config/devflow/artifacts/` with a `summary.md` per page and an `INDEX.md` per repository, opened in Brave.
- `docs/work-model.md`: spec, plan and ticket; the outer and inner loops; sessions and orchestration.
- `onboard` skill: detects a repository's scripts, docs, CI and tracker, saves the private contract and reports readiness gaps. Includes an audit mode.
