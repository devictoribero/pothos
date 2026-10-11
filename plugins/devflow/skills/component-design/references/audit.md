# Auditing existing components

Review a folder of components and report what to change and toward what. The audit changes no code. Sequencing the work into changes and executing it is a process concern outside this skill.

## Procedure

1. **Read the plumbing and project rules once** (tokens, icons, exports, test runner, `AGENTS.md`, lint). A project rule that contradicts this skill wins; record it once as "project rules in force", never as a finding.
2. **Inventory**: one row per component with kind, public API, state ownership, contract or spec, tests and what they query, and **consumers** (non-test files importing it).
3. **Per component, read its consumers before judging it.** The worst findings often show only at call sites (two consumers resolving the same props in opposite ways).
4. **Run** `scripts/lint.py` over the folder, then the decision guide and `accessibility.md` per component. Record findings as `file:line (symbol)` plus one sentence: what is wrong, what it should be. Skip taste.
5. **Classify.**
   - 🔴 **Red**, users or consumers can be hurt: nested interactive elements; a control or image without a name; state by color alone; focus lost on interaction; a URL change done with a button; drag attributes on an element holding controls; non-copy-overridable text that is an accessible name; business vocabulary or a DTO in a primitive; an import pointing the wrong way (a primitive importing a feature, domain or data module); a feature component in the shared folder; a presentational component reading URL, storage or session; impossible states representable; a native attribute renamed or a non-native element doing a native job; outer margins baked in.
   - 🟡 **Yellow**, inconsistency or cost: names off `naming.md` (`isOpen`, `onSelect`, `selectedId`, `default` as a value, `id` as identity, a custom `label` naming the root); configuration props where a slot or part would do; no pass-through or ref; wrappers extending a primitive's whole props type; overridable copy defaults; no contract; tests through classes or test ids where roles exist; helpers duplicated per component; a list of cards without headings; a primitive with a single consumer.
6. **Cross-cutting**: patterns repeated across components (the same missing primitive improvised, the same hand-rolled behavior). These are the highest-value fixes.
7. **Target per component with red findings**: additive fix or migration, and the new contract in outline with its rewritten call sites. A broad pass is first; a component proposed for migration gets a second, deeper pass with its consumers.
8. **Priority list**: red first; within each, by consumers affected.

## Report

```markdown
# Audit · <folder> · <date>

## Project rules in force (recorded, not scored)

## Inventory
| Component | Kind | Consumers | API | State | Contract | Tests | 🔴 | 🟡 |

## Findings
### <Component>
- 🔴 `<file>:<line>` <what and what it should be>
- 🟡 `<file>:<line>` <what and what it should be>
- Keep: <what is right and must survive>
- Target: additive | migration. <one line>

## Cross-cutting
- <pattern>. <components>. <fix once, where>

## Priority
1. <component>. <why first>
```
