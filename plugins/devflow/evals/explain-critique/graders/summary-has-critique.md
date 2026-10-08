---
type: regex
target: {source: file, path: ".devflow-home/artifacts/github.com/acme/vetapp/latest/summary.md"}
pattern: 'worker[\s\S]{0,300}(reminder-model|REMINDER_TABLE|model)|(reminder-model|REMINDER_TABLE)[\s\S]{0,300}worker'
flags: i
weight: 1
---

The top critique finding reaches summary.md, so other agents see it.
