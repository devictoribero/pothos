#!/usr/bin/env bash
# react-dropzone sits on a line dead for years; its latest two majors are hours old. The target must be the
# version that matured five months ago, never the fresh one, and the entry is never cancelled.
set -euo pipefail
cd "${1:-$PWD}"
bash "$(dirname "${BASH_SOURCE[0]}")/../_shared/deps-seed.sh" "$PWD"
