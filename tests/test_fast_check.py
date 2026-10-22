import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugins", "pothos", "shared"))
import fast_check  # noqa: E402

SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "fast_check.py")


class FastCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, data):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(json.dumps(data) if isinstance(data, dict) else data)

    def test_a_root_check_fast_script_wins_and_names_the_contract_drift(self):
        self.write("package.json", {"scripts": {"check:fast": "turbo run lint type-check"}})
        self.write("pnpm-lock.yaml", "")
        pick = fast_check.discover(self.repo, {"verify": {"fast": "pnpm run type-check", "full": "pnpm run validate"}})
        self.assertEqual(pick["command"], "pnpm run check:fast")
        self.assertEqual(pick["source"], "script")
        self.assertIn("declares `check:fast`", pick["why"])
        self.assertEqual(pick["drift"], "pnpm run type-check")

    def test_a_matching_contract_fast_is_not_drift(self):
        self.write("package.json", {"scripts": {"check:fast": "x"}, "packageManager": "yarn@4.1.0"})
        pick = fast_check.discover(self.repo, {"verify": {"fast": "yarn check:fast", "full": "yarn validate"}})
        self.assertEqual(pick["command"], "yarn check:fast")
        self.assertIsNone(pick["drift"])

    def test_the_contract_fast_comes_second(self):
        self.write("package.json", {"scripts": {"lint": "eslint ."}})
        pick = fast_check.discover(self.repo, {"verify": {"fast": "npm run lint", "full": "npm test"}})
        self.assertEqual(pick["command"], "npm run lint")
        self.assertEqual(pick["source"], "contract")
        self.assertEqual(pick["fallback"], [])

    def test_fallback_lists_each_workspace_with_its_own_scripts(self):
        self.write("package.json", {"name": "shop", "private": True, "workspaces": ["apps/*"],
                                    "scripts": {"validate": "turbo run lint test type-check"}})
        self.write("pnpm-lock.yaml", "")
        self.write("apps/api/package.json", {"name": "@acme/api", "scripts": {"lint": "eslint .", "test:unit": "jest",
                                                                             "type-check": "tsc --noEmit"}})
        self.write("apps/web/package.json", {"name": "@acme/web", "devDependencies": {"vitest": "1"},
                                             "scripts": {"lint": "eslint .", "test": "vitest run", "typecheck": "tsc"}})
        self.write("apps/docs/package.json", {"name": "docs", "scripts": {"build": "astro build"}})
        pick = fast_check.discover(self.repo, {"verify": {"full": "pnpm run validate"}})
        self.assertIsNone(pick["command"])
        self.assertEqual(pick["source"], "fallback")
        self.assertEqual([s["path"] for s in pick["fallback"]], ["apps/api", "apps/web"])
        api, web = pick["fallback"]
        self.assertEqual(api["lint"], "pnpm --filter @acme/api lint")
        self.assertEqual(api["unit"], "pnpm --filter @acme/api test:unit")
        self.assertTrue(api["jest"])
        self.assertEqual(api["typecheck"], "pnpm --filter @acme/api type-check")
        self.assertFalse(web["jest"])
        self.assertEqual(web["typecheck"], "pnpm --filter @acme/web typecheck")
        lines = fast_check.fallback_lines(pick["fallback"])
        self.assertIn("all of these even after one fails", lines[0])
        self.assertIn("`pnpm --filter @acme/api test:unit -- --findRelatedTests <files>` (jest)", lines[1])
        self.assertIn("`pnpm --filter @acme/web test` (not jest", lines[2])

    def test_alike_packages_share_one_fallback_line(self):
        self.write("package.json", {"name": "shop", "workspaces": ["apps/*"]})
        for app in ("api", "mobile", "web"):
            self.write(f"apps/{app}/package.json", {"name": app, "scripts": {"lint": "eslint .", "test:unit": "jest", "type-check": "tsc"}})
        self.write("apps/docs/package.json", {"name": "docs", "scripts": {"lint": "eslint ."}})
        lines = fast_check.fallback_lines(fast_check.discover(self.repo, {})["fallback"])
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[1].startswith("- `apps/api`, `apps/mobile`, `apps/web` (shown for `apps/api`): "
                                            "`npm run lint --workspace apps/api -- <files>`"), lines[1])
        self.assertTrue(lines[2].startswith("- `apps/docs`: `npm run lint --workspace apps/docs -- <files>`"), lines[2])

    def test_pnpm_workspace_yaml_is_read(self):
        self.write("package.json", {"name": "shop"})
        self.write("pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n  - apps/mobile\n")
        self.write("packages/core/package.json", {"name": "core", "scripts": {"test": "jest"}})
        self.write("apps/mobile/package.json", {"name": "mobile", "scripts": {"lint": "eslint ."}})
        pick = fast_check.discover(self.repo, {"verify": {"full": "pnpm test"}})
        self.assertEqual([s["path"] for s in pick["fallback"]], ["packages/core", "apps/mobile"])
        self.assertEqual(pick["fallback"][0]["unit"], "pnpm --filter core test")

    def test_a_single_package_falls_back_to_its_root_scripts(self):
        self.write("package.json", {"name": "ledger", "scripts": {"lint": "eslint .", "test:unit": "jest", "type-check": "tsc"}})
        self.write("package-lock.json", "{}")
        pick = fast_check.discover(self.repo, {"verify": {"full": "npm run validate"}})
        self.assertEqual(pick["fallback"], [{"path": ".", "name": "ledger", "lint": "npm run lint", "unit": "npm run test:unit",
                                             "jest": True, "typecheck": "npm run type-check",
                                             "scripts": ["lint", "test:unit", "type-check"]}])

    def test_nothing_to_run_is_reported_as_none(self):
        self.write("package.json", {"name": "site", "scripts": {"build": "astro build"}})
        pick = fast_check.discover(self.repo, {"verify": {"full": "npm run build"}})
        self.assertEqual(pick["source"], "none")
        self.assertEqual(pick["fallback"], [])
        self.assertEqual(fast_check.discover(self.repo, {})["source"], "none")  # no package.json at all

    def test_cli_prints_the_pick(self):
        self.write("package.json", {"scripts": {"check:fast": "x"}})
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        out = subprocess.run([sys.executable, SCRIPT, self.repo], capture_output=True, text=True, check=True,
                             env={**os.environ, "POTHOS_HOME": os.path.join(self.repo, ".home")})
        self.assertEqual(json.loads(out.stdout)["command"], "npm run check:fast")


if __name__ == "__main__":
    unittest.main()
