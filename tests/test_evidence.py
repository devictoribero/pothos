import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "evidence", "scripts", "evidence.py")


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
        self.env = {**os.environ, "POTHOS_HOME": self.home}

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

    def write_file(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def mobile_contract(self, capture=True):
        app = {"name": "mobile", "path": "apps/mobile", "screenshots": "android-emulator",
               "ui": {"components": ["apps/mobile/components"], "tokens": ["apps/mobile/shared/theme"],
                      "screens": ["apps/mobile/features/*/screens", "apps/mobile/app/**/_layout.tsx"],
                      "locales": ["apps/mobile/shared/i18n/locales"], "languages": ["es", "ca"]}}
        if capture:
            app["capture"] = {"command": f"{sys.executable} capture.py"}
        self.contract({"run": {"apps": [app]}, "pr": {"base": "main"}})

    def test_screens_names_the_screens_the_branch_touches_and_the_importers_of_a_component(self):
        self.write_file("apps/mobile/features/pet/screens/PetScreen.tsx", "import { Button } from '@/primitives/Button/Button';\n")
        self.write_file("apps/mobile/features/home/screens/HomeScreen.tsx", "import { Card } from '@/primitives/Card/Card';\n")
        self.write_file("apps/mobile/components/primitives/Button/Button.tsx", "export const Button = 1;\n")
        self.write_file("apps/mobile/shared/i18n/locales/ca.ts", "export const ca = {};\n")
        self.commit("README.md")
        subprocess.run(["git", "-C", self.repo, "branch", "main"], check=True)
        self.write_file("apps/mobile/components/primitives/Button/Button.tsx", "export const Button = 2;\n")
        self.write_file("apps/mobile/components/primitives/Button/Button.spec.tsx", "test\n")
        self.write_file("apps/mobile/shared/i18n/locales/ca.ts", "export const ca = { a: 1 };\n")
        self.write_file("apps/mobile/app/(tabs)/_layout.tsx", "layout\n")
        self.commit("apps/mobile/features/pet/screens/other.txt")
        self.mobile_contract()
        result = self.run_script("screens")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("screen apps/mobile/app/(tabs)/_layout.tsx", out)
        self.assertIn("via apps/mobile/components/primitives/Button/Button.tsx: apps/mobile/features/pet/screens/PetScreen.tsx", out)
        self.assertNotIn("HomeScreen", out.split("via")[1].split("\n")[0])
        self.assertNotIn("Button.spec", out)
        self.assertIn("copy ca", out)
        self.assertIn("languages es,ca", out)
        self.assertIn(f"capture {sys.executable} capture.py (app mobile)", out)

    def test_screens_captures_only_the_first_language_when_no_copy_changed(self):
        self.commit("README.md")
        subprocess.run(["git", "-C", self.repo, "branch", "main"], check=True)
        self.commit("apps/mobile/features/pet/screens/PetScreen.tsx")
        self.mobile_contract(capture=False)
        out = self.run_script("screens").stdout
        self.assertIn("screen apps/mobile/features/pet/screens/PetScreen.tsx", out)
        self.assertIn("languages es (es always)", out)
        self.assertIn("capture none", out)

    def test_screens_says_none_when_the_branch_reaches_no_screen(self):
        self.commit("README.md")
        subprocess.run(["git", "-C", self.repo, "branch", "main"], check=True)
        self.commit("apps/mobile/features/pet/api/pet.ts")
        self.mobile_contract()
        out = self.run_script("screens").stdout
        self.assertTrue(out.startswith("none:"), out)

    def test_capture_runs_the_contract_command_and_keeps_before_and_after(self):
        self.write_file("capture.py", "\n".join([
            "import os, sys",
            "args = sys.argv[1:]",
            "out = args[args.index('--out') + 1]",
            "langs = args[args.index('--lang') + 1].split(',') if '--lang' in args else ['es']",
            "base = '--base' in args",
            "names = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i-1] not in ('--out', '--lang', '--base'))]",
            "os.makedirs(out, exist_ok=True)",
            "for n in names:",
            "    for l in langs:",
            "        for suffix in ([''] + (['-base'] if base else [])):",
            "            p = os.path.join(out, f'{n}-{l}{suffix}.png')",
            "            open(p, 'wb').write(b'\\x89PNG')",
            "            print(p)",
        ]) + "\n")
        self.mobile_contract()
        result = self.run_script("capture", "home", "--lang", "es,ca", "--base", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = self.run_script("dir").stdout.strip()
        names = sorted(os.path.basename(p) for p in result.stdout.split())
        self.assertEqual(names, ["after-home-ca.png", "after-home-es.png", "before-home-ca.png", "before-home-es.png"])
        for name in names:
            self.assertTrue(os.path.isfile(os.path.join(folder, name)), name)

    def test_capture_without_a_capture_command_exits_3(self):
        self.mobile_contract(capture=False)
        result = self.run_script("capture", "home")
        self.assertEqual(result.returncode, 3)
        self.assertIn("no capture command", result.stderr)

    def test_capture_reports_a_command_that_fails(self):
        self.write_file("capture.py", "import sys; sys.exit(7)\n")
        self.mobile_contract()
        result = self.run_script("capture", "home")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited 7", result.stderr)

    def test_plan_without_apps_reports_the_repository_and_flags_unknown(self):
        self.contract({"run": {"dev": "true"}})
        out = self.run_script("plan").stdout
        self.assertIn("app=(repository) screenshots=unknown", out)
        self.assertIn("plant audit", out)

    def test_serve_unknown_app_exits_3(self):
        self.contract({"run": {"apps": [{"name": "web", "path": "apps/web"}]}})
        self.assertEqual(self.run_script("serve", "--app", "admin").returncode, 3)

    def test_a_dev_command_that_backgrounds_the_server_and_exits_0_is_waited_for(self):
        port = free_port()
        self.contract({"run": {"dev": f"(sleep 1; exec {sys.executable} -m http.server {port} --bind 127.0.0.1) & exit 0",
                               "url": f"http://127.0.0.1:{port}/"}})
        result = self.run_script("serve", "--timeout", "20")
        self.assertEqual(result.returncode, 0, result.stderr)
        pid = result.stdout.split("pid=")[1].split()[0]
        self.assertEqual(self.run_script("stop", pid).returncode, 0)

    def test_stop_never_signals_the_callers_process_group(self):
        for pid in ("0", "1"):
            self.assertEqual(self.run_script("stop", pid).returncode, 64, pid)

    def test_each_app_keeps_its_own_server_log(self):
        self.contract({"run": {"apps": [{"name": "web", "path": "apps/web", "dev": "false", "url": "http://127.0.0.1:9/"},
                                        {"name": "admin", "path": "apps/admin", "dev": "false", "url": "http://127.0.0.1:9/"}]}})
        self.run_script("serve", "--app", "web", "--timeout", "3")
        self.run_script("serve", "--app", "admin", "--timeout", "3")
        folder = self.run_script("dir").stdout.strip()
        self.assertEqual(sorted(f for f in os.listdir(folder) if f.startswith("server-")), ["server-admin.log", "server-web.log"])

    def test_an_unreadable_contract_exits_2(self):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("{not json")
        result = self.run_script("plan")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def fake_tool(self, name, body):
        """A stand-in for gh or adb on PATH that logs its arguments to calls.log."""
        bin_dir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        path = os.path.join(bin_dir, name)
        with open(path, "w") as fh:
            fh.write(f"#!/bin/sh\necho \"{name} $*\" >> {self.tmp.name}/calls.log\n{body}\n")
        os.chmod(path, 0o755)
        self.env["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]

    def calls(self):
        with open(os.path.join(self.tmp.name, "calls.log")) as fh:
            return fh.read().splitlines()

    def screenshot(self, name="after home.png"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG fake")
        return path

    def test_upload_needs_the_contract_to_enable_it(self):
        self.contract({})
        self.fake_tool("gh", "exit 0")
        result = self.run_script("upload", self.screenshot())
        self.assertEqual(result.returncode, 3)
        self.assertIn("github-release", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "calls.log")))

    def test_upload_creates_the_month_release_and_names_assets_after_the_branch(self):
        self.contract({"pr": {"evidence": "github-release"}})
        self.fake_tool("gh", 'case "$1 $2" in "release view") exit 1;; "pr view") exit 1;; esac; exit 0')
        result = self.run_script("upload", self.screenshot())
        self.assertEqual(result.returncode, 0, result.stderr)
        tag = "pr-evidence-" + time.strftime("%Y-%m")
        self.assertEqual(result.stdout.strip(),
                         f"![feature-login-after-home.png](https://github.com/acme/shop/releases/download/{tag}/feature-login-after-home.png)")
        calls = self.calls()
        self.assertTrue(any(c.startswith(f"gh release create {tag} -R github.com/acme/shop --prerelease") for c in calls))
        self.assertTrue(any(c.startswith(f"gh release upload {tag} ") and "feature-login-after-home.png -R github.com/acme/shop --clobber" in c
                            for c in calls))
        self.assertFalse(any(c.startswith(("gh release delete", "gh release delete-asset")) for c in calls))

    def test_upload_names_assets_after_the_pull_request_and_links_videos(self):
        self.contract({"pr": {"evidence": "github-release"}})
        self.fake_tool("gh", 'case "$1 $2" in "pr view") echo 42;; esac; exit 0')
        result = self.run_script("upload", self.screenshot("flow.mp4"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("[pr42-flow.mp4](https://github.com/acme/shop/releases/download/"))
        self.assertFalse(any(c.startswith("gh release create") for c in self.calls()))

    def test_upload_reports_a_missing_file_before_calling_github(self):
        self.contract({"pr": {"evidence": "github-release"}})
        self.fake_tool("gh", "exit 0")
        result = self.run_script("upload", os.path.join(self.tmp.name, "nope.png"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no such file", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "calls.log")))

    def test_emu_saves_the_emulator_screenshot_in_the_branch_folder(self):
        self.fake_tool("adb", "printf '\\211PNG fake'")
        result = self.run_script("emu", "after home")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout.strip()
        self.assertTrue(out.endswith(os.path.join("feature-login", "after-home.png")))
        with open(out, "rb") as fh:
            self.assertTrue(fh.read().startswith(b"\x89PNG"))

    def test_emu_without_a_device_fails(self):
        self.fake_tool("adb", "echo 'error: no devices/emulators found' >&2; exit 1")
        result = self.run_script("emu", "after")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no devices", result.stderr)

    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_script().returncode, 64)
        self.assertEqual(self.run_script("shot", "http://x").returncode, 64)
        self.assertEqual(self.run_script("stop", "abc").returncode, 64)
        self.assertEqual(self.run_script("upload").returncode, 64)


if __name__ == "__main__":
    unittest.main()
