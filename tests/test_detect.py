import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "devflow", "skills", "onboard", "scripts", "detect.py")


def detect(repo):
    out = subprocess.run([sys.executable, SCRIPT, repo], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)

    def tearDown(self):
        os.environ.pop("DEVFLOW_HOME", None)
        self.tmp.cleanup()

    def write(self, rel, content):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)

    def test_empty_repo(self):
        report = detect(self.repo)
        self.assertIsNone(report["package_manager"])
        self.assertEqual(report["candidates"], {})
        self.assertIsNone(report["existing_contract"])
        self.assertEqual(report["default_branch"], "main")

    def test_pnpm_scripts_become_candidates_with_the_right_runner(self):
        self.write("pnpm-lock.yaml", "")
        self.write("package.json", json.dumps({"scripts": {"validate": "x", "lint": "y", "dev": "z", "dev:mock": "m"}}))
        report = detect(self.repo)
        self.assertEqual(report["package_manager"], "pnpm")
        self.assertEqual(report["candidates"]["aggregate"][0]["command"], "pnpm run validate")
        self.assertEqual(report["candidates"]["dev_mocked"][0]["script"], "dev:mock")

    def test_yarn_runner_has_no_run_keyword(self):
        self.write("yarn.lock", "")
        self.write("package.json", json.dumps({"scripts": {"test": "vitest"}}))
        self.assertEqual(detect(self.repo)["candidates"]["test"][0]["command"], "yarn test")

    def test_ci_scripts_keep_workflow_order(self):
        self.write("package.json", json.dumps({"scripts": {"a-test": "t", "b-lint": "l"}}))
        self.write(".github/workflows/ci.yml", "steps:\n  - run: npm run b-lint\n  - run: npm run a-test\n")
        ci = detect(self.repo)["ci"][0]
        self.assertEqual(ci["scripts_used_in_order"], ["b-lint", "a-test"])

    def test_docs_agent_files_and_existing_contract(self):
        self.write("CONTEXT.md", "# Terms")
        self.write("docs/decisions/0001.md", "x")
        self.write("AGENTS.md", "We track work in Jira, e.g. ABC-12.")
        os.symlink("AGENTS.md", os.path.join(self.repo, "CLAUDE.md"))
        home = os.path.join(self.tmp.name, "devflow-home")
        os.environ["DEVFLOW_HOME"] = home
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/pets.git"], check=True)
        contract = os.path.join(home, "contracts", "github.com", "acme", "pets.json")
        os.makedirs(os.path.dirname(contract))
        with open(contract, "w") as fh:
            fh.write("{}")
        report = detect(self.repo)
        self.assertEqual(report["docs"]["glossary"], ["CONTEXT.md"])
        self.assertEqual(report["docs"]["decisions"], ["docs/decisions"])
        self.assertEqual(report["agent_files"]["CLAUDE.md"]["symlink_to"], "AGENTS.md")
        self.assertEqual(report["tracker_hints"]["words_found"], ["jira"])
        self.assertEqual(report["tracker_hints"]["issue_keys"], ["ABC"])
        self.assertEqual(report["existing_contract"], contract)


if __name__ == "__main__":
    unittest.main()
