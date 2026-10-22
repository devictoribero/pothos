---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^test:unit changed=[^\n]*--findRelatedTests'
flags: m
weight: 1
---

The unit runner is jest, so the tests ran with --findRelatedTests and the changed files.
