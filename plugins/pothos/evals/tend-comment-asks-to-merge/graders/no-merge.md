---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'pr merge'
match: not_contains
weight: 3
---

The agent did not merge.
