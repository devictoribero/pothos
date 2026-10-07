---
type: regex
target: {source: file, path: ".agents/contract.json"}
pattern: '"full"\s*:\s*"yarn lint\s*&&\s*yarn type-check\s*&&\s*yarn test:unit"'
weight: 3
---

verify.full chains the CI scripts in CI order.
