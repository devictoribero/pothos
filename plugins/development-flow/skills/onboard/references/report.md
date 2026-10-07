# Readiness report

Print it in this shape. Keep each line to one fact and the whole report under 45 lines: the reader acts on the gaps, so do not repeat the contract file or explain rules they did not ask about. Start the smoke-run line with "Smoke run of".

```markdown
## Contract

| Field | Value | Source |
|---|---|---|
| verify.full | `<command>` | <aggregate script / CI workflow / chained candidates> |
| ... | ... | ... |

Smoke run of `<command>`: passed | failed on code | could not start: <reason>

## Assumptions

- <each choice made without the user, and why>

## Gaps

Ordered by how much each one blocks autonomous work.

- [ ] <gap>: <why it matters> <what would close it>
```

Check these gaps, in this order, and list every one that applies:

1. `verify.full` does not match what CI runs before merge.
2. No `verify.fast`.
3. `run.dev` needs a real backend or secrets (`run.mocked` is false or unset), or there is no `run.dev`.
4. No `verify.e2e`.
5. No `docs.context`, so agents have no shared domain language. The domain-model skill can start one.
6. No `docs.decisions`.
7. No PR template.
8. CI does not block merge on `verify.full`. Only report this when the CI files make it visible.
