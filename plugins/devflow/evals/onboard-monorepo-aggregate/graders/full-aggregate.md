---
type: regex
target: {source: file, path: ".agents/contract.json"}
pattern: '"full"\s*:\s*"pnpm run validate"'
weight: 3
---

verify.full is the aggregate validate script, not the build-only check.
