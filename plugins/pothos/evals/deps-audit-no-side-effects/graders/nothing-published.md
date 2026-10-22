---
type: regex
target: {source: file, path: ".fakegh/calls.log"}
pattern: 'pr create|issue create|pr merge|add-label'
match: not_contains
weight: 3
---

No pull request, ticket, label or merge: audit publishes nothing.
