---
type: regex
target: {source: file, path: ".devflow-home/contracts/github.com/acme/pets.json"}
pattern: '"full"\s*:\s*"pnpm run validate"'
weight: 3
---

verify.full is the aggregate validate script, not the build-only check.
