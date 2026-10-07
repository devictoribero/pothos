# Changelog

## 0.1.0

- Plugin and marketplace skeleton.
- Agent contract v1: JSON schema and `shared/contract.py` to locate, read, write and validate it. Contracts are private, stored in `~/.config/devflow/contracts/<host>/<owner>/<repo>.json` and shared by every clone and worktree of a repository; nothing is written inside the repository.
- Contract fields `docs.glossary` (GLOSSARY.md, or CONTEXT.md in older repos) and tracker kind `local` for markdown tickets under `.scratch/`.
- `docs/work-model.md`: spec, plan and ticket; the outer and inner loops; sessions and orchestration.
- `onboard` skill: detects a repository's scripts, docs, CI and tracker, saves the private contract and reports readiness gaps. Includes an audit mode.
