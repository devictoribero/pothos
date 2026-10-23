---
type: regex
target: {source: file, path: ".pothos-home/deps/github.com/acme/ledger/latest"}
pattern: '"swiper": \{[\s\S]*?"status": "(reported|failed)"'
weight: 2
---

The record says what happened to swiper: reported as an assessment, or failed with the gate's output.
