# Work model

How devflow turns an idea into merged code: the artifacts, the two loops, and who runs each step. Skills follow this document; when a skill and this document disagree, fix one of them.

Most steps run Matt Pocock's skills, vendored unchanged. The vocabulary is his: spec, ticket, blocked by, frontier, tracer bullet, integration branch, glossary. devflow adds the private contract, `verify`, `evidence`, `explain` and the standards.

## Artifacts

| Artifact | Answers | Exists when | Lives in |
|---|---|---|---|
| **Signal** | Something might be worth doing | Always: a request, a bug report, a telemetry alert, a review finding | Wherever it came from |
| **Spec** | What problem, for whom, and why; what is out of scope | The work needs more than one ticket, or the why is not obvious. A PRD is a spec. | Tracker parent issue, or `spec.md` in the local tracker |
| **Plan** | How the work splits and in which order | More than one ticket | The tickets themselves plus their `Blocked by` edges |
| **Ticket** | One change and how to check it is done | Always | Tracker issue, or `issues/NN-slug.md` in the local tracker |
| **Verify receipt** | Did this exact commit pass the checks? | Before every merge | `~/.config/devflow/receipts/`, outside the repository |
| **Evidence** | Does it work, shown rather than claimed? | Before the pull request leaves draft | `~/.config/devflow/evidence/`, outside the repository |
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
                         a person reviews and merges into the base branch
```

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
main ─────────────────────────────────────────────▶ feature pull request (a person reviews and merges)
  └─ feature/<slug> ──●──────●──────●──●──────●──●──▶
                       ▲ 01   ▲ 02   ▲ 03 ▲ 04  ▲ 05 ▲ 06
      each ticket merges straight in once `verify check` passes on the merged commit
```

- **Before the first ticket,** `implement-spec` creates the integration branch `feature/<slug>` from the base branch. When the contract lists several backends under `run.environments`, the agent asks which one this feature runs against and records the answer on the spec, so every ticket, evidence run and end-to-end run uses the same backend.
- **Tickets merge without pull requests.** A merger subagent merges each finished ticket into the integration branch and runs `verify`; a red result goes back to an implementer, never into the branch. The receipt is checked locally, so this works whether or not the repository's CI runs on feature branches.
- **One pull request, opened as a draft** after the first merge and marked ready only when every ticket is merged, `code-review` findings are fixed, `verify check` passes and evidence is attached.
- **Merging into the base branch is always a person's decision.** No agent does it.

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
| 3. Unattended | `scripts/devflow-run` | Starts `implement-spec` headless in a fresh session for a spec, logs to a file, and stops at the draft pull request or at `needs-replan`. |

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
