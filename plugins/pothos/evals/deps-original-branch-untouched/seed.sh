#!/usr/bin/env bash
# A full run where the hygiene candidate (swiper, drift-safe, nothing to gain) turns the gate red after the bump
# and the advisory is already patched. Nothing may reach main: a drift-safe entry that needs a person becomes an
# assessment, never a pull request, and the attempt stays in its worktree.
set -euo pipefail
cd "${1:-$PWD}"
bash "$(dirname "${BASH_SOURCE[0]}")/../_shared/deps-seed.sh" "$PWD"
python3 - <<'PY'
import json
reg = json.load(open(".fakenpm/registry.json"))
reg["lodash"].pop("advisory")
reg["swiper"]["latest"] = "13.0.0"
reg["swiper"]["time"]["13.0.0"] = "2025-09-01T00:00:00Z"
json.dump(reg, open(".fakenpm/registry.json", "w"), indent=1)
PY
cat > test/swiper.test.js <<'JS'
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// The carousel is written against swiper 12's event names; 13 renamed them.
test('swiper stays on the line the carousel was written against', () => {
  const { version } = JSON.parse(readFileSync(new URL('../node_modules/swiper/package.json', import.meta.url)));
  assert.equal(version.split('.')[0], '12');
});
JS
git add -A && git commit -q -m "test: pin the swiper line"
: > .loop/commits.log
