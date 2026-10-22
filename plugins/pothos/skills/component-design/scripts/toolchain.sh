#!/usr/bin/env bash
# Print the folder of the cached React 18 + TypeScript + Vitest + Testing Library toolchain, installing
# it on first use and again whenever the package list below changes. verify.sh --minimal and
# evals/fixture.py link its node_modules package by package.
# COMPONENT_DESIGN_TOOLCHAIN overrides the location (default ~/.cache/component-design/toolchain); a
# folder given that way with node_modules but no package.json is used as it is.
# `toolchain.sh --packages` prints the package list and installs nothing.
# The install runs in a sibling folder and moves into place only when npm succeeds, so a failed install
# (network, registry, disk) leaves no half-installed cache that a later run would accept.
set -euo pipefail
TC="${COMPONENT_DESIGN_TOOLCHAIN:-$HOME/.cache/component-design/toolchain}"
PKG='{ "private": true, "type": "module", "devDependencies": {
  "@testing-library/dom": "^10.4.0", "@testing-library/jest-dom": "^6.6.3", "@testing-library/react": "^16.1.0",
  "@testing-library/user-event": "^14.5.2", "@types/react": "^18.3.12", "@types/react-dom": "^18.3.1",
  "jsdom": "^25.0.1", "react": "^18.3.1", "react-dom": "^18.3.1", "typescript": "^5.6.3", "vitest": "^2.1.8" } }'
if [[ "${1:-}" == "--packages" ]]; then
  printf '%s\n' "$PKG"
  exit 0
fi
if [[ ! -d "$TC/node_modules" || ( -f "$TC/package.json" && "$(cat "$TC/package.json")" != "$PKG" ) ]]; then
  STAGE="$TC.installing.$$"
  trap 'rm -rf "$STAGE"' EXIT
  rm -rf "$STAGE"
  mkdir -p "$STAGE" "$(dirname "$TC")"
  printf '%s\n' "$PKG" > "$STAGE/package.json"
  if ! (cd "$STAGE" && npm install --no-audit --no-fund --loglevel=error >&2); then
    echo "toolchain.sh: npm install failed in $STAGE; nothing was changed under $TC" >&2
    exit 1
  fi
  rm -rf "$TC"
  mv "$STAGE" "$TC"
fi
echo "$TC"
