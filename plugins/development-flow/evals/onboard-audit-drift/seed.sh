#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
cat > package.json <<'JSON'
{ "name": "notes", "private": true, "scripts": { "lint": "echo ok", "test": "echo ok", "dev": "echo dev" } }
JSON
touch package-lock.json
mkdir -p .agents
cat > .agents/contract.json <<'JSON'
{
  "version": 1,
  "verify": { "fast": "npm run lint", "full": "npm run lint && npm run test:old" },
  "run": { "dev": "npm run dev" },
  "docs": { "context": "GLOSSARY.md" },
  "tracker": { "kind": "none" }
}
JSON
echo "# notes" > AGENTS.md
git add -A && git commit -q -m "initial"
