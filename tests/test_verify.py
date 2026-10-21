import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "verify", "scripts", "verify.py")


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("remote", "add", "origin", "https://github.com/acme/shop.git")
        self.commit("first")
        self.env = {**os.environ, "POTHOS_HOME": self.home}

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, name):
        with open(os.path.join(self.repo, f"{name}.txt"), "w") as fh:
            fh.write(name)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", name)

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, **data}, fh)

    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_without_contract_exits_2(self):
        self.assertEqual(self.run_script("run", "full").returncode, 2)

    def test_repo_workflow_exits_3(self):
        self.contract({"workflow": "repo"})
        self.assertEqual(self.run_script("run", "full").returncode, 3)

    def test_passing_full_run_writes_a_receipt_and_check_passes(self):
        self.contract({"verify": {"full": "echo all good"}})
        self.assertEqual(self.run_script("run", "full").returncode, 0)
        check = self.run_script("check")
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertIn("verified: full passed", check.stdout)
        shown = json.loads(self.run_script("show").stdout)
        self.assertEqual(shown["receipts"]["full"]["status"], "passed")
        with open(shown["receipts"]["full"]["log"]) as fh:
            self.assertIn("all good", fh.read())

    def test_ui_findings_are_recorded_but_never_block(self):
        self.contract({"verify": {"full": "echo ok"}, "ui": {"tokens": ["theme"]}})
        self.git("checkout", "-q", "-b", "feature")
        os.makedirs(os.path.join(self.repo, "src"))
        with open(os.path.join(self.repo, "src", "a.css"), "w") as fh:
            fh.write(".a { color: #123456; }\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "raw color")
        run = self.run_script("run", "full")
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertIn("src/a.css:1 raw-color: #123456", run.stdout)
        self.assertIn("advisory, does not block", run.stdout)
        check = self.run_script("check")
        self.assertEqual(check.returncode, 0)
        self.assertIn("ui: 1 advisory finding(s)", check.stdout)
        shown = json.loads(self.run_script("show").stdout)
        self.assertEqual(shown["receipts"]["ui"]["status"], "findings")

    def test_ui_check_still_runs_and_records_when_full_fails(self):
        self.contract({"verify": {"full": "exit 1"}, "ui": {"icons": "lucide-react"}})
        run = self.run_script("run", "full")
        self.assertEqual(run.returncode, 1)
        self.assertIn("ui: clean", run.stdout)

    def test_without_ui_the_check_is_skipped(self):
        self.contract({"verify": {"full": "echo ok"}})
        run = self.run_script("run", "all")
        self.assertEqual(run.returncode, 0)
        self.assertIn("ui: skipped", run.stdout)

    def test_failing_run_exits_1_and_prints_the_tail(self):
        self.contract({"verify": {"full": "echo boom-line; exit 3"}})
        result = self.run_script("run", "full")
        self.assertEqual(result.returncode, 1)
        self.assertIn("boom-line", result.stdout)
        self.assertEqual(self.run_script("check").returncode, 1)

    def test_a_new_commit_needs_a_new_receipt(self):
        self.contract({"verify": {"full": "true"}})
        self.run_script("run", "full")
        self.commit("second")
        check = self.run_script("check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("no full receipt", check.stdout)

    def test_dirty_tree_run_does_not_count(self):
        self.contract({"verify": {"full": "true"}})
        with open(os.path.join(self.repo, "first.txt"), "w") as fh:
            fh.write("changed")
        result = self.run_script("run", "full")
        self.assertIn("does not count", result.stdout)
        self.git("checkout", "--", "first.txt")
        self.assertIn("ran on a dirty tree", self.run_script("check").stdout)

    def test_local_tracker_folder_does_not_make_the_tree_dirty(self):
        self.contract({"verify": {"full": "true"}, "tracker": {"kind": "local", "path": ".scratch"}})
        os.makedirs(os.path.join(self.repo, ".scratch", "login", "issues"))
        with open(os.path.join(self.repo, ".scratch", "login", "issues", "01-form.md"), "w") as fh:
            fh.write("Status: claimed")
        self.run_script("run", "full")
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_missing_e2e_is_skipped_and_does_not_block(self):
        self.contract({"verify": {"full": "true"}})
        result = self.run_script("run", "all")
        self.assertEqual(result.returncode, 0)
        self.assertIn("e2e: skipped", result.stdout)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_configured_e2e_is_required_by_check(self):
        self.contract({"verify": {"full": "true", "e2e": "true"}})
        self.run_script("run", "full")
        self.assertIn("no e2e receipt", self.run_script("check").stdout)
        self.run_script("run", "e2e")
        self.assertEqual(self.run_script("check").returncode, 0)
        self.assertEqual(self.run_script("check", "--no-e2e").returncode, 0)

    def test_environment_specific_e2e_needs_an_env(self):
        self.contract({"verify": {"full": "true"},
                       "run": {"environments": [{"name": "dev", "dev": "x", "e2e": "echo e2e-on-dev"},
                                                {"name": "demo", "dev": "y", "e2e": "echo e2e-on-demo"}]}})
        self.assertEqual(self.run_script("run", "e2e").returncode, 3)
        self.assertEqual(self.run_script("run", "e2e", "--env", "nope").returncode, 3)
        result = self.run_script("run", "e2e", "--env", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.run_script("show").stdout)["receipts"]["e2e"]["env"], "demo")

    def test_a_slow_run_outlives_the_caller_and_wait_picks_it_up(self):
        self.contract({"verify": {"full": "sleep 3 && echo slow but fine"}})
        first = self.run_script("run", "full", "--wait", "1")
        self.assertEqual(first.returncode, 4, first.stdout)
        self.assertIn("verify.py wait", first.stdout)
        again = self.run_script("run", "full", "--wait", "0")
        self.assertIn("already going", again.stdout)
        self.assertEqual(again.returncode, 4)
        waited = self.run_script("wait", "--wait", "30")
        self.assertEqual(waited.returncode, 0, waited.stdout)
        self.assertIn("full: passed", waited.stdout)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_wait_reports_a_failed_background_run(self):
        self.contract({"verify": {"full": "sleep 2 && exit 5"}})
        self.assertEqual(self.run_script("run", "full", "--wait", "0").returncode, 4)
        waited = self.run_script("wait", "--wait", "30")
        self.assertEqual(waited.returncode, 1)
        self.assertIn("full: failed", waited.stdout)

    def test_wait_without_a_run_exits_1(self):
        self.contract({"verify": {"full": "true"}})
        self.assertEqual(self.run_script("wait").returncode, 1)

    def test_mutation_refuses_to_start_without_a_passing_fast_or_full_receipt(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch mutation-ran"}}})

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: run fast or full first", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        self.assertNotIn("mutation", json.loads(self.run_script("show").stdout)["receipts"])

    def add_file(self, rel, text="x = 1\n"):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def branch_with(self, *files, message="change"):
        self.git("checkout", "-q", "-b", "feature")
        for rel in files:
            self.add_file(rel)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_mutation_is_skipped_when_only_test_files_or_excluded_files_changed(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch mutation-ran", "exclude": ["src/generated/*"]}}})
        self.branch_with("src/a.test.js", "src/b.spec.ts", "src/__tests__/c.js", "tests/d.py", "src/test_e.py",
                         "src/generated/f.js")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: skipped (no source files changed)", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "skipped")
        self.assertEqual(receipt["reason"], "no source files changed")

    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_script("run").returncode, 64)
        self.assertEqual(self.run_script("frobnicate").returncode, 64)
        self.assertEqual(self.run_script().returncode, 64)


if __name__ == "__main__":
    unittest.main()
