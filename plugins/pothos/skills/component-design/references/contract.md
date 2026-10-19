# Contract template

The contract records what code can't say: how parts compose, who owns state, invariants, accessibility and why. It lives next to the component (`README.md` or the doc block) and changes in the same change as the API. Props, types and defaults stay in TypeScript and JSDoc, never here. Omit sections that don't apply; a leaf component (icon, divider) needs only purpose, usage, accessibility and decisions.

Write State, Behavior and Accessibility as **one fact per bullet**, phrased so it can be a test name: in the product's words where possible ("Using a control in the action never opens the card" rather than "never calls `onOpen`"), so the test that proves it can say the same thing. `scripts/check_contract.py` matches each bullet to a test.

````markdown
## <ComponentName>

**Purpose:** <one line of product vocabulary; whether a host is needed>
**Assumed plumbing:** <what you assumed because the project couldn't be read; omit if none>

**Minimal usage**
```tsx
<the most frequent case, as consumers will write it>
```

**Full usage**
```tsx
<every part and slot in use>
```

**Parts**
| Part | Kind | Accepts | Renders as | Required |
|------|------|---------|------------|----------|
| `<Name>.Root` | root | | <element; where pass-through and ref land> | yes |
| `<slotProp>` | slot prop | | | |
| `<Name>.<Part>` | text part / grouping part / control / state part / layout part / field | | | |

**State**
- <state> is <controlled / uncontrolled with default / by presence / internal / derived from <what>>: <what changes it, what it changes>

**Behavior and invariants**
- <one fact per line, e.g. "Without `onOpen` the card has no interactive element of its own", "A selected item that leaves `items` renders as nothing selected">

**Accessibility**
- <one fact per line: role, name, keyboard, focus after each action, announcement>

**Recipes (consumer side)**
- <integrations the component enables but doesn't own: URL sync, router links, persistence>

**Decisions**
- <decision>. <why>. <to confirm with whom>

**Out of scope**
- <what it deliberately doesn't do>
````

A skeleton for loading is `<Name>.Skeleton` (with parts) or `<Name>Skeleton` (without): it shares the root's private layout, is `aria-hidden`, and the list around it announces loading.
