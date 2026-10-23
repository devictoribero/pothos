#!/usr/bin/env bash
# Audit mode on a repository with a runtime advisory and a dead line: everything is decided and may be measured,
# nothing is published, and the person's branch stays as it was.
set -euo pipefail
cd "${1:-$PWD}"
bash "$(dirname "${BASH_SOURCE[0]}")/../_shared/deps-seed.sh" "$PWD"
