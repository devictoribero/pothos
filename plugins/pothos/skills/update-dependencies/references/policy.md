# Policy: why a dependency moves, and what shape its pull request takes

Three questions, kept apart. The usual mistake is to use the severity of the reason as a stand-in for the technical impact: a security update can be mechanical, a hygiene bump can demand a large migration.

| Question | Decides | Who answers |
|---|---|---|
| Why update? | Urgency and merge order | The script, from the registry, the audit and the policy; the model only for `bug` and `feature` |
| What really changed? | The pull request's shape | The measured diff and gates in a worktree |
| What is safe to do? | What gets published and how it is marked | The rules below, and a person at the moment of publishing |

## Drivers, strongest first

Each entry gets exactly one driver, the strongest that applies, with the evidence recorded on the entry and reproduced in the pull request body.

| Driver | When | Evidence recorded | Who |
|---|---|---|---|
| `security` | The audit has an advisory that covers the installed version and a published version escapes it | Advisory ids, severity, whether it reaches runtime (`dependencies`) or only development | Script |
| `eol` | The registry marks the package deprecated | The deprecation message | Script |
| `drift-exposed` | The installed major line is dead (below) | Last version on the line, its date, days silent | Script |
| `unblocks` | Named prerequisite of another entry that has its own driver | The blocked entry | Model, recorded with `deps.py update` |
| `bug` / `feature` | Evidence in this repository or its tracker: a ticket, a `TODO`, a workaround, a pinned version with a note | The file or ticket | Model |
| `drift-safe` | None of the above; the line is alive | None; enters the hygiene batch only when it stays mechanical | Script |

Note where `drift-exposed` sits: above `bug` and `feature`. A dead line is a bigger problem than a bug you already work around.

### The dead line is the measure that matters

The question is: if an advisory lands on this package tomorrow, can we patch cheaply? If the installed major is the latest, yes. If we are a major behind but the installed line had a release within the last twelve months (`deps.dead_line_months`), also yes: upstream still backports. If the line has been silent longer, it is dead, and the future patch will not reach us. That is latent security debt, and it counts more than a bug already worked around.

Version distance does not predict it. A linter one major behind with its line patched two days ago is fine. A form widget in two files whose line has been silent for four years is the risk.

### The cooling-off window retargets

The target is not "the latest, unless it is too new". It is the newest version that has already matured: published at least `deps.cooling_off_days` ago. Cancelling when the latest is recent condemns packages that publish weekly to never update. The script's `matured_target` picks the newest version past the window; when that version is already installed, the entry is skipped as up to date, not reported as a skip worth reading.

A package that published two majors in one day after years of silence has the signature of a hijacked account. Retargeting picks the version from months ago: it leaves the dead line and sidesteps both suspicious releases. More than one major within thirty days is flagged on the entry as erratic versioning; it is not malicious by itself, but the version numbers have stopped meaning anything, so the changelog gets a closer read.

The security driver overrides the window: the minimum version outside every advisory range, whatever its age. Waiting two weeks on a known-exploitable version to avoid a hypothetical bad release is a bad trade.

### Numbers are heuristics, not guarantees

Fourteen days reduce exposure to a hijacked release; they do not prove stability. Twelve months without a release suggest abandonment; they do not prove it. Both values live in the contract, and the record keeps the dates and signals behind every classification, so a person can argue with the data in front of them. Dates, peer ranges and advisories are external facts: the record says where each came from, and when one is missing the entry fails explicitly instead of being classified with a gap.

### Holds and decisions

The policy file (`deps.policy`, a markdown file in the repository) carries two kinds of line, anywhere in the file:

```markdown
- react stays on 18 until 2027-01-01: the router migration is scheduled for Q1
- swiper: not before 2026-12-01: v14 only matters once the carousel is rebuilt
```

A hold freezes a package on a major until a date. Before the hold blocks a coupled package, the script reads that package's real peer range at its target: a package that accepts `^18 || ^19` is not blocked by a React 18 hold, whatever its name suggests. A wrong skip is invisible, since nobody reviews an update that never happened, so the range is always verified. A decision silences an entry until its review date; a `security` or `eol` driver voids it, because it was taken under other facts. Past their dates, both are stale and the entry is assessed again.

The summary reports a hold once, with what it keeps back, never one line per frozen package.

## The pull request's shape

Two shapes, one question: does a person have to read code to approve this?

- **Mechanical.** The diff is `package.json` and the lockfile, every gate green. The reviewer looks at CI and merges. All of these go in one pull request, whatever their driver.
- **Migration.** Hand-written code, or a failed gate. The reviewer reads it line by line and tests it. One pull request each. Batching three migrations triples the reading to save two CI runs.

Five questions in order. The first three take entries out without opening anything; the last two choose between the grouped pull request, the individual one and the report, and are answered by measuring.

1. **Security batch.** Runtime advisories that turn out mechanical go in a pull request apart from hygiene. Not for risk, for velocity: a critical patch does not wait for thirty cosmetic bumps. Development-only advisories travel with hygiene.
2. **Security buys no quality.** Three different things: priority (the advisory skips the window and merges first), publication (the pull request opens even when red, so the person sees what the patch costs) and merge authorization (never automatic). A red security pull request opens as a draft marked for a person, each failure documented, never presented as ready; `tend`'s gate does not merge while a check is red or the label is missing.
3. **Hygiene batch.** Everything else that turned out mechanical, one pull request per run.
4. **Migrations.** One pull request each, up to `deps.review_budget`. The ones that do not fit queue, ordered by driver and age, and the summary lists them.
5. **Assessments.** What does not reach green, or is not worth attempting: a ticket in the contract's tracker with the estimated cost, what blocks and what would have to be decided.

### What the risk matrix is for

Severity of the change (trivial, behaviour-preserving, behaviour-changing, API removed) by radius (none, narrow with one to three call sites, wide with four or more). The entry's tier is the maximum over its changes, never the sum. It serves two purposes and nothing else: not attempting what clearly will not land (API removed and wide radius goes straight to an assessment) and telling the reviewer what to test in the pull request body. It never decides the shape; the diff does.

The radius is measured with the anchored import (`from 'pkg'` or `from 'pkg/`), because unanchored, `vite` counts the files of `vitest`. Tooling configured by a file and imported by nobody (TypeScript, the linter, the bundler) is wide by definition: its radius is what it processes, not who imports it. `deps.py impact` applies both rules.

A mechanical, green bump may still go alone when the policy file asks for it. There is no automatic exception for critical areas: which folder is critical is a fact of the repository, not of the private contract.

## Confidence

- **Green is not correctness.** Type-check, lint and tests do not see a behaviour change nothing covers, above all in UI, authentication, serialization and tooling. The contract's `verify.full` is the floor; `deps.gates` adds a gate per package type (the build for bundlers and transpilers, a smoke test for the database client). The mechanical pull request says what verify covered and what it cannot see.
- **Type-check as the detector of a removed API.** When the package ships types, the type-check finds every symbol that disappeared; read its errors before the changelog.
- **Impact tests first.** `deps.py impact` lists the test files that import the files that import the package. Run those before the whole suite: a specific signal in seconds, and a shorter fan-out when the batch is red.
- **Changelog narrowed to our symbols.** Search it for the names this repository imports; cite in the pull request only what affects us.
- **A worktree per attempt.** Nothing touches the person's branch; two attempts never collide. A worktree does not isolate a `postinstall` script: install with `--ignore-scripts` first, and only when a gate fails on a missing binary repeat with scripts for those packages, noted in the record. A real network sandbox is outside the plugin: in a headless run it belongs to whoever launches the runner.
- **Edge cases the record must show.** An install that fails (`failed`, with the output). A lockfile out of sync with `package.json` before the bump (the run stops, nothing opens). A registry that does not answer (no entry classified with partial data; the record says what was missing). Two runs at once (the second sees the lock and stops). A base that moves during the run (the pull request opens on the new base, or the record says it fell behind). Two packages whose peer ranges exclude each other (the entry fails with the conflict, never a blind resolution).

## Never propose

- Packages under an active hold, or with a live decision: reported once per hold, never as skips.
- Packages matching `deps.exclude`, unless named explicitly.
- Prerelease versions, unless the installed version is already on that channel.
- A pull request for an entry with no driver, or a migration for a `drift-safe` entry.
