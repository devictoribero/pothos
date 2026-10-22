---
type: regex
target: trace
pattern: 'fast check: (?!picked <)[^<*\n]{1,160}?\b(because|as|since)\b'
flags: i
match: "count:1"
weight: 2
---

The session said once which fast command it picked and why ("picked X because Y", or the same with "as" or "since"). The session context's own bold line and its template never match: the pattern stops at `*` and at `<`.
