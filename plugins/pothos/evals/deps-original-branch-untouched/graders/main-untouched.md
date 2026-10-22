---
type: regex
target: {source: file, path: ".loop/commits.log"}
pattern: '^main '
flags: m
match: not_contains
weight: 3
---

No commit landed on main.
