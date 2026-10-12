#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/pets.git
# Contracts are private and live in the agent's ~/.config/pothos. The agent's home is the
# workspace's parent directory; link that folder into the workspace so graders can read it.
mkdir -p .pothos-home "$(dirname "$PWD")/.config"
ln -s "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
echo ".pothos-home" >> .git/info/exclude
cat > package.json <<'JSON'
{
  "name": "pets",
  "private": true,
  "scripts": {
    "dev": "pnpm -r --parallel run dev",
    "dev:mock": "echo app with mocked API on http://localhost:8081",
    "lint": "pnpm -r run lint",
    "type-check": "pnpm -r run type-check",
    "test": "pnpm -r run test",
    "validate": "pnpm run lint && pnpm run type-check && pnpm run test",
    "check": "pnpm -r run build"
  }
}
JSON
printf 'packages:\n  - apps/*\n' > pnpm-workspace.yaml
touch pnpm-lock.yaml
mkdir -p apps/api apps/mobile docs/decisions
echo '{"name":"api","scripts":{"lint":"echo ok","type-check":"echo ok","test":"echo ok","build":"echo ok"}}' > apps/api/package.json
echo '{"name":"mobile","scripts":{"lint":"echo ok","type-check":"echo ok","test":"echo ok","build":"echo ok"}}' > apps/mobile/package.json
cat > CONTEXT.md <<'MD'
# Pets

**Household**: the people who care for pets together.
MD
echo "# 0001 Use REST" > docs/decisions/0001-use-rest.md
cat > CLAUDE.md <<'MD'
# pets

We do not use Jira or any issue tracker. Work is planned in docs files.

Run `pnpm run validate` before opening a pull request.
MD
git add -A && git commit -q -m "initial"
