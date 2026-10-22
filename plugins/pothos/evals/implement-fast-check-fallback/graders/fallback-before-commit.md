---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^type-check changed=[\s\S]*^commit '
flags: m
weight: 2
---

The fallback ran before the first commit.
