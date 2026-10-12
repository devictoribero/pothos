---
name: evidence
description: Captures proof that a change works, for the Evidence section of a pull request. It records the before and after of a test run, takes screenshots of the running app (web through a headless browser, iOS through the booted simulator) and writes an evidence.md, all stored outside the repository. Use after verify passes and before a pull request leaves draft, or when asked for "evidence", "proof", "screenshots" or "show me it works".
---

# Evidence

A reviewer should not have to run the branch to believe it works. This skill produces the proof and keeps it in `~/.config/pothos/evidence/<repo>/<branch>/`, never in the repository.

Mechanics go through `"${CLAUDE_SKILL_DIR}/scripts/evidence.py"`. Run it from inside the repository. `evidence.py dir` prints the folder.

## Check what this repository can show

Run `python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" plan` first. It prints one line per app the branch touches (in a monorepo, the `run.apps` entries whose folder changed) with its `screenshots` setting:

- `web` or `ios-simulator`: take screenshots that way, as described below. In a monorepo, start the app with `serve --app <name>`.
- `none`: do not start the app or try a screenshot. Use test output and real calls, and write "Not shown: screenshots, not supported in this app" in evidence.md.
- `unknown`: try once. If it fails, fall back to test output and tell the user to set `screenshots` with `/pothos:plant audit`, so the next run does not try again.

## Pick the kind of proof

Use the strongest proof the change allows, and more than one when they show different things.

| The change | Proof |
|---|---|
| Fixes a bug | The regression test failing on the base commit, then passing on the branch. Run only that test file both times and keep the two outputs. |
| Adds or changes behavior with no UI | The new tests' output, plus one real call (a command, a request) that shows the result. |
| Changes a web UI | Screenshots of each state the change touches: before (base branch) and after. |
| Changes a mobile UI | Simulator screenshots, when a simulator is booted. Otherwise the component tests' output, and say that screenshots need a device. |
| Refactor with no behavior change | The full suite passing before and after, and a note on what stayed the same. |

## Web screenshots

1. Start the app: `python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" serve [--app NAME] [--env NAME]`. It runs the contract's dev command and waits until `run.url` answers. It prints `pid=…`, or `already-running` when something already serves the URL. If the session context lists backend environments, use the one the user chose for this feature.
2. Shoot each state: `evidence.py shot "<url>/<path>" <name> [--width 390 --height 844 for mobile web]`. Name files `before-<state>` and `after-<state>`. Take the before shots on the base branch, in a separate worktree or before your first commit.
3. Pages behind a login: when the contract has `run.mocked: true`, the mocked backend needs no credentials. Otherwise follow `run.login` if set. If you can't reach the page, say so and fall back to test output. Never type real credentials.
4. Open each screenshot with the Read tool and check it shows what you claim. A blank page, an error overlay or a login wall is not evidence.
5. Stop the server you started: `evidence.py stop <pid>`.

## Write evidence.md

Write `evidence.md` in the folder `evidence.py dir` printed. Use this shape. It fits the Evidence section of the `pr` skill's template and most repository templates:

```markdown
## Evidence

- **Before:** <what was wrong, with the failing output or screenshot path>
  **After:** <what is right now, with the passing output or screenshot path>
- **Checked:** <verify receipt line, e.g. "verified: full passed on 3f2a91c04b1e">
- **Not shown:** <anything you could not capture and why>
```

## Images in the pull request

If the contract has `pr.evidence`, run it with the screenshot paths. It uploads them and prints markdown to embed. Otherwise, do not commit screenshots to the repository. Describe each one in a line, keep the files local, and tell the user where they are, so they can drag them into the pull request.

## Rules

- Evidence must come from the commit being proposed. If you change the code afterwards, capture it again.
- Never stage, fake or edit a screenshot or an output.
- Keep evidence.md short: the reviewer reads it in under a minute.
