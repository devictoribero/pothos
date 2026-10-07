---
type: regex
target: last_message
pattern: 'npm run lint && npm run test(?![:\w])|npm run test`'
weight: 2
---

The report proposes replacing the renamed script with the one that exists.
