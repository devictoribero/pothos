import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "onboard", "scripts", "detect.py")


def detect(repo):
    out = subprocess.run([sys.executable, SCRIPT, repo], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)

    def tearDown(self):
        os.environ.pop("POTHOS_HOME", None)
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

    def test_environment_variants(self):
        self.write("yarn.lock", "")
        self.write("package.json", json.dumps({"scripts": {"local:dev": "a", "local:demo": "b", "local:mock": "c", "dev": "d"}}))
        variants = detect(self.repo)["environment_variants"]
        self.assertEqual([v["name"] for v in variants], ["dev", "demo"])
        self.assertEqual(variants[1]["command"], "yarn local:demo")

    def test_npm_test_shorthand_in_ci(self):
        self.write("package.json", json.dumps({"scripts": {"lint": "l", "test": "t", "build": "b"}}))
        self.write(".github/workflows/ci.yml", "steps:\n  - run: npm run lint\n  - run: npm test\n  - run: npm run build\n")
        self.assertEqual(detect(self.repo)["ci"][0]["scripts_used_in_order"], ["lint", "test", "build"])

    def test_default_branch_is_not_the_current_feature_branch(self):
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", "feature/x"], check=True)
        self.assertEqual(detect(self.repo)["default_branch"], "main")
        subprocess.run(["git", "-C", self.repo, "branch", "-q", "-m", "main", "trunk"], check=True)
        self.assertIsNone(detect(self.repo)["default_branch"])

    def test_broken_package_json_is_reported_not_fatal(self):
        self.write("package.json", '{"scripts": {"test": "t",}}')
        report = detect(self.repo)
        self.assertIn("package_json_error", report)
        bom = os.path.join(self.repo, "package.json")
        with open(bom, "w", encoding="utf-8-sig") as fh:
            fh.write(json.dumps({"scripts": {"test": "t"}}))
        self.assertIn("test", detect(self.repo)["candidates"])

    def test_e2e_config_in_a_monorepo_app(self):
        self.write("apps/web/playwright.config.ts", "")
        self.write("node_modules/x/cypress.config.js", "")
        report = detect(self.repo)
        self.assertEqual(report["e2e_tools"], ["playwright"])
        self.assertEqual(report["e2e_config_paths"], ["apps/web/playwright.config.ts"])

    def test_monorepo_apps_with_start_commands_and_kind(self):
        self.write("pnpm-lock.yaml", "")
        self.write("pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n")
        self.write("package.json", '{"scripts": {}}')
        self.write("apps/web/package.json", '{"name": "@acme/web", "scripts": {"dev": "next dev"}, "dependencies": {"next": "1"}}')
        self.write("apps/mobile/package.json", '{"name": "@acme/mobile", "scripts": {"start": "expo start"}, "dependencies": {"expo": "1"}}')
        self.write("apps/api/package.json", '{"name": "@acme/api", "scripts": {"dev": "nest start"}}')
        apps = {a["path"]: a for a in detect(self.repo)["apps"]}
        self.assertEqual(apps["apps/web"]["kind"], "web")
        self.assertEqual(apps["apps/mobile"]["kind"], "mobile")
        self.assertEqual(apps["apps/api"]["kind"], "other")
        self.assertEqual(apps["apps/web"]["dev_scripts"][0]["command"], "pnpm --filter @acme/web dev")

    def test_single_package_repo_has_no_apps(self):
        self.write("package.json", '{"scripts": {"dev": "vite"}}')
        self.assertEqual(detect(self.repo)["apps"], [])

    def test_yarn_runner_has_no_run_keyword(self):
        self.write("yarn.lock", "")
        self.write("package.json", json.dumps({"scripts": {"test": "vitest"}}))
        self.assertEqual(detect(self.repo)["candidates"]["test"][0]["command"], "yarn test")

    def test_ci_scripts_keep_workflow_order(self):
        self.write("package.json", json.dumps({"scripts": {"a-test": "t", "b-lint": "l"}}))
        self.write(".github/workflows/ci.yml", "steps:\n  - run: npm run b-lint\n  - run: npm run a-test\n")
        ci = detect(self.repo)["ci"][0]
        self.assertEqual(ci["scripts_used_in_order"], ["b-lint", "a-test"])

    def test_ci_setup_steps_before_the_first_check(self):
        self.write("package.json", json.dumps({"scripts": {"validate": "v", "db:generate": "g"}}))
        self.write(".github/workflows/ci.yml", "steps:\n  - uses: actions/checkout@v4\n  - run: pnpm install --frozen-lockfile\n"
                   "  - run: pnpm --filter api db:generate\n  - run: echo hello\n  - run: pnpm run validate\n  - run: pnpm run generate:after\n")
        ci = detect(self.repo)["ci"][0]
        self.assertEqual(ci["setup_steps"], ["pnpm install --frozen-lockfile", "pnpm --filter api db:generate"])
        self.assertEqual(detect(self.repo)["candidates"]["setup"][0]["script"], "db:generate")

    def test_docs_agent_files_and_existing_contract(self):
        self.write("CONTEXT.md", "# Terms")
        self.write("docs/decisions/0001.md", "x")
        self.write("AGENTS.md", "We track work in Jira, e.g. ABC-12.")
        os.symlink("AGENTS.md", os.path.join(self.repo, "CLAUDE.md"))
        home = os.path.join(self.tmp.name, "pothos-home")
        os.environ["POTHOS_HOME"] = home
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
