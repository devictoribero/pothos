#!/usr/bin/env bash
# Shared shape of the deps-* cases: a node repo whose origin fetch URL is GitHub (for the contract key), whose
# pushes go to a local bare repository, with node_modules written by hand (never an install), and stand-ins for
# npm and gh first on PATH through the shell profiles of the eval's home. The npm stand-in answers `view` and
# `audit` from .fakenpm/registry.json and applies `install <pkg>@<version>` to package.json, the lockfile and
# node_modules, logging every call to .fakenpm/calls.log; the gh stand-in logs to .fakegh/calls.log and keeps the
# body of a created pull request in .fakegh/pr-body.md. A post-commit hook logs the branch of every commit to
# .loop/commits.log, so a grader can see that main was never touched.
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git init -q --bare .origin.git
git remote add origin https://github.com/acme/ledger.git
git remote set-url --push origin "$PWD/.origin.git"
mkdir -p .pothos-home/contracts/github.com/acme "$(dirname "$PWD")/.config" .fakegh .fakenpm .loop
ln -sfn "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
printf '.pothos-home\n.origin.git\n.fakegh\n.fakenpm\n.loop\nnode_modules\n.scratch\n' >> .git/info/exclude
cat > .pothos-home/contracts/github.com/acme/ledger.json <<'JSON'
{"version": 1, "tracker": {"kind": "local", "path": ".scratch"}, "verify": {"fast": "node --check src/total.js", "full": "node --test"},
 "run": {"setup": "npm install"}, "deps": {"policy": "docs/dependencies.md", "label": "dependency-update"}, "pr": {"base": "main"}}
JSON
cat > .fakenpm/npm <<'PY'
#!/usr/bin/env python3
import json, os, re, sys
d = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(" ".join(args) + "\n")
reg = json.load(open(os.path.join(d, "registry.json")))
def parse(v):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", v); return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
def installed(name):
    p = os.path.join("node_modules", name, "package.json")
    return json.load(open(p))["version"] if os.path.exists(p) else None
if args[:1] == ["--version"]:
    print("10.0.0"); sys.exit(0)
if args[:1] == ["view"]:
    spec = args[1]; name, version = (spec.rsplit("@", 1) if "@" in spec[1:] else (spec, ""))
    pkg = reg.get(name)
    if not pkg:
        print("npm ERR! 404 Not Found - " + spec, file=sys.stderr); sys.exit(1)
    fields = [a for a in args[2:] if a != "--json"]
    if fields == ["peerDependencies"]:
        print(json.dumps((pkg.get("peers") or {}).get(version, {}))); sys.exit(0)
    out = {"time": pkg["time"], "dist-tags.latest": pkg["latest"]}
    if pkg.get("deprecated"): out["deprecated"] = pkg["deprecated"]
    print(json.dumps(out)); sys.exit(0)
if args[:1] == ["audit"]:
    vulns = {}
    for name, pkg in reg.items():
        adv = pkg.get("advisory")
        cur = installed(name)
        if adv and cur and parse(cur) < parse(adv["patched"]):
            vulns[name] = {"name": name, "severity": adv["severity"], "isDirect": True, "range": "<" + adv["patched"], "fixAvailable": True,
                           "via": [{"source": 1, "name": name, "title": adv["title"], "url": adv["url"], "severity": adv["severity"], "range": "<" + adv["patched"]}]}
    print(json.dumps({"vulnerabilities": vulns, "metadata": {"vulnerabilities": {"total": len(vulns)}}})); sys.exit(1 if vulns else 0)
if args[:1] == ["outdated"]:
    out = {}
    for name in sorted(reg):
        cur = installed(name)
        if cur and parse(cur) < parse(reg[name]["latest"]):
            out[name] = {"current": cur, "wanted": cur, "latest": reg[name]["latest"]}
    print(json.dumps(out)); sys.exit(1 if out else 0)
if args[:1] in (["install"], ["i"], ["add"], ["update"], ["ci"]):
    specs = [a for a in args[1:] if not a.startswith("-") and "@" in a[1:]]
    if specs and os.path.exists("package.json"):
        pkg = json.load(open("package.json"))
        lock = json.load(open("package-lock.json")) if os.path.exists("package-lock.json") else {"lockfileVersion": 3, "packages": {"": {}}}
        for spec in specs:
            name, version = spec.rsplit("@", 1)
            if name not in reg or version not in reg[name]["time"]:
                print(f"npm ERR! notarget No matching version found for {spec}", file=sys.stderr); sys.exit(1)
            for section in ("dependencies", "devDependencies"):
                if name in (pkg.get(section) or {}):
                    pkg[section][name] = "^" + version
                    lock["packages"][""].setdefault(section, {})[name] = "^" + version
            os.makedirs(os.path.join("node_modules", name), exist_ok=True)
            json.dump({"name": name, "version": version}, open(os.path.join("node_modules", name, "package.json"), "w"))
        json.dump(pkg, open("package.json", "w"), indent=2); open("package.json", "a").write("\n")
        json.dump(lock, open("package-lock.json", "w"), indent=2); open("package-lock.json", "a").write("\n")
    sys.exit(0)
sys.exit(0)
PY
chmod +x .fakenpm/npm
cat > .fakegh/gh <<'PY'
#!/usr/bin/env python3
# Stand-in for gh: logs every call, keeps the body of a created pull request, answers lists with nothing.
import os, sys
d = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
line = " ".join(args)
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(line + "\n")
if args[:2] == ["pr", "create"]:
    body = ""
    if "--body-file" in args:
        body = open(args[args.index("--body-file") + 1]).read()
    elif "--body" in args:
        body = args[args.index("--body") + 1]
    elif "-b" in args:
        body = args[args.index("-b") + 1]
    with open(os.path.join(d, "pr-body.md"), "a") as fh:
        fh.write(body + "\n---\n")
    print("https://github.com/acme/ledger/pull/42")
elif args[:2] == ["pr", "list"]:
    print("[]")
elif args[:2] == ["pr", "view"]:
    print('{"number": 42, "url": "https://github.com/acme/ledger/pull/42", "state": "OPEN", "isDraft": true}')
elif args[:2] == ["repo", "view"]:
    print('{"nameWithOwner":"acme/ledger","owner":{"login":"acme"},"name":"ledger"}')
elif args[:2] == ["auth", "status"]:
    print("Logged in to github.com account eval")
PY
chmod +x .fakegh/gh
: > .fakegh/calls.log
: > .fakenpm/calls.log
for rc in .zshenv .zshrc .bashrc .bash_profile .profile; do
  printf 'export PATH="%s:%s:$PATH"\n' "$PWD/.fakenpm" "$PWD/.fakegh" >> "$(dirname "$PWD")/$rc"
done
cat > .fakenpm/registry.json <<'JSON'
{
 "lodash": {"latest": "4.17.21", "time": {"4.17.20": "2020-08-13T00:00:00Z", "4.17.21": "2021-02-20T00:00:00Z"},
            "advisory": {"patched": "4.17.21", "severity": "high", "title": "Prototype pollution in zipObjectDeep", "url": "https://github.com/advisories/GHSA-p6mc-m468-83gw"}},
 "react": {"latest": "19.1.0", "time": {"18.2.0": "2022-06-14T00:00:00Z", "18.3.1": "2024-04-26T00:00:00Z", "19.0.0": "2024-12-05T00:00:00Z", "19.1.0": "2025-03-28T00:00:00Z"}},
 "react-dropzone": {"latest": "17.0.0", "time": {"11.7.1": "2022-02-01T00:00:00Z", "15.0.0": "__MATURED__", "16.0.0": "__YESTERDAY__", "17.0.0": "__TODAY__"}},
 "react-konva": {"latest": "19.0.0", "time": {"18.2.10": "2023-09-01T00:00:00Z", "19.0.0": "2025-01-10T00:00:00Z"}, "peers": {"19.0.0": {"react": "^19.0.0"}}},
 "react-select": {"latest": "6.0.0", "time": {"5.8.0": "2024-01-01T00:00:00Z", "6.0.0": "2025-02-01T00:00:00Z"}, "peers": {"6.0.0": {"react": "^18.0.0 || ^19.0.0"}}},
 "swiper": {"latest": "12.0.0", "time": {"12.0.0": "2025-06-01T00:00:00Z"}}
}
JSON
# Dates relative to the run: 15.0.0 matured five months ago, 16.0.0 and 17.0.0 are this week's two majors.
python3 - <<'PY'
import datetime
today = datetime.date.today()
stamp = lambda days: (today - datetime.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
text = open(".fakenpm/registry.json").read().replace("__MATURED__", stamp(152)).replace("__YESTERDAY__", stamp(1)).replace("__TODAY__", stamp(0))
open(".fakenpm/registry.json", "w").write(text)
PY
cat > package.json <<'JSON'
{
  "name": "ledger",
  "private": true,
  "type": "module",
  "scripts": {"test": "node --test"},
  "dependencies": {"lodash": "^4.17.20", "react": "^18.2.0", "react-dropzone": "^11.7.1", "react-select": "^5.8.0", "swiper": "^12.0.0"},
  "devDependencies": {"react-konva": "^18.2.10"}
}
JSON
python3 - <<'PY'
import json, os
pkg = json.load(open("package.json"))
lock = {"name": "ledger", "lockfileVersion": 3, "packages": {"": {"dependencies": pkg["dependencies"], "devDependencies": pkg["devDependencies"]}}}
json.dump(lock, open("package-lock.json", "w"), indent=2); open("package-lock.json", "a").write("\n")
for name, spec in {**pkg["dependencies"], **pkg["devDependencies"]}.items():
    os.makedirs(os.path.join("node_modules", name), exist_ok=True)
    json.dump({"name": name, "version": spec.lstrip("^")}, open(os.path.join("node_modules", name, "package.json"), "w"))
PY
mkdir -p src test docs
cat > src/total.js <<'JS'
export function total(lines) {
  return lines.reduce((sum, l) => sum + l.amount, 0);
}
JS
cat > src/upload.js <<'JS'
// The only call site of react-dropzone; nothing under test imports it.
import { useDropzone } from 'react-dropzone';
export const dropzone = useDropzone;
JS
cat > test/total.test.js <<'JS'
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { total } from '../src/total.js';
test('sums amounts', () => assert.equal(total([{ amount: 2 }, { amount: 3 }]), 5));
JS
printf '# Dependencies\n\nHolds and decisions for update-dependencies.\n' > docs/dependencies.md
cat > .git/hooks/post-commit <<HOOK
#!/bin/sh
echo "\$(git rev-parse --abbrev-ref HEAD) \$(git rev-parse --short HEAD)" >> "$PWD/.loop/commits.log"
HOOK
chmod +x .git/hooks/post-commit
git add -A && git commit -q -m "chore: ledger"
git push -q origin HEAD
: > .loop/commits.log
