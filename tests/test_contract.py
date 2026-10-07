import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "development-flow", "shared", "contract.py")
TEMPLATE = os.path.join(ROOT, "plugins", "development-flow", "templates", "contract.json")


def run(args, cwd):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, capture_output=True, text=True)


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        os.makedirs(os.path.join(self.repo, ".agents"), exist_ok=True)
        with open(os.path.join(self.repo, ".agents", "contract.json"), "w") as fh:
            json.dump(data, fh)

    def test_missing_contract_exits_2(self):
        self.assertEqual(run(["locate"], self.repo).returncode, 2)
        self.assertEqual(run(["get", "verify.full"], self.repo).returncode, 2)
        self.assertEqual(run(["validate"], self.repo).returncode, 2)

    def test_minimal_contract_is_valid(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        result = run(["validate", "--strict"], self.repo)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_get_prints_strings_raw_and_others_as_json(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "review": {"skills": ["a"]}})
        self.assertEqual(run(["get", "verify.full"], self.repo).stdout.strip(), "npm test")
        self.assertEqual(run(["get", "review.skills"], self.repo).stdout.strip(), '["a"]')

    def test_get_unset_key_exits_3(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        self.assertEqual(run(["get", "verify.fast"], self.repo).returncode, 3)

    def test_locate_works_from_a_subdirectory(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        sub = os.path.join(self.repo, "src", "deep")
        os.makedirs(sub)
        self.assertEqual(run(["get", "verify.full"], sub).stdout.strip(), "npm test")

    def test_schema_errors_are_reported(self):
        self.write({"version": 2, "verify": {"fast": ""}, "extra": True, "tracker": {"kind": "trello"}})
        result = run(["validate"], self.repo)
        self.assertEqual(result.returncode, 1)
        for expected in ["version", "missing required field 'full'", "must not be empty", "unknown field 'extra'", "trello"]:
            self.assertIn(expected, result.stdout)

    def test_strict_reports_missing_paths(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "docs": {"context": "CONTEXT.md"}})
        self.assertEqual(run(["validate"], self.repo).returncode, 0)
        result = run(["validate", "--strict"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("CONTEXT.md", result.stdout)

    def test_invalid_json_exits_1(self):
        os.makedirs(os.path.join(self.repo, ".agents"))
        with open(os.path.join(self.repo, ".agents", "contract.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(run(["validate"], self.repo).returncode, 1)

    def test_template_has_every_schema_field(self):
        with open(TEMPLATE) as fh:
            template = json.load(fh)
        schema_path = os.path.join(ROOT, "plugins", "development-flow", "shared", "contract.schema.json")
        with open(schema_path) as fh:
            schema = json.load(fh)
        self.assertEqual(set(template) - {"$schema"}, set(schema["properties"]) - {"$schema"})
        for key, child in schema["properties"].items():
            if child.get("type") == "object":
                self.assertEqual(set(template[key]), set(child["properties"]), key)


if __name__ == "__main__":
    unittest.main()
