---
type: regex
target: {source: file, path: ".loop/log"}
pattern: '^(?=[\s\S]*^lint )(?=[\s\S]*^test:unit )[\s\S]*^type-check '
flags: m
weight: 3
---

All three fallback steps ran: lint, the unit tests and the type-check.
