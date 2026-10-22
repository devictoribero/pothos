---
name: evidence
description: Captures proof that a change works, for the Evidence section of a pull request. It records the before and after of a test run, takes screenshots of the running app (web through a headless browser, iOS through the booted simulator, Android through the running emulator, or a mobile screen without a device through the repository's capture command) and writes an evidence.md, all stored outside the repository. Use after verify passes and before a pull request leaves draft, whenever a change touches a screen, or when asked for "evidence", "proof", "screenshots" or "show me it works".
---

# Evidence

A reviewer should not have to run the branch to believe it works. This skill produces the proof and keeps it in `~/.config/pothos/evidence/<repo>/<branch>/`, never in the repository.

Mechanics go through `"${CLAUDE_SKILL_DIR}/scripts/evidence.py"`. Run it from inside the repository. `evidence.py dir` prints the folder.

## Check what this repository can show

Run `python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" plan` first. It prints one line per app the branch touches (in a monorepo, the `run.apps` entries whose folder changed) with its `screenshots` setting:

- `web`, `ios-simulator` or `android-emulator`: take screenshots that way, as described below. In a monorepo, start the app with `serve --app <name>`.
- `none`: do not start the app or try a screenshot. Use test output and real calls, and write "Not shown: screenshots, not supported in this app" in evidence.md.
- `unknown`: try once. If it fails, fall back to test output and tell the user to set `screenshots` with `/pothos:plant audit`, so the next run does not try again.

## Pick the kind of proof

Use the strongest proof the change allows, and more than one when they show different things.

| The change | Proof |
|---|---|
| Fixes a bug | The regression test failing on the base commit, then passing on the branch. Run only that test file both times and keep the two outputs. |
| Adds or changes behavior with no UI | The new tests' output, plus one real call (a command, a request) that shows the result. |
| Changes a web UI | Screenshots of each state the change touches: before (base branch) and after. |
| Changes a mobile UI | The screens `evidence.py screens` names, captured as described under "Mobile screens": through the capture command when the contract has one, else on the simulator or emulator that is already running, else listed in the pull request's test plan for a person to check by hand. |
| Refactor with no behavior change | The full suite passing before and after, and a note on what stayed the same. |

## Web screenshots

1. Start the app: `python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" serve [--app NAME] [--env NAME]`. It runs the contract's dev command and waits until `run.url` answers. It prints `pid=…`, or `already-running` when something already serves the URL. If the session context lists backend environments, use the one the user chose for this feature.
2. Shoot each state: `evidence.py shot "<url>/<path>" <name> [--width 390 --height 844 for mobile web]`. Name files `before-<state>` and `after-<state>`. Take the before shots on the base branch, in a separate worktree or before your first commit.
3. Pages behind a login: when the contract has `run.mocked: true`, the mocked backend needs no credentials. Otherwise follow `run.login` if set. If you can't reach the page, say so and fall back to test output. Never type real credentials.
4. Open each screenshot with the Read tool and check it shows what you claim. A blank page, an error overlay or a login wall is not evidence.
5. Stop the server you started: `evidence.py stop <pid>`.

## Mobile screens

A screen can pass its tests and still be wrong: a layout that overflows at a large font scale, a sheet whose title sits under the handle, a translation that wraps where the original did not. Only a picture catches that.

1. **Which screens.** Run `python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" screens`. From the contract's `ui.screens`, `ui.components`, `ui.tokens` and `ui.locales` it lists the screen files the branch changed, the screens that import a changed component or token (one grep level; when none does, name the screens that use it yourself), the languages whose copy changed, the languages to capture and the capture command. `none` means the change reaches no screen: skip this section and say so. Capture at most three screens, the ones most changed; name them and the ones you left out in the pull request.
2. **Which languages.** The first of `ui.languages` always; the others only when the change edits copy (`screens` prints the list). A translation that wraps differently is one of the bugs this is for.
3. **Where you are.** No `adb` and no simulator (a cloud session): use the capture command when the contract has one; without one, list the screens in the pull request's test plan, one checkbox each with the screen, the state and the language, so the reviewer looks at the right ones, and say that no screenshot was possible. On a laptop with the capture command, prefer it; use the emulator for what it cannot show (font scale, native surfaces).
4. **Capture command.** `evidence.py capture <screen> [<screen> ...] --lang <codes> --base <branch>` runs the contract's command (`<command> <screen> --lang <code> --out <dir> [--base <ref>]`), keeps what it prints as `after-<screen>-<lang>.png`, and the `*-base.png` images as `before-…`. The screen names are the repository's (read the doc the contract names for the list and for how to add one). If the command fails with `--base`, run it again without and say the pair is missing and why. The repository decides what the command cannot show; repeat that in evidence.md under "Not shown".
5. **Emulator or simulator.** Only one that is already running with the branch's code: never start one, never start the bundler (that kills the developer's), and when a person is using the device, ask them for the screenshot instead of opening anything. The app must be signed in, or the link lands on the login. Open the screen with a deep link (`adb shell am start -W -a android.intent.action.VIEW -d "<scheme>://<path>" <package>`, `xcrun simctl openurl booted "<scheme>://<path>"`); a link opens a screen, never a sheet, dialog or menu, so for those tap once (`adb shell input tap <x> <y>` at a coordinate you read off a capture, fragile, say so) or ask the person. Switch the language the way the repository's run doc says; an app that follows the account's language needs the account changed, not the device. Then `evidence.py emu <name>` or `evidence.py sim <name>`. Font scale, emulator only: `adb shell settings put system font_scale 1.3`, capture, then the largest value the device accepts (read it back with `settings get system font_scale`), capture, then put `1.0` back.
6. **The pair.** Capture the same screen on the base branch first, same link, same language, same scale: `--base` on the capture command, or the base branch's code on the device from a worktree. If the pair cannot be produced, say why and capture the new state only.
7. **Look.** Open every capture with the Read tool and check it shows the screen and state you claim; a splash, a login or a blank page is not evidence. Label each image with the screen, the state and the language in evidence.md.

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

- `pr.evidence` is `github-release`: run `evidence.py upload <files>`. It adds them to this month's `pr-evidence-YYYY-MM` prerelease, named after the pull request (or the branch before one exists), and prints markdown to embed. Nothing is ever deleted from those releases: they are the pull requests' history.
- `pr.evidence` is any other value: run it with the screenshot paths. It uploads them and prints markdown to embed.
- No `pr.evidence`: do not commit screenshots to the repository. Describe each one in a line, keep the files local, and tell the user where they are, so they can drag them into the pull request.

Lay a before and after out side by side, one row per screen and state. Phone captures are tall, so give them a fixed width:

```markdown
| Screen · state | Before | After |
|---|---|---|
| Home · empty | <img src="<before url>" width="280"> | <img src="<after url>" width="280"> |
```

## Rules

- Evidence must come from the commit being proposed. If you change the code afterwards, capture it again.
- Never stage, fake or edit a screenshot or an output.
- Keep evidence.md short: the reviewer reads it in under a minute.
