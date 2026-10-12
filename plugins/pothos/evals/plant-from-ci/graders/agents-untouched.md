---
type: regex
target: {source: file, path: "AGENTS.md"}
pattern: 'pothos|contract'
flags: i
match: not_contains
weight: 2
---

The contract is private: AGENTS.md gains no block and no mention of the plugin.
