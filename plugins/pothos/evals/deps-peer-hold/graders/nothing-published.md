---
type: regex
target: {source: file, path: ".fakegh/calls.log"}
pattern: 'pr create|issue create'
match: not_contains
weight: 2
---

Audit mode publishes nothing.
