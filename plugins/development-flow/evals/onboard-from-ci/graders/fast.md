---
type: regex
target: {source: file, path: ".agents/contract.json"}
pattern: '"fast"\s*:\s*"yarn type-check:fast'
weight: 1
---

verify.fast uses the declared fast script.
