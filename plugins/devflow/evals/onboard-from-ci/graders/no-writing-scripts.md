---
type: regex
target: {source: file, path: ".devflow-home/contracts/github.com/acme/shop-web.json"}
pattern: 'lint:fix'
match: not_contains
weight: 2
---

No verify command runs a script that writes files.
