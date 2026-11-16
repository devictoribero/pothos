#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
bash "$(dirname "${BASH_SOURCE[0]}")/../_shared/council-seed.sh" "$PWD" settled
