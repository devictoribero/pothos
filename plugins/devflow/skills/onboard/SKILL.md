---
name: onboard
description: Connect a repository to devflow by writing its agent contract (.agents/contract.json), which tells the other skills how the repo is verified, run, documented and shipped. Run it the first time you use devflow in a repo, or again to audit an existing contract for drift. Use when the user says "onboard this repo", "set up devflow", "create the agent contract", "audit the contract", or when another devflow skill reports that no contract exists.
argument-hint: "[audit]"
disable-model-invocation: true
---

# onboard

Write or audit `.agents/contract.json`, the only place where devflow learns project specifics. Every other skill reads the contract; none of them hardcode a command, path or tracker.

**Output:** a contract that passes `contract.py validate --strict`, an "Agent contract" section in AGENTS.md, and a readiness report listing what still blocks autonomous work.

## Rules

- Never invent a command. Every command in the contract must come from the detection report: a declared script, or scripts chained with `&&`. If a role has no candidate, leave the field out and report it as a gap.
- Never change the repository's build, scripts or CI. Onboard describes the repo; fixing it is product work for the gaps report.
- Ask only when the detection report leaves a real choice, such as two dev scripts or no obvious verify command. When nobody can answer, apply the rules in `references/mapping.md`, and list each assumption in the report.
- Write project files in English.

## Steps

1. **Detect.** Run the detection script from the repository root and read its JSON:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/detect.py" .
   ```
   If `existing_contract` is set, or the argument is `audit`, follow **Audit mode** instead.
2. **Read context.** Skim AGENTS.md or CLAUDE.md and the CI files the report lists. They settle what the word hits in `tracker_hints` cannot, such as "we do not use Jira".
3. **Draft.** Map the report to contract fields with `references/mapping.md`. Start from `${CLAUDE_PLUGIN_ROOT}/templates/contract.json` and drop every field you cannot fill.
4. **Confirm.** Show the draft and its assumptions in one message, and ask about the open choices only. Skip this step when the user asked for no questions or nobody is available.
5. **Write and validate.** Write `.agents/contract.json`, then run:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/shared/contract.py" validate --strict
   ```
   Fix and re-run until it prints `ok`.
6. **Smoke-run.** Run `verify.fast`, or `verify.full` when there is no fast command, once. Record whether it passed, failed on code, or could not start because of the environment, such as a missing tool or credentials. Do not try to fix a failure.
7. **Link from AGENTS.md.** Insert or replace the block from `references/agents-md-block.md` between its markers in AGENTS.md. If only CLAUDE.md exists and it is not a symlink, put the block there instead. If neither exists, create AGENTS.md with the block, and a CLAUDE.md that contains the line `@AGENTS.md`.
8. **Report.** Print the readiness report from `references/report.md`.

## Audit mode

1. Validate the existing contract with `--strict` and run the detection script.
2. Compare them. Drift means a command that names a script that no longer exists, a path that no longer exists, CI that now runs scripts `verify.full` does not, or a new e2e tool or docs folder the contract ignores.
3. Report each drift with a proposed fix. Apply the fixes only after the user confirms. Without a user, change nothing and report.
4. End with the readiness report.

## Next step

Tell the user which gap to close first. The verification gaps come before everything else, because no other skill can prove its work without them.
