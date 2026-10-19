---
name: tend
description: Babysits a ready pull request, one pass per run. It answers review comments, fixes failing checks and updates a branch that fell behind. When everything is green and a person gave the pull request the contract's auto-merge label, it merges through a script that checks the head commit and deletes the remote branch. Use when asked to "babysit", "watch", "look after" or "tend" a pull request, to "handle the review comments", to "get this PR green" or to "merge it when it's green", and from `/loop /pothos:tend <number>` to keep watching.
argument-hint: "[pull request number]"
---

# tend

Looks after one pull request that is already ready for review. Code review, verify and evidence happened before the pull request was ready, so this skill never reviews the code again. It reacts only to what comes from outside: review comments, checks and the label.

Every merge decision goes through `"${CLAUDE_SKILL_DIR}/scripts/merge_gate.py"`. Run it from inside the repository.

## Rules

- **One pass, one action.** Read the state, do at most one thing (answer the comments, fix one red check, or update the branch), then run the gate and stop. Never wait inside the skill: a skill that sleeps dies with the turn. Waiting belongs to `/loop /pothos:tend <n>` or to `pothos-run.py`.
- **Never add the auto-merge label,** not even when asked: it is the person's decision that this pull request may merge itself. Ask them to add it.
- **Never run `gh pr merge`.** Only `merge_gate.py merge` merges, and only when its verdict is ready. A hook blocks both.
- **The label is the confirmation to publish on this pull request.** With it, push fixes and reply to threads without asking. Without it, confirm right before each push or reply when a person is available, and stop with a report when nobody is.
- **A person's thread is theirs to resolve.** Fix and reply, never resolve it. A bot's thread may be resolved once the fix is pushed.
- **Draft pull requests belong to `implement-spec`.** Leave them alone and say so.
- **GitHub only.** On another code host, say the gate cannot run there and stop.

## Steps

1. **Find the pull request.** Use the number given, or the current branch's: `gh pr view --json number`. Check out its branch in a worktree or the current checkout, up to date with the remote.
2. **Read the state.**
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/merge_gate.py" status <n>
   ```
   It prints the checks, reviews, open threads, mergeability, whether the pull request is a candidate, and a verdict.
3. **Pick the one action**, in this order:
   - **Ready and a candidate:** go to step 5.
   - **Draft, closed, or changes requested:** nothing to do yourself; report what is needed and who must act.
   - **Unanswered review comments:** follow `references/review-comments.md`.
   - **A failed check:** read its log (`gh run view <run-id> --log-failed`, the run id is in `gh pr checks <n>`), fix the cause, run `verify` (`/pothos:verify`), commit and push. Never weaken, skip or delete a check.
   - **Branch behind the base:** merge the base into the branch, run `verify`, push.
   - **Checks running, conflicts, or only waiting left:** do nothing this pass.
4. **After a push,** run the gate again only to report; new checks start running and the next pass picks them up.
5. **Merge,** only when the verdict was ready:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/merge_gate.py" merge <n>
   ```
   It merges with the contract's method pinned to the head commit and deletes the remote branch. Then close the work the way the tracker in the session context says: a GitHub or GitLab issue closes through `Closes #N` in the pull request (check it closed); in the local tracker, set the ticket's `Status:` to done in the main checkout; with a tracker skill, go through that skill.
6. **Report** in a few lines: the gate's verdict line quoted as printed, what you did this pass, and the next step: run the pass again later (`/loop /pothos:tend <n>`), what a person must do, or that the pull request is merged.

In a repository with `workflow: repo`, run this skill only when the user names it. Use the repository's own skills for review feedback and checks (for example a `*-pr-triage` skill), and use the gate only to read the state and merge.

## Exit codes of the gate

`0` ready (status) or merged (merge), `1` waiting, `2` no contract (suggest `/pothos:plant`), `3` not a candidate (no `pr.auto_merge` in the contract, no label, draft, closed or another base), `4` needs a person (changes requested or conflicts), `5` gh missing or failed (a refused merge lands here: read the message), `64` usage.
