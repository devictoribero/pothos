---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^fast changed=[^\n]*committed=0'
flags: m
weight: 2
---

A fast run happened before the first commit.
