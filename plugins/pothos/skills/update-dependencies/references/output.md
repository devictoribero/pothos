# What a run leaves behind

## The run record

`$POTHOS_HOME/deps/<host>/<owner>/<repo>/<date>.json`, written by `deps.py plan` and updated by `deps.py update`. It is the checkable output: evals read it, and the next run reads it too. Per entry: driver and evidence, line status with its dates, installed and target versions with the reason for the target, peer ranges, radius with the importing files and their tests, the gates that apply, the hold or decision that silenced it, the related pull request, the status and its history. Per run: the settings used, the environment (node, package manager, lockfile hash), the holds and decisions read, the open pull requests found, and the provenance and errors of every external source.

Entry statuses: `candidate`, `skipped` (with `reason`: `held`, `decided`, `existing-pr`, `up-to-date`, `no-safe-target`, `prerelease`, `excluded`, `not-selected`), `failed` (with the reason: registry data missing, advisories unavailable, installed version unknown, no version escapes the advisories, a peer conflict, a gate that failed), `applied`, `in-progress` (verify exit 4; never counts as green), `verified`, `pr-opened`, `reported`, `superseded`. Excluded and unselected packages stay in the record, unclassified, so a candidate's peer range is checked against what they keep installed.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/deps.py" update <record> <pkg> --status verified --set verify_exit=0
python3 "${CLAUDE_SKILL_DIR}/scripts/deps.py" update <record> <pkg> --status failed --note "type-check: 3 errors in src/upload.ts"
python3 "${CLAUDE_SKILL_DIR}/scripts/deps.py" update <record> <pkg> --status pr-opened --pr <url>
```

## Pull requests

Drafts, with the contract's label (`deps.label`), assigned to whoever opens them (the plugin's hook does it), using the repository's template when it has one. The body answers, in this order:

1. **Why now.** The driver and its evidence, first. A reviewer must know in one line whether this is an advisory fix or a hygiene bump. Security entries first in a batch.
2. **Versions.** Installed to target, and why that target (matured on a date, minimum patched, retargeted away from a release that is too young, erratic versioning noted).
3. **What verify covered, and what it cannot see.** The receipt's rows and counts, the `deps.gates` run, and the areas no test exercises. For a mechanical pull request this is what makes "look at CI and merge" an informed decision.
4. **Radius and what to test.** The importing files, the severity by radius tier, and what a person should try by hand.
5. **The changelog, narrowed.** Only the lines that touch the symbols this repository imports.
6. **For a migration:** what changed in the code and why; for a red security draft: every failure, and that a person must take it from here.
7. **Why this pull request is on its own**, when it is: a migration, a security batch, or the policy file asking for it.
8. **Reconciliation.** The older pull request it supersedes, closed after this one exists with a comment linking both.

The footer carries the metadata the next run reconciles on, one line each:

```text
Dependency-Root: <package>
Dependency-Target: <version>
Dependency-Driver: <driver>
Dependency-Entry-Id: <package>@<version>
```

## Assessments

A ticket in the contract's tracker, `Status: ready-for-human` (the triage label the session context maps), and no code change. It answers from this repository, not from the changelog:

1. What breaks here: the breaking changes that hit our call sites, with counts.
2. What it costs: files, config, types, tests.
3. What we gain: the concrete reason; "we stay closer to upstream" is written as exactly that.
4. What it costs not to do it: advisories accruing on the old line, packages it freezes, the exit closing.
5. A recommendation (`do it now`, `schedule it`, `not worth it yet`) and the trigger that would change it.

An assessment for a `drift-exposed` entry says "the exit is closed", not "we are a bit behind": those are different conversations.

## The summary

`deps.py summary <record>` prints it; the final message quotes it. One line per entry (driver, line, versions, radius, outcome and link), each hold once with what it keeps back, the decisions in one line, and every source that failed or warned. Nothing goes to chat or a channel: the outputs are the pull requests, the tickets and the record.
