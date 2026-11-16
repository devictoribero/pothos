---
name: council
description: Contrasts a decision before it is taken. Independent advisors read the repository, reviewers check their claims anonymously, and one verdict comes out. Use for a fork with real alternatives that is costly to revert ("council this", "pressure-test this decision", "¿A o B?" with stakes). Not for what a test, a prototype or a cheap undo settles.
argument-hint: "[the decision]"
---

# council

One agent asked "A or B?" anchors on how the question was put. A council gives the same question to advisors who each hold one angle and cannot see each other, has reviewers check their claims without knowing who made them, and ends in one verdict tied to evidence in the repository.

**Output:** a council folder outside the repository with every answer, the verdict and a receipt; `check` exits 0 only when it is complete.

Every command calls `"${CLAUDE_SKILL_DIR}/scripts/council.py"`. Write that full path each time: shell variables do not survive between tool calls. The script prints what to do next; follow its `next:` line.

## When

- **Where in the cycle:** after `grilling` has made the options concrete, before `to-spec` or a decision record fixes one. Also when a ticket comes back `needs-replan` or a review finds a design fork: there, list the code already written as a cost of an option, never as the default.
- **Why here:** `grilling` questions the person, `code-review` judges code that exists, `prototype` answers what running it can answer. This is the one step that contrasts a decision before it is taken.
- **Size it by three facts:** is it costly to revert, does it cross a module or a public contract, does it create or contradict a recorded decision? No yes: answer directly, run nothing. One yes: a light council, three advisors. Two or three: a full one, five advisors, three reviewers and a chair.
- **Stand aside** when a test, a measurement or a prototype settles it (name it instead), when a recorded decision already answers it (cite it), and when the person has decided.

## Rules

- The brief is neutral. Your lean and the person's go under `Sealed lean`, which no advisor, reviewer or chair ever sees.
- Advisors, reviewers and the chair store their own text through the script and reply with one line. Read `check`'s output, never their files.
- The verdict is the council's. Add what the council could not know as your own note after it, marked as yours.
- The decision is the person's. Record it with `decide` once they take it.

## Steps

1. **Open.** Pipe the brief to `python3 "${CLAUDE_SKILL_DIR}/scripts/council.py" open --slug <kebab-slug> --revert y|n --wide y|n --decision y|n`. Run it with an empty brief first when you need the form: the refusal prints it. Search the decision records and the glossary before writing `Recorded decisions`. Done when it prints `spawn:` lines.
2. **Seat the council.** Spawn every `spawn:` line as one subagent, all in one message, with the model and the prompt the line gives (`inherit` means no override). A seat that does not reply `stored` is spawned once more.
3. **Review** (full only). Run the `next:` command, then spawn its lines the same way.
4. **Tally.** Run the `next:` command. Full: spawn the chair it prints. Light: you are the chair; write the verdict from the packet it prints and store it with the command the packet ends on.
5. **Check and reply.** `python3 "${CLAUDE_SKILL_DIR}/scripts/council.py" check <folder>` prints the verdict and whether the council moved the lean. Reply with the verdict as stored, the folder, and the next step: `domain-modeling` to record the decision once the person takes it, or `grilling` when the verdict left questions only they can answer.
