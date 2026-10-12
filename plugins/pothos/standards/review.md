# Reviewer standards

These are one reviewer's personal standards, distilled from past reviews. The repository's own documented standards win whenever the two conflict.
Severity maps to red and yellow. Red blocks the merge. Yellow is recommended and can be a tracked follow-up. Rules are ordered by how often the concern came up.

### 1. Reuse the existing helper, service, hook or factory before writing a new one
Yellow. Generic.
A local copy drifts from the shared one and teaches the next reader, human or agent, the wrong pattern. If nothing fits, add one shared helper rather than a second inline copy.

### 2. Use design tokens and the primitive's typed props instead of raw values
Yellow. Generic.
Raw sizes, colors and breakpoints land between the scale's steps and break theming. If a raw value is truly needed, leave a comment saying why so nobody "fixes" it later. For components, the `component-design` skill has the full rules.

### 3. Keep vendor and infrastructure details out of the domain and application layers
Red. Generic.
Core code must survive swapping a provider or a database. Vendor types, SQL concerns and "which adapter is enabled" decisions belong in infrastructure or the composition root. A repository persists, it does not orchestrate I/O.

```ts
// before
function syncUser(payload: VendorWebhookUser) {}
// after
function syncUser(command: UpdateUserCommand) {}
```

### 4. Never swallow an error, and keep failure kinds apart
Red. Generic.
A catch that maps everything to one generic failure makes production problems invisible. Separate "not applicable" from "provider failed" from "unavailable", return the status code that matches what happened, throw on impossible cases instead of defaulting, and log the error class with enough context to debug.

```ts
// before
} catch { throw new ServiceUnavailable(); }
// after
} catch (error) {
  logger.error(`send failed (${errorName(error)})`);
  throw new ProviderFailed();
}
```

### 5. Validate input at every boundary and configuration at startup
Red. Generic.
Every free text field gets a maximum length, client and server rules must agree, and URLs are restricted to safe schemes. Read required configuration once at boot and fail there, so a missing variable breaks the deploy rather than a user request days later.

### 6. Authorize ownership in every handler, and deny by default
Red. Generic.
Checking that the caller is logged in is not checking that they own the resource. Put the ownership check first in each command and query. Gate on "not allowed" lists so a new role starts restricted.

```ts
// before
const card = await cards.get(cardId);
// after
await authorizeAccess(identity, businessId);
const card = await cards.get(cardId);
```

### 7. Remove dead, leftover and speculative code
Yellow. Generic.
Unused branches, options for features nobody plans to build and fields that cross a contract with no consumer are cost without benefit. Bring them back when a real need appears.

### 8. Name things after the intent or the domain fact, not the mechanism, type or vendor
Yellow. Generic, with a style preference for domain verbs like `change` over `set`.
Prefer `bannedAt` over `banTimestamp`, past tense for recorded facts, and exception names that state the rule rather than how it is enforced. Use one term for one concept across code, endpoints and copy.

### 9. Keep the PR description, specs and code comments true to the code
Yellow. Generic.
A wrong claim in the description misleads reviewers and future readers. When review proves a claim wrong, correct it in place and say so.

### 10. Model domain concepts as value objects and keep invariants inside the aggregate
Yellow. Personal style.
Entities take value objects, not primitives, and normalization lives in the value object. A rule like "grants access when active or trialing" is a method on the aggregate, so services stay thin guards.

### 11. Avoid N+1 queries and push filtering to the database
Red for N+1, yellow otherwise. Generic.
Load in batch, filter with a query criteria object instead of in memory, add read models for new screens, and skip writes when nothing changed.

### 12. Keep one source of truth, one write path and one mechanism per problem
Red. Generic.
Two code paths that build the same thing already behave differently. Two locking strategies or two reporting sources hide bugs behind disclaimers. Pick one and delete the other.

### 13. Keep pull requests focused and call out unrelated changes
Yellow. Generic.
Refactors, global changes and bug fixes found on the way deserve their own commit or PR. In a stack, publish complete contracts so dependent branches still compile.

### 14. Verify the change in the real environment before merging
Red when the feature is unverified. Generic.
Run it on a device, in a browser with client side navigation, or through the local end to end suite. Reading the diff does not prove the form submits.

### 15. Pair every fix and behavior with a test that fails without it
Yellow. Generic.
The test is seen failing without the fix, and a fix also guards its neighbours. How: `standards/testing.md`, rules 1 and 2.

### 16. Build test data from shared factories with neutral defaults
Yellow. Generic.
One small builder per domain type, fixed neutral defaults, each test overrides only what it is about. How: `standards/testing.md`, rule 7.

### 17. Finish a rule, rename or cleanup everywhere it applies
Red when left halfway. Generic.
A convention applied to half the call sites is worse than none, because readers and agents copy the old half. Sweep the codebase or do it in a tiny preceding PR.

### 18. Extract cohesive logic into named hooks, functions and small classes
Yellow. Generic.
Split large components and classes that own many jobs. Replace long condition chains with a declarative lookup map.

### 19. Keep secrets and personal data out of the repository, logs, disk and unused contracts
Red. Generic.
Commit an example config without keys. Never log tokens, query parameters or user written content. Do not pass personal data through a port no adapter needs.

### 20. Do not cast and do not use `any`
Red. Generic.
A cast hides silent errors. Map fields explicitly, validate external data with a schema, and use `unknown` when the type is truly unknown.

```ts
// before
const user = body as User;
// after
const user = userSchema.parse(body);
```

### 21. Design for partial failure and concurrent writes
Red. Generic.
A loop that sends to many recipients must record per item results instead of failing all or nothing. Use one concurrency control, versioning or explicit locks, and add idempotency keys where a retry could duplicate a side effect.

### 22. Ship features complete end to end
Red. Generic.
Every state you can enter must be visible, listable and recoverable. Do not leave inputs missing, actions without an undo path, or helpers created but never rendered.

### 23. Test through the public or accessible surface, at the right layer
Yellow. Generic.
Query by role and text, assert what a person sees or a caller gets, and keep each test next to the layer it exercises. How: `standards/testing.md`, rules 5 and 6.

### 24. Meet basic accessibility
Red for text contrast below the normal minimum, yellow otherwise. Generic.
Clickable rows need keyboard support and a visible focus ring. Focus must land somewhere sensible when content unmounts. For components, `component-design` decides accessibility with the API; see its `references/accessibility.md`.

### 25. Give each intention its own command and avoid boolean or null switches
Yellow. Generic.

```ts
// before
updateBan(cardId, null); // null means unban
// after
banCard(cardId, reason);
unbanCard(cardId);
```

### 26. Prefer a plain function, a key or render time derivation over another hook or effect
Yellow. Personal style.
A hook that holds no state is a utility. Reset state with a `key` and adjust state during render instead of in an effect that causes an extra paint.

### 27. Import from the defining file, not from barrel files
Yellow. Personal style.
Barrels slow builds and hide circular dependencies, which block code splitting later.

### 28. Use `null` for a known empty value
Yellow. Personal style.
`null` says "we know there is nothing". Keep `undefined` for "not provided".
