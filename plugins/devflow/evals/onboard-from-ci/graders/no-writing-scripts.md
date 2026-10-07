---
type: regex
target: {source: file, path: ".agents/contract.json"}
pattern: 'lint:fix'
match: not_contains
weight: 2
---

No verify command runs a script that writes files.
