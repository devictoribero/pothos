## Button

**Purpose:** the action control of the product. A URL change is a link, not a button.

**Minimal usage**
```tsx
<Button onClick={save}>Save</Button>
```

**Full usage**
```tsx
<Button variant="danger" isPending={isDeleting} onClick={remove} aria-describedby="hint">Delete</Button>
```

**State**
- `isPending` is controlled by the consumer: while true the button announces busy and ignores clicks.

**Behavior and invariants**
- Clicking a pending button does nothing.
- Every native button attribute and event passes through to the element.
- `type` defaults to `button` so a button inside a form never submits by accident.

**Accessibility**
- The element is a native button with the visible text as its name.
- A pending button is `aria-busy` and `aria-disabled`.
- A pending button stays in the tab order.

**Decisions**
- `isPending` instead of `disabled` while saving, so focus never drops when a save starts.
- Pending shows a spinner next to the text (CSS on `aria-busy`), so the state is never color alone.
