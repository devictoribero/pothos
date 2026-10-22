---
type: regex
target: trace
pattern: 'fast check: picked [^<]{1,160}? because'
flags: i
match: "count:1"
weight: 2
---

The session said once which fast command it picked and why, in the form the session context asks for.
