---
type: regex
target: {source: file, path: ".agents/contract.json"}
pattern: '"full"\s*:\s*"npm run lint\s*&&\s*npm run type-check\s*&&\s*npm run test:unit"'
weight: 3
---

verify.full chains the CI scripts in CI order.
