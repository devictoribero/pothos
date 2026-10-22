---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^validate$'
flags: m
match: "count:1"
weight: 3
---

The gate ran exactly once: not twice through the pre-push hook, and not skipped.
