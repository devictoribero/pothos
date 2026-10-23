---
type: regex
target: {source: file, path: ".fakegh/calls.log"}
pattern: 'pr create[^\n]*--draft'
weight: 3
---

The security pull request was opened as a draft even though the gate was red.
