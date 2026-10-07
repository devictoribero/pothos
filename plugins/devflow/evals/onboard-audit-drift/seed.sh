#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/notes.git
# Contracts are private and live in the agent's ~/.config/devflow. The agent's home is the
# workspace's parent directory; link that folder into the workspace so graders can read it.
mkdir -p .devflow-home "$(dirname "$PWD")/.config"
ln -s "$PWD/.devflow-home" "$(dirname "$PWD")/.config/devflow"
echo ".devflow-home" >> .git/info/exclude
cat > package.json <<'JSON'
{ "name": "notes", "private": true, "scripts": { "lint": "echo ok", "test": "echo ok", "dev": "echo dev" } }
JSON
touch package-lock.json
CONTRACT=".devflow-home/contracts/github.com/acme/notes.json"
mkdir -p "$(dirname "$CONTRACT")"
cat > "$CONTRACT" <<'JSON'
{
  "version": 1,
  "verify": { "fast": "npm run lint", "full": "npm run lint && npm run test:old" },
  "run": { "dev": "npm run dev" },
  "docs": { "glossary": "GLOSSARY.md" },
  "tracker": { "kind": "none" }
}
JSON
echo "# notes" > AGENTS.md
git add -A && git commit -q -m "initial"
