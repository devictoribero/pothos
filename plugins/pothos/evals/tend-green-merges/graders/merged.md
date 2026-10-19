---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'pr merge 7 --squash --match-head-commit [0-9a-f]{40}'
weight: 3
---

The gate merged with squash, pinned to the head commit.
