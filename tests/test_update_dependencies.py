import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "pothos", "skills", "update-dependencies", "scripts")
SCRIPT = os.path.join(SCRIPTS, "deps.py")
CONTRACT_SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "contract.py")
CONTEXT_SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "session_context.py")
DETECT_SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "plant", "scripts", "detect.py")
sys.path.insert(0, SCRIPTS)
import deps  # noqa: E402

TODAY = datetime.date(2026, 7, 13)


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

# Stand-in for npm: `view` answers from $FAKE_REGISTRY/registry.json, `audit` from audit.json, everything is logged.
FAKE_NPM = r'''#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_REGISTRY"]; args = sys.argv[1:]
with open(os.path.join(d, "npm.log"), "a") as fh:
    fh.write(" ".join(args) + "\n")
if args[:1] == ["--version"]:
    print("10.0.0"); sys.exit(0)
if os.path.exists(os.path.join(d, "registry-down")):
    print("npm ERR! network request failed", file=sys.stderr); sys.exit(1)
if args[:1] == ["view"]:
    reg = json.load(open(os.path.join(d, "registry.json")))
    spec = args[1]
    name, version = (spec.rsplit("@", 1) if "@" in spec[1:] else (spec, ""))
    pkg = reg.get(name)
    if not pkg:
        print("npm ERR! 404 Not Found - " + spec, file=sys.stderr); sys.exit(1)
    fields = [a for a in args[2:] if a != "--json"]
    if fields == ["peerDependencies"]:
        print(json.dumps((pkg.get("peers") or {}).get(version, {}))); sys.exit(0)
    out = {"time": pkg["time"], "dist-tags.latest": pkg.get("latest")}
    if pkg.get("deprecated"):
        out["deprecated"] = pkg["deprecated"]
    print(json.dumps(out)); sys.exit(0)
if args[:1] == ["audit"]:
    if os.path.exists(os.path.join(d, "audit-down")):
        print("npm ERR! audit endpoint unreachable", file=sys.stderr); sys.exit(1)
    p = os.path.join(d, "audit.json")
    print(open(p).read() if os.path.exists(p) else '{"vulnerabilities":{}}'); sys.exit(0)
sys.exit(0)
'''

FAKE_GH = r'''#!/usr/bin/env python3
import os, sys
d = os.environ["FAKE_REGISTRY"]; args = sys.argv[1:]
with open(os.path.join(d, "gh.log"), "a") as fh:
    fh.write(" ".join(args) + "\n")
if args[:2] == ["pr", "list"]:
    p = os.path.join(d, "prs.json")
    print(open(p).read() if os.path.exists(p) else "[]")
sys.exit(0)
'''

REGISTRY = {
    "react": {"latest": "19.1.0", "time": {"18.2.0": "2022-06-14T00:00:00Z", "18.3.1": "2024-04-26T00:00:00Z",
                                           "19.0.0": "2024-12-05T00:00:00Z", "19.1.0": "2025-03-28T00:00:00Z"}},
    "react-dropzone": {"latest": "17.0.0", "time": {"11.7.1": "2022-02-01T00:00:00Z", "15.0.0": "2026-02-11T00:00:00Z",
                                                    "16.0.0": "2026-07-12T00:00:00Z", "17.0.0": "2026-07-13T00:00:00Z"}},
    "lodash": {"latest": "4.17.21", "time": {"4.17.20": "2020-08-13T00:00:00Z", "4.17.21": "2021-02-20T00:00:00Z"}},
    "swiper": {"latest": "14.0.0", "time": {"12.0.0": "2025-06-01T00:00:00Z", "14.0.0": "2026-05-01T00:00:00Z"}},
    "eslint": {"latest": "10.0.0", "time": {"9.0.0": "2024-04-05T00:00:00Z", "9.39.5": "2026-07-11T00:00:00Z", "10.0.0": "2026-06-01T00:00:00Z"}},
    "react-konva": {"latest": "19.0.0", "time": {"18.2.10": "2023-09-01T00:00:00Z", "19.0.0": "2025-01-10T00:00:00Z"},
                    "peers": {"19.0.0": {"react": "^19.0.0"}}},
    "react-select": {"latest": "6.0.0", "time": {"5.8.0": "2024-01-01T00:00:00Z", "6.0.0": "2025-02-01T00:00:00Z"},
                     "peers": {"6.0.0": {"react": "^18.0.0 || ^19.0.0"}}},
    "request": {"latest": "2.88.2", "deprecated": "request has been deprecated", "time": {"2.88.2": "2020-02-11T00:00:00Z"}},
    "prettier": {"latest": "3.6.0", "time": {"3.5.0": "2026-07-01T00:00:00Z", "3.6.0": "2026-07-10T00:00:00Z"}},
}

AUDIT = {"vulnerabilities": {"lodash": {"name": "lodash", "severity": "high", "isDirect": True, "range": "<4.17.21", "fixAvailable": True,
                                        "via": [{"source": 1, "name": "lodash", "title": "Prototype pollution",
                                                 "url": "https://github.com/advisories/GHSA-x", "severity": "high", "range": "<4.17.21"}]}}}


class SemverTest(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(deps.parse("v1.2.3"), (1, 2, 3, None))
        self.assertIsNone(deps.parse("1.2"))
        self.assertEqual(deps.compare("1.2.3", "1.10.0"), -1)
        self.assertEqual(deps.compare("2.0.0-rc.1", "2.0.0"), -1)
        self.assertTrue(deps.is_prerelease("3.0.0-beta.2"))

    def test_ranges(self):
        self.assertTrue(deps.satisfies("18.3.1", "^18.0.0 || ^19.0.0"))
        self.assertFalse(deps.satisfies("18.3.1", "^19.0.0"))
        self.assertTrue(deps.satisfies("4.17.20", "<4.17.21"))
        self.assertFalse(deps.satisfies("4.17.21", "<4.17.21"))
        self.assertTrue(deps.satisfies("2.0.5", ">=2.0.0 <2.1.5 || >=3.0.0 <3.0.3"))
        self.assertFalse(deps.satisfies("2.1.5", ">=2.0.0 <2.1.5 || >=3.0.0 <3.0.3"))
        self.assertTrue(deps.satisfies("1.4.0", "~1.4.0"))
        self.assertFalse(deps.satisfies("1.5.0", "~1.4.0"))
        self.assertTrue(deps.satisfies("18.2.0", "18.x"))
        self.assertTrue(deps.satisfies("18.2.0", "18"))
        self.assertTrue(deps.satisfies("1.5.0", "1.2.0 - 1.9.0"))
        self.assertTrue(deps.satisfies("9.9.9", "*"))
        self.assertFalse(deps.satisfies("2.0.0-rc.1", "^2.0.0"))


class ClassifyTest(unittest.TestCase):
    """Pure functions, no processes."""

    def reg(self, name):
        return {"versions": REGISTRY[name]["time"], "deprecated": REGISTRY[name].get("deprecated"), "latest": REGISTRY[name]["latest"]}

    def test_dead_line_becomes_drift_exposed_and_a_backported_line_stays_safe(self):
        status, facts = deps.line_status("11.7.1", self.reg("react-dropzone"), TODAY, 365)
        self.assertEqual(status, "dead")
        self.assertEqual(facts["last_on_line"], "11.7.1")
        self.assertGreater(facts["silent_days"], 1500)
        status, facts = deps.line_status("9.0.0", self.reg("eslint"), TODAY, 365)
        self.assertEqual(status, "backported")
        self.assertEqual(facts["last_on_line"], "9.39.5")
        self.assertEqual(deps.line_status("4.17.21", self.reg("lodash"), TODAY, 365)[0], "current")

    def test_the_window_retargets_to_the_newest_matured_version(self):
        target, why = deps.matured_target("11.7.1", self.reg("react-dropzone"), TODAY, 14)
        self.assertEqual(target, "15.0.0")
        self.assertIn("2026-02-11", why)
        self.assertTrue(deps.erratic(self.reg("react-dropzone"), TODAY))
        self.assertFalse(deps.erratic(self.reg("lodash"), TODAY))

    def test_nothing_matured_or_already_installed_is_not_a_target(self):
        target, why = deps.matured_target("10.0.0", self.reg("eslint"), TODAY, 14)
        self.assertIsNone(target)
        self.assertIn("already installed", why)
        target, why = deps.matured_target("3.5.0", self.reg("prettier"), TODAY, 14)
        self.assertIsNone(target)
        self.assertIn("no version has matured", why)

    def test_security_takes_the_minimum_patched_version_whatever_its_age(self):
        entry = {"name": "lodash", "installed": "4.17.20", "runtime": True}
        audit = {"lodash": {"severity": "high", "range": "<4.17.21", "direct": True, "fix": True,
                            "advisories": [{"id": "GHSA-x", "severity": "high", "title": "t", "range": "<4.17.21"}]}}
        out = deps.classify(entry, self.reg("lodash"), audit, TODAY, deps.DEFAULTS)
        self.assertEqual((out["driver"], out["target"]), ("security", "4.17.21"))
        self.assertEqual(out["evidence"]["reaches"], "runtime")
        patched = {**self.reg("lodash"), "versions": {"4.17.20": "2020-08-13T00:00:00Z"}}
        self.assertIn("escapes the advisory", deps.classify(entry, patched, audit, TODAY, deps.DEFAULTS)["failure"])

    def test_deprecated_is_eol_and_a_live_line_is_drift_safe(self):
        out = deps.classify({"name": "request", "installed": "2.88.2", "runtime": True}, self.reg("request"), {}, TODAY, deps.DEFAULTS)
        self.assertEqual(out["driver"], "eol")
        out = deps.classify({"name": "eslint", "installed": "9.0.0", "runtime": False}, self.reg("eslint"), {}, TODAY, deps.DEFAULTS)
        self.assertEqual((out["driver"], out["target"]), ("drift-safe", "10.0.0"))

    def test_a_hold_blocks_only_what_the_peer_range_cannot_keep(self):
        holds = [{"package": "react", "major": 18, "until": "2027-01-01", "why": "router first"}]
        konva = {"name": "react-konva", "target": "19.0.0", "driver": "drift-exposed"}
        self.assertEqual(deps.apply_policy(konva, holds, [], TODAY, {"react": "^19.0.0"})[0], "held")
        select = {"name": "react-select", "target": "6.0.0", "driver": "drift-safe"}
        self.assertEqual(deps.apply_policy(select, holds, [], TODAY, {"react": "^18.0.0 || ^19.0.0"})[0], None)
        react = {"name": "react", "target": "19.1.0", "driver": "drift-safe"}
        self.assertIn("stays on 18", deps.apply_policy(react, holds, [], TODAY, None)[1])
        expired = [{**holds[0], "until": "2026-01-01"}]
        self.assertEqual(deps.apply_policy(react, expired, [], TODAY, None)[0], None)

    def test_a_decision_silences_until_its_date_but_not_security(self):
        decisions = [{"package": "swiper", "until": "2026-12-01", "why": "carousel first"}]
        self.assertEqual(deps.apply_policy({"name": "swiper", "target": "14.0.0", "driver": "drift-safe"}, [], decisions, TODAY, None)[0], "decided")
        self.assertEqual(deps.apply_policy({"name": "swiper", "target": "14.0.0", "driver": "security"}, [], decisions, TODAY, None)[0], None)
        self.assertEqual(deps.apply_policy({"name": "swiper", "target": "14.0.0", "driver": "drift-safe"}, [], decisions,
                                           datetime.date(2027, 1, 1), None)[0], None)

    def test_reconciliation(self):
        pulls = [{"number": 12, "title": "bump vite", "root": "vite", "target": "5.4.0"},
                 {"number": 13, "title": "Upgrade lodash by hand", "root": None, "target": None}]
        self.assertEqual(deps.reconcile({"name": "vite", "target": "5.4.0"}, pulls), ("existing-pr", 12))
        self.assertEqual(deps.reconcile({"name": "vite", "target": "6.0.0"}, pulls), ("supersede", 12))
        self.assertEqual(deps.reconcile({"name": "lodash", "target": "4.17.21"}, pulls), ("overlaps-person", 13))
        self.assertEqual(deps.reconcile({"name": "zod", "target": "4.0.0"}, pulls), (None, None))


class RepoTest(unittest.TestCase):
    """deps.py against a repository on disk, with stand-ins for npm and gh."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        self.fake = os.path.join(self.tmp.name, "fake")
        os.makedirs(self.fake)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        for name, body in (("npm", FAKE_NPM), ("gh", FAKE_GH)):
            path = os.path.join(self.fake, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
        self.json(os.path.join(self.fake, "registry.json"), REGISTRY)
        self.json(os.path.join(self.fake, "audit.json"), AUDIT)
        self.env = {**os.environ, "POTHOS_HOME": self.home, "FAKE_REGISTRY": self.fake,
                    "POTHOS_NPM": os.path.join(self.fake, "npm"), "POTHOS_PNPM": os.path.join(self.fake, "pnpm"),
                    "POTHOS_GH": os.path.join(self.fake, "gh")}
        self.contract({"deps": {"policy": "docs/dependencies.md", "gates": {"^vite$": "npm run build"}}})
        self.package({"react": "^18.2.0", "react-dropzone": "^11.7.1", "lodash": "^4.17.20", "swiper": "^12.0.0"},
                     {"react-konva": "^18.2.10", "react-select": "^5.8.0", "eslint": "^9.0.0"})
        self.write("docs/dependencies.md", "# Dependencies\n\n- react stays on 18 until 2027-01-01: router first\n"
                                           "- swiper: not before 2026-12-01: carousel first\n")
        self.write("src/drop.tsx", "import { useDropzone } from 'react-dropzone';\n")
        self.write("src/drop.test.tsx", "import { x } from './drop';\n")

    def json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(data, fh)

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def contract(self, extra):
        self.json(os.path.join(self.home, "contracts", "github.com", "acme", "shop.json"),
                  {"version": 1, "verify": {"full": "npm test"}, **extra})

    def package(self, dependencies, dev, installed=None):
        pkg = {"name": "shop", "scripts": {"test": "node --test", "lint": "eslint ."}, "dependencies": dependencies, "devDependencies": dev}
        self.json(os.path.join(self.repo, "package.json"), pkg)
        self.json(os.path.join(self.repo, "package-lock.json"),
                  {"lockfileVersion": 3, "packages": {"": {"dependencies": dependencies, "devDependencies": dev}}})
        for name, spec in {**dependencies, **dev}.items():
            version = (installed or {}).get(name) or spec.lstrip("^~")
            self.json(os.path.join(self.repo, "node_modules", name, "package.json"), {"name": name, "version": version})

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)

    def plan(self, *args):
        result = self.run_script("plan", "--today", "2026-07-13", *args)
        path = result.stdout.splitlines()[0] if result.stdout.strip() else None
        return result, (load(path) if path and os.path.isfile(path) else None)

    def test_without_a_contract_exits_2(self):
        os.remove(os.path.join(self.home, "contracts", "github.com", "acme", "shop.json"))
        self.assertEqual(self.run_script("plan").returncode, 2)

    def test_the_plan_classifies_every_direct_dependency_and_writes_the_record(self):
        result, record = self.plan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.splitlines()[0].startswith(os.path.join(self.home, "deps", "github.com", "acme", "shop")))
        entries = record["entries"]
        self.assertEqual(entries["lodash"]["driver"], "security")
        self.assertEqual(entries["lodash"]["target"], "4.17.21")
        self.assertEqual(entries["react-dropzone"]["driver"], "drift-exposed")
        self.assertEqual(entries["react-dropzone"]["target"], "15.0.0")
        self.assertTrue(entries["react-dropzone"]["erratic"])
        self.assertEqual(entries["react-dropzone"]["impact"]["radius"], "narrow")
        self.assertEqual(entries["react-dropzone"]["impact"]["tests"], ["src/drop.test.tsx"])
        self.assertEqual(entries["eslint"]["driver"], "drift-safe")
        self.assertEqual(entries["eslint"]["impact"]["radius"], "wide")
        self.assertIn("lint", entries["eslint"]["impact"]["why"])
        self.assertEqual((entries["react"]["status"], entries["react"]["reason"]), ("skipped", "held"))
        self.assertEqual((entries["react-konva"]["status"], entries["react-konva"]["reason"]), ("skipped", "held"))
        self.assertIn("needs react ^19.0.0", entries["react-konva"]["note"])
        self.assertEqual(entries["react-select"]["status"], "candidate", "a peer range that keeps 18 is not held")
        self.assertEqual((entries["swiper"]["status"], entries["swiper"]["reason"]), ("skipped", "decided"))
        self.assertEqual(record["environment"]["npm"], "10.0.0")
        self.assertEqual(record["environment"]["lockfile"]["file"], "package-lock.json")
        self.assertEqual(record["entries"]["lodash"]["provenance"]["audit"], "npm audit --json")
        self.assertIn("hold react stays on 18 until 2027-01-01: keeps react, react-konva back", result.stdout)
        self.assertIn("1 silenced by decisions", result.stdout)
        self.assertNotIn("react-konva: skipped", result.stdout, "held entries are reported once, under the hold")
        self.assertIn("lodash: candidate, security (runtime)", result.stdout)
        self.assertIn("react-dropzone: candidate, drift-exposed line dead 11.7.1 -> 15.0.0, radius narrow, erratic versioning", result.stdout)

    def test_gates_from_the_contract_attach_to_matching_entries(self):
        self.package({"vite": "^5.0.0"}, {})
        self.json(os.path.join(self.fake, "registry.json"), {"vite": {"latest": "6.0.0", "time": {"5.0.0": "2023-11-16T00:00:00Z", "6.0.0": "2024-11-26T00:00:00Z"}}})
        _, record = self.plan()
        self.assertEqual(record["entries"]["vite"]["gates"], ["npm run build"])

    def test_only_and_exclude(self):
        self.contract({"deps": {"exclude": ["react*"]}})
        result, record = self.plan()
        self.assertEqual((record["entries"]["react"]["status"], record["entries"]["react"]["reason"]), ("skipped", "excluded"))
        self.assertNotIn("driver", record["entries"]["react-dropzone"], "excluded packages are never classified")
        self.assertEqual(record["entries"]["lodash"]["status"], "candidate")
        self.assertIn("4 excluded by deps.exclude: react, react-dropzone, react-konva, react-select", result.stdout)
        self.assertNotIn("react: skipped", result.stdout)
        self.assertNotIn("view react ", read(os.path.join(self.fake, "npm.log")), "no registry call for an excluded package")
        result, record = self.plan("react-dropzone")
        self.assertEqual(record["entries"]["react-dropzone"]["status"], "candidate", "a named package wins over exclude")
        self.assertEqual(record["entries"]["lodash"]["reason"], "not-selected")
        self.assertNotIn("lodash", result.stdout)

    def test_a_registry_that_does_not_answer_fails_the_entry_explicitly(self):
        open(os.path.join(self.fake, "registry-down"), "w").close()
        result, record = self.plan()
        self.assertEqual(result.returncode, 1)
        for entry in record["entries"].values():
            self.assertEqual(entry["status"], "failed")
            self.assertIn("registry data missing", entry["reason"])
            self.assertNotIn("driver", entry)
        self.assertEqual(record["status"], "planned-with-failures")

    def test_advisories_unavailable_fails_every_entry(self):
        open(os.path.join(self.fake, "audit-down"), "w").close()
        result, record = self.plan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("advisories unknown", record["entries"]["lodash"]["reason"])
        self.assertIn("audit endpoint unreachable", record["sources"]["audit"]["error"])

    def test_a_lockfile_out_of_sync_stops_the_run_before_any_bump(self):
        lock = os.path.join(self.repo, "package-lock.json")
        data = load(lock)
        data["packages"][""]["dependencies"]["lodash"] = "^4.0.0"
        self.json(lock, data)
        result, record = self.plan()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(record["status"], "failed")
        self.assertIn("package-lock.json dependencies differ", record["failure"])
        self.assertEqual(record["entries"], {})
        self.assertNotIn("view", read(os.path.join(self.fake, "npm.log")))

    def test_an_installed_version_missing_from_node_modules_fails_that_entry_only(self):
        import shutil
        shutil.rmtree(os.path.join(self.repo, "node_modules", "swiper"))
        result, record = self.plan()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(record["entries"]["swiper"]["status"], "failed")
        self.assertIn("installed version unknown", record["entries"]["swiper"]["reason"])
        self.assertEqual(record["entries"]["lodash"]["status"], "candidate")

    def test_open_pull_requests_reconcile_by_metadata_and_never_touch_a_person(self):
        self.json(os.path.join(self.fake, "prs.json"), [
            {"number": 12, "title": "chore(deps): bump react-dropzone to 15.0.0", "body": "Dependency-Root: react-dropzone\nDependency-Target: 15.0.0",
             "headRefName": "deps/dropzone", "author": {"login": "bot"}, "isDraft": True},
            {"number": 13, "title": "Upgrade lodash by hand", "body": "", "headRefName": "x", "author": {"login": "ana"}, "isDraft": False}])
        result, record = self.plan()
        self.assertEqual((record["entries"]["react-dropzone"]["status"], record["entries"]["react-dropzone"]["reason"]), ("skipped", "existing-pr"))
        self.assertEqual(record["entries"]["react-dropzone"]["related_pr"], 12)
        self.assertEqual(record["entries"]["lodash"]["reconciliation"], "overlaps-person")
        self.assertIn("overlaps a person's #13", result.stdout)
        self.assertIn("pr list --state open --label dependency-update", read(os.path.join(self.fake, "gh.log")))

    def test_a_peer_the_run_will_not_satisfy_fails_the_entry_with_the_conflict(self):
        # No hold: react moves to 19.1.0, so react-konva's ^19 peer is satisfied by react's target.
        os.remove(os.path.join(self.repo, "docs", "dependencies.md"))
        _, record = self.plan()
        self.assertEqual(record["entries"]["react-konva"]["status"], "candidate")
        # react excluded from the run: it stays installed at 18.2.0 and react-konva 19 cannot have its peer.
        self.contract({"deps": {"exclude": ["react"]}})
        result, record = self.plan()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(record["entries"]["react-konva"]["status"], "failed")
        self.assertEqual(record["entries"]["react-konva"]["reason"], "peer conflict: needs react ^19.0.0, react will be 18.2.0 (installed)")
        self.assertEqual(record["entries"]["react-select"]["status"], "candidate", "^18 || ^19 is satisfied by the installed 18")
        self.assertIn("react-konva: failed, peer conflict", result.stdout)

    def test_a_missing_policy_file_is_a_note_not_a_failure(self):
        os.remove(os.path.join(self.repo, "docs", "dependencies.md"))
        result, record = self.plan()
        self.assertEqual(result.returncode, 0)
        self.assertIn("does not exist", record["sources"]["policy"]["note"])
        self.assertEqual(record["entries"]["react"]["status"], "candidate")

    def test_update_records_states_and_refuses_a_false_verified(self):
        _, record = self.plan()
        path = os.path.join(self.home, "deps", "github.com", "acme", "shop", "2026-07-13.json")
        self.assertEqual(self.run_script("update", path, "lodash", "--status", "applied").returncode, 0)
        still = self.run_script("update", path, "lodash", "--status", "verified", "--set", "verify_exit=4")
        self.assertEqual(still.returncode, 64)
        self.assertIn("exit 4 means the run is still going", still.stderr)
        self.assertEqual(self.run_script("update", path, "lodash", "--status", "in-progress", "--note", "verify exit 4").returncode, 0)
        done = self.run_script("update", path, "lodash", "--status", "pr-opened", "--pr", "https://github.com/acme/shop/pull/20")
        self.assertIn("lodash: pr-opened https://github.com/acme/shop/pull/20", done.stdout)
        entry = load(path)["entries"]["lodash"]
        self.assertEqual([h["status"] for h in entry["history"]], ["applied", "in-progress", "pr-opened"])
        self.assertEqual(self.run_script("update", path, "nothing", "--status", "applied").returncode, 64)
        self.assertEqual(self.run_script("update", path, "lodash", "--status", "green").returncode, 64)

    def test_summary_reads_a_record_back(self):
        self.plan()
        path = os.path.join(self.home, "deps", "github.com", "acme", "shop", "2026-07-13.json")
        out = self.run_script("summary", path)
        self.assertEqual(out.returncode, 0)
        self.assertIn("lodash: candidate, security (runtime)", out.stdout)
        self.assertIn("hold react stays on 18", out.stdout)

    def test_two_records_on_one_day_do_not_overwrite_and_latest_points_at_the_newest(self):
        self.plan()
        self.plan()
        folder = os.path.join(self.home, "deps", "github.com", "acme", "shop")
        self.assertEqual(sorted(os.listdir(folder)), ["2026-07-13-2.json", "2026-07-13.json", "latest"])
        self.assertEqual(os.readlink(os.path.join(folder, "latest")), "2026-07-13-2.json")
        self.assertEqual(load(os.path.join(folder, "latest"))["date"], "2026-07-13")

    def test_a_second_run_sees_the_lock_and_stops(self):
        folder = os.path.join(self.home, "deps", "github.com", "acme", "shop")
        os.makedirs(folder)
        with open(os.path.join(folder, ".lock"), "w") as fh:
            fh.write(str(os.getpid()))
        result = self.run_script("plan")
        self.assertEqual(result.returncode, 4)
        self.assertIn("holds the lock", result.stderr)
        self.assertEqual(self.run_script("unlock").returncode, 0)
        self.assertEqual(self.run_script("plan", "--today", "2026-07-13").returncode, 0)

    def test_a_stale_lock_from_a_dead_process_is_taken_over(self):
        folder = os.path.join(self.home, "deps", "github.com", "acme", "shop")
        os.makedirs(folder)
        with open(os.path.join(folder, ".lock"), "w") as fh:
            fh.write("999999")
        self.assertEqual(self.run_script("plan", "--today", "2026-07-13").returncode, 0)

    def test_impact_anchors_the_import_and_treats_configured_tooling_as_wide(self):
        self.write("src/vite-user.ts", "import { defineConfig } from 'vitest/config';\n")
        self.write("vite.config.ts", "export default {};\n")
        out = json.loads(self.run_script("impact", "vite").stdout)
        self.assertEqual(out["importers"], [], "vitest is not vite")
        self.assertEqual(out["radius"], "wide")
        self.assertIn("vite.config", out["why"])
        out = json.loads(self.run_script("impact", "react-dropzone").stdout)
        self.assertEqual(out["importers"], ["src/drop.tsx"])
        self.assertEqual(out["tests"], ["src/drop.test.tsx"])
        self.assertEqual(out["count"], 1)
        for i in range(4):
            self.write(f"src/more{i}.tsx", "import 'react-dropzone/dist/style.css';\n")
        self.assertEqual(json.loads(self.run_script("impact", "react-dropzone").stdout)["radius"], "wide")

    def test_workspaces_are_inventoried_with_their_own_installed_versions(self):
        self.json(os.path.join(self.repo, "package.json"), {"name": "mono", "workspaces": ["apps/*"], "devDependencies": {"eslint": "^9.0.0"}})
        os.remove(os.path.join(self.repo, "package-lock.json"))
        self.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        self.json(os.path.join(self.repo, "apps", "web", "package.json"), {"name": "web", "dependencies": {"lodash": "^4.17.20", "@acme/ui": "workspace:*"}})
        self.json(os.path.join(self.repo, "apps", "web", "node_modules", "lodash", "package.json"), {"version": "4.17.20"})
        entries = deps.inventory(self.repo)
        self.assertEqual(sorted(entries), ["eslint", "lodash"])
        self.assertEqual(entries["lodash"]["installed"], "4.17.20")
        self.assertEqual(entries["lodash"]["declared"][0]["package"], "apps/web")
        self.assertTrue(entries["lodash"]["runtime"])
        self.assertFalse(entries["eslint"]["runtime"])
        self.assertEqual(deps.package_manager(self.repo), "pnpm")

    def test_pnpm_audit_format_is_read_too(self):
        self.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        os.remove(os.path.join(self.repo, "package-lock.json"))
        pnpm = os.path.join(self.fake, "pnpm")
        with open(pnpm, "w") as fh:
            fh.write(FAKE_NPM)
        os.chmod(pnpm, 0o755)
        self.json(os.path.join(self.fake, "audit.json"), {"advisories": {"1": {"module_name": "lodash", "severity": "high", "title": "Prototype pollution",
                                                                               "vulnerable_versions": "<4.17.21", "url": "https://github.com/advisories/GHSA-x",
                                                                               "findings": [{"version": "4.17.20", "paths": ["lodash"]}]}}})
        result, record = self.plan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(record["entries"]["lodash"]["driver"], "security")
        self.assertEqual(record["sources"]["audit"]["command"], "pnpm audit --json")
        self.assertIn("audit --json", read(os.path.join(self.fake, "npm.log")))


class ContractAndContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        self.env = {**os.environ, "POTHOS_HOME": self.home}

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, "verify": {"full": "npm test"}, **data}, fh)
        return path

    def validate(self, *args):
        return subprocess.run([sys.executable, CONTRACT_SCRIPT, "validate", *args], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def context(self):
        result = subprocess.run([sys.executable, CONTEXT_SCRIPT], cwd=self.repo, env=self.env, capture_output=True, text=True, input="")
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_the_schema_accepts_deps_and_rejects_unknown_fields(self):
        self.contract({"deps": {"exclude": ["@acme/*"], "cooling_off_days": 7, "dead_line_months": 18, "review_budget": 2,
                                "label": "deps", "policy": "docs/dependencies.md", "gates": {"^vite$": "npm run build"}}})
        self.assertEqual(self.validate().returncode, 0, self.validate().stdout)
        self.contract({"deps": {"package_manager": "pnpm"}})
        result = self.validate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown field 'package_manager'", result.stdout)
        self.contract({"deps": {"cooling_off_days": -1}})
        self.assertEqual(self.validate().returncode, 0, "the subset validator has no minimum; the schema documents it")

    def test_strict_validation_lets_the_policy_file_be_created_later_but_inside_the_repository(self):
        self.contract({"deps": {"policy": "docs/dependencies.md"}})
        self.assertEqual(self.validate("--strict").returncode, 0)
        self.contract({"deps": {"policy": "../elsewhere.md"}})
        result = self.validate("--strict")
        self.assertEqual(result.returncode, 1)
        self.assertIn("deps.policy: '../elsewhere.md' must be a path inside the repository", result.stdout)

    def test_the_template_carries_the_section(self):
        template = load(os.path.join(ROOT, "plugins", "pothos", "templates", "contract.json"))
        self.assertEqual(sorted(template["deps"]), ["cooling_off_days", "dead_line_months", "exclude", "gates", "label", "policy", "review_budget"])

    def test_the_session_context_names_the_skill_only_when_the_contract_has_deps(self):
        self.contract({})
        self.assertNotIn("update-dependencies", self.context())
        self.contract({"deps": {"label": "deps", "policy": "docs/dependencies.md", "cooling_off_days": 7}})
        text = self.context()
        self.assertIn("### Dependencies", text)
        self.assertIn("`/pothos:update-dependencies` (label `deps`, policy file `docs/dependencies.md`, cooling-off 7 days)", text)
        self.contract({"deps": {}})
        text = self.context()
        self.assertIn("`/pothos:update-dependencies`: it bumps only", text)
        self.assertLess(len(text.split("### Dependencies")[1]), 500, "one short paragraph: the context has a size limit")

    def test_detect_reports_dependency_bots_and_a_policy_file(self):
        report = json.loads(subprocess.run([sys.executable, DETECT_SCRIPT, self.repo], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(report["dependency_bots"], [])
        self.assertIsNone(report["dependency_policy"])
        for rel in (".github/dependabot.yml", "renovate.json", "docs/dependencies.md"):
            path = os.path.join(self.repo, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").close()
        report = json.loads(subprocess.run([sys.executable, DETECT_SCRIPT, self.repo], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(report["dependency_bots"], ["dependabot", "renovate"])
        self.assertEqual(report["dependency_policy"], "docs/dependencies.md")


class SkillTextTest(unittest.TestCase):
    def test_the_skill_quotes_the_defaults_the_script_uses(self):
        text = read(os.path.join(ROOT, "plugins", "pothos", "skills", "update-dependencies", "SKILL.md"))
        self.assertIn(f"`deps.cooling_off_days` ago ({deps.DEFAULTS['cooling_off_days']} by default)", text)
        self.assertIn(f"`deps.dead_line_months` ({deps.DEFAULTS['dead_line_months']})", text)
        self.assertIn(f"`deps.review_budget` ({deps.DEFAULTS['review_budget']})", text)
        output = read(os.path.join(ROOT, "plugins", "pothos", "skills", "update-dependencies", "references", "output.md"))
        for status in deps.ENTRY_STATUSES:
            self.assertIn(f"`{status}`", output, status)


if __name__ == "__main__":
    unittest.main()
