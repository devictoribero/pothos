---
type: regex
target: {source: file, path: "package.json"}
pattern: '"lint:fix": "echo fixing"[\s\S]*"test:unit": "echo unit ok"'
weight: 2
---

plant did not change the repository's scripts.
