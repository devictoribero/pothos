#!/usr/bin/env bash
# A hold keeps React on 18. react-konva 19 needs React 19 and must be held; react-select 6 accepts 18 or 19 and
# must not be, whatever its name suggests.
set -euo pipefail
cd "${1:-$PWD}"
bash "$(dirname "${BASH_SOURCE[0]}")/../_shared/deps-seed.sh" "$PWD"
cat > docs/dependencies.md <<'MD'
# Dependencies

Holds and decisions for update-dependencies.

- react stays on 18 until 2099-01-01: the router migration goes first
MD
git add -A && git commit -q -m "docs: hold react on 18"
: > .loop/commits.log
