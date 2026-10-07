# Changelog

## 0.1.0

- Plugin and marketplace skeleton.
- Agent contract v1: JSON schema and `shared/contract.py` to locate, read and validate it.
- Contract fields `docs.glossary` (GLOSSARY.md, or CONTEXT.md in older repos) and tracker kind `local` for markdown tickets under `.scratch/`.
- `docs/work-model.md`: spec, plan and ticket; the outer and inner loops; sessions and orchestration.
- `onboard` skill: detects a repository's scripts, docs, CI and tracker, writes the contract, links it from AGENTS.md and reports readiness gaps. Includes an audit mode.
