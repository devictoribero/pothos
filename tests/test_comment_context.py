import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "comment_context.py")


class CommentContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, cwd=None, stdin=""):
        result = subprocess.run([sys.executable, SCRIPT], cwd=cwd or self.repo, capture_output=True, text=True, input=stdin,
                                env={**os.environ, "POTHOS_HOME": os.path.join(self.tmp.name, "pothos-home")})
        assert result.returncode == 0, result.stderr
        if not result.stdout.strip():
            return None
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "SessionStart")
        return payload["hookSpecificOutput"]["additionalContext"]

    def test_outside_a_git_repository_prints_nothing(self):
        outside = os.path.join(self.tmp.name, "plain")
        os.makedirs(outside)
        self.assertIsNone(self.ctx(cwd=outside))

    def test_asks_for_the_callout_on_every_comment_without_needing_a_contract(self):
        text = self.ctx()
        self.assertIn("## Comments you post", text)
        self.assertIn("> [!NOTE]\n> 🤖 **<model> responding on behalf of @<login>**", text)
        self.assertIn("gh api user --jq .login", text)
        self.assertIn("even when the person dictated the words", text)
        self.assertIn("pull request bodies keep their own attribution", text)
        self.assertLess(len(text), 1200, f"the comment context is {len(text)} characters")

    def test_reads_the_session_directory_from_the_hook_event(self):
        outside = os.path.join(self.tmp.name, "plain")
        os.makedirs(outside)
        self.assertIsNotNone(self.ctx(cwd=outside, stdin=json.dumps({"cwd": self.repo})))


if __name__ == "__main__":
    unittest.main()
