## TextField

**Purpose:** a single-line text input with its label and validation message.

**Minimal usage**
```tsx
<TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
```

**Full usage**
```tsx
<TextField label="Name" value={name} onChange={handleChange} error="Name is required" autoFocus maxLength={80} />
```

**State**
- `value` is controlled by the consumer, as on a native input.
- Uncontrolled with `defaultValue` also works.

**Behavior and invariants**
- Every native input attribute and event passes through to the input.
- With `error` the input is invalid and described by the message.

**Accessibility**
- The input is labelled by the visible label.
- The error message is an alert, so it is announced when it appears.
