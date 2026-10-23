---
name: update-dependencies
description: Updates npm dependencies only when there is an evidenced reason to (a security advisory, a deprecation, a dead version line, a bug or feature the repository needs), targets the newest version that has matured, applies every candidate at once in a worktree and lets the measured diff decide the pull request's shape (one mechanical pull request for what stays green and lockfile-only, one pull request per migration, a tracker ticket for what does not reach green). Use when asked to "update <pkg>", "upgrade <pkg>", "bump <pkg>", "refresh dependencies", "update all deps" or to audit what is outdated, and with "audit" to decide and measure without publishing anything.
argument-hint: "[audit] [package ...]"
---

# update-dependencies

"There is a newer version" is not a reason to update. Every entry carries a driver with evidence, and the shape of its pull request comes from what the bump changed in this repository, measured in a worktree, never from the version number. Three questions stay apart: why update (urgency and order), what really changed (the pull request's shape), what is safe to do (what gets published and how it is marked).

The deterministic half runs through `"${CLAUDE_SKILL_DIR}/scripts/deps.py"`: inventory, registry facts, drivers, targets, radius, holds and decisions, reconciliation with open pull requests, and the run record. The model adds judgement only where it is needed: evidence for a `bug` or `feature` driver, the changelog read against the symbols this repository imports, and the migration itself. The rules in full, with the worked examples, are in `references/policy.md`; the pull request, ticket and summary formats in `references/output.md`.

Three ways to call it:

```text
/pothos:update-dependencies              # decide, measure, confirm, publish
/pothos:update-dependencies audit        # the same without publishing: the record and the report stay
/pothos:update-dependencies swiper zod   # only these packages
```

## Rules

- **A driver or nothing.** `security` > `eol` > `drift-exposed` > `unblocks` > `bug`/`feature` > `drift-safe`, first match wins, with the evidence recorded. `drift-safe` entries enter the hygiene batch only; one that needs hand-written code becomes an assessment, never a migration nobody asked for.
- **The window retargets, it never cancels.** The target is the newest version published at least `deps.cooling_off_days` ago (14 by default). A `security` driver takes the minimum patched version now, whatever its age. A version line with no release in `deps.dead_line_months` (12) while a newer major exists is dead, and being on it is `drift-exposed`: latent security debt, ranked above a bug you already work around.
- **The diff decides the shape.** Green and only `package.json` plus the lockfile changed: mechanical, all of them in one pull request whatever their driver. Hand-written code or a failed gate: a migration, one pull request each, at most `deps.review_budget` (3) per run; the rest queue. Semver distance, popularity, lockfile churn and changelog length decide nothing.
- **Security buys priority, not quality.** Runtime advisories ship in their own mechanical pull request, ahead of hygiene, and leave the batch the moment it goes red. A red security pull request opens as a draft marked for a person, every failure documented, and is never presented as ready; the merge gate stays a person's.
- **A hold is verified, never inferred.** Before a hold on one package blocks another, read the coupled package's real peer range: `^18 || ^19` is not blocked by a React 18 hold. A decision silences an entry until its review date, unless `security` or `eol` voids it.
- **A worktree per attempt, with limits.** The optimistic batch and each migration live in their own worktree with `run.setup` from the contract. Install with `--ignore-scripts` first and repeat with scripts only for the packages whose gate failed on a missing binary, noting them in the record. No credentials beyond what `run.setup` needs; a time limit per attempt; the record keeps the node, package manager and lockfile hash. The person's branch is never touched.
- **Green is not proof.** `verify` covers what its tests cover. Run the contract's `deps.gates` for the packages they match, and say in every mechanical pull request what verify ran and what it cannot see. A verify that is still running (exit 4) is `in-progress`, never verified.
- **Publishing needs a person.** Applying and measuring never asks. Opening pull requests and tickets confirms right before, when a person is available; in `audit` mode or a headless session, stop with the report and the record. Never merge, never add the auto-merge label: that is `tend`'s gate.
- **Memory is the record and the policy file.** Every entry's driver, evidence, target, radius, gates and outcome land in the run record outside the repository; holds and live decisions live in the repository file `deps.policy` names, which the team sees. A run that changes no code but records why is a successful run.

## Steps

1. **Plan.** From the repository root:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/deps.py" plan [package ...]
   ```
   It writes the run record and prints one line per entry: driver, line status, installed to target, radius, what a hold or decision silenced, what an open pull request already covers. Exit `1` means some entry failed explicitly (registry data missing, advisories unavailable, no installed version): report those, never classify them by hand. Exit `4`: another run holds the lock; wait. Read the summary before touching anything, and show it to the person when one is available.
2. **Evidence the judgement drivers.** For every `drift-safe` entry, look for a `bug` or `feature` driver in this repository or its tracker: a ticket, a `TODO`, a workaround comment, a pinned version with a note. A changelog line is not evidence. Record what you find with `deps.py update <record> <pkg> --status candidate --set driver=bug --note "<where>"`.
3. **Pre-filter.** For each candidate with radius `narrow` or `wide`, read the release notes between the installed and target versions looking only for the symbols `deps.py impact <pkg>` says this repository imports. A removed or changed API with a wide radius goes straight to an assessment (`--status reported`), unattempted. Severity (trivial, behaviour-preserving, behaviour-changing, API removed) by radius gives the tier the pull request body tells the reviewer; it never decides the shape.
4. **Apply everything at once.** One worktree from the base branch, `run.setup`, then one install of every remaining candidate at its target. Run the fast check, then `/pothos:verify` (`verify.py run all`) and the matching `deps.gates`. Record each entry as `applied`, then `verified`, `in-progress` or `failed`.
5. **Classify by the result.** Green with no diff outside `package.json` and the lockfile: every entry is mechanical. Red, or source changed: run the impact tests of each entry first (`deps.py impact` lists them), then fan out, each suspect alone and the rest together; an interaction between packages (fails together, passes alone) is recorded as such, never dropped. Security entries leave the batch to their own attempt at the first red.
6. **Migrate.** Each entry that needs code gets its own worktree. Write the migration, run the fast check as you go, then verify. What does not reach green, or grows beyond what the pre-filter expected, becomes an assessment ticket.
7. **Publish**, after confirming with the person (skip this step in `audit` mode or without a person: report and stop). Pull requests as drafts with the contract's label and the body in `references/output.md`; assessments as tracker tickets with `Status: ready-for-human`; supersede an older pull request only after the new one exists, with a comment linking them; never touch a person's pull request. Record the URL on each entry.
8. **Report** with `deps.py summary <record>`: one line per entry, each hold reported once with what it keeps back, decisions in one line, what was opened, reported and skipped and why.

## Exit codes of the script

`0` ok, `1` at least one entry failed or the run could not classify (the record says what), `2` no contract (suggest `/pothos:plant`), `3` nothing to do (no `package.json`, or everything excluded), `4` another run holds the lock, `64` usage.
