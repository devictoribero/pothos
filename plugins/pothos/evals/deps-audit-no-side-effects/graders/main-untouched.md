---
type: regex
target: {source: file, path: ".loop/commits.log"}
pattern: '^main '
flags: m
match: not_contains
weight: 2
---

No commit landed on main (the post-commit hook logs the branch of every commit).
