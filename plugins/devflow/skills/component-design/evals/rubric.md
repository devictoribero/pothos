# Rubric

Score each output 0, 1 or 2 per criterion (0 = missing or wrong, 1 = partly, 2 = done well). The total is out of 22. Criteria 1 to 3 are measured by scripts; the rest by a reviewer reading the code with the evidence written next to each score.

| # | Criterion | 2 means | How it is measured |
|---|---|---|---|
| 1 | Works | type-check clean and every test passes | `scripts/verify.sh --minimal <output>` |
| 2 | Contract is the test list | ≥ 95% of contract bullets have a test | `scripts/check_contract.py` per component |
| 3 | Names | no findings, or each one justified | `scripts/lint.py <output>/src` (Names section) |
| 4 | Composition | content as slot props, parts or typed data by the decision guide; no fat objects, flags or props bags; the most frequent usage has no part every consumer would add | reviewer |
| 5 | State | ownership written for every state; controlled by default; closed unions rendered exhaustively; nothing representable that can't happen | reviewer |
| 6 | Accessibility | roles, names, keyboard and focus right for the pattern; no state by color alone; focus never drops; headings where lists of items need them | reviewer, plus `accessibility.md` defaults |
| 7 | Extensibility | the next likely need is additive (a new part, prop or union value) without touching existing parts | reviewer names two likely needs and checks |
| 8 | Maintainability | one way to do each thing; layers separated (feature: domain, data, view, container); no duplicated helpers; size proportional to the problem | reviewer |
| 9 | Honest verification | the summary states what ran, what didn't and every assumption | reviewer |
| 10 | Product completeness | realistic states the product needs (empty, loading, failed, edge content) are handled and visible in the preview | reviewer looks at preview.html in a browser |
| 11 | Dependencies and boundaries | imports point one way and primitives hold no business words | `scripts/lint.py <output>/src --business-words <the eval's domain words>` (Boundaries section) plus reviewer |

## Comparing two skill versions

1. Run every eval `runs_per_eval` times with each version, same model, fresh agents, same toolchain.
2. Score blind: the reviewer doesn't know which version produced which output.
3. Report the mean and the spread per criterion. A difference smaller than the spread between runs of the same version is noise.
4. Keep a rule only if removing it lowers a score (ablation); add a rule only when a run shows the failure it prevents.
