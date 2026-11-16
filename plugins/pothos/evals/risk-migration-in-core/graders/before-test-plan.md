---
type: regex
target: {source: file, path: "pr-body.md"}
pattern: '## Risk[\s\S]*## Test plan'
weight: 1
---

The repository template has no risk section, so Risk sits right before its test plan.
