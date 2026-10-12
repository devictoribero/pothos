# Accessibility

Decide these while designing the API: they change it. Follow WAI-ARIA Authoring Practices for established patterns and write the roles in the contract.

## Rules

- **Real elements.** Interactive parts are real interactive elements, never a `div` with `onClick`, never nested in one another.
- **Disabled.** Native `disabled` when the control only needs skipping; `aria-disabled` (focusable, inert) when it carries information to reach, or can become unavailable while focused through its own action (Next on the last page).
- **Names.** Every image, icon-only control and field has an accessible name in every state; when content can't provide it, it is a required prop.
- **State in text.** A current page, a completed step, an unseen mark or a status has text, visible or hidden; never color or an icon alone.
- **Focus never drops.** In-place content opened by the user receives focus and returns it to its trigger on exit, never on mount. A removed item leaves focus on an Undo placeholder. Never disable the focused control during a busy state.
- **Optional capabilities by handler presence.** No handler, no control: a read-only stepper, a non-resizable panel.
- **Landmarks.** A navigation or region the user jumps to is a named landmark. No `main` inside a dialog.
- **Announcements.** A component that appears on its own decides how it is announced. One the user must remove has a named dismiss control or a timer, and warns in development when it has neither.
- **Hidden content.** Tabs and accordion panels stay mounted and `hidden`; popups (listbox, menu, popover) unmount when closed.
- **Contrast.** State styling keeps text at WCAG AA; never `opacity` on an element holding text.

## Defaults per pattern

| Pattern | Default |
|---|---|
| Card in a list | `article`, never `li`; its title is a heading at `headingLevel` (default 3); a stretched link or button in the title, other actions raised above it |
| Adornment beside a name (verified, "new") | sibling of the name, never inside its link; named if it carries information, `aria-hidden` otherwise |
| Non-interactive element named differently from its text (icon-only badge, a bare "4") | visually hidden text, visible content `aria-hidden`; `aria-label` on a `span` is ignored by several screen readers |
| `article`, `section` | native `aria-label` or `aria-labelledby` |
| Group of options | `fieldset` + `legend`, native inputs inside |
| Select without typing | button `role="combobox"` + `listbox` |
| Typing to filter | input `role="combobox"` + `aria-activedescendant` |
| Navigation list driving a detail view | `ul` of `button`s with `aria-current`, roving tabindex, manual activation |
| Data with headers | native `table` with `caption`; `aria-sort` on the sorted column only |
| Sections switched in place | `tablist` |
| Actions in a popup | `menu` |
| Accordion panel | `region` + `aria-labelledby`; `group` when there are many |
| Toast, banner | `alert` for errors, `status` otherwise; each control focusable |
| Conversation | `role="log"` with a name |
| Chronological feed | `ol > li` with headings per day; `role="feed"` only with keyboard paging |
| Count on a trigger | in the trigger's name ("Notifications, 3 unseen"), visual count hidden; "9+" when unknown; no live region for polled counts |
| Scroll box without focusable content | `tabIndex={0}`, `region`, a name, only while it overflows |
| Resize handle | `separator` with `aria-valuenow/min/max` and a name; arrows resize in the visual direction, mirrored in RTL |
| Side panel over content (medium width) | main content `inert`, scrim, Escape closes |
| Link that can't be followed yet | `aria-disabled`, described by the visible reason, click and middle click cancelled; a button when a server step runs first |
| Controls revealed on hover | always in the DOM and tab order; shown on `:hover` and `:focus-within`; always visible under `@media (hover: none)` |
| Escape with nested layers | the innermost layer handles it and stops it |
| Sortable list | the `li` moves; a named handle `button`; keyboard sensor; announcements by name and position |

## React Native

`accessibilityRole` when its union has the role, `role` (RN 0.73+) otherwise. The name is `accessibilityLabel`, passed through when it lands on the pressable. No Escape: decide which of swipe, hardware back and tap-outside dismisses. `accessibilityLiveRegion` works on Android only; iOS needs `AccessibilityInfo.announceForAccessibility`. Touch targets reach 44pt with `hitSlop`.
