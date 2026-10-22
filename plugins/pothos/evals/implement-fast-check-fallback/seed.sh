#!/usr/bin/env bash
# The implement-fast-check repo without a root `check:fast`: only `lint`, `test:unit` (jest) and `type-check`
# scripts, stand-ins that log to .loop/log and exit 0, plus the same `validate` gate, a pre-push hook that runs
# validate, a pull request template with a test plan, and a local
# ticket that needs edits in two source files. Pushes go to a local bare repository whose post-receive hook
# logs the push and the commit messages; gh is a logging stand-in that saves the pull request body.
# The graders read the logs, so they check what ran and in which order, not what the agent says.
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git config push.negotiate false
git init -q --bare .origin.git
git remote add origin https://github.com/acme/ledger.git
git remote set-url --push origin "$PWD/.origin.git"
mkdir -p .pothos-home/contracts/github.com/acme "$(dirname "$PWD")/.config" .fakegh .loop .github scripts src test .scratch/refunds/issues
ln -sfn "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
# The eval harness drops its own dotfiles into the workspace; keep them out of git status, so verify sees a clean tree.
printf '.pothos-home\n.origin.git\n.fakegh\n.loop\n.claude/\n.claude.json\n.mcp.json\n.eval-artifacts\n.bashrc\n.bash_profile\n.profile\n.zshrc\n.zshenv\n.zprofile\n.gitconfig\n.ripgreprc\n.config/\n.cache/\n.npm/\n.local/\n' >> .git/info/exclude
cat > .pothos-home/contracts/github.com/acme/ledger.json <<'JSON'
{"version": 1, "tracker": {"kind": "local", "path": ".scratch"}, "verify": {"full": "npm run validate"},
 "pr": {"base": "main", "template": ".github/pull_request_template.md"}}
JSON
cat > .fakegh/gh <<'PY'
#!/usr/bin/env python3
# Stand-in for gh: logs every call to .fakegh/calls.log, saves a created pull request's body to .loop/pr-body.md.
import os, sys
d = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(d)
args = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(" ".join(args) + "\n")
def value(flags):
    for i, a in enumerate(args):
        if a in flags and i + 1 < len(args):
            return args[i + 1]
        for f in flags:
            if a.startswith(f + "="):
                return a[len(f) + 1:]
    return None
if args[:2] == ["pr", "create"]:
    body = value(("--body", "-b"))
    path = value(("--body-file", "-F"))
    if path and os.path.exists(path):
        body = open(path).read()
    with open(os.path.join(root, ".loop", "pr-body.md"), "w") as fh:
        fh.write(body or "")
    print("https://github.com/acme/ledger/pull/1")
elif args[:2] == ["pr", "view"]:
    print('{"number": 1, "url": "https://github.com/acme/ledger/pull/1", "state": "OPEN", "isDraft": false, "headRefName": "refunds", "baseRefName": "main"}')
elif args[:2] == ["pr", "list"]:
    print("[]")
elif args[:2] == ["repo", "view"]:
    print('{"nameWithOwner":"acme/ledger","owner":{"login":"acme"},"name":"ledger","defaultBranchRef":{"name":"main"}}')
elif args[:2] == ["auth", "status"]:
    print("Logged in to github.com account eval")
PY
chmod +x .fakegh/gh
: > .fakegh/calls.log
for rc in .zshenv .zshrc .bashrc .bash_profile .profile; do
  printf 'export PATH="%s:$PATH"\n' "$PWD/.fakegh" >> "$(dirname "$PWD")/$rc"
done
cat > .origin.git/hooks/post-receive <<HOOK
#!/bin/sh
while read old new ref; do
  echo "push \$ref" >> "$PWD/.loop/log"
  git log --format=%B -n 20 "\$new" >> "$PWD/.loop/commits.txt"
done
HOOK
chmod +x .origin.git/hooks/post-receive
cat > .git/hooks/post-commit <<HOOK
#!/bin/sh
echo "commit \$(git rev-parse --short HEAD)" >> "$PWD/.loop/log"
HOOK
cat > .git/hooks/pre-push <<'HOOK'
#!/bin/sh
# The repository's gate runs before every push unless the push says --no-verify.
npm run validate
HOOK
chmod +x .git/hooks/post-commit .git/hooks/pre-push
cat > scripts/loop-log.sh <<'SH'
#!/bin/sh
# Stand-in for a check: logs its name, the source files changed since the base commit, whether anything is committed yet, and its arguments.
name="$1"; shift
base=$(cat .loop/base)
changed=$( { git diff --name-only "$base" -- src; git ls-files --others --exclude-standard -- src; } | sort -u | paste -sd, -)
committed=1; [ "$(git rev-parse HEAD)" = "$base" ] && committed=0
echo "$name changed=$changed committed=$committed args=$*" >> .loop/log
SH
cat > scripts/lint.sh <<'SH'
#!/bin/sh
sh scripts/loop-log.sh lint "$@"
echo "lint: 0 problems"
SH
cat > scripts/jest.sh <<'SH'
#!/bin/sh
# The unit runner is jest here, so the fallback passes --findRelatedTests with the changed files.
sh scripts/loop-log.sh test:unit "$@"
echo "unit: 4 passed, 0 failed"
SH
cat > scripts/type-check.sh <<'SH'
#!/bin/sh
sh scripts/loop-log.sh type-check "$@"
echo "type-check: 0 errors"
SH
cat > scripts/validate.sh <<'SH'
#!/bin/sh
# The full gate: everything CI runs. A stand-in that logs and reports green with counts.
echo "validate" >> .loop/log
echo "lint: 0 problems in 6 files"
echo "type-check: 0 errors"
echo "unit: 6 passed, 0 failed"
echo "build: ok"
SH
cat > package.json <<'JSON'
{
  "name": "ledger",
  "private": true,
  "type": "module",
  "scripts": {
    "lint": "sh scripts/lint.sh",
    "test:unit": "sh scripts/jest.sh",
    "type-check": "sh scripts/type-check.sh",
    "validate": "sh scripts/validate.sh",
    "test": "node --test"
  }
}
JSON
cat > .github/pull_request_template.md <<'MD'
## Summary

## Test plan

| Step | Result | Notes |
|---|---|---|
| lint | | |
| type-check | | |
| unit tests | | |
| build | | |

✅ passed · ❌ failed · ⏭️ skipped (say why)
MD
cat > src/total.js <<'JS'
export function total(lines) {
  return lines.reduce((sum, l) => sum + l.amount, 0);
}
JS
cat > src/receipt.js <<'JS'
import { total } from './total.js';

export function receipt(lines) {
  return `Total: ${total(lines)}`;
}
JS
cat > test/total.test.js <<'JS'
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { total } from '../src/total.js';
test('sums amounts', () => assert.equal(total([{ amount: 2 }, { amount: 3 }]), 5));
JS
cat > test/receipt.test.js <<'JS'
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { receipt } from '../src/receipt.js';
test('prints the total', () => assert.equal(receipt([{ amount: 2 }, { amount: 3 }]), 'Total: 5'));
JS
cat > .scratch/refunds/issues/01-refunded-lines.md <<'MD'
# Refunded lines are left out of the total and counted on the receipt

Status: ready-for-agent

## What

A line with `refunded: true` was already paid back, so it must not count towards the total, and the receipt must say how many lines were refunded.

## Acceptance criteria

- `total(lines)` in `src/total.js` ignores lines with `refunded: true`: `total([{ amount: 2 }, { amount: 3, refunded: true }])` is `2`.
- `receipt(lines)` in `src/receipt.js` appends ` (N refunded)` when at least one line is refunded: `receipt([{ amount: 2 }, { amount: 3, refunded: true }])` is `Total: 2 (1 refunded)`. With no refunded line it stays `Total: 5`.
- Tests under `test/` cover both.
MD
git add -A
git commit -q -m "chore: ledger with a receipt"
git push -q origin main
git checkout -q -b refunds
git rev-parse HEAD > .loop/base
: > .loop/log
: > .loop/commits.txt
