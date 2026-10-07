#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
cat > package.json <<'JSON'
{
  "name": "shop-web",
  "private": true,
  "scripts": {
    "dev": "echo dev server on http://localhost:5173",
    "lint": "echo lint ok",
    "lint:fix": "echo fixing",
    "type-check": "echo types ok",
    "type-check:fast": "echo fast types ok",
    "test:unit": "echo unit ok",
    "build": "echo build"
  }
}
JSON
touch yarn.lock
mkdir -p .github/workflows
cat > .github/workflows/ci.yml <<'YML'
name: ci
on: [pull_request]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: yarn install --frozen-lockfile
      - run: yarn lint
      - run: yarn type-check
      - run: yarn test:unit
YML
cat > AGENTS.md <<'MD'
# shop-web

Original project notes: the storefront for a small shop. Work is planned in GitHub issues.

## Conventions

- Components live in src/components.
MD
git add -A && git commit -q -m "initial"
