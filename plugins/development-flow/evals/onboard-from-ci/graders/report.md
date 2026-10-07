---
type: llm
weight: 2
---

PASS if the final message contains all of these:
- a summary of the contract fields and where each came from,
- the result of a smoke run of a verify command,
- a list of assumptions made without the user,
- gaps that include the missing end-to-end suite and that the dev command is not known to run without a real backend.

FAIL if any of these is missing, or if the message claims it changed package.json, CI or other build files.
