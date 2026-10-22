# Visual verification of mobile changes · 22 October 2026

The finding for the second round of the Lifetails pilot: what visual verification an agent can do on an Expo app from a cloud session, which tier works, what it costs, and what does not work. Dated snapshot; the mechanism-independent rule lives in the `evidence` skill ("Mobile screens"), the mechanism in the Lifetails pull request named below.

## The answer

**Possible in a cloud session, through a web render of the whole app.** `npx expo export --platform web` bundles the entire app (Expo 54, React Native 0.81, Expo Router 6, NativeWind's Metro wrapper included) on the first try, and it boots in the session's Chromium (Playwright build 1194, `playwright-core` 1.56.1) once three packages with no web implementation are replaced: `expo-secure-store`, `expo-notifications` and `burnt`. The real root layout, the real auth bootstrap on a seeded Supabase session, the real `AuthRedirectGuard`, the tab bar, the fonts, both languages, and the real `@gorhom/bottom-sheet` 5.2.8 with its backdrop, handle and header. The record sheet, one of the three bugs the round was for, is covered.

A fresh session, no manual step, five screens in Spanish and Catalan: 78 seconds including the one-minute export, 27 seconds from a warm one. A before-and-after pair against the base branch (worktree, install, export, capture) adds 28 seconds. Three runs produce byte-identical images once the harness verifies the route push, seeds `Math.random` and photographs only a still frame. That meets the bar (the same command twice, a screenshot of the affected screen, under five minutes), so tiers two and three were not pursued further than the one-line check: `ls /dev/kvm` and `which adb emulator` find nothing in a cloud session, and the laptop's emulator stays the reference for what the web tier cannot show.

## What carries it

| Where | What |
|---|---|
| Lifetails pull request `feat(mobile): web screenshot tier` on branch `mobile-web-screenshot-tier` | `scripts/screenshot/` (the capture command, stand-ins, scenarios on the spec builders, specs), the Metro alias on `web`, `playwright-core`, `react-native-web` and `react-dom` as devDependencies, `docs/workflows/screenshots.md`, language and font-scale sections in `opening-a-screen.md`, `docs/research/mobile-visual-verification/2026-10-22.md` with the measurements, `docs/decisions/0056`. |
| This Pothos branch | Contract fields `run.capture`, `ui.screens`, `ui.locales`, `ui.languages`; `evidence.py screens` and `evidence.py capture`; the "Mobile screens" step of the `evidence` skill; the session context lines; `plant`'s mapping; the eval `evidence-screen-capture`. |
| The owner's private contract, by hand | For the mobile app: `capture.command` `pnpm --filter @lifetails/mobile screenshot`, `capture.doc` `apps/mobile/docs/workflows/screenshots.md`, `ui.screens` `apps/mobile/features/*/screens` and `apps/mobile/app/**/_layout.tsx`, `ui.locales` `apps/mobile/shared/i18n/locales`, `ui.languages` `es`, `ca`; and `pr.evidence: github-release` so the images reach the pull request. `/pothos:plant audit` validates the paths. |

## Tiers

1. **Web render.** Works, as above. Not needed: the fallback entry that mounts one screen in the providers, and the page of components alone (all 26 primitives and 24 patterns ride along inside the real screens).
2. **Emulator.** Not a tier in the cloud: no KVM, no SDK, no `adb`. On the laptop it works as `opening-a-screen.md` describes, and the two steps nobody had written are written now: the signed-in app follows the account's language (Cuenta › Idioma, not the device locale, which only decides the welcome screen), and the font scale is `adb shell settings put system font_scale 1.3` then the largest value the AVD accepts, read back with `settings get`. A sheet needs one tap after the link (`adb shell input tap`, at a coordinate read off a capture, fragile) or a person.
3. **Maestro.** Not started: tier one met the bar, and Maestro would sit on tier two.

## What the web tier does not show

Font scale (a shim in the `Text` primitive would be a product change, its own decision), native surfaces (date picker, keyboard, share sheet, image picker, push), toasts (printed to stderr instead), Skia and video screens (the weight chart, the media pager), and pixel fidelity: the browser's line breaking and font rendering differ from Android by a pixel or a word, so the tier answers "does this look right", and the emulator decides exact wrapping. iOS was not measured; the simulator path has the same shape (`xcrun simctl openurl`, `xcrun simctl io booted screenshot`), unverified.

## Where a screenshot lives

`.context/` is gitignored and the GitHub CLI cannot put an image into a description. The answer already existed in Pothos: `pr.evidence: github-release`, under which `evidence.py upload` adds the images to a monthly `pr-evidence-YYYY-MM` prerelease and prints the markdown to embed. The Lifetails contract has to set it (it publishes, so `plant` asks first). Without it the images stay on disk, the test plan names them, and the person drags them in: that fallback is written into the skill.

## What the first captures found

Two things nobody had seen, which is the point: the add-record form wraps the meal-type chips mid-word in Spanish at 390 CSS pixels ("Húmed a", "Natura l"), to confirm on the emulator before fixing because the browser may break the word differently; and the record sheet titles a treat "Menjar Sec" in title case above a row that says "Menjar sec". Both are in the Lifetails research file with the captures.

## Rules the step encodes

- A change touches a screen when it reaches `ui.screens`, `ui.components`, `ui.tokens` or `ui.locales`; for a component or token, the screens are the ones that import it (one grep level, `evidence.py screens`); at most three captured, named with the ones left out.
- The first of `ui.languages` always, the rest when copy changed.
- The base pair first, same screen, same language, same scale; when it cannot be produced, say why and capture the new state only.
- In a cloud session: the capture command when the contract has one, otherwise the screens listed by hand in the test plan. On a laptop: the emulator and bundler that already run, never started; a signed-in session; and when a person is using the emulator, ask them for the screenshot.
- Every capture is opened and looked at before it is called evidence.
