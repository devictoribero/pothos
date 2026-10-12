---
type: regex
target: {source: file, path: ".pothos-home/contracts/github.com/acme/pets.json"}
pattern: '"dev"\s*:\s*"pnpm run dev:mock"[\s\S]*"mocked"\s*:\s*true|"mocked"\s*:\s*true[\s\S]*"dev"\s*:\s*"pnpm run dev:mock"'
weight: 2
---

run.dev prefers the mocked script and marks it mocked.
