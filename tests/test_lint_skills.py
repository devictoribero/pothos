import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("lint_skills", os.path.join(ROOT, "scripts", "lint_skills.py"))
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)


class CheckHooksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = self.tmp.name
        os.makedirs(os.path.join(self.plugin, "hooks"))
        os.makedirs(os.path.join(self.plugin, "shared"))
        self.original = lint.PLUGIN
        lint.PLUGIN = self.plugin

    def tearDown(self):
        lint.PLUGIN = self.original
        self.tmp.cleanup()

    def hooks(self, data):
        with open(os.path.join(self.plugin, "hooks", "hooks.json"), "w") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))

    def hook(self, script, timeout=5):
        entry = {"type": "command", "command": f'python3 "${{CLAUDE_PLUGIN_ROOT}}/{script}"'}
        if timeout is not None:
            entry["timeout"] = timeout
        return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [entry]}]}}

    def test_the_real_hooks_file_is_clean(self):
        lint.PLUGIN = self.original
        self.assertEqual(lint.check_hooks(), [])

    def test_no_hooks_file_is_fine(self):
        self.assertEqual(lint.check_hooks(), [])

    def test_a_present_script_with_a_timeout_passes(self):
        open(os.path.join(self.plugin, "shared", "guard.py"), "w").close()
        self.hooks(self.hook("shared/guard.py"))
        self.assertEqual(lint.check_hooks(), [])

    def test_a_missing_script_and_a_missing_timeout_are_reported(self):
        self.hooks(self.hook("shared/missing.py", timeout=None))
        errors = lint.check_hooks()
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("PreToolUse names a missing script shared/missing.py", errors[0])
        self.assertIn("PreToolUse command has no timeout", errors[1])

    def test_invalid_json_is_one_error(self):
        self.hooks("{not json")
        errors = lint.check_hooks()
        self.assertEqual(len(errors), 1)
        self.assertIn("not valid JSON", errors[0])


if __name__ == "__main__":
    unittest.main()
