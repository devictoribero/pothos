# Naming

If the project spells a name differently, the project wins. `scripts/lint.py` flags the most common slips.

## Vocabulary kinds

The test for a primitive's prop name: would a different product (a bank, a hospital, a game) use the component with the same prop meaning the same thing? If not, the name is business vocabulary and belongs to a feature.

| Business (feature only) | Product and UI language (primitive) |
|---|---|
| `price`, `total`, `amount` on a row | `value`, `trailing`, `meta` |
| `listing`, `product`, `ticket` | `media`, `title`, `subtitle`, `description` |
| `bedrooms`, `bathrooms` | `facts`, `meta` entries |
| `sender`, `customer` | `author`, `avatar` |
| `onAddToCart`, `onCheckout` | `onAction`, `onClick` on the part, or a slot for the consumer's button |
| `isSold`, `isReserved` | `status` union of UI states (`muted`, `highlighted`), or a `badge` slot |


- **Product/UI** names what the thing is in the interface: `author`, `body`, `meta`, `action`. Primitives use it.
- **Technical** names the implementation: `user`, `data`, `items`, `config`. Never in public names, the component's own included: `ProfileCard`, not `UserCard`.
- **Business** is one product's domain: `invoice`, `jobLead`. Feature components only.
- **Established** names (Avatar, Badge, Tabs, Dialog) are product vocabulary by adoption. Parts too: `Initials`, not `Fallback`.

## Props

| Name | Meaning | Not |
|---|---|---|
| `disabled`, `required`, `readOnly`, `href`, `name` | Platform attributes, passed through | `isDisabled`, `isRequired` |
| `open`, `checked`, `selected`, `pressed` | A state the platform has a word for, also as the component's own state, with `defaultOpen` and `onOpenChange` | `isOpen`, `isChecked` |
| `is<State>`, `has<State>` | A boolean state the platform has no word for (`isLoading`, `hasError`). Never shows or hides a part | a visibility flag |
| `value`, `defaultValue`, `onValueChange(next)` | A single selection on the root, matching the items' `value`; or a field-like part's text or scalar | `selectedId`, `onSelect`, `onChange` on a compound |
| `value` on an item | The item's identity (`<Tabs.Tab value>`). `<thing>Id` only when the item renders a submitted form control | `id`, the DOM id |
| `current<Thing>Id` | The current item of a sequence the component derives state from | `value`, which reads as a choice |
| `aria-label` | Accessible name landing on the root or the control the root is | a custom `label` |
| `label`, `<x>Label` | Accessible name landing elsewhere: an image's alt, a field, hidden text, an icon-only button inside | visible text |
| `<thing>Text` | Visible text a state requires (`statusText`) | `label` |
| `variant` | A visual style of the same thing | semantic color, state |
| `tone` | Semantic color: `neutral`, `info`, `success`, `warning`, `danger` | `color` |
| `size` | A step of the scale: `sm`, `md`, `lg` | pixels |
| `status` | One of mutually exclusive states | several booleans |
| `mode`, `selectionMode`, `orientation` | A behavior setting | a boolean (`allowsMultiple`) |
| `placement` | Where an overlaid or docked part sits, in logical terms (`start`, `end`, `top-end`) | `left`, `right` |
| Union values | What the value is: `light`, `dark`, `sm`, `comfortable` | `default`, `normal`, `regular`, `base` |
| Numeric unions | A capped count: `0 \| 1 \| 2 \| 3` | an open `number` |
| `default<Name>` | Uncontrolled initial value | `initial<Name>`, `defaultIsOpen` |
| `accept`, `multiple`, `maxFiles`, `maxFileSize` | File limits, native names first | `isMulti`, `acceptedFileTypes` |

Variants and settings are string unions, never booleans. Default them when one value is neutral; require them when none is. Being the default is a property of the prop, never a value named `default`.

## Handlers

Handlers start with `on` and say **when** they fire, never what the consumer does with them. Pick by where the prop lands:

| The prop lands on | Name | Example |
|---|---|---|
| The element the user activates (the part is the control) | the native event | `<Tag.Remove onClick>`, `<Callout.Action onClick>` |
| A root that contains a control the component renders | the outcome | `<Tag.Root onRemove>`, `<Card.Root onOpen>`, `onDismiss(reason)` |
| An item activated without a click on it (Enter in a combobox, typeahead) | `onAction` | `<Combobox.Option onAction>` |
| State | `on<Name>Change(next)` | `onValueChange`, `onOpenChange` |

- An outcome with several triggers takes a `reason` union: `onDismiss('timeout' | 'escape' | 'close')`.
- A part that wraps a native control composes the consumer's handler with its own: call the consumer's first, then skip the component's behavior if `event.defaultPrevented`.
- Functions the component calls to obtain something are not handlers: `renderLink`, `getRowId`, `formatValue`.
- Inside the component, functions handling its own events start with `handle`: `handleKeyDown`.
- `onSubmit(text)` on a composer: a whitespace-only draft never submits. `onSubmit(value)` on a field-like part: blank is a value unless `required`, and may return a promise.
- `on<Items>Add({ accepted, rejected })`: items added, refusals with a `reason`.

## Copy

A primitive holds no copy: no labels, plurals, units or "+5". Every text arrives through a prop or slot. A text needed for accessibility that content can't provide is a required prop. The component's own affordance icons (chevron, close) are not copy; render them through the project's icon primitive, hidden when decorative.
