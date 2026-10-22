---
name: plant
description: Connect a repository to Pothos by writing its private agent contract, which tells the other skills how the repo is verified, run, documented and shipped. The contract lives outside the repository, so the repo and its team see no change. Use it the first time Pothos works in a repo, when the session context says the repository has no contract and the task needs one, when asked to onboard, connect or set up a repository for Pothos, or with "audit" to check an existing contract for drift.
argument-hint: "[audit]"
---

# plant

Plant Pothos in a repository: write or audit the repository's agent contract, the only place where Pothos learns project specifics. Every other skill reads the contract; none of them hardcode a command, path or tracker.

The contract is private. It lives under `~/.config/pothos/contracts/`, keyed by the repository's origin remote, so every clone and worktree of the repo shares it. `shared/contract.py` decides the location; never write the file yourself.

**Output:** a saved contract that passes strict validation, and a readiness report listing what still blocks autonomous work. The repository is left exactly as it was.

## Rules

- Never create, edit or delete a file inside the repository. Not AGENTS.md, not CLAUDE.md, not `.agents/`. `git status` must be unchanged when you finish.
- Never invent a command. Every command in the contract must come from the detection report: a declared script, or scripts chained with `&&`. If a role has no candidate, leave the field out and report it as a gap.
- Ask only when the detection report leaves a real choice, such as two dev scripts or no obvious verify command. When nobody can answer, apply the rules in `references/mapping.md`, and list each assumption in the report.

If the user says the repository follows its own workflow, skip the steps: save `{"version": 1, "workflow": "repo"}` with `contract.py write` and say that Pothos will stand aside in this repo.

## Steps

1. **Detect.** Run the detection script from the repository root and read its JSON:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/detect.py" .
   ```
   If `existing_contract` is set, or the argument is `audit`, follow **Audit mode** instead.
2. **Read context.** Skim AGENTS.md or CLAUDE.md, any `docs/agents/*.md` files, and the CI files the report lists. They settle what the word hits in `tracker_hints` cannot, such as "we do not use Jira".
3. **Draft.** Map the report to contract fields with `references/mapping.md`. Start from `${CLAUDE_PLUGIN_ROOT}/templates/contract.json` and drop every field you cannot fill.
4. **Confirm.** Show the draft and its assumptions in one message, and ask about the open choices only. Always ask which screenshots each app supports (`run.screenshots`, and per app in a monorepo): evidence relies on it to avoid trying what cannot work. In a repository with UI, show the `ui` section and ask about any folder or icon set the mapping left open. Skip this step when the user asked for no questions or nobody is available.
5. **Save.** Pipe the draft to the contract script, which validates it strictly and saves it only if it is valid:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/shared/contract.py" write <<'JSON'
   { ...the draft... }
   JSON
   ```
   Fix and re-run until it prints `ok: saved`.
6. **Smoke-run.** Run `verify.fast`, or `verify.full` when there is no fast command, once. Record whether it passed, failed on code, or could not start because of the environment, such as a missing tool or credentials. Do not try to fix a failure.
7. **Report.** Print the readiness report from `references/report.md`.

## Audit mode

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/shared/contract.py" validate --strict` and the detection script.
2. Compare them. Drift means a command that names a script that no longer exists, a path that no longer exists (including `ui` folders and token files), a UI the contract has no `ui` section for, CI that now runs scripts `verify.full` does not, or a new e2e tool, mutation tool or docs folder the contract ignores.
3. Report each drift with a proposed fix. Apply the fixes with `contract.py write` only after the user confirms. Without a user, change nothing and report.
4. End with the readiness report.

## Next step

Tell the user which gap to close first. The verification gaps come before everything else, because no other skill can prove its work without them.
