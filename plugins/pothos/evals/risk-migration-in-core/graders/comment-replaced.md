---
type: regex
target: {source: file, path: "pr-body.md"}
pattern: '<!-- Confidence ceiling'
match: not_contains
weight: 1
---

The agent replaced the script's placeholder comment with its own reason for the Confidence level.
