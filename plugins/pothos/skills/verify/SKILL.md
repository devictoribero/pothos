---
name: verify
description: Runs the repository's checks from its private Pothos contract (fast, full, end-to-end, and advisory mutation testing) and records a receipt for the current commit, outside the repository. Use before merging a ticket into an integration or feature branch, before a pull request leaves draft, when asked to "verify", "run the checks" or "is this green?", and whenever you are about to claim that work passes. A claim of green without a passing receipt for the current commit is not allowed.
---

# Verify

Runs the commands the contract lists and keeps a receipt per commit, so anyone (you, another agent, the pull request step) can check that this exact commit passed. The receipts live in `~/.config/pothos/receipts/`, never in the repository.

Every command goes through `"${CLAUDE_SKILL_DIR}/scripts/verify.py"`. Run it from inside the repository.

## Levels

| Level | When | Counts as a gate |
|---|---|---|
| `fast` | While working, after each meaningful edit. Seconds. | No |
| `full` | Before any merge and before a pull request leaves draft. Everything CI checks. | Yes |
| `e2e` | With `full`, when the contract has an end-to-end command. | Yes, when configured |
| `mutation` | Once after green and before the pull request, when the contract has a mutation command. | No |

A level the contract does not configure is recorded as skipped and does not block. Say so in the pull request.

After `full`, the UI check runs on the lines the branch adds, when the contract's `ui` sets tokens or icons, and writes a `ui` receipt. It is advisory: it never changes an exit code. Fix its findings or mark an intended value with `ui-ok: <why>`, and list what remains in the pull request.

## Steps

1. **Commit first.** A run on uncommitted changes is recorded, but it never counts as a pass. The local tracker folder (`.scratch/` by default) is ignored, because tickets change while code is verified.
2. **Pick the environment.** If the session context lists backend environments and end-to-end runs per environment, ask the user which one to use. Ask once per feature, never pick one yourself, and pass it with `--env NAME`.
3. **Run.**
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/verify.py" run all [--env NAME]
   ```
   This runs `full` and then `e2e` when configured. Use `run fast` while iterating.

   Run it in the foreground, never as a background command: a background command dies when your turn or your subagent ends, and nobody gets notified. The checks run in a detached process, and `run` returns within about nine minutes. Exit `4` means they are still going: run `verify.py wait` (also in the foreground) until it returns another code. Never start a second run for the same commit; `run` attaches to the one in progress anyway.
4. **On failure**, read the tail the script prints, then open the log it names if you need more. Fix the cause, commit, and run again. Never weaken, skip or delete a check to get a pass. If the failure is unrelated to the change and also fails on the base branch, say so with evidence (the base commit's receipt) and stop. Do not paper over it.
5. **Mutation**, once after green and before the pull request, when the contract has a mutation command:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/verify.py" run mutation
   ```
   It stays out of `run all` and needs a passing `fast` or `full` receipt for HEAD on a clean tree. Read the receipt and act on each `new` survivor it prints as rule 1 of `standards/testing.md` says, commit, and run `fast` then `mutation` again. The pull request lists the survivors killed, each with the test that kills it, and the survivors left, each with why.
6. **Gate.** Before merging or marking a pull request ready:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/verify.py" check
   ```
   Exit 0 means the current commit has a passing `full` receipt and, when configured, a passing `e2e` receipt, on a clean tree. Anything else means not verified. Report the exact line it printed.

## Reporting

State the level, the commit and the result in one line each. Quote the script's own output rather than paraphrasing it, for example `verified: full, e2e passed on 3f2a91c04b1e`. For `mutation`, quote its closing line, for example `mutation: 1 new surviving mutant(s) in 2 changed file(s); 4 inherited, see verify.py show. Advisory, does not block. Each new one is a missing test or dead code.` If something was skipped, say what and why.

## Exit codes

`0` passed or skipped, `1` failed or not verified, `2` no contract (suggest `/pothos:plant`), `3` the contract or environment is unusable (the message says which), `4` still running (run `wait`), `64` usage.
