# Testing and verification

Tests are the executable contract: a reviewer verifies the component by reading contract bullets and test names side by side, and the next person changes it without fear.

## What every component ships

1. The contract's **minimal and full usages** are the first two tests, and type-check as a consumer would write them.
2. **One test per contract bullet** in State, Behavior and Accessibility, with the bullet's words: "Without `onOpen` the card has no interactive element of its own" becomes `describe('given a card without onOpen')` › `it('has no interactive element of its own')`. Run `scripts/check_contract.py README.md *.test.tsx`.
3. **Every member of a closed set** and every failure renders: loading, empty, failed, failed again after retry.
4. **The preview shows every state** side by side from the real components, with realistic content: the states above plus long and missing content. Reviewers judge what they can see.
5. Every part that reads context **throws its documented error** outside its root.
6. Tests go through **roles, text and real interaction**. A test id or class only when no accessible query exists, with a comment saying why. Never assert that a handler was called in place of what the user sees, except for the event payload itself.
7. **Controlled state never changes on its own**: render controlled, interact, assert the handler got the next value and the UI didn't move.

## Writing tests

How to write any test (structure, names, test data, what to replace, fake timers, async) lives in the testing standards (`standards/testing.md` in this plugin, listed in the session context); use them together with this file. What a component test needs on top:

- `describe('<Component>')` › `describe('given <situation>')` › `it('<result> when <action>')`, with setup, action and check separated by blank lines in the body (comment markers optional), and names a non-technical person understands: the contract bullet's words become the test's words.
- Content and items come from mothers (`createMessage({ status: 'failed' })`), never hand-written objects or `as`.

## Changing an existing component

Before redesigning, **pin current behavior** with tests through the public API: what renders in each state, what each interaction does, what consumers rely on. Then change. A test that breaks is either an intended change (update it in the same change and say so) or a regression. Migrate every consumer in the same change and run their tests too.

## Running

- `scripts/verify.sh <project-dir> [overlay-dir]` copies the project to a scratch folder, links `node_modules` package by package (linking the whole folder lets Vite write caches into the original), lays your files over it, and runs the project's type-check and tests. The original is never modified.
- Without a project, `scripts/verify.sh --minimal <overlay-dir>` builds a throwaway React 18 + TypeScript + Vitest + Testing Library project.
- If you could not run something, the first line of your summary says so.
- **CSS behavior** (sticky, overflow, layering, stretched hit areas): assert the DOM facts it depends on, and look at it in a real browser or a headless screenshot. jsdom doesn't lay out, and specificity bugs pass in jsdom.

## Feature components, by layer

- Domain functions: unit tests over every state and permission.
- DTO adapter: real-shaped fixtures.
- View: one test per domain state from factories, and each member of the resource union when it has a frame.
- Container: data access replaced at the network boundary with MSW handlers (see the testing standards), never by mocking its hooks. Every UI state, each intention's pending and failed states, a failure clearing on retry, loaded content surviving a failed refresh.
- Time and identity are inputs; never read them inside domain functions.

## React tooling

- Testing Library and `user-event`. Check the installed `user-event` version: from 14, `const user = userEvent.setup()` and `await user.click()`; below 14 there is no `setup()` or `keyboard()`, so call `userEvent.click(el)` synchronously and wrap later assertions in `waitFor`.
- `fireEvent` only for events a user can't produce (`load`, `error`, `transitionend`).
- Portaled content (popover, dialog): query through `screen`. Polyfill what jsdom lacks (`ResizeObserver`) instead of mocking the component.
- Usage tests type-check only if the project's `tsc` includes test files.
- React Native: `@testing-library/react-native` with Jest and the `react-native` preset; `getByRole` matches `accessibilityRole`.
