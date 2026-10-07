# Work model

How development-flow turns an idea into merged code: the artifacts, the two loops, and who runs each step. Skills follow this document; when a skill and this document disagree, fix one of them.

The vocabulary follows Matt Pocock's skills where they overlap: spec, ticket, blocked by, frontier, tracer bullet, glossary.

## Artifacts

| Artifact | Answers | Exists when | Lives in |
|---|---|---|---|
| **Signal** | Something might be worth doing | Always: a request, a bug report, a telemetry alert, a review finding | Wherever it came from |
| **Spec** | What problem, for whom, and why; what is out of scope | The work needs more than one ticket, or the why is not obvious. A PRD is a spec. | Tracker parent issue, or `spec.md` in the local tracker |
| **Plan** | How the work splits and in which order | More than one ticket | The tickets themselves plus their `Blocked by` edges. There is no separate plan document unless the split needs explaining. |
| **Ticket** | One change and how to check it is done | Always | Tracker issue, or `issues/NN-slug.md` in the local tracker |
| **Pull request** | The change itself, with evidence | One per ticket | The code host |

Rules:

- **A ticket is the unit of delivery.** One ticket, one branch, one pull request. A plan groups tickets; a ticket never contains a plan.
- **Tickets are vertical slices.** Each cuts a narrow, complete path through every layer it needs (schema, API, UI, tests) and can be verified on its own. The exceptions are prefactors and wide mechanical refactors, which are sequenced expand, migrate, contract.
- **A ticket fits one fresh context window.** If an agent needs the conversation that produced it to understand it, the ticket is not finished.
- **Acceptance criteria are checkable.** Each one is something verify, a test or evidence can prove.

Small work skips levels: a signal can become a single ticket with no spec and no plan.

## Two loops

```
OUTER LOOP: one per initiative, a person decides
  signal ─▶ triage ─▶ grill ─▶ distill ─▶ spec + tickets with Blocked by
                                              │
                         frontier: open, unblocked, unclaimed tickets
                                              │
INNER LOOP: one per ticket, an agent can run it alone
  implement ─▶ verify ─▶ evidence ─▶ review ─▶ pull-request ─▶ CI + review
       ▲          │ fails                                          │ comments
       └──────────┘                    address-review ◀────────────┘
                                              │
                         merge ─▶ blocked tickets unblock ─▶ next frontier
                                              │
                         observe in production ─▶ new signals
```

### Outer loop

- **Input:** a signal.
- **Output:** a spec when needed, and tickets with blocking edges, ready for an agent.
- **Who:** you and an agent in an interactive session. Triage can run unattended once it exists; grill and distill need you.
- **Re-entry:** the outer loop runs again when an inner loop finds the plan is wrong.

### Inner loop

- **Input:** exactly one ticket from the frontier.
- **Output:** one pull request whose verify receipt matches its head commit, with evidence when the UI changed.
- **Who:** one agent, alone.
- **Never re-plans.** If the ticket turns out wrong or too big, the inner loop writes what it found on the ticket, marks it `needs-replan` and stops. Improvising scope inside a pull request is how plans and code drift apart.

## Sessions, subagents and state

- **Each inner loop runs with a fresh context in its own git worktree**, preferably as its own top-level session. Three reasons: subagents can only nest three levels below the main conversation, and an orchestrator, an inner loop, review's reviewers and their validators already use all three; the run can be long and must be resumable; and the loop maps one to one to a branch and a pull request. A workflow agent with an isolated worktree is acceptable at level 3 below, as long as review keeps its validators.
- **Subagents are for work inside a loop that returns a summary:** review's reviewers and validators, codebase exploration, research.
- **State lives in the tracker, never in a session.** Ticket status, claims and blocking edges are the only shared state. Any session can stop, and any other can pick up from the tracker. Status values: `ready-for-agent`, `claimed`, `in-review`, `needs-replan`, `done`.
- **A ticket starts when its blockers are merged,** not when their pull requests open. Stacked branches are faster but make every review and rebase harder; they are out of scope until the simple path is reliable.

## Who orchestrates

| Level | Orchestrator | How |
|---|---|---|
| 1. Manual | You | Open one session per frontier ticket (a Conductor workspace is one), run implement through pull-request, merge, repeat. |
| 2. Assisted | You, with a frontier view | A command lists the frontier and starts one headless session per ticket in its own worktree. You merge. |
| 3. Autonomous | A workflow | A script walks the frontier, runs the inner loop for each unblocked ticket in parallel, and stops at pull requests or at `needs-replan`. Merging stays human unless the repo's policy says otherwise. |

The orchestrator holds only the ticket graph, never code, so its context stays small however big the initiative is.

## Example: a new booking flow

A spec asks for a new flow where a household books a vet appointment: a database migration, three new API endpoints and three screens.

**Outer loop, once.** One interactive session: grill settles the open questions, distill writes the spec and splits it into tickets.

| # | Ticket | Blocked by |
|---|---|---|
| 01 | Add the appointments tables (expand only, nothing reads them yet) | None |
| 02 | Book an appointment end to end: one endpoint, one screen, the happy path | 01 |
| 03 | Pick a clinic and a time slot | 02 |
| 04 | Confirmation screen and notification | 02 |
| 05 | Cancel or reschedule | 03 |
| 06 | End-to-end test of the whole flow and removal of the feature flag | 03, 04, 05 |

**Inner loop, six times,** one session per ticket. The frontier moves like this:

1. 01 alone.
2. 02 alone, after 01 merges.
3. 03 and 04 in parallel.
4. 05, after 03 merges.
5. 06 last.

If ticket 03 discovers that slots need a new rule nobody specified, it stops with `needs-replan`, and the outer loop runs again for that question only.

So the answer to "how many cycles" is: one outer loop per initiative plus one per re-plan, and one inner loop per ticket plus one more pass per round of review comments.
