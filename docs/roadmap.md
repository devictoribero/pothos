# Roadmap

Status of each phase.

| Phase | Goal | State |
|---|---|---|
| 0 | Hygiene: revoke leaked tokens, remove the old personal agent and duplicate skills | done except revoking tokens, which only the owner can do |
| 1 | Skeleton, private contract, `plant`, `explain`, `archify` | done |
| 2 | The full cycle, built on Matt Pocock's skills | done (0.2.0) |
| 3 | Pilot on a side project | running on Lifetails, see below |
| 4 | Work repositories, once the pilot holds | later |
| 5 | Remaining repositories and more autonomy | later |

## Phase 3: pilot on Lifetails

The pilot builds phase 0 of a real plan (two tickets, the second blocked by the first) with `to-tickets` and then `implement-spec` headless, on an integration branch, without pushing.

What the pilot settled:

- **Fresh worktrees run `run.setup` first.** It creates whatever the checks need that git does not carry, such as a generated database client or an env file.
- **Each worktree gets its own test database.** The contract's `full` command points each worktree at its own database, so migrations from unmerged branches never reach another worktree. The repository itself is unchanged.
- **Slow checks run detached.** `verify` keeps the suite alive in a detached process and returns exit 4 with a `wait` command, and the session context forbids background suites, which die with the subagent that started them.
- **Headless sessions never end their turn to wait.** In `claude -p` that ends the process and kills the subagents. `pothos-run.py` tells the session so, and resumes it until it writes `report.md`.

Phase 4 starts after the owner reviews the pilot's branch.

## Phase 2: Pothos on top of Matt Pocock's skills

### Why this shape

[mattpocock/skills](https://github.com/mattpocock/skills) (MIT) covers most of the development cycle, and its `implement-spec` runs the same model this repo describes in [work-model.md](work-model.md): a task graph, a frontier, implementer subagents in worktrees and one integration branch. Keeping copies of our own would mean maintaining them against a project that improves every week.

So Pothos is a thin layer around that cycle. It vendors Pocock's skills unchanged and adds only what they don't have. It uses Pocock's names, so his docs and newsletter apply as written.

### What comes from Pocock

Vendored into `plugins/pothos/skills/` at a pinned commit, through `vendor.json` and the weekly sync, never edited by hand.

| Our step | Pocock skill |
|---|---|
| Define | `grilling`, `grill-with-docs` |
| Define in depth | `to-spec` |
| Organize | `to-tickets`, `wayfinder` for work bigger than one session |
| Execute | `implement` for one ticket, `implement-spec` for a whole spec, `tdd`, `prototype` |
| Review | `code-review` |
| Open the PR | `pr` |
| Understand what went wrong | `diagnosing-bugs`, `retro` |
| Design | `codebase-design`, `domain-modeling`, `improve-codebase-architecture` |
| Other | `triage`, `handoff` |

Left out:

- `setup-matt-pocock-skills`, because it writes configuration into the repository (`docs/agents/*.md` and a block in `CLAUDE.md`). `plant` replaces it.
- `ask-matt`, whose router points at the excluded setup skill.
- `research`, which writes into the repository; `explain` covers it.
- `wizard`, `grill-me`, `teach`, `to-questionnaire` and `wait-what`, which are niche or covered.
- The `misc/` bucket (frozen upstream) and `in-progress/`.

### What Pothos adds

1. **Contract adapter.** A `SessionStart` hook reads the private contract and injects it as context: the issue tracker, the domain docs, the verify commands, the run environments and apps, and the standards files. Pocock's skills say "the issue tracker should have been provided to you", so they work unchanged and the repository stays untouched.
2. **`verify`.** It runs the contract's `fast`, `full` and optional `e2e` checks, asks which run environment to use, and records a receipt tied to the commit. It is the gate before any merge into the integration branch.
3. **`evidence`.** It runs the app and captures before-and-after proof, within what the contract says each app supports. Its output fills the Evidence section of Pocock's `pr` template.
4. **`plant`, `explain`, `archify`.**
5. **Judgment.** These encode how the owner decides, not how the process runs:
   - `component-design`, a skill loaded before UI work and used again in review.
   - `standards/testing.md`. A blind comparison (4 fixtures, 2 runs each) scored no skill 11.9/14, Pocock's `tdd` 11.5 and a dedicated testing skill 11.6, at 1.15, 1.50 and 2.85 dollars per task. Only fake clocks and settling before negative assertions clearly helped; those and the bug-neighbour rule are the standard.
   - `standards/review.md`, built from 260 past review comments across four repositories, keeping a concern when it appears at least three times or in two repositories.

### Decisions

- **Direct merges, not ticket pull requests.** `implement-spec`'s merger subagent merges each ticket into `feature/<slug>`, and `verify` gates every merge. One pull request per spec. See [work-model.md](work-model.md).
- **The local tracker lives in the main checkout.** The SessionStart context gives its absolute path, so implementers in worktrees update the same files, and `verify` ignores the folder when it checks for a clean tree.
- **Every step starts from plain language; publishing needs a person.** `vendor.json` removes `disable-model-invocation` from the vendored skills that set it and adds trigger phrases to their descriptions. Pushing, opening a pull request and merging still wait for the owner.
