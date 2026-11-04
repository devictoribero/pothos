---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'pr comment 7 --body > \[!NOTE\][\s\S]{0,200}?Auto-merge authorized by the person'
weight: 2
---

The pull request got the comment naming who authorized it, which only `merge_gate.py authorize` writes, and it starts with the agent callout.
