import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "self_update.py")
PLUGIN = os.path.join("plugins", "pothos")


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class SelfUpdateTest(unittest.TestCase):
    """A marketplace checkout cloned from a bare origin, with the hook script inside its plugin directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.origin = os.path.join(self.tmp.name, "origin.git")
        self.upstream = os.path.join(self.tmp.name, "upstream")
        self.checkout = os.path.join(self.tmp.name, "checkout")
        git(self.tmp.name, "init", "--quiet", "--bare", "--initial-branch=main", self.origin)
        git(self.tmp.name, "clone", "--quiet", self.origin, self.upstream)
        git(self.upstream, "checkout", "--quiet", "-b", "main")
        self.write(self.upstream, os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), '{"name": "pothos"}\n')
        self.write(self.upstream, os.path.join(PLUGIN, "skills", "a.md"), "first\n")
        os.makedirs(os.path.join(self.upstream, PLUGIN, "shared"))
        shutil.copy(SCRIPT, os.path.join(self.upstream, PLUGIN, "shared", "self_update.py"))
        self.commit(self.upstream, "initial")
        git(self.upstream, "push", "--quiet", "origin", "main")
        git(self.tmp.name, "clone", "--quiet", self.origin, self.checkout)
        self.hook = os.path.join(self.checkout, PLUGIN, "shared", "self_update.py")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, repo, path, text):
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)

    def read(self, path):
        with open(os.path.join(self.checkout, path)) as fh:
            return fh.read()

    def commit(self, repo, message):
        git(repo, "add", "-A")
        git(repo, "commit", "--quiet", "-m", message)

    def merge_upstream(self, text="second\n"):
        """A pull request merges into origin's main, changing one skill file."""
        self.write(self.upstream, os.path.join(PLUGIN, "skills", "a.md"), text)
        self.commit(self.upstream, "merged pull request")
        git(self.upstream, "push", "--quiet", "origin", "main")
        return git(self.upstream, "rev-parse", "HEAD")

    def run_hook(self, *args, script=None):
        result = subprocess.run([sys.executable, script or self.hook, *args], input="{}", capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def head(self):
        return git(self.checkout, "rev-parse", "HEAD")

    def test_fast_forwards_a_checkout_on_the_default_branch(self):
        merged = self.merge_upstream()
        self.run_hook("--run")
        self.assertEqual(self.head(), merged)
        self.assertEqual(self.read(os.path.join(PLUGIN, "skills", "a.md")), "second\n")

    def test_hook_mode_returns_at_once_and_updates_in_the_background(self):
        merged = self.merge_upstream()
        self.run_hook()
        deadline = time.time() + 20
        while self.head() != merged and time.time() < deadline:
            time.sleep(0.1)
        self.assertEqual(self.head(), merged)

    def test_leaves_a_feature_branch_alone(self):
        git(self.checkout, "checkout", "--quiet", "-b", "feature", "--track", "origin/main")
        before = self.head()
        self.merge_upstream()
        self.run_hook("--run")
        self.assertEqual(self.head(), before)

    def test_keeps_uncommitted_changes_to_files_the_update_does_not_touch(self):
        self.write(self.checkout, os.path.join(PLUGIN, "skills", "b.md"), "work in progress\n")
        merged = self.merge_upstream()
        self.run_hook("--run")
        self.assertEqual(self.head(), merged)
        self.assertEqual(self.read(os.path.join(PLUGIN, "skills", "b.md")), "work in progress\n")

    def test_skips_when_an_uncommitted_change_touches_an_updated_file(self):
        self.write(self.checkout, os.path.join(PLUGIN, "skills", "a.md"), "work in progress\n")
        before = self.head()
        self.merge_upstream()
        self.run_hook("--run")
        self.assertEqual(self.head(), before)
        self.assertEqual(self.read(os.path.join(PLUGIN, "skills", "a.md")), "work in progress\n")

    def test_never_merges_into_a_default_branch_with_local_commits(self):
        self.write(self.checkout, os.path.join(PLUGIN, "skills", "c.md"), "local\n")
        self.commit(self.checkout, "local commit")
        before = self.head()
        self.merge_upstream()
        self.run_hook("--run")
        self.assertEqual(self.head(), before)

    def test_does_nothing_for_a_copy_outside_git(self):
        copy = os.path.join(self.tmp.name, "cache", "pothos", "shared")
        os.makedirs(copy)
        shutil.copy(SCRIPT, copy)
        self.run_hook("--run", script=os.path.join(copy, "self_update.py"))


if __name__ == "__main__":
    unittest.main()
