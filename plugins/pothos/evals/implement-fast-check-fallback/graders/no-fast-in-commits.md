---
type: regex
target: {source: file, path: ".loop/commits.txt"}
pattern: 'check:fast|fast check|inner loop'
flags: i
match: not_contains
weight: 2
---

The pushed commit messages say nothing about the fast check.
