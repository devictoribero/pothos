---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'add-label|--label|/labels'
match: not_contains
weight: 3
---

The agent never added a label.
