---
type: regex
target: {source: "file", path: ".fakegh/calls.log"}
pattern: 'run view .*log-failed'
weight: 1
---

The agent read the failing check's log.
