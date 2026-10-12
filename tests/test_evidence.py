import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "devflow", "skills", "evidence", "scripts", "evidence.py")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "feature/login", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        self.env = {**os.environ, "DEVFLOW_HOME": self.home}

    def tearDown(self):
        self.tmp.cleanup()

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, "verify": {"full": "true"}, **data}, fh)

    def run_script(self, *args, timeout=60):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=timeout)

    def test_dir_is_per_branch_outside_the_repo(self):
        out = self.run_script("dir").stdout.strip()
        self.assertEqual(out, os.path.join(self.home, "evidence", "github.com", "acme", "shop", "feature-login"))
        self.assertTrue(os.path.isdir(out))
        self.assertFalse(out.startswith(self.repo))

    def test_serve_without_contract_exits_2(self):
        self.assertEqual(self.run_script("serve").returncode, 2)

    def test_serve_without_dev_command_exits_3(self):
        self.contract({})
        self.assertEqual(self.run_script("serve").returncode, 3)

    def test_serve_unknown_environment_exits_3(self):
        self.contract({"run": {"dev": "true", "url": "http://127.0.0.1:1", "environments": [{"name": "dev", "dev": "true"}]}})
        self.assertEqual(self.run_script("serve", "--env", "prod").returncode, 3)

    def test_serve_waits_for_the_url_then_stop_kills_it(self):
        port = free_port()
        self.contract({"run": {"dev": f"sleep 1 && {sys.executable} -m http.server {port} --bind 127.0.0.1",
                               "url": f"http://127.0.0.1:{port}/"}})
        result = self.run_script("serve", "--timeout", "30")
        self.assertEqual(result.returncode, 0, result.stderr)
        pid = result.stdout.split("pid=")[1].split()[0]
        self.assertEqual(self.run_script("serve").stdout.split()[0], "already-running")
        self.assertEqual(self.run_script("stop", pid).returncode, 0)

    def test_serve_reports_a_dev_command_that_dies(self):
        self.contract({"run": {"dev": "echo cannot-start; exit 4", "url": f"http://127.0.0.1:{free_port()}/"}})
        result = self.run_script("serve", "--timeout", "20")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited with 4", result.stderr)

    def commit(self, rel):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        git = ["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", rel], check=True)

    def test_plan_lists_only_the_apps_the_branch_touches(self):
        self.commit("README.md")
        subprocess.run(["git", "-C", self.repo, "branch", "main"], check=True)
        self.commit("apps/mobile/screen.tsx")
        self.contract({"run": {"apps": [{"name": "web", "path": "apps/web", "screenshots": "web"},
                                        {"name": "mobile", "path": "apps/mobile", "screenshots": "none"}]},
                       "pr": {"base": "main"}})
        out = self.run_script("plan").stdout
        self.assertIn("app=mobile screenshots=none", out)
        self.assertNotIn("app=web", out)

    def test_plan_without_apps_reports_the_repository_and_flags_unknown(self):
        self.contract({"run": {"dev": "true"}})
        out = self.run_script("plan").stdout
        self.assertIn("app=(repository) screenshots=unknown", out)
        self.assertIn("onboard audit", out)

    def test_serve_unknown_app_exits_3(self):
        self.contract({"run": {"apps": [{"name": "web", "path": "apps/web"}]}})
        self.assertEqual(self.run_script("serve", "--app", "admin").returncode, 3)

    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_script().returncode, 64)
        self.assertEqual(self.run_script("shot", "http://x").returncode, 64)
        self.assertEqual(self.run_script("stop", "abc").returncode, 64)


if __name__ == "__main__":
    unittest.main()
