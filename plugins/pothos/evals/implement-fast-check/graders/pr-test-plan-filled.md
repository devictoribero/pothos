---
type: regex
target: {source: file, path: ".loop/pr-body.md"}
pattern: 'Test plan[\s\S]*(✅|⏭️)'
weight: 1
---

The pull request keeps the template's test plan and fills its rows from the gate run.
