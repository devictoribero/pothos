---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^validate$[\s\S]*^push refs/heads/refunds$'
flags: m
weight: 2
---

The gate ran before the branch was pushed.
