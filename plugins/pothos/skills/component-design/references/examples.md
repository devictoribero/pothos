# Examples

Each example shows the decision, the good version, the bad one and why. Examples are web React; React Native keeps the same shapes with `onPress` and `accessibilityLabel`.

**Contents:** Comment · Callout · Tabs · Stepper · Chat · Tag · Card in two layers · Line item in two layers · Workbench · AvatarGroup · ChoiceCards · A filled contract · Anti-patterns

## Comment: slot props for regions, parts for what varies

```tsx
<Comment.Root
  avatar={<Avatar.Root label="Ana García"><Avatar.Image src={avatarUrl} /></Avatar.Root>}
  author="Ana García"
  actions={<Button onClick={reply}>{t('comment.reply')}</Button>}
>
  <Comment.Body>{text}</Comment.Body>
  <Comment.Meta>
    <Comment.Time dateTime={createdAt}>{formatRelative(createdAt)}</Comment.Time>
    {editedAt && <Comment.MetaItem>{t('comment.edited')}</Comment.MetaItem>}
  </Comment.Meta>
</Comment.Root>

// Minimal
<Comment.Root author="Ana García"><Comment.Body>{text}</Comment.Body></Comment.Root>
```

- `avatar`, `author`, `actions` are fixed regions: the root renders them in its own DOM order, so a screen reader reads author, body, meta, actions whatever order the props are written in. The author region names the `article`.
- `Body` is a part although fixed: it is in the main flow and can get siblings (attachments). `Meta` entries vary per product, written with `&&`. `Meta` draws the separator in CSS with empty alternative text: `& > * + *::before { content: '·' / ''; }`.
- Nothing is typed data: `Comment` never sees a user or formats a date.

❌ `<Comment user={user} createdAt={date} showAvatar onReplyClick={reply} />`: couples to one data shape, decides what shows, grows a prop per need.
❌ `meta={[{ id: 'time', content }].filter(Boolean)}`: children reinvented as an array with invented ids and a cast.

## Callout: a default part, replaceable and removable

```tsx
<Callout.Root tone="warning"><Callout.Body>{t('backup.off')}</Callout.Body></Callout.Root>          // tone icon by default
<Callout.Root tone="warning" icon={<Icon icon={shield} label={t('security')} />}>…</Callout.Root>  // replaced
<Callout.Root tone="neutral" icon={null}>…</Callout.Root>                                        // removed
<Callout.Root tone="info" onDismiss={hide}>
  <Callout.Body>{t('backup.off')}</Callout.Body>
  <Callout.Dismiss aria-label={t('common.dismiss')} />
</Callout.Root>
```

- Every consumer wants the tone's icon, so it is a default, not a part each consumer must remember.
- `Callout.Dismiss` is the button, so it takes `aria-label`; the root asks to leave with `onDismiss`.

❌ `<Callout hideIcon hasTitle isDismissible actions={[{ label, onClick }]} />`.

## Tabs: controlled state and item identity

```tsx
<Tabs.Root value={tab} onValueChange={setTab}>
  <Tabs.List aria-label={t('settings.sections')}>
    <Tabs.Tab value="profile">{t('settings.profile')}</Tabs.Tab>
    <Tabs.Tab value="billing">{t('settings.billing')}</Tabs.Tab>
  </Tabs.List>
  <Tabs.Panel value="profile">…</Tabs.Panel>
  <Tabs.Panel value="billing">…</Tabs.Panel>
</Tabs.Root>

<Tabs.Root defaultValue="profile" onValueChange={track}>…</Tabs.Root>   // uncontrolled, still notified
```

- `value` + `onValueChange(next)` as in Radix and Base UI. Items pair through `value`, never `id`, which is the DOM id the component generates.
- Hidden panels stay mounted and `hidden`. Focus and arrow keys are internal.

❌ `<Tabs tabs={[{ id, label, content }]} />`: a badge on one tab or a lazy panel means growing the schema.
❌ `onSelect={setTab}`: reads as a gesture and hides that it pairs with the value.

## Stepper: typed data when the component operates on the items

```tsx
<Stepper
  aria-label={t('intake.steps')}
  steps={[
    { id: 'owners', label: t('intake.owners') },
    { id: 'access', label: t('intake.access'), description: t('common.optional') },
    { id: 'review', label: t('intake.review'), hasError: reviewFailed },
  ]}
  currentStepId={currentStepId}
  onCurrentStepIdChange={canLeave ? setCurrentStepId : undefined}
/>
```

- The component derives complete, current and upcoming from the order, so two current steps can't be written.
- `hasError` is a separate axis: any step can need attention.
- Navigation exists only when the handler is passed; only completed steps become buttons.

❌ `<Stepper.Step status="complete">` per step plus a current id: two sources the consumer must keep consistent.

## Chat: grouping part, root value, required author

```tsx
<Chat.Root readOnly={isArchived} aria-label={t('chat.conversation')}>
  {groups.map((g) => (
    <Chat.Group key={g.key} isOwn={g.isOwn} author={g.isOwn ? t('chat.you') : g.authorName}
      avatar={g.isOwn ? undefined : <Avatar.Root label={g.authorName} />}>
      {g.messages.map((m) => <Chat.Message key={m.id}>{m.text}</Chat.Message>)}
    </Chat.Group>
  ))}
  <Chat.Composer label={t('chat.message')} submitLabel={t('chat.send')} value={draft} onValueChange={setDraft} onSubmit={send} />
</Chat.Root>
```

- `readOnly` is a whole-component state on the root; groups and composer read it from context.
- Consecutive messages of one author are a `Chat.Group`, never a per-message `position` flag.
- `author` names every message, "You" visually hidden in the reader's own group, never omitted.
- The conversation is `role="log"`. Composer's `label` lands on the field, `submitLabel` on an icon-only button: both land elsewhere, so `label`.

## Tag: handler names by where the prop lands

```tsx
<Tag.Root onRemove={() => removeLabel(id)} removeLabel={`Remove ${name}`}>{name}</Tag.Root>  // root holds the button it renders
<Tag.Root>{name}<Tag.Remove aria-label={`Remove ${name}`} onClick={remove} /></Tag.Root>       // the part is the button
<Combobox.Option onAction={() => assign(ana.id)}>Ana García</Combobox.Option>                  // activated by Enter without a click
<Tabs.Root value={tab} onValueChange={setTab}>…</Tabs.Root>                                    // state changed
```

- On the root, `onClick` would land on the `span` and fire on any click inside, so the root names the outcome.
- On a part that is the control, the native event: the part's name already says what it does.
- In a combobox, focus stays in the input; `onAction` covers click, Enter and typeahead.
- Handlers say when they fire, never what the consumer does (telemetry is the consumer's). Functions the component calls to get something are `render`/`get`/`format`, not `on`.

## Card in two layers: a primitive and a thin feature

```tsx
// ui/MediaCard: knows no business
<MediaCard.Root headingLevel={3} media={<img src={src} alt="" />} action={saveButton}>
  <MediaCard.Title><a href={href}>{title}</a></MediaCard.Title>
  <MediaCard.Meta>{facts}</MediaCard.Meta>
</MediaCard.Root>

// features/listings/ListingCard: maps the entity, owns copy and intentions
export function ListingCard({ listing, isSaved, onSave, onUnsave }: ListingCardProps) {
  return (
    <MediaCard.Root headingLevel={3} media={<ListingPhoto photo={listing.photo} />}
      action={onSave && <SaveButton pressed={isSaved} onClick={isSaved ? onUnsave : onSave} label={`Save ${listing.address.street}`} />}>
      <MediaCard.Title><a href={listingPath(listing)}>{listing.address.street}</a></MediaCard.Title>
      <MediaCard.Meta><ListingFacts listing={listing} /></MediaCard.Meta>
    </MediaCard.Root>
  );
}
```

- The title is a heading: in a list of results, screen reader users move by heading. `headingLevel` fits the page outline.
- The link stretches over the card; `action` is a sibling raised above it, a separate tab stop.
- Media and action are slot props: the card places them and fixes reading order (title first, action last).

❌ One `HouseCard` taking `listing` and rendering everything: not reusable outside listings, and a design system can't share it.

## Line item in two layers: no business props in the primitive

```tsx
// ui/LineItem: a row with media, text, a control and a trailing value. Any product can use it.
<LineItem.Root media={<img src={src} alt="" />} control={<QuantityField … />} trailing={<LineItem.Value>{formatted}</LineItem.Value>}>
  <LineItem.Title><a href={href}>{name}</a></LineItem.Title>
  <LineItem.Meta>{variant}</LineItem.Meta>
</LineItem.Root>

// features/cart/CartLine: the business. Knows prices, stock and copy.
export function CartLine({ line, onQuantityChange, onRemove }: CartLineProps) {
  return (
    <LineItem.Root media={<ProductThumb product={line.product} />}
      control={<QuantityField aria-label={`Quantity of ${line.product.name}`} value={line.quantity} max={line.stock} onValueChange={onQuantityChange} />}
      trailing={<LineItem.Value><Money amount={line.total} /></LineItem.Value>}
      actions={<Button onClick={onRemove}>{copy.remove}</Button>}>
      <LineItem.Title><a href={productPath(line.product)}>{line.product.name}</a></LineItem.Title>
      <LineItem.Meta><StockNote line={line} /></LineItem.Meta>
    </LineItem.Root>
  );
}
```

- The primitive says `trailing` and `Value`, not `price`: a bank statement or an order history uses the same row.
- Money formatting, stock rules and copy live in the feature. The primitive imports nothing from `features/`.

❌ `<LineItem price={…} quantity={…} onRemoveFromCart={…} />` in `ui/`: one business baked into a shared piece, and the dependency points the wrong way the moment it imports `CartLine` types.

## Extracting a piece: a second consumer, not shorter JSX

```tsx
// features/projects/ProjectNameEditor: one consumer, one job. The field, Save and Cancel stay inline.
// Editing is controlled by default (`isEditing` + `onEditingChange`) because the "Each state" row says so,
// not because anyone asked for it.
export function ProjectNameEditor({ name, isEditing, onEditingChange, onRename }: ProjectNameEditorProps) { … }

// Later, features/boards/BoardTitleEditor needs the same rest → edit → pending → failed cycle. Now the piece
// has one coherent job and a name a consumer would look for: ui/InlineEditable, extracted with both consumers
// moved onto it in the same change.
<InlineEditable.Root isEditing={isEditing} onEditingChange={setEditing} onSubmit={rename}>
  <InlineEditable.Display>{name}</InlineEditable.Display>
  <InlineEditable.Field label="Project name" />
</InlineEditable.Root>
```

- The first consumer paid for no abstraction it did not use; the second one bought it, and the primitive speaks UI words (`Display`, `Field`), not `projectName`.
- Extracting changes nothing about who owns the state: controlled in the feature, controlled in the primitive.

❌ `<NameRow>`, `<EditControls>` and `useEditMode` extracted on day one to shorten the JSX, or because the design file has layers with those names: three names to search for and nothing reused.

## Workbench: regions, capabilities by handler presence

```tsx
<Workbench.Root
  list={<Workbench.List aria-label="Tickets">{items}</Workbench.List>}
  toolbar={<Workbench.AsideToggle>Details</Workbench.AsideToggle>}
  aside={<Workbench.Aside aria-label="Details" width={w} onWidthChange={setW}>…</Workbench.Aside>}
  asideOpen={open} onAsideOpenChange={setOpen}
>
  {detail}
</Workbench.Root>
```

- Regions are slot props; a region with settings takes its part. The panel's open state changes the whole layout, so it is on the root; its width is on the panel.
- No `onWidthChange`, no resize handle. Narrowing never opens or closes the panel.
- On narrow screens the visible pane is **derived from the selection**: nothing selected shows the list; selecting shows the main content and moves focus there; `Workbench.Back` clears the selection and returns focus to the item. A separate `pane` state would let "show content" coexist with "nothing selected".
- Escape closes the overlaying panel only if no inner layer (a menu, a combobox, a dialog) handled it first: check `event.defaultPrevented` and stop propagation when you handle it.

❌ `pane` + `onPaneChange` beside `value`: two states that must agree, and a phone that can show an empty content pane.

## AvatarGroup: no copy, no counting

```tsx
<AvatarGroup.Root aria-label={t('task.assignees')} size="sm">
  {shown.map((p) => <Avatar.Root key={p.id} label={p.name}>…</Avatar.Root>)}
  {rest > 0 && <AvatarGroup.Overflow label={t('task.more', { count: rest })}>{t('plus', { count: rest })}</AvatarGroup.Overflow>}
</AvatarGroup.Root>
```

- The consumer slices; the group never counts children. "+3" is copy, so it arrives as children with an accessible phrase.

❌ `<AvatarGroup max={3} avatars={people} />`.

## ChoiceCards: the native form control inside

```tsx
<ChoiceCards.Root selectionMode="single" name="plan" value={plan} onValueChange={setPlan} required>
  <ChoiceCards.Label>{t('billing.choosePlan')}</ChoiceCards.Label>
  <ChoiceCards.Item value="pro" disabled>
    <ChoiceCards.Title>{t('billing.pro')}</ChoiceCards.Title>
    <ChoiceCards.Note>{t('billing.notInRegion')}</ChoiceCards.Note>
  </ChoiceCards.Item>
</ChoiceCards.Root>
```

- `fieldset` + `legend`, each item a `label` around a hidden native `input`: keyboard, announcement and `FormData` for free.
- A disabled card carrying a reason renders `aria-disabled`, focusable and inert.

## A filled contract

````markdown
## TaskCard

**Purpose:** One task in a list; it opens the task when the consumer passes `onOpen`. No host.

**Minimal usage**
```tsx
<TaskCard.Root><TaskCard.Title>Fix the gutter</TaskCard.Title></TaskCard.Root>
```

**Full usage**
```tsx
<TaskCard.Root headingLevel={3} isCompleted onOpen={open} media={<Avatar … />} action={<TaskMenu task={task} />}>
  <TaskCard.Title>Fix the gutter</TaskCard.Title>
  <TaskCard.Description>Front side, second floor</TaskCard.Description>
  <TaskCard.Meta>{dueDate}{assignee}</TaskCard.Meta>
</TaskCard.Root>
```

**Parts**
| Part | Kind | Accepts | Renders as | Required |
|---|---|---|---|---|
| `TaskCard.Root` | root | the parts below | `article`; pass-through and ref | yes |
| `media` | slot prop | an avatar, icon or thumbnail | leading cell, hidden from assistive technology when decorative | no |
| `action` | slot prop | the consumer's controls | trailing cell, raised above the stretched button | no |
| `TaskCard.Title` | text part | text or a link | heading at `headingLevel`; with `onOpen`, a stretched `button` inside | yes |
| `TaskCard.Description` | text part | text | `p` | no |
| `TaskCard.Meta` | grouping part | any entries | `div`, separators drawn in CSS | no |

**State**
- Completion is controlled through `isCompleted`; the card never changes it.

**Behavior and invariants**
- Without `onOpen` the card has no interactive element of its own.
- With `onOpen`, activating the title's button calls `onOpen`.
- Using a control in `action` never opens the card.
- A completed card mutes its content and strikes the title.

**Accessibility**
- The root is an `article` named by its title.
- The title is a heading at `headingLevel`, default 3.
- The action is a separate tab stop after the title's button.
- Completion is announced as text, not only by the strike-through.

**Decisions**
- `onOpen`, not `onClick`: the handler is on the root, which holds the button it renders. To confirm: none.
- Due date and assignee are `Meta` content: the card doesn't operate on them.

**Out of scope**
- Selection for bulk actions; drag-and-drop; spacing between cards.
````

Each bullet under State, Behavior and Accessibility becomes one Given, When, Then test with the same words: `describe('given a card without onOpen')` › `it('has no interactive element of its own')`.

## Anti-patterns

| ❌ | Why | ✅ |
|---|---|---|
| `theme: 'default' \| 'dark'` | changing the default changes what `default` means | `'light' \| 'dark'`, default set on the prop |
| `isOpen`, `isChecked`, `isDisabled` | the platform has words for these | `open`, `checked`, `disabled` |
| `onSelect` | ambiguous between a selection and an action | `onValueChange`, `onClick`, `onAction` |
| `<X.Item id="a">` | `id` is the DOM id | `value="a"` |
| `label` naming the root | the platform word is `aria-label` | `aria-label` |
| `marginBottom: 16` on the root | the parent owns spacing | none |
| `// used in Checkout` | names a consumer | explain why, not who |
| `position: 'first' \| 'middle'` per item | neighbor layout as flags | a grouping part |
| `status` via color only | invisible to screen readers and color-blind users | text, visible or hidden |
