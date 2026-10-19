---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'pr merge 7 --squash --match-head-commit'
weight: 3
---

The gate merged after verify passed.
