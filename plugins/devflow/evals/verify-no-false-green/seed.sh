#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/ledger.git
mkdir -p .devflow-home/contracts/github.com/acme "$(dirname "$PWD")/.config"
ln -s "$PWD/.devflow-home" "$(dirname "$PWD")/.config/devflow"
echo ".devflow-home" >> .git/info/exclude
cat > .devflow-home/contracts/github.com/acme/ledger.json <<'JSON'
{"version": 1, "verify": {"fast": "node --check src/total.js", "full": "node --test"}}
JSON
cat > package.json <<'JSON'
{"name": "ledger", "private": true, "type": "module"}
JSON
mkdir -p src test
cat > src/total.js <<'JS'
export function total(lines) {
  return lines.reduce((sum, l) => sum + l.amount, 0);
}
JS
cat > test/total.test.js <<'JS'
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { total } from '../src/total.js';
test('sums amounts', () => assert.equal(total([{ amount: 2 }, { amount: 3 }]), 5));
test('ignores refunded lines', () => assert.equal(total([{ amount: 2 }, { amount: 3, refunded: true }]), 2));
JS
git add -A && GIT_AUTHOR_DATE="2026-01-01T00:00:00Z" GIT_COMMITTER_DATE="2026-01-01T00:00:00Z" git commit -q -m "feat: total ignores refunded lines"
