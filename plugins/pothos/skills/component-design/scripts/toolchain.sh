#!/usr/bin/env bash
# Print the folder of the cached React 18 + TypeScript + Vitest + Testing Library toolchain, installing
# it on first use and again whenever the package list below changes. verify.sh --minimal and
# evals/fixture.py link its node_modules package by package.
# COMPONENT_DESIGN_TOOLCHAIN overrides the location (default ~/.cache/component-design/toolchain); a
# folder given that way with node_modules but no package.json is used as it is.
set -euo pipefail
TC="${COMPONENT_DESIGN_TOOLCHAIN:-$HOME/.cache/component-design/toolchain}"
PKG='{ "private": true, "type": "module", "devDependencies": {
  "@testing-library/dom": "^10.4.0", "@testing-library/jest-dom": "^6.6.3", "@testing-library/react": "^16.1.0",
  "@testing-library/user-event": "^14.5.2", "@types/react": "^18.3.12", "@types/react-dom": "^18.3.1",
  "jsdom": "^25.0.1", "react": "^18.3.1", "react-dom": "^18.3.1", "typescript": "^5.6.3", "vitest": "^2.1.8" } }'
if [[ ! -d "$TC/node_modules" || ( -f "$TC/package.json" && "$(cat "$TC/package.json")" != "$PKG" ) ]]; then
  mkdir -p "$TC"
  printf '%s\n' "$PKG" > "$TC/package.json"
  (cd "$TC" && rm -rf node_modules package-lock.json && npm install --no-audit --no-fund --silent >&2)
fi
echo "$TC"
