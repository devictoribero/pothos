# Work model

How Pothos turns an idea into merged code: the artifacts, the two loops, and who runs each step. Skills follow this document; when a skill and this document disagree, fix one of them.

Most steps run Matt Pocock's skills, vendored unchanged. The vocabulary is his: spec, ticket, blocked by, frontier, tracer bullet, integration branch, glossary. Pothos adds the private contract, `verify`, `evidence`, `tend`, `explain` and the standards.

## Artifacts

| Artifact | Answers | Exists when | Lives in |
|---|---|---|---|
| **Signal** | Something might be worth doing | Always: a request, a bug report, a telemetry alert, a review finding | Wherever it came from |
| **Spec** | What problem, for whom, and why; what is out of scope | The work needs more than one ticket, or the why is not obvious. A PRD is a spec. | Tracker parent issue, or `spec.md` in the local tracker |
| **Plan** | How the work splits and in which order | More than one ticket | The tickets themselves plus their `Blocked by` edges |
| **Ticket** | One change and how to check it is done | Always | Tracker issue, or `issues/NN-slug.md` in the local tracker |
| **Verify receipt** | Did this exact commit pass the checks? | Before every merge | `~/.config/pothos/receipts/`, outside the repository |
| **Evidence** | Does it work, shown rather than claimed? | Before the pull request leaves draft | `~/.config/pothos/evidence/`, outside the repository |
| **Feature pull request** | The whole spec, ready for the base branch | One per spec | Code host, integration branch into the base branch |

Rules:

- **Tickets are vertical slices.** Each cuts a narrow, complete path through every layer it needs (schema, API, UI, tests) and can be verified on its own. The exceptions are prefactors and wide mechanical refactors, sequenced expand, migrate, contract.
- **A ticket fits one fresh context window.** If an agent needs the conversation that produced it to understand it, the ticket is not finished.
- **Acceptance criteria are checkable.** Each one is something verify, a test or evidence can prove.

Small work skips levels: a signal can become a single ticket with no spec, built with `implement` on a branch of its own.

## Two loops

```
OUTER LOOP: one per initiative, a person decides
  signal ─▶ triage ─▶ grilling / grill-with-docs ─▶ to-spec ─▶ to-tickets (Blocked by edges)
                                              │
                         frontier: open, unblocked, unclaimed tickets
                                              │
INNER LOOP: implement-spec runs one per ticket, in parallel where the frontier allows
  implementer subagent (worktree, tdd) ─▶ verify run ─▶ verify check ─▶ merge into feature/<slug>
       ▲                                         │ fails
       └─────────────────────────────────────────┘
                                              │
                         all tickets merged ─▶ code-review ─▶ fixes ─▶ evidence ─▶ pr (draft → ready)
                                              │
AFTER THE PULL REQUEST: tend, one pass at a time from /loop
  answer review comments / fix a red check / update the branch ─▶ merge gate
       ▲                                                              │ something missing
       └──────────────────────────────────────────────────────────────┘
                                              │ all green and a person authorized the auto-merge label
                         merge into the base branch, delete the remote branch, close the ticket
                         (without the label, a person reviews and merges)
```

Small work enters at the same point: `implement` builds one ticket on its own branch, ends with `code-review`, and `pr` opens the pull request ready for review.

### After the pull request

- **Input:** one pull request that is ready for review. Drafts belong to `implement-spec`.
- **Who:** `tend`, one pass per run. Each pass does at most one thing: answer review comments, fix a failing check, or update a branch that fell behind. Waiting between passes belongs to `/loop /pothos:tend <n>`.
- **Never reviews again.** Code review, verify and evidence happen before the pull request is ready; `tend` reacts only to review comments, checks and the label.
- **Merges only through the gate.** `merge_gate.py` merges when the contract has `pr.auto_merge`, the pull request carries its label, every check on the head commit is green (or, in a repository whose workflows never run on pull requests, a passing verify receipt exists), no person's review asks for changes and no thread is open. A commit whose checks have not been reported yet waits. It pins the merge to the head commit and deletes the remote branch.
- **A person's thread is theirs to resolve.** `tend` fixes and replies; a bot's thread it may resolve after the fix.

### Outer loop

- **Input:** a signal.
- **Output:** a spec when needed, and tickets with blocking edges, labelled `ready-for-agent`.
- **Who:** you and an agent in an interactive session. `grilling` needs you; `to-spec` and `to-tickets` only need your approval of the result.
- **Re-entry:** the outer loop runs again when an inner loop finds the plan is wrong.

### Inner loop

- **Input:** exactly one ticket from the frontier.
- **Output:** a commit on the integration branch with a passing verify receipt.
- **Who:** one implementer subagent, alone, in its own worktree.
- **Never re-plans.** If the ticket turns out wrong or too big, the implementer writes what it found on the ticket, marks it `needs-replan` and stops. Improvising scope is how plans and code drift apart.

## Branches and merges

```
main ─────────────────────────────────────────────▶ feature pull request (a person merges, or labels it for `tend`)
  └─ feature/<slug> ──●──────●──────●──●──────●──●──▶
                       ▲ 01   ▲ 02   ▲ 03 ▲ 04  ▲ 05 ▲ 06
      each ticket merges straight in once `verify check` passes on the merged commit
```

- **Before the first ticket,** `implement-spec` creates the integration branch `feature/<slug>` from the base branch. When the contract lists several backends under `run.environments`, the agent asks which one this feature runs against and records the answer on the spec, so every ticket, evidence run and end-to-end run uses the same backend.
- **Tickets merge without pull requests.** A merger subagent merges each finished ticket into the integration branch and runs `verify`; a red result goes back to an implementer, never into the branch. The receipt is checked locally, so this works whether or not the repository's CI runs on feature branches.
- **One pull request, opened as a draft** after the first merge and marked ready only when every ticket is merged, `code-review` findings are fixed, `verify check` passes and evidence is attached.
- **Merging into the base branch is always a person's decision.** A person merges, or authorizes the pull request so `tend`'s merge gate merges it once everything is green. They authorize it by adding the contract's auto-merge label, by asking for the merge in their own message ("do X and merge it", `/pothos:tend <n> merge`), or by approving a local ticket that carries `Merge: auto`, which `to-tickets` proposes for copy and documentation changes. An agent adds the label only through `merge_gate.py authorize`, which leaves a comment naming who authorized it.

Why not one pull request per ticket: it adds a review surface nobody reads, it would need a fork of `implement-spec`, and the receipt already gives each merge the guarantee a ticket pull request's CI would.

## Sessions, subagents and state

- **The orchestrator holds only the ticket graph,** never code, so its context stays small however big the initiative is. Communication goes through pointers: the spec, the tickets, earlier commits.
- **Subagents nest at most three levels below the main session.** An `implement-spec` session uses two: implementers and mergers at level one, `code-review`'s reviewers below them. Keep `implement-spec` as the top-level session, not as a subagent of something else.
- **State lives in the tracker, never in a session.** Ticket status, claims and blocking edges are the only shared state, so any session can stop and another can pick up.
- **The local tracker lives in the main checkout.** Implementers in worktrees read and update tickets by absolute path in the main checkout, never in their worktree copy. The folder is ignored by `verify`'s clean-tree check.

## Who orchestrates

| Level | Orchestrator | How |
|---|---|---|
| 1. Manual | You | One session per ticket with `implement`, then `verify` and merge yourself. |
| 2. Assisted | `implement-spec` | One session builds the whole spec with parallel implementers; you watch and answer questions. |
| 3. Unattended | `plugins/pothos/scripts/pothos-run.py` | Creates a worktree and branch, runs `run.setup`, starts `implement-spec` (or `implement` for one ticket) headless, logs under `~/.config/pothos/runs/`, and stops at a pull request body, or at a draft pull request with `--open-pr`. A headless session dies when its turn ends, so the run counts as finished only when the session writes `report.md`; until then the script resumes it. `status` lists the runs. |

## Example: a new booking flow

A spec asks for a flow where a household books a vet appointment: a database migration, three new API endpoints and three screens.

**Outer loop, once.** One interactive session: `grill-with-docs` settles the open questions and records new terms, `to-spec` writes the spec, `to-tickets` splits it.

| # | Ticket | Blocked by |
|---|---|---|
| 01 | Add the appointments tables (expand only, nothing reads them yet) | None |
| 02 | Book an appointment end to end: one endpoint, one screen, the happy path | 01 |
| 03 | Pick a clinic and a time slot | 02 |
| 04 | Confirmation screen and notification | 02 |
| 05 | Cancel or reschedule | 03 |
| 06 | End-to-end test of the whole flow and removal of the feature flag | 03, 04, 05 |

**Inner loop, six times,** inside one `implement-spec` session. The frontier moves like this: 01 alone; 02 after 01 merges; 03 and 04 in parallel; 05 after 03; 06 last.

If ticket 03 discovers that slots need a rule nobody specified, it stops with `needs-replan`, and the outer loop runs again for that question only.

One outer loop per initiative plus one per re-plan; one inner loop per ticket; one pull request per spec.
