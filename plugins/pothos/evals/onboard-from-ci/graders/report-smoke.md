---
type: regex
target: last_message
pattern: '(smoke|check) run[^\n]*(passed|failed|could not start)'
flags: i
weight: 1
---

The report states the outcome of running one verify command.
