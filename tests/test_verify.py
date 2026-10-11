import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "devflow", "skills", "verify", "scripts", "verify.py")


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("remote", "add", "origin", "https://github.com/acme/shop.git")
        self.commit("first")
        self.env = {**os.environ, "DEVFLOW_HOME": self.home}

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

    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_script("run").returncode, 64)
        self.assertEqual(self.run_script("frobnicate").returncode, 64)
        self.assertEqual(self.run_script().returncode, 64)


if __name__ == "__main__":
    unittest.main()
