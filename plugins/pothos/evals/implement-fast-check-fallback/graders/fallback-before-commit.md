---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^type-check changed=[^\n]*committed=0'
flags: m
weight: 2
---

The fallback ran before the first commit.
