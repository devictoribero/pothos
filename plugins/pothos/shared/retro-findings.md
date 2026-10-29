# Retro findings

A retro finding is one change to the agent's environment worth making later: a missing check, a
skill step that left the agent guessing, a hook message that hid the way forward. `/pothos:retro`
presents them; any session that hits such friction may record one. They live outside the
repository, in the Pothos home, one file per finding:

```
<pothos home>/retros/<host>/<owner>/<repo>/<slug>.md
```

- **One file per finding, not per session.** Parallel sessions never edit the same file, and a
  finding seen twice gathers its occurrences in one place.
- **Filed under the repository where the fix lands**, which is not always where the friction
  showed up: a fix to a plugin hook goes under the plugin's repository. The key is the same
  `<host>/<owner>/<repo>` as the contract's.
- **The slug names the fix**, in kebab-case: `merge-guard-names-authorize-path`, not
  `merge-blocked`.
- **Look before you write.** If a file in that folder covers the same finding, add an occurrence
  to it instead of creating a second one. A finding that keeps recurring is the signal it should
  be fixed next.

## Format

```markdown
---
status: open # open | deferred | done | dropped
severity: high # high | medium | low
opened: 2026-10-29
---

# <The change, as an imperative>

## Occurrences

- 2026-10-29, PR #12 (<repo or worktree>): what happened, in one or two sentences.

## Proposal

The change, concrete enough to apply without the session: file, line, wording.

## Notes

Optional: related pull requests, gotchas, open questions.
```

`deferred` is a decision to wait, with the reason under Notes. Close a finding with `done` and a
dated line under Notes naming the pull request or commit that fixed it; `dropped` says why. Never
delete a file: its occurrences are the history.
