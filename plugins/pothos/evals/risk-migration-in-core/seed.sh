#!/usr/bin/env bash
# A service whose contract declares billing as a core area. The branch adds a database migration inside billing,
# with the code and a test that use it, and no verify receipt yet. The repository's own template has a test plan.
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/ledger.git
mkdir -p .pothos-home/contracts/github.com/acme "$(dirname "$PWD")/.config"
ln -sfn "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
printf '.pothos-home\npr-body.md\n' >> .git/info/exclude
cat > .pothos-home/contracts/github.com/acme/ledger.json <<'JSON'
{
  "version": 1,
  "verify": {"full": "node --test"},
  "pr": {
    "base": "main",
    "template": ".github/pull_request_template.md",
    "risk": {"core": [{"name": "billing", "paths": ["services/billing"]}]}
  }
}
JSON
mkdir -p .github services/billing/migrations services/catalog test
cat > .github/pull_request_template.md <<'MD'
## Summary

## Test plan
MD
cat > package.json <<'JSON'
{"name": "ledger", "private": true}
JSON
cat > services/billing/migrations/0001_create_invoices.sql <<'SQL'
CREATE TABLE invoices (id TEXT PRIMARY KEY, amount INTEGER NOT NULL);
SQL
cat > services/billing/invoice.js <<'JS'
exports.total = (invoices) => invoices.reduce((sum, i) => sum + i.amount, 0);
JS
cat > services/catalog/item.js <<'JS'
exports.label = (item) => item.name;
JS
cat > test/invoice.test.js <<'JS'
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { total } = require('../services/billing/invoice.js');
test('sums invoices', () => assert.equal(total([{ amount: 2 }, { amount: 3 }]), 5));
JS
git add -A && git commit -q -m "chore: ledger"
git checkout -q -b refunds
cat > services/billing/migrations/0002_add_refunds.sql <<'SQL'
ALTER TABLE invoices ADD COLUMN refunded INTEGER NOT NULL DEFAULT 0;
UPDATE invoices SET amount = amount - refunded;
SQL
cat > services/billing/invoice.js <<'JS'
exports.total = (invoices) => invoices.reduce((sum, i) => sum + i.amount - (i.refunded || 0), 0);
JS
cat > test/invoice.test.js <<'JS'
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { total } = require('../services/billing/invoice.js');
test('sums invoices', () => assert.equal(total([{ amount: 2 }, { amount: 3 }]), 5));
test('subtracts refunds', () => assert.equal(total([{ amount: 5, refunded: 2 }]), 3));
JS
git add -A && git commit -q -m "feat(billing): refunds reduce the invoice total"
