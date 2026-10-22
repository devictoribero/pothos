---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^(lint|test:unit|type-check) changed=src/(total|receipt)\.js '
flags: m
weight: 3
---

A fallback step ran when exactly one of the two source files had changed: after the first edit and before the second.
