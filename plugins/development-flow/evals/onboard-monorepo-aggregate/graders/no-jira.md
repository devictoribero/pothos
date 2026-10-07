---
type: regex
target: {source: file, path: ".agents/contract.json"}
pattern: '"kind"\s*:\s*"jira"'
match: not_contains
weight: 2
---

The tracker is not set to Jira just because the word appears.
