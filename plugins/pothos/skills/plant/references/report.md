# Readiness report

Print it in this shape. Keep each line to one fact and the whole report under 45 lines: the reader acts on the gaps, so do not repeat the contract file or explain rules they did not ask about. Start the smoke-run line with "Smoke run of".

```markdown
Contract saved at `<path>`. The repository is unchanged.

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
4. `run.screenshots` unset (or unset for an app in `run.apps`): evidence will try screenshots it may not be able to take.
5. No `verify.e2e`.
6. No `docs.glossary`, so agents have no shared domain language. A `GLOSSARY.md` at the root closes it; the planned domain-model skill will maintain it.
7. No `docs.decisions`.
8. A repository with UI but no `ui.components` or `ui.tokens`: agents may build a second button or use raw colors.
9. No PR template.
10. CI does not block merge on `verify.full`. Only report this when the CI files make it visible.
11. No `verify.mutation`. Optional: it never blocks readiness, because verify skips the level and says so. A mutation tool configured in the repository closes it; when `mutation_tools` already lists one, the command from the mapping closes it.
12. `mutation_temp_ignored` is false: the tool's temp folder is not in the ignore file, so a crashed run leaves it in the working tree and the next receipt reports a dirty tree. Optional, never blocks readiness. Naming the folder in `.gitignore` closes it; Pothos does not edit that file.
13. No `deps` section in a repository with a `package.json`: dependency updates have no owner, so a session bumps packages only when a task needs it. Optional, never blocks readiness. Adding the section (the mapping's `deps` rules) closes it; when `dependency_bots` lists Renovate or Dependabot, say that the skill would only cover what the bot cannot (drivers, dead lines, migrations, assessments).
