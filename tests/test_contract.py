import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "contract.py")
TEMPLATE = os.path.join(ROOT, "plugins", "pothos", "templates", "contract.json")


def run(args, cwd, stdin=None):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, capture_output=True, text=True, input=stdin)


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "pothos-home")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "git@github.com-work:acme/shop.git"], check=True)
        os.environ["POTHOS_HOME"] = self.home
        self.expected = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")

    def tearDown(self):
        os.environ.pop("POTHOS_HOME", None)
        self.tmp.cleanup()

    def write(self, data):
        os.makedirs(os.path.dirname(self.expected), exist_ok=True)
        with open(self.expected, "w") as fh:
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
        self.write({"version": 1, "verify": {"full": "npm test"}, "docs": {"glossary": "GLOSSARY.md"}})
        self.assertEqual(run(["validate"], self.repo).returncode, 0)
        result = run(["validate", "--strict"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("GLOSSARY.md", result.stdout)

    def test_invalid_json_exits_1(self):
        os.makedirs(os.path.dirname(self.expected))
        with open(self.expected, "w") as fh:
            fh.write("{not json")
        self.assertEqual(run(["validate"], self.repo).returncode, 1)

    def test_path_is_keyed_by_remote_and_outside_the_repo(self):
        self.assertEqual(run(["path"], self.repo).stdout.strip(), self.expected)

    def test_remote_url_forms_share_one_key(self):
        sys.path.insert(0, os.path.dirname(SCRIPT))
        import contract
        for url in ["git@github.com:acme/shop.git", "https://github.com/acme/shop.git",
                    "ssh://git@github.com/acme/shop", "git@github.com-personal:acme/shop.git"]:
            self.assertEqual(contract.remote_key(url), "github.com/acme/shop", url)
        self.assertEqual(contract.remote_key("https://gitlab.example.com/group/sub/app.git"), "gitlab.example.com/group/sub/app")

    def test_worktrees_share_the_contract(self):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", self.repo, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        wt = os.path.join(self.tmp.name, "wt")
        subprocess.run(["git", "-C", self.repo, "worktree", "add", "-q", wt], check=True)
        self.assertEqual(run(["path"], wt).stdout.strip(), self.expected)

    def test_repo_without_remote_gets_a_local_key(self):
        subprocess.run(["git", "-C", self.repo, "remote", "remove", "origin"], check=True)
        path = run(["path"], self.repo).stdout.strip()
        self.assertIn(os.path.join("contracts", "local", "repo-"), path)

    def test_write_validates_and_saves_outside_the_repo(self):
        bad = run(["write"], self.repo, stdin=json.dumps({"version": 1}))
        self.assertEqual(bad.returncode, 1)
        self.assertFalse(os.path.exists(self.expected))
        good = run(["write"], self.repo, stdin=json.dumps({"version": 1, "verify": {"full": "npm test"}}))
        self.assertEqual(good.returncode, 0, good.stdout)
        self.assertTrue(os.path.isfile(self.expected))
        self.assertEqual(os.listdir(self.repo), [".git"])

    def test_repo_workflow_needs_no_verify(self):
        self.write({"version": 1, "workflow": "repo"})
        self.assertEqual(run(["validate", "--strict"], self.repo).returncode, 0)

    def test_pothos_workflow_requires_verify(self):
        self.write({"version": 1})
        result = run(["validate"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify", result.stdout)

    def test_environments_are_validated(self):
        self.write({"version": 1, "verify": {"full": "x"}, "run": {"environments": [{"name": "dev", "dev": "yarn local:dev", "note": "with the backend developer"}, {"name": "demo"}]}})
        result = run(["validate"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("run.environments[1]: missing required field 'dev'", result.stdout)

    def test_screenshots_and_apps_are_validated(self):
        self.write({"version": 1, "verify": {"full": "x"}, "run": {"screenshots": "android", "apps": [{"name": "web", "path": "apps/web"}, {"name": "api"}]}})
        result = run(["validate"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("run.screenshots: 'android' is not one of", result.stdout)
        self.assertIn("run.apps[1]: missing required field 'path'", result.stdout)
        strict = run(["validate", "--strict"], self.repo)
        self.assertIn("run.apps[0].path: path 'apps/web' does not exist", strict.stdout)

    def test_ui_section_is_validated(self):
        self.write({"version": 1, "verify": {"full": "x"}, "ui": {"components": ["src/ui"], "tokens": ["../theme.css"],
                                                                  "icons": "", "preview": {"url": "http://localhost:6006"}}})
        result = run(["validate"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ui.icons: must not be empty", result.stdout)
        self.assertIn("ui.preview: missing required field 'command'", result.stdout)
        strict = run(["validate", "--strict"], self.repo)
        self.assertIn("ui.components[0]: path 'src/ui' does not exist", strict.stdout)
        self.assertIn("ui.tokens[0]: '../theme.css' must be a path inside the repository", strict.stdout)

    def test_remote_key_edge_cases(self):
        sys.path.insert(0, os.path.dirname(SCRIPT))
        import contract
        self.assertEqual(contract.remote_key("git@github.company.com:o/r.git"), "github.company.com/o/r")
        self.assertEqual(contract.remote_key("HTTPS://github.com/Acme/Shop"), "github.com/acme/shop")
        self.assertEqual(contract.remote_key("git@gitlab.com-work:g/app.git"), "gitlab.com/g/app")
        for unsafe in ["../../../escaped", "../upstream", "/srv/git/repo.git", "file:///srv/x.git", "git@github.com:a/../b.git"]:
            self.assertIsNone(contract.remote_key(unsafe), unsafe)

    def test_path_remotes_share_a_contract_between_clones(self):
        upstream = os.path.join(self.tmp.name, "up.git")
        subprocess.run(["git", "init", "-q", "--bare", upstream], check=True)
        paths = []
        for name in ("clone-a", "clone-b"):
            clone = os.path.join(self.tmp.name, name)
            subprocess.run(["git", "init", "-q", clone], check=True)
            subprocess.run(["git", "-C", clone, "remote", "add", "origin", "../up.git"], check=True)
            paths.append(run(["path"], clone).stdout.strip())
        self.assertEqual(paths[0], paths[1])
        self.assertIn(os.path.join("contracts", "local", "up-"), paths[0])

    def test_folders_created_later_need_not_exist_but_must_stay_inside(self):
        ok = run(["write"], self.repo, stdin=json.dumps({"version": 1, "verify": {"full": "x"}, "tracker": {"kind": "local", "path": ".scratch"}, "docs": {"prd": "docs/prd"}}))
        self.assertEqual(ok.returncode, 0, ok.stdout)
        for bad in ["/etc/hosts", "../outside"]:
            result = run(["write"], self.repo, stdin=json.dumps({"version": 1, "verify": {"full": "x"}, "docs": {"glossary": bad}}))
            self.assertEqual(result.returncode, 1, bad)
            self.assertIn("inside the repository", result.stdout)

    def test_template_has_every_schema_field(self):
        with open(TEMPLATE) as fh:
            template = json.load(fh)
        schema_path = os.path.join(ROOT, "plugins", "pothos", "shared", "contract.schema.json")
        with open(schema_path) as fh:
            schema = json.load(fh)
        self.assertEqual(set(template) - {"$schema"}, set(schema["properties"]) - {"$schema"})
        for key, child in schema["properties"].items():
            if child.get("type") == "object":
                self.assertEqual(set(template[key]), set(child["properties"]), key)


if __name__ == "__main__":
    unittest.main()
