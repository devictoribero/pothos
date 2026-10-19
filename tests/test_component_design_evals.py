import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "plugins", "pothos", "skills", "component-design")
REUSE = os.path.join(SKILL, "evals", "reuse_check.py")
FIXTURE = os.path.join(SKILL, "evals", "fixture.py")
TOOLCHAIN = os.path.join(SKILL, "scripts", "toolchain.sh")


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class ReuseCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = os.path.join(self.tmp.name, "fixture")
        write(self.fixture, "src/ui/Button/Button.tsx", "export function Button() {}\n")
        write(self.fixture, "src/ui/TextField/TextField.tsx", "export function TextField() {}\n")
        write(self.fixture, "src/ui/index.ts", "export { Button } from './Button/Button';\nexport { TextField } from './TextField/TextField';\n")
        write(self.fixture, "src/hooks/useControllableState.ts", "export function useControllableState() {}\n")
        write(self.fixture, "package.json", "{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, name):
        dest = os.path.join(self.tmp.name, name)
        shutil.copytree(self.fixture, dest)
        return dest

    def check(self, project):
        out = subprocess.run([sys.executable, REUSE, self.fixture, project, "--components", "Button,TextField",
                              "--hooks", "useControllableState", "--json"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_scores_2_when_the_feature_imports_the_primitives_and_the_hook(self):
        p = self.project("a")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n")
        write(p, "src/features/projects/NameEditor.test.tsx", "<button>tests are not scored</button>\n")
        write(p, "src/features/projects/example/Usage.tsx", "<input />\n")
        result = self.check(p)
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["hooks"], {"useControllableState": True})
        self.assertEqual(result["raw_controls"], {})
        self.assertEqual(result["code_files"], ["src/features/projects/NameEditor.tsx"])

    def test_scores_0_when_the_feature_rebuilds_its_own_controls(self):
        p = self.project("b")
        write(p, "src/features/projects/NameEditor.tsx",
              "export function NameEditor() { return <><button /><input /><input /></>; }\n")
        write(p, "src/features/projects/Button.tsx", "export function Button() {}\n")
        write(p, "src/hooks/useControllableValue.ts", "export function useControllableValue() {}\n")
        result = self.check(p)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["raw_controls"], {"button": 1, "input": 2})
        self.assertEqual(result["second_copies"], ["src/features/projects/Button.tsx", "src/hooks/useControllableValue.ts"])

    def test_scores_1_when_some_primitives_are_reused_and_the_rest_rebuilt(self):
        p = self.project("c")
        write(p, "src/features/projects/NameEditor.tsx", "import { Button } from '../../ui';\nexport const field = <input />;\n")
        result = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["components"], {"Button": True, "TextField": False})
        self.assertEqual(result["raw_controls"], {"input": 1})

    def test_a_second_copy_in_the_shared_folder_costs_the_score_even_with_imports(self):
        p = self.project("d")
        write(p, "src/features/projects/NameEditor.tsx", "import { Button, TextField } from '../../ui';\n")
        write(p, "src/ui/IconButton/IconButton.tsx", "export function IconButton() {}\n")
        result = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["second_copies"], ["src/ui/IconButton/IconButton.tsx"])

    def test_reports_fixture_files_the_run_changed_or_removed(self):
        p = self.project("e")
        write(p, "src/ui/index.ts", "export { Button } from './Button/Button';\n")
        os.remove(os.path.join(p, "src/ui/TextField/TextField.tsx"))
        write(p, "src/features/projects/NameEditor.tsx", "import { Button } from '../../ui';\n")
        result = self.check(p)
        self.assertEqual(result["changed_fixture_files"], ["src/ui/index.ts"])
        self.assertEqual(result["removed_fixture_files"], ["src/ui/TextField/TextField.tsx"])

    def test_usage_error_without_components(self):
        out = subprocess.run([sys.executable, REUSE, self.fixture, self.fixture], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.evals_dir = os.path.join(self.tmp.name, "evals")
        write(self.evals_dir, "fixtures/demo/package.json", json.dumps({"devDependencies": {"react": "^18", "typescript": "^5"}}))
        write(self.evals_dir, "fixtures/demo/src/ui/index.ts", "export {};\n")
        write(self.evals_dir, "fixtures/demo/node_modules/left/over.js", "")
        write(self.evals_dir, "evals.json", json.dumps({"evals": [
            {"id": "demo", "fixture": "fixtures/demo", "prompt": "Work in {project} now.",
             "reuse": {"components": ["Button"], "hooks": ["useThing"]}},
            {"id": "plain", "prompt": "No fixture."}]}))
        self.toolchain = os.path.join(self.tmp.name, "toolchain")
        write(self.toolchain, "node_modules/react/package.json", "{}")
        write(self.toolchain, "node_modules/.bin/tsc", "")
        self.env = dict(os.environ, COMPONENT_DESIGN_TOOLCHAIN=self.toolchain)

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, *args):
        return subprocess.run([sys.executable, FIXTURE, *args, "--evals", os.path.join(self.evals_dir, "evals.json")],
                              capture_output=True, text=True, env=self.env)

    def test_copies_the_fixture_links_the_toolchain_and_prints_the_prompt(self):
        dest = os.path.join(self.tmp.name, "run1")
        out = self.prepare("demo", dest)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), f"Work in {dest} now.")
        self.assertTrue(os.path.isfile(os.path.join(dest, "src", "ui", "index.ts")))
        self.assertFalse(os.path.exists(os.path.join(dest, "node_modules", "left")))
        self.assertTrue(os.path.islink(os.path.join(dest, "node_modules", "react")))
        self.assertTrue(os.path.islink(os.path.join(dest, "node_modules", ".bin")))
        self.assertIn("lacks typescript", out.stderr)
        self.assertIn("--components Button --hooks useThing", out.stderr)

    def test_refuses_an_existing_destination_and_evals_without_a_fixture(self):
        dest = os.path.join(self.tmp.name, "run2")
        os.makedirs(dest)
        self.assertEqual(self.prepare("demo", dest).returncode, 2)
        self.assertEqual(self.prepare("plain", os.path.join(self.tmp.name, "run3")).returncode, 2)
        self.assertEqual(self.prepare("nope", os.path.join(self.tmp.name, "run4")).returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "run3")))


class ToolchainTest(unittest.TestCase):
    def test_prints_the_override_without_installing_when_node_modules_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "node_modules"))
            out = subprocess.run(["bash", TOOLCHAIN], capture_output=True, text=True,
                                 env=dict(os.environ, COMPONENT_DESIGN_TOOLCHAIN=tmp))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout.strip(), tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "package.json")))


if __name__ == "__main__":
    unittest.main()
