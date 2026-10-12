---
type: regex
target: {source: file, path: ".github/workflows/ci.yml"}
pattern: 'run: npm run lint\n\s*- run: npm run type-check\n\s*- run: npm run test:unit'
weight: 2
---

onboard did not change CI.
