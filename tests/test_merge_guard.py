import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "merge_guard.py")


class MergeGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "feature", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self, command, stdin=None):
        event = stdin if stdin is not None else json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": self.repo})
        return subprocess.run([sys.executable, SCRIPT], input=event, capture_output=True, text=True,
                              env={**os.environ, "POTHOS_HOME": self.home})

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, **data}, fh)

    def test_merging_is_blocked_even_inside_a_compound_command(self):
        for command in ("gh pr merge 7 --squash", "git push && gh  pr merge 7",
                        "gh api -X PUT repos/acme/shop/pulls/7/merge -f merge_method=squash",
                        "gh api --method PUT repos/acme/shop/pulls/7/merge",
                        'N=$(gh pr view --json number -q .number); gh api -X PUT "repos/acme/shop/pulls/$N/merge"',
                        "gh api -X PUT repos/acme/shop/pulls/${PR}/merge",
                        "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
                        "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
                        "curl -X PUT -H \"Authorization: token $(gh auth token)\" https://api.github.com/repos/acme/shop/pulls/7/merge",
                        "gh alias set m 'pr merge' && gh m 7"):
            result = self.guard(command)
            self.assertEqual(result.returncode, 2, command)
            self.assertIn("agents never merge a pull request", result.stderr)

    def test_pushing_to_the_base_branch_is_blocked(self):
        for command in ("git push origin HEAD:main", "git push origin fix-total:main", "git push -f origin main",
                        "git push origin refs/heads/fix-total:refs/heads/main",
                        "git checkout main && git merge fix-total && git push origin main"):
            result = self.guard(command)
            self.assertEqual(result.returncode, 2, command)
            self.assertIn("agents never push to the base branch", result.stderr)

    def test_a_bare_push_from_the_base_branch_is_blocked(self):
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", "main"], check=True)
        self.assertEqual(self.guard("git push").returncode, 2)
        self.assertEqual(self.guard("git push -u origin").returncode, 2)
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", "fix-total"], check=True)
        self.assertEqual(self.guard("git push").returncode, 0)

    def test_the_base_branch_comes_from_the_contract(self):
        self.contract({"pr": {"base": "develop"}})
        self.assertEqual(self.guard("git push origin HEAD:develop").returncode, 2)
        self.assertEqual(self.guard("git push origin HEAD:main").returncode, 0)

    def test_adding_the_default_label_is_blocked(self):
        for command in ("gh pr edit 7 --add-label auto-merge", "gh pr create --label auto-merge --fill",
                        "gh api repos/acme/shop/issues/7/labels -f 'labels[]=auto-merge'",
                        "gh pr edit 7 --add-label Auto-Merge"):
            self.assertEqual(self.guard(command).returncode, 2, command)

    def test_the_contract_label_is_blocked_too(self):
        self.contract({"pr": {"auto_merge": {"label": "ship-it"}}})
        self.assertEqual(self.guard("gh pr edit 7 --add-label ship-it").returncode, 2)
        self.assertEqual(self.guard("gh pr edit 7 --add-label SHIP-IT").returncode, 2)

    def test_everything_else_passes(self):
        for command in ("ls", "gh pr view 7", "gh pr edit 7 --add-label bug", "gh pr edit 7 --add-label auto-merge-later",
                        "git merge main", "python3 merge_gate.py merge 7", "gh label create auto-merge",
                        "gh api repos/acme/shop/pulls/7/merges", "gh pr view 7 --json mergedAt",
                        "git push -u origin fix-total", "git push origin main:fix-total", "git push origin HEAD",
                        "git pull origin main", "curl https://api.github.com/repos/acme/shop/pulls/7",
                        "gh alias set co 'pr checkout'"):
            self.assertEqual(self.guard(command).returncode, 0, command)

    def test_bad_input_never_blocks(self):
        self.assertEqual(self.guard(None, stdin="not json").returncode, 0)


if __name__ == "__main__":
    unittest.main()
