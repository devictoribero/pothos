import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "devflow", "scripts", "devflow-run.py")

FAKE_CLAUDE = """#!/bin/sh
# Stands in for claude -p: records its arguments and directory, prints one result event.
pwd > "$FAKE_LOG"
printf '%s\\n' "$@" >> "$FAKE_LOG"
echo '{"type":"result","result":"built 2 tickets; verified: full passed","total_cost_usd":1.5}'
"""


class DevflowRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(base, "shop")
        self.home = os.path.join(base, "home")
        self.bin = os.path.join(base, "bin")
        self.log = os.path.join(base, "claude.log")
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as fh:
            fh.write(FAKE_CLAUDE)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("remote", "add", "origin", "https://github.com/acme/shop.git")
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        os.makedirs(os.path.join(self.repo, ".scratch", "reminders", "issues"))
        self.env = {**os.environ, "DEVFLOW_HOME": self.home, "FAKE_LOG": self.log, "PATH": self.bin + os.pathsep + os.environ["PATH"]}

    def tearDown(self):
        subprocess.run(["git", "-C", self.repo, "worktree", "prune"], capture_output=True)
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, **data}, fh)

    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_without_contract_exits_2(self):
        self.assertEqual(self.run_script("spec", ".scratch/reminders/issues").returncode, 2)

    def test_repo_workflow_exits_3(self):
        self.contract({"workflow": "repo"})
        self.assertEqual(self.run_script("spec", ".scratch/reminders/issues").returncode, 3)

    def test_dry_run_names_the_feature_branch_after_the_tracker_folder(self):
        self.contract({"verify": {"full": "true"}, "pr": {"base": "main"}})
        plan = json.loads(self.run_script("spec", ".scratch/reminders/issues", "--dry-run").stdout)
        self.assertEqual(plan["branch"], "feature/reminders")
        self.assertEqual(plan["worktree"], os.path.join(os.path.dirname(self.repo), "shop-devflow", "reminders"))
        self.assertIn("/devflow:implement-spec", plan["command"])
        self.assertIn("Do not push", plan["command"])
        self.assertFalse(os.path.exists(plan["worktree"]))

    def test_open_pr_allows_a_draft_but_never_a_merge(self):
        self.contract({"verify": {"full": "true"}})
        plan = json.loads(self.run_script("ticket", ".scratch/reminders/issues/01-opt-in.md", "--open-pr", "--dry-run").stdout)
        self.assertEqual(plan["branch"], "ticket/01-opt-in")
        self.assertIn("open a draft pull request", plan["command"])
        self.assertIn("never merge it", plan["command"])

    def test_a_run_creates_the_worktree_runs_setup_and_records_the_result(self):
        self.contract({"verify": {"full": "true"}, "run": {"setup": "touch setup-ran"}})
        result = self.run_script("spec", ".scratch/reminders/issues")
        self.assertEqual(result.returncode, 0, result.stderr)
        worktree = os.path.join(os.path.dirname(self.repo), "shop-devflow", "reminders")
        self.assertTrue(os.path.exists(os.path.join(worktree, "setup-ran")))
        with open(self.log) as fh:
            logged = fh.read()
        self.assertTrue(logged.startswith(worktree))
        self.assertIn("/devflow:implement-spec", logged)
        status = self.run_script("status").stdout
        self.assertIn("done $1.50  feature/reminders  built 2 tickets; verified: full passed", status)

    def test_failed_setup_stops_before_the_session(self):
        self.contract({"verify": {"full": "true"}, "run": {"setup": "exit 7"}})
        result = self.run_script("spec", ".scratch/reminders/issues")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(os.path.exists(self.log))
        self.assertIn("setup-failed", self.run_script("status").stdout)

    def test_an_existing_worktree_is_never_reused(self):
        self.contract({"verify": {"full": "true"}})
        self.run_script("spec", ".scratch/reminders/issues")
        self.assertEqual(self.run_script("spec", ".scratch/reminders/issues").returncode, 3)

    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_script().returncode, 64)
        self.assertEqual(self.run_script("spec").returncode, 64)
        self.assertEqual(self.run_script("deploy", "x").returncode, 64)


if __name__ == "__main__":
    unittest.main()
