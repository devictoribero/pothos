---
name: component-design
description: Designs, builds, reviews and audits UI components (React, React Native or any component technology) as composable puzzle pieces: dependencies that point one way, business-agnostic primitives in product language, clean platform-standard APIs with consistent names, closed states, accessibility designed in, and contracts with one test per line so components stay easy to test, extend and maintain. Ships scripts that check dependency direction, names, contract-to-test coverage, and run type-check and tests in a scratch copy. Use it when designing, implementing, reviewing or auditing a component, a design-system primitive or a feature module.
---

# Component Design

Components are puzzle pieces: small, honest about what they need, and joined by composition rather than hidden behind configuration. Design them so they are easy to **test**, **extend** and **maintain**, and so anyone can **verify** them by reading the contract next to the tests. This file is the judgment; `references/` holds examples and rules; `scripts/` checks what can be checked mechanically. Planning and sequencing a migration across a codebase is a process concern and stays out of this skill.

## How to use this skill

1. Decide the **kind**: a **primitive** knows no business and speaks product and UI words (`author`, `body`, `action`, `media`); a **feature component** renders one concept of one product (`JobCard`) by composing primitives. Asked for something reusable with no design system: build both, the primitive and a thin feature on top.
2. Look for what exists before writing: a component with the same role (button, field, dialog, menu, card) in the shared UI folder or the design system, the shared hooks and helpers, the tokens and icons; when the session context names those folders, start there. Reuse or extend it (`references/mechanics.md`, Project plumbing): a second button costs every future consumer a choice. Then read one component and one test next to where yours goes. With no project, write your assumptions at the top of each file.
3. Settle every row of the **decision guide** below, reading the example it points to. Write the contract (`references/contract.md`) before the code.
4. Build. Then run `scripts/verify.sh`, `scripts/lint.py` and `scripts/check_contract.py`, and fix until they pass. Render the preview and look at it.
5. Summarize what you assumed, what you decided that the request didn't, and anything you could not run, in the first lines.

Read `references/examples.md` first: most decisions below are shown there as a good and a bad version side by side.

## Principles

1. **Dependencies point one way.** Screens depend on features, features on primitives, primitives on the platform and shared helpers only. A primitive never imports a feature, a domain type, a DTO or a data hook, and its props speak product and UI language, never one business (`media`, `title`, `meta`, not `listing`, `price`, `bedrooms`). A feature reaches another feature only through its public entry. Data flows down as props; what happens flows up as events.
2. **Compose, don't encapsulate.** Each piece does one job and fits with others: the consumer passes content and composes parts, never data the component unpacks, flags that show parts, or props bags. Presence is the configuration. When a component seems to need knowledge of its consumer or its environment (URL, router, storage, locale, user), the varying piece becomes a slot or a prop instead.
3. **The API is the platform's, with more.** A real semantic element, every native attribute and event passed through, native form participation, and the platform's names (`disabled`, `open`, `value`, `onClick`). A URL change is a link. Invent a name only where the platform has none.
4. **Names are consistent everywhere.** The same thing has the same name in every component: one vocabulary for props, union values and handlers (`references/naming.md`), checked by `scripts/lint.py`.
5. **The consumer owns the state.** Controlled by default; the component never changes controlled state itself. Several possible states are a closed union rendered exhaustively, so nothing impossible can be written.
6. **Accessibility is designed with the API.** Role, name, keyboard, focus and announcement change the API, so they are decided first. State is never color alone, and focus never drops.
7. **Easy to test, extend and maintain.** The contract is the test list: each fact has a test with the same words, and every state renders in a test and in the preview. New needs are additive (a part, an optional prop, a union value); a breaking change updates every consumer in the same change, with no shims. One way to do each thing, and no helper written twice.

## Decision guide

| Decide | Options | Rule | Example |
|---|---|---|---|
| Each piece of content | slot prop · part · typed data | **Slot prop** for a fixed region the component places (column, corner, wrapper): `avatar={…}`. **Part** for what varies, repeats or grows: `<Comment.Meta>`. **Typed data** only when the component operates on the items (orders, derives state, counts): `steps={[…]}` | Comment, Stepper |
| A part every consumer would add | default · explicit part | Render it by default; replaceable with a slot, removable with `null`. Native structures (tables) keep their HTML parts | Callout |
| Nesting | nested part · composed component | Nest only when it reads root values or the root lays it out. One dot level | Chat |
| Many items | children · owned iteration · typed data | Children by default. Owned iteration for virtualization, select-all or items the component computes. Neighbor-dependent layout is a grouping part, never a per-item flag | Chat, Stepper |
| Each state | controlled · uncontrolled with default · by presence · internal · derived | Controlled (`value` + `onValueChange`, `open` + `onOpenChange`) by default. Transient UI is controlled by presence and asks to leave with `onDismiss`. Hover, focus and timers are internal. A value that follows from props or other state is derived at render, never stored (`references/mechanics.md`, State) | Tabs, Workbench |
| A value several parts need | root value · part prop | Root only when several parts need it or it is a whole-component state (`readOnly`) | Chat |
| States that exclude each other | union · booleans | One union per independent axis, each member carrying its data; exhaustive `switch` with `never` | Stepper |
| Names | see `references/naming.md` | Platform words for platform states (`open`, `checked`, `disabled`); item identity `value`; `aria-label` when the name lands on the root; handlers named by where they land; never `default` as a union value | Tag, Tabs |
| Optional capabilities | handler presence | A capability exists only when its handler is passed: no `onWidthChange`, no resize handle | Workbench |
| Layout panes on narrow screens | derived · separate state | Derive the visible pane from the selection (nothing selected shows the list; Back clears it); never a second `pane` state that can contradict it. Escape is handled by the innermost layer and stopped | Workbench |
| Where code lives | primitive · feature · screen | Primitives in the shared UI folder with no business imports; business rules, data and copy in the feature; routing and wiring in the screen. `scripts/lint.py` checks the direction | Card in two layers |
| Extracting a piece | private file · shared · inline | A piece with one coherent job, a name a consumer would look for and tests of its own may be a file of its own, private to the feature; it moves to the shared UI or hooks folder only when a second consumer appears. Never for length alone, or because the design file has a layer with that name. State ownership is the "Each state" row, whatever the request says | Extracting a piece |
| Outer layout | none | No outer margin, width or self-positioning; overlaid parts offer an `Anchor` and `placement` | Comment |
| Copy | consumer's | A primitive holds no copy, numbers or units; accessible names content can't provide are required props | AvatarGroup |
| Files and exports | namespace with `Root` · plain export | Parts make a namespace (`<Tabs.Root>`); no parts, a plain export. Project conventions win | Tabs |
| Change to an existing API | additive · migration | Optional part, then optional prop, then union value. Otherwise migrate every consumer in one change; pin current behavior with tests first | — |

Anything the input doesn't settle is written in the contract's Decisions with its reason. When the input asks for something these principles reject (reading the URL), satisfy it from the consumer side, show the recipe and record the deviation. When it contradicts a documented spec or a design decision, keep the documented behavior and ask. A visual change to a shared primitive (weight, size, color across every use) is a design question, not a fix.

## Verification

- The contract's minimal and full usages are the first two tests.
- Every line of the contract's State, Behavior and Accessibility sections has a test with the same words. `scripts/check_contract.py <README.md> <test files…>` lists the lines with no matching test.
- Every member of a closed set and every failure state renders in a test.
- Every test has the Given, When, Then structure: the situation in a `describe('given …')`, one plain sentence per `it` (`it('sends it again when the reader presses Retry')`), with setup, action and check separated by blank lines. Names use the product's words so a non-technical person understands them.
- Tests go through roles, text and real interaction, never class names or handler calls.
- `scripts/lint.py <src> --business-words <the domain's words>` flags imports that point the wrong way (a primitive importing a feature, domain, DTO or data module; a feature reaching into another feature's internals), business words in primitive props, and names off the vocabulary (`isOpen`, `onSelect`, `selectedId`, `default` as a value, `id` as an item's identity).
- `scripts/verify.sh <project> [overlay-dir]` runs the project's type-check and tests in a scratch copy, so the project is never modified; with an overlay, its `src/` is laid over the copy and only the overlay's test files run. Without a project, `scripts/verify.sh --minimal <dir>` builds a minimal one.
- The preview shows **every state** the product needs side by side, rendered from the real components: loading, empty, failed, failed after retry, long and missing content, and each member of each closed set. A state that exists only in code is invisible to the reviewer.
- When behavior lives in CSS (sticky, overflow, layering), also look at it in a real browser or a headless screenshot: jsdom doesn't lay out.
- Look at layouts narrow as well as wide: at 390 px (a viewport, or a 390 px container when the browser will not shrink) the page never scrolls sideways, every control stays reachable and text wraps; a box that scrolls by design (a wide table) scrolls inside its own bounds. The preview includes one 390 px wide container, so the reviewer sees it: panes and toolbars that only work wide are not done.

Details and tooling: `references/testing.md`. How to write the tests themselves (test data, what to replace, timers, async): the testing standards listed under Coding standards in the session context (`standards/testing.md` in this plugin).

## References

| File | Read when |
|---|---|
| `references/examples.md` | Always, first: good and bad versions of the decisions above |
| `references/naming.md` | Naming anything |
| `references/accessibility.md` | Roles, names, keyboard, focus, announcements per pattern |
| `references/contract.md` | Writing the contract |
| `references/testing.md` | Writing and running tests |
| `references/mechanics.md` | React mechanics: context, registration, defaults, pass-through, hosts, layouts, scroll containers, sortable lists |
| `references/feature-components.md` | Building a feature component |
| `references/audit.md` | Reviewing a folder of existing components |
| `evals/` | Changing this skill: run the fixed eval set and compare scores before and after |
