---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^fast changed=src/(total|receipt)\.js '
flags: m
weight: 3
---

The fast check ran when exactly one of the two source files had changed: after the first edit and before the second.
