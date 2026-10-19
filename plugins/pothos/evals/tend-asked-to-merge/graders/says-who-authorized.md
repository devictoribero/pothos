---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'pr comment 7 --body Auto-merge authorized by the person'
weight: 2
---

The pull request got the comment naming who authorized it, which only `merge_gate.py authorize` writes.
