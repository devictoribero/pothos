import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "retro_context.py")


class RetroContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "pothos-home")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        self.folder = os.path.join(self.home, "retros", "github.com", "acme", "shop")

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, cwd=None):
        result = subprocess.run([sys.executable, SCRIPT], cwd=cwd or self.repo, capture_output=True, text=True, input="",
                                env={**os.environ, "POTHOS_HOME": self.home})
        assert result.returncode == 0, result.stderr
        if not result.stdout.strip():
            return None
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        return payload["hookSpecificOutput"]["additionalContext"]

    def finding(self, slug, frontmatter):
        os.makedirs(self.folder, exist_ok=True)
        with open(os.path.join(self.folder, f"{slug}.md"), "w") as fh:
            fh.write(frontmatter + f"\n# {slug}\n")

    def test_outside_a_git_repository_prints_nothing(self):
        outside = os.path.join(self.tmp.name, "plain")
        os.makedirs(outside)
        self.assertIsNone(self.ctx(outside))

    def test_names_the_folder_and_the_format_without_a_contract(self):
        text = self.ctx()
        self.assertIn(f"under `{self.folder}` when the fix lands in this repository", text)
        self.assertIn("retro-findings.md", text)
        self.assertIn("Open findings for this repository: 0.", text)

    def test_counts_only_open_findings(self):
        self.finding("add-a-check", "---\nstatus: open\nseverity: high\n---\n")
        self.finding("fix-the-hook", "---\nstatus: open   # open | done\n---\n")
        self.finding("wait-for-upstream", "---\nstatus: deferred\n---\n")
        self.finding("already-fixed", "---\nstatus: done\n---\n")
        self.finding("no-frontmatter", "status: open\n")
        self.assertIn("Open findings for this repository: 2.", self.ctx())

    def test_the_format_file_ships_with_the_plugin(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "plugins", "pothos", "shared", "retro-findings.md")))


if __name__ == "__main__":
    unittest.main()
