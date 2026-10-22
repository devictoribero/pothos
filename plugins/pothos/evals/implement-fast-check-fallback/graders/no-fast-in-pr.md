---
type: regex
target: {source: file, path: ".loop/pr-body.md"}
pattern: 'check:fast|fast check|inner loop'
flags: i
match: not_contains
weight: 2
---

The pull request body, test plan included, says nothing about the fast check.
