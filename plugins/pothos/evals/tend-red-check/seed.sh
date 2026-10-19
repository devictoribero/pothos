#!/usr/bin/env bash
# Shared shape: a node repo whose origin fetch URL is GitHub (for the contract key) and whose pushes
# go to a local bare repository; gh is a logging stand-in put first on PATH by the shell profiles.
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git init -q --bare .origin.git
git remote add origin https://github.com/acme/ledger.git
git remote set-url --push origin "$PWD/.origin.git"
mkdir -p .pothos-home/contracts/github.com/acme "$(dirname "$PWD")/.config" .fakegh
ln -sfn "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
printf '.pothos-home\n.origin.git\n.fakegh\n' >> .git/info/exclude
cat > .pothos-home/contracts/github.com/acme/ledger.json <<'JSON'
{"version": 1, "tracker": {"kind": "github"}, "verify": {"full": "node --test"}, "pr": {"base": "main", "auto_merge": {"label": "auto-merge"}}}
JSON
cat > .fakegh/gh <<'PY'
#!/usr/bin/env python3
# Stand-in for gh: answers from .fakegh/*.json and logs every call to .fakegh/calls.log.
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
line = " ".join(args)
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(line + "\n")
def show(name, default=""):
    p = os.path.join(d, name)
    print(open(p).read() if os.path.exists(p) else default)
if args[:2] == ["pr", "view"]:
    show("pr.json")
elif args[:2] == ["pr", "checks"]:
    show("checks.txt", "test\tpass\t1m\thttps://github.com/acme/ledger/actions/runs/101")
elif args[:2] == ["run", "view"]:
    show("failed-log.txt")
elif args[:2] == ["pr", "list"]:
    print("[]")
elif args[:2] == ["api", "graphql"]:
    if "addPullRequestReviewThreadReply" in line:
        print('{"data":{"addPullRequestReviewThreadReply":{"comment":{"id":"C_reply"}}}}')
    elif "resolveReviewThread" in line:
        print('{"data":{"resolveReviewThread":{"thread":{"isResolved":true}}}}')
    else:
        show("threads.json", '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[]}}}}}')
elif args[:1] == ["api"] and "/git/ref/heads/" in line:
    sys.exit(1)
elif args[:1] == ["api"] and "/comments" in line:
    show("comments.json", "[]")
elif args[:2] == ["repo", "view"]:
    print('{"nameWithOwner":"acme/ledger","owner":{"login":"acme"},"name":"ledger"}')
PY
chmod +x .fakegh/gh
: > .fakegh/calls.log
cat > .origin.git/hooks/post-receive <<HOOK
#!/bin/sh
while read old new ref; do echo "\$ref \$new" >> "$PWD/.fakegh/pushes.log"; done
HOOK
chmod +x .origin.git/hooks/post-receive
# The eval's HOME is the parent folder: put the stand-in first on PATH for every shell the agent starts.
for rc in .zshenv .zshrc .bashrc .bash_profile .profile; do
  printf 'export PATH="%s:$PATH"\n' "$PWD/.fakegh" >> "$(dirname "$PWD")/$rc"
done
cat > package.json <<'JSON'
{"name": "ledger", "private": true, "type": "module"}
JSON
mkdir -p src test
cat > test/total.test.js <<'JS'
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { total } from '../src/total.js';
test('sums amounts', () => assert.equal(total([{ amount: 2 }, { amount: 3 }]), 5));
JS
cat > src/total.js <<'JS'
export function total(lines) {
  return lines.reduce((sum, l) => sum + l.amount, 0);
}
JS
git add -A && git commit -q -m "chore: ledger"
git push -q origin main
git checkout -q -b fix-total
# The pull request: a test for refunded lines and the code that should make it pass.
cat >> test/total.test.js <<'JS'
test('ignores refunded lines', () => assert.equal(total([{ amount: 2 }, { amount: 3, refunded: true }]), 2));
JS
cat > src/total.js <<'JS'
export function total(lines) {
  return lines.filter((l) => !l.refunded).reduce((sum, l) => sum + l.amount, 0);
}
JS
cat > src/total.js <<'JS'
export function total(lines) {
  return lines.filter((l) => l.refunded !== false).reduce((sum, l) => sum + l.amount, 0);
}
JS
git add -A && git commit -q -m 'fix: ignore refunded lines'
git push -q origin fix-total
cat > .fakegh/failed-log.txt <<'DATA'
test	Run tests	2026-10-19T10:00:00Z ✖ ignores refunded lines
test	Run tests	2026-10-19T10:00:00Z   AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
test	Run tests	2026-10-19T10:00:00Z   5 !== 2
test	Run tests	2026-10-19T10:00:00Z   at test/total.test.js:5
DATA
cat > .fakegh/checks.txt <<'DATA'
test	fail	1m	https://github.com/acme/ledger/actions/runs/101
DATA
cat > .fakegh/pr.json <<'DATA'
{
 "number": 7,
 "url": "https://github.com/acme/ledger/pull/7",
 "title": "Ignore refunded lines in total",
 "state": "OPEN",
 "isDraft": false,
 "baseRefName": "main",
 "headRefName": "fix-total",
 "headRefOid": "__HEAD__",
 "isCrossRepository": false,
 "labels": [
  {
   "name": "auto-merge"
  }
 ],
 "mergeable": "MERGEABLE",
 "mergeStateStatus": "CLEAN",
 "latestReviews": [],
 "reviews": [],
 "comments": [],
 "body": "Closes #3",
 "statusCheckRollup": [
  {
   "__typename": "CheckRun",
   "name": "test",
   "status": "COMPLETED",
   "conclusion": "FAILURE"
  }
 ]
}
DATA
sed -i.bak "s/__HEAD__/$(git rev-parse HEAD)/" .fakegh/pr.json && rm .fakegh/pr.json.bak
: > .fakegh/pushes.log
