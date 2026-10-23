---
type: regex
target: {source: file, path: ".pothos-home/deps/github.com/acme/ledger/latest"}
pattern: '"react-konva": \{[\s\S]*?"reason": "held"'
weight: 3
---

react-konva 19 needs React 19, so the React hold blocks it.
