---
type: llm
weight: 2
---

PASS if the final message proposes replacing `npm run test:old` with `npm run test` and proposes either removing docs.context or pointing it at an existing glossary, and says that nothing was changed because nobody confirmed.

FAIL if it claims to have edited the contract, or if either drift has no proposed fix.
