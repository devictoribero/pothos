---
type: regex
target: {source: file, path: "pr-body.md"}
pattern: 'one-way[^\n]*(migration|0002_add_refunds)'
flags: i
weight: 2
---

The door line says why it is one-way: the database migration.
