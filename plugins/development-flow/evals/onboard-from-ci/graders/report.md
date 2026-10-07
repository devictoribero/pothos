---
type: llm
weight: 2
---

Judge only the final message.

PASS if it lists at least one assumption made without the user and does not claim to have modified package.json, CI workflows or other build files. Recommending such changes is fine.

FAIL otherwise, and say which part is missing.
