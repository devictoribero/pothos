---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^fast changed=[\s\S]*^commit '
flags: m
weight: 2
---

A fast run precedes the first commit.
