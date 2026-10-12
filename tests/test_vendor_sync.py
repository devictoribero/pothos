import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("vendor_sync", os.path.join(ROOT, "scripts", "vendor_sync.py"))
vendor_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor_sync)


class OverridesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "SKILL.md")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        with open(self.path, "w") as fh:
            fh.write(text)

    def read(self):
        with open(self.path) as fh:
            return fh.read()

    def test_model_invocable_drops_the_flag_and_keeps_the_body(self):
        self.write('---\nname: x\ndescription: "Build it."\ndisable-model-invocation: true\n---\n\nBody stays.\n')
        vendor_sync.apply_overrides(self.path, {"model_invocable": True, "triggers": "Use when asked to build."})
        self.assertEqual(self.read(), '---\nname: x\ndescription: "Build it. Use when asked to build."\n---\n\nBody stays.\n')

    def test_unquoted_descriptions_get_the_triggers_appended(self):
        self.write("---\nname: x\ndescription: Interview the user.\n---\nBody\n")
        vendor_sync.apply_overrides(self.path, {"triggers": "Use for new ideas."})
        self.assertIn("description: Interview the user. Use for new ideas.\n", self.read())

    def test_applying_twice_changes_nothing(self):
        self.write('---\nname: x\ndescription: "Build it."\ndisable-model-invocation: true\n---\nBody\n')
        entry = {"model_invocable": True, "triggers": "Use when asked to build."}
        vendor_sync.apply_overrides(self.path, entry)
        once = self.read()
        vendor_sync.apply_overrides(self.path, entry)
        self.assertEqual(self.read(), once)

    def test_entries_without_overrides_are_left_alone(self):
        self.write("---\nname: x\ndisable-model-invocation: true\n---\nBody\n")
        self.assertFalse(vendor_sync.apply_overrides(self.path, {}))
        self.assertIn("disable-model-invocation: true", self.read())


if __name__ == "__main__":
    unittest.main()
