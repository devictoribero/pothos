# Mechanics

How to build what the decision guide chose. Web React first; React Native notes at the end.

**Contents:** Files and exports · Context · State · Default parts · Registration · Pass-through and refs · Links and cards · Native form controls · Wrapping a primitive that renders no element · Hosts · Spacing and anchoring · Layout components · Scroll containers · Lists · Async work · Extending · Project plumbing · React Native

## Files and exports

- Parts are named exports re-exported from an `index`; consumers write `import * as Tabs` and `<Tabs.Root>`. Not `Object.assign(Root, { Tab })`: attached parts are `undefined` across a server-component boundary and can't be tree-shaken.
- A component without parts is a plain named export (`<Icon />`).
- Export each part's props type when the project allows unused exports, plus pure helpers the contract's recipes use (`getPageRange`). Never the context or a default export.
- One file while it reads in one sitting; past that a folder: `index`, one file per part or group of parts, a private context file, tests, `README.md`.
- A primitive never imports a DTO or domain-types package; the consumer adapts at the boundary.
- A product adapter many features use (`ListingPagination`) lives next to the primitive. A business-agnostic layout used by one feature lives in that feature until a second use.

## Context

```tsx
const ChatContext = createContext<{ readOnly: boolean } | null>(null);
function useChatContext(part: string) {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error(`<Chat.${part}> must be rendered inside <Chat.Root>`);
  return ctx;
}
```

Memoize the value. Never export the context or its hook. A grouping part (`Accordion.Item`) provides its own private context. A layout-only part that reads nothing needn't enforce placement. Don't introspect children (`Children.map`, `cloneElement`, `child.type`): it breaks when a consumer wraps a part.

## State

One hook resolves controlled and uncontrolled so the rest of the component never knows the mode. Use the project's (`useControllableState`); otherwise create it once in the shared hooks folder:

```tsx
function useControllableState<T>(controlled: T | undefined, defaultValue: T, onChange?: (next: T) => void) {
  const [internal, setInternal] = useState(defaultValue);
  const isControlled = controlled !== undefined;
  const setValue = useCallback((next: T) => { if (!isControlled) setInternal(next); onChange?.(next); }, [isControlled, onChange]);
  return [isControlled ? controlled : internal, setValue] as const;
}
```

The handler fires in both modes. Transient UI controlled by presence takes `open` only when it needs an exit animation or a portal. A timer that ends in an event is internal, configured by a prop named after the outcome and its unit (`autoDismissAfter`), restarted only when that prop changes.

Derive, don't duplicate: a value that follows from props or other state (the visible pane from the selection, `isEmpty` from the items, a count) is computed at render, never stored where it can disagree. When controlled state names an item (`value`, `selectedIds`) and that item leaves the data, the component renders as nothing selected and the contract says so; the consumer picks the next one (a recipe in the contract). It never shows a ghost item nor selects a neighbour on its own. Plumbing hooks (controllable state, focus trap, roving focus) are shared from day one, as above. Whether feature logic becomes a hook is the row "Extracting a piece" in SKILL.md; such a hook has no UI of its own and moves to the shared hooks folder with its second consumer.

## Default parts

1. **Presence:** a part with no children shows its default (`<Marker aria-label />` shows "add"; with children it shows them). Checking for `null`/`undefined`/`false` is not introspection.
2. **Registration:** a replacing part registers and the root drops its default (an avatar's figure until `Initials` mounts).
3. **Removable slot prop:** `icon` absent shows the default, a node replaces it, `null` removes it. Never `hideIcon`.
4. **Derived content:** a part registers content another part shows (`<Select.Value />` shows the chosen option's text).

## Registration

Parts register in a private context so the root knows what rendered: presence, generated ids for `aria-labelledby`, a default to drop, where focus lands. Register in a layout effect keyed on identity; unregister in cleanup. When a missing part silently breaks accessibility (a dialog without a title), the root warns in development. Many items registering layout values cost n² renders: batch registrations into one state update per commit, keep the previous result when unchanged, use primitive deps; past a few dozen items, own the iteration instead.

## Pass-through and refs

- Extend the underlying element's props (`ComponentPropsWithoutRef<'article'>`) and spread the rest; forward the ref (`forwardRef` in React 18, a prop in 19).
- When a part renders a wrapper and a control (`label > input`), pass-through and the ref go to the control; `className` and `style` go to the visible box.
- A wrapper of a primitive extends its exported **appearance type** (look plus native attributes, no content), never `ComponentProps<typeof X>`: `Omit` doesn't distribute over unions, and narrowing the primitive later breaks every wrapper.
- A library's styling mechanism (styled-components `$props`) never names a public prop.
- Generic components in React 18: cast the `forwardRef` result to keep the type parameter.

## Links and cards

- A root that is the only interactive element may be polymorphic (`asChild`), never `href`/`to` props.
- A card with actions uses a **link overlay**: the link lives in the title part, `::after` stretches it over the root (`position: relative`), every other control is raised with `:where(a, button, input, select, textarea, [tabindex]) { position: relative; z-index: 1 }`, and the focus ring shows on the root with `:has(:focus-visible)`.
- Controls the component generates (a pager's pages) take `renderLink={({ page, children }) => <Link …>{children}</Link>}`; the component merges look, `aria-current` and name through `asChild`. The button version takes `on<Name>Change`; type the two as a union.

## Native form controls

A choice among options is a `fieldset` with a `legend`; each option a `label` around a visually hidden native `input`. Pass-through and the ref go to the input; `className` and `style` to the visible label. When the visible control can't be native (a combobox with chips), keep a hidden native mirror (`<select multiple name required>`) in sync so `FormData`, `required` and `reset()` work. When the value can't live in a native input (uploaded files, rich text), the consumer owns it in its form library, and the contract says the field doesn't join `FormData`.

## Wrapping a primitive that renders no element

When the root composes a mandated primitive whose root renders nothing (a Radix `Popover` or `Dialog`), the root renders nothing either and the contract says so: no pass-through, no ref there. The parts wrapping the primitive's trigger and content take its options as pass-through and forward the ref.

## Hosts

The presentational component works rendered directly; the host (queue, stack, positioner) is a second component with its own contract. Host API: `show((dismiss) => <Toast onDismiss={dismiss}>…</Toast>)`, `dismiss(id)`, `dismissAll()`, exported as a hook next to the host. The part that renders the text announces it.

## Spacing and anchoring

No outer margin, width or position in the parent. Localization is layout too: rows use logical `start`/`end` so RTL mirrors, text parts wrap, controls don't shrink. A layout container that needs a bounded box may fill its parent's main axis (`flex: 1`), stated in the contract. An overlaid part (a marker on a field) offers an optional `Anchor` (`position: relative`) and a `placement` union in logical terms (`inline | top-start | top-end | bottom-start | bottom-end`).

## Layout components

- Regions are slot props in a fixed DOM order; a region with settings takes its part (`aside={<Workbench.Aside width>}`).
- A panel's open state is a root value (it changes the layout); its size belongs to the panel's part, controlled (`width` + `onWidthChange`); persistence is the consumer's.
- Responsive by its own width (container queries or `ResizeObserver`), not the viewport; expose the layout as `data-layout`. Wide: panel beside. Medium: panel over the main content, which goes `inert`, with a scrim and Escape. Narrow: one pane at a time; focus moves to the new pane and back on Back. Narrowing never opens or closes a panel.

## Scroll containers

- `position: sticky` sticks to the nearest scrolling ancestor: a table's sticky header sticks inside its box, which needs a bounded height (contract recipe).
- Inside grid or flex, the scroll box's ancestor needs `min-inline-size: 0` or a `minmax(0, 1fr)` track.
- Logical insets (`inset-inline-end`) so pinned parts mirror in RTL.
- Sizes CSS can't sum (pinned columns of content width) are measured in a layout effect with `ResizeObserver`, compared before setting state, and published as custom properties and `data-*` attributes named after what they describe (`data-overflow-end`).

## Lists

- A list part renders `ul`/`ol`; the consumer wraps composed items in `li`. Add an `Item` part only when items carry state the list must know.
- Owned iteration takes `items`, `getItemId` and `renderItem`, which returns the component's row part.
- Collection states are parts by presence (`<Table.Empty>`, `<Table.Loading>`): a failed first load replaces the collection with the consumer's error and retry; a failed load-more stays in the load-more control so focus stays; a partial failure keeps what loaded.
- Metadata rows: entries are direct children; the group draws separators in CSS with empty alternative text.
- Sortable lists: the `li` moves; the handle is a named `button` in a `handle` slot; keyboard sensor required; the drag library loads lazily.
- Filtering: the query is controlled state of a search part (`query` + `onQueryChange`); the consumer decides what matches, with a pure helper exported for the local case (`matchesQuery`).
- A group of an existing component (`AvatarGroup`) overrides the item's own prop (`size`) through a private context the item reads optionally.
- Dates render in `<time dateTime>`; grouping by day takes `today` and the time zone as inputs; a copy-free helper (`groupByDay`) lives next to the component.

## Async work

- An event that starts the consumer's work may return a promise: the component owns `pending | failed`, the consumer owns the value. Use props instead when several components show the same operation.
- Per-item async state reused across features (uploads) is a headless hook in the shared hooks folder: transport-agnostic, owns cancel, retry and concurrency, and returns a union the primitive's `status` mirrors.
- Removing an item waits for the server and leaves an Undo placeholder with focus; value changes (quantity, toggles) are optimistic with rollback; with concurrent changes to one item the newest wins, and a submit waits while changes are in flight.

## Extending

Additive first: optional part, optional prop with a behavior-preserving default, new union value. A data boolean that only decides whether one more thing shows is a slot. A state prop changes how existing parts render (`isCompleted`). A capability requested before any use is minimal and marked speculative. Otherwise migrate: the new contract, every consumer updated in the same change, the old component deleted, no shims. Outside an audit, draft the component and tests with the proposal; edit consumers after acceptance.

## Project plumbing

Project rules win on plumbing: primitives, tokens, lint, exports, test tooling. Shared behavior (focus trap, controllable state, roving focus, class-name helper) is consumed, never rewritten: step 2 of the skill looks for it first, and what is missing is created once in the shared place. An additive change the new component needs on a shared primitive (pass-through, a name) goes in the same change; plumbing that hurts accessibility is fixed at its source or recorded as a red finding, never wrapped locally. Without tokens, keep values where tokens can replace them: prefixed custom properties with fallbacks (`var(--card-radius, 8px)`). A third-party behavior library is consumed for behavior; override roles and `tabindex` that contradict the pattern.

## React Native

- A parent can't detect a child's presence, so a region whose presence changes layout is a slot prop; a part can register and return `null` while the root places it ("register and place").
- Pass-through: extend `ViewProps`/`PressableProps`; merge `style` last (`[styles.root, style]`, or a function when `Pressable.style` is one).
- `Pressable` or the project's wrapper, never touch handlers on a `View`; no `Pressable` inside a `Pressable`. `onPress` on a part that is the pressable; outcomes on a root that renders it.
- Text in slots: a string passed to a slot must be wrapped in `Text` by the component, since React Native can't render bare strings in a `View`.
- Platform differences (keyboard avoidance, safe areas, haptics) are the consumer's or the host's, passed in, never read inside the component.
- Development warnings use `__DEV__`. A host takes a consumer-passed `offset` for safe areas.
