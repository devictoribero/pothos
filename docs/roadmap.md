# Roadmap

Status of each phase, newest decisions first. Phase 2 was rewritten on 2026-10-10 and built on 2026-10-11.

| Phase | Goal | State |
|---|---|---|
| 0 | Hygiene: revoke leaked tokens, remove the old personal agent and duplicate skills | done except revoking tokens, which only the owner can do |
| 1 | Skeleton, private contract, `onboard`, `explain`, `archify` | done |
| 2 | The full cycle, built on Matt Pocock's skills | done (0.2.0) |
| 3 | Pilot on a side project | running on Lifetails, see below |
| 4 | Work repositories, once the pilot holds | later |
| 5 | Remaining repositories and more autonomy | later |

## Phase 3: pilot on Lifetails

The pilot built phase 0 of a real plan (two tickets, the second blocked by the first) with `to-tickets` and then `implement-spec` headless, on an integration branch, without pushing.

What it found in Pothos, all fixed:

- **Fresh worktrees could not run the checks.** The generated database client and the env file were missing. The contract gained `run.setup`, which every worktree runs first.
- **Shared test databases leak between worktrees.** Migrations from unmerged branches polluted the shared test database. The contract's `full` command now points each worktree at its own database. The repository itself is unchanged.
- **A slow suite killed the run silently.** An implementer started the full suite as a background command; it outlived the ten-minute command limit, died with the subagent, and the orchestrator waited forever. `verify` now runs the checks detached and returns exit 4 with a `wait` command, and the session context forbids background suites.
- **A headless orchestrator ended its turn to wait for its reviewers.** In `claude -p` that ends the process and kills the subagents. `pothos-run.py` now tells the session never to end its turn to wait, and resumes it until it writes `report.md`.
- **`disable-model-invocation` skills need a slash command in headless runs.** `pothos-run.py` already starts sessions that way.

Phase 4 starts only after the owner reviews the pilot's branch.

## Phase 2: Pothos on top of Matt Pocock's skills

### Why the change

The first plan had Pothos writing nine skills of its own: grill, distill, implement, code, verify, evidence, review, pull-request and address-review. [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) already covers most of that cycle, and its `implement-spec` runs the same model this repo describes in [work-model.md](work-model.md): a task graph, a frontier, implementer subagents in worktrees and one integration branch. Writing our own copies would mean maintaining them against a project that improves every week.

So Pothos stops being the cycle and becomes a thin layer around it. It vendors Pocock's skills unchanged and adds only what they don't have.

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

Left out: `setup-matt-pocock-skills`, because it writes configuration into the repository (`docs/agents/*.md` and a block in `CLAUDE.md`). `onboard` replaces it. Also left out are `ask-matt`, whose router would point at the excluded setup skill, plus the `misc/` bucket (frozen upstream) and `in-progress/`.

The planned names `grill`, `distill`, `implement`, `code`, `review`, `pull-request` and `domain-model` are dropped. We use Pocock's names so his docs and newsletter apply as written.

### What Pothos adds

1. **Contract adapter.** This is a `SessionStart` hook that reads the private contract and injects it as context: the issue tracker, the domain docs, the verify commands, the run environments and the standards files. Pocock's skills say "the issue tracker should have been provided to you", so they work unchanged and the repository stays untouched.
2. **`verify`.** It runs the contract's `fast`, `full` and optional `e2e` checks, asks which run environment to use, and records a receipt tied to the commit. It is the gate before any merge into the integration branch.
3. **`evidence`.** It runs the app and captures before-and-after proof. Its output fills the Evidence section of Pocock's `pr` template.
4. **`onboard`, `explain`, `archify`.** These exist already.
5. **Judgment.** These encode how the owner decides, not how the process runs:
   - `component-design` stays as a skill.
   - `testing` stays only if the comparison below shows it beats Pocock's `tdd`. If not, it shrinks to a standards document.
   - Review criteria become a standards document that `code-review` reads. Its axis already checks "this repo's documented coding standards", and the adapter adds personal standards files kept outside the repository. The first draft comes from mining the owner's past review comments.

### Order

1. Vendor Pocock's skills, extend `vendor_sync.py` to take several upstream paths from one source, and check for name collisions with the installed plugins.
2. Write the `SessionStart` adapter with a test per contract field, plus an eval showing that `to-tickets` writes to the tracker named in the contract without asking.
3. Write `verify` and its receipt.
4. Write `evidence`.
5. Decide the testing comparison, then write the review standards document.
6. Update the README and the skills table to match.

### Decisions taken while building

- **Direct merges, not ticket pull requests.** `implement-spec`'s merger subagent merges each ticket into `feature/<slug>`, and `verify` gates every merge. One pull request per spec. See [work-model.md](work-model.md).
- **The local tracker lives in the main checkout.** The SessionStart context gives its absolute path, so implementers in worktrees update the same files, and `verify` ignores the folder when it checks for a clean tree.
- **Testing became a standards file.** The comparison (4 fixtures, 2 runs each, blind review) gave no skill 11.9/14, Pocock's `tdd` 11.5 and the testing skill 11.6, at 1.15, 1.50 and 2.85 dollars per task. Only fake clocks and settling before negative assertions clearly helped; those and the bug-neighbour rule are in `standards/testing.md`.
- **Review criteria came from 260 past review comments** (four repositories), kept when a concern appeared at least three times or in two repositories: `standards/review.md`.
- **Skills may start on their own; publishing is what needs a person.** `onboard` lost `disable-model-invocation`. Pocock's skills keep their own setting.
- **Pocock skills left out:** `setup-matt-pocock-skills` (writes into the repository), `ask-matt` (routes to it), `research` (writes into the repository; `explain` covers it), `wizard`, `grill-me`, `teach`, `to-questionnaire`, `wait-what` (niche or covered).
