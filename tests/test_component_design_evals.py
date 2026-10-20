import json
import os
import re
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
        write(self.fixture, "src/features/projects/ProjectActions.tsx", "import { Button } from '../../ui';\nexport const a = <Button />;\n")
        write(self.fixture, "package.json", "{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, name):
        dest = os.path.join(self.tmp.name, name)
        shutil.copytree(self.fixture, dest)
        return dest

    def check(self, project, hooks="useControllableState"):
        out = subprocess.run([sys.executable, REUSE, self.fixture, project, "--components", "Button,TextField",
                              "--hooks", hooks, "--json"], capture_output=True, text=True)
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

    def test_scores_1_when_the_hook_the_state_calls_for_is_not_used(self):
        p = self.project("g")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { useState } from 'react';\nimport { Button, TextField } from '../../ui';\n")
        result = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["hooks"], {"useControllableState": False})
        self.assertEqual(self.check(p, hooks="")["score"], 2)  # an eval whose task calls for no hook

    def test_scores_code_added_to_an_existing_fixture_file(self):
        p = self.project("h")
        write(p, "src/features/projects/ProjectActions.tsx",
              "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n"
              "export const a = <Button />;\nexport function ProjectNameEdit() { return <TextField />; }\n")
        result = self.check(p)
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["changed_code_files"], ["src/features/projects/ProjectActions.tsx"])
        self.assertEqual(result["code_files"], [])

    def test_only_the_added_lines_of_a_changed_fixture_file_count(self):
        p = self.project("i")
        # The fixture's own `import { Button }` line stays; the run adds a raw input and nothing else.
        write(p, "src/features/projects/ProjectActions.tsx",
              "import { Button } from '../../ui';\nexport const a = <Button />;\nexport const b = <input />;\n")
        result = self.check(p)
        self.assertEqual(result["components"], {"Button": False, "TextField": False})
        self.assertEqual(result["raw_controls"], {"input": 1})
        self.assertEqual(result["score"], 0)

    def test_a_second_copy_in_the_shared_folder_costs_the_score_even_with_imports(self):
        p = self.project("d")
        write(p, "src/features/projects/NameEditor.tsx", "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n")
        write(p, "src/ui/IconButton/IconButton.tsx", "export function IconButton() {}\n")
        result = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["second_copies"], ["src/ui/IconButton/IconButton.tsx"])

    def test_a_new_shared_component_with_another_name_is_not_a_copy(self):
        p = self.project("j")
        write(p, "src/features/projects/NameEditor.tsx", "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n")
        write(p, "src/ui/FieldGroup/FieldGroup.tsx", "export function FieldGroup() {}\n")
        result = self.check(p)
        self.assertEqual(result["second_copies"], [])
        self.assertEqual(result["score"], 2)

    def test_previews_and_examples_are_excluded_by_folder_prefix_or_suffix_not_by_substring(self):
        p = self.project("k")
        write(p, "src/features/projects/NameEditor.tsx", "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n")
        write(p, "src/features/projects/ProjectNamePreview.tsx", "export const v = <button><input /></button>;\n")
        write(p, "src/features/projects/preview.build.tsx", "<input />\n")
        write(p, "src/features/projects/ProjectName.example.tsx", "<input />\n")
        write(p, "src/features/projects/examples/Usage.tsx", "<input />\n")
        result = self.check(p)
        self.assertEqual(result["code_files"], ["src/features/projects/NameEditor.tsx", "src/features/projects/ProjectNamePreview.tsx"])
        self.assertEqual(result["raw_controls"], {"button": 1, "input": 1})
        self.assertEqual(result["score"], 1)

    def test_reports_fixture_files_the_run_changed_or_removed(self):
        p = self.project("e")
        write(p, "src/ui/index.ts", "export { Button } from './Button/Button';\n")
        os.remove(os.path.join(p, "src/ui/TextField/TextField.tsx"))
        write(p, "src/features/projects/NameEditor.tsx", "import { Button } from '../../ui';\n")
        result = self.check(p)
        self.assertEqual(result["changed_fixture_files"], ["src/ui/index.ts"])
        self.assertEqual(result["removed_fixture_files"], ["src/ui/TextField/TextField.tsx"])

    def test_counts_named_imports_spread_over_lines_with_type_and_alias_forms(self):
        p = self.project("f")
        write(p, "src/features/projects/NameEditor.tsx",
              "import {\n  type ButtonProps,\n  Button as PrimaryButton,\n  TextField,\n} from '@/ui';\n"
              "import { useControllableState as useControllable } from '@/hooks/useControllableState';\n")
        result = self.check(p)
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["hooks"], {"useControllableState": True})

    def test_counts_namespace_imports_used_as_alias_dot_name(self):
        p = self.project("l")
        write(p, "src/features/projects/NameEditor.tsx",
              "import * as UI from '../../ui';\nimport * as Hooks from '../../hooks/useControllableState';\n"
              "export const v = <UI.Button><UI.TextField /></UI.Button>;\nconst [x] = Hooks.useControllableState();\n")
        result = self.check(p)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["hooks"], {"useControllableState": True})
        self.assertEqual(result["score"], 2)

    def test_an_eval_id_resolves_the_fixture_and_the_reuse_entry(self):
        evals = os.path.join(self.tmp.name, "evals.json")
        with open(evals, "w", encoding="utf-8") as fh:
            json.dump({"evals": [{"id": "demo", "fixture": "fixture", "prompt": "x",
                                  "reuse": {"components": ["Button", "TextField"], "hooks": ["useControllableState"]}},
                                 {"id": "plain", "prompt": "x"}]}, fh)
        p = self.project("m")
        write(p, "src/features/projects/NameEditor.tsx", "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n")
        out = subprocess.run([sys.executable, REUSE, "demo", p, "--evals", evals, "--json"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["score"], 2)
        self.assertEqual(subprocess.run([sys.executable, REUSE, "plain", p, "--evals", evals], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, REUSE, "nope", p, "--evals", evals], capture_output=True).returncode, 2)

    def test_usage_error_without_components_and_help_print_the_usage(self):
        out = subprocess.run([sys.executable, REUSE, self.fixture, self.fixture], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        out = subprocess.run([sys.executable, REUSE, "-h"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("Usage: reuse_check.py", out.stdout)


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.evals_dir = os.path.join(self.tmp.name, "evals")
        write(self.evals_dir, "fixtures/demo/package.json", json.dumps({"devDependencies": {"react": "^18"}}))
        write(self.evals_dir, "fixtures/demo/src/ui/index.ts", "export {};\n")
        write(self.evals_dir, "fixtures/demo/node_modules/left/over.js", "")
        write(self.evals_dir, "fixtures/needy/package.json", json.dumps({"devDependencies": {"react": "^18", "typescript": "^5"}}))
        write(self.evals_dir, "evals.json", json.dumps({"evals": [
            {"id": "demo", "fixture": "fixtures/demo", "prompt": "Work in {project} now.",
             "reuse": {"components": ["Button"], "hooks": ["useThing"]}},
            {"id": "needy", "fixture": "fixtures/needy", "prompt": "Work in {project} now.", "reuse": {"components": ["Button"]}},
            {"id": "unscored", "fixture": "fixtures/demo", "prompt": "Work in {project} now."},
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
        self.assertIn(f"reuse_check.py demo {dest} --evals", out.stderr)

    def test_refuses_a_project_the_toolchain_cannot_run(self):
        dest = os.path.join(self.tmp.name, "run6")
        out = self.prepare("needy", dest)
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout, "")
        self.assertIn("lacks typescript", out.stderr)
        self.assertFalse(os.path.exists(dest))

    def test_says_when_the_eval_names_nothing_to_score_instead_of_printing_a_broken_command(self):
        dest = os.path.join(self.tmp.name, "run5")
        out = self.prepare("unscored", dest)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("reuse_check.py", out.stderr)
        self.assertIn("names no `reuse.components`", out.stderr)

    def test_help_prints_the_usage(self):
        out = self.prepare("--help")
        self.assertEqual(out.returncode, 2)
        self.assertIn("Usage: fixture.py", out.stdout)

    def test_refuses_an_existing_destination_and_evals_without_a_fixture(self):
        dest = os.path.join(self.tmp.name, "run2")
        os.makedirs(dest)
        self.assertEqual(self.prepare("demo", dest).returncode, 2)
        self.assertEqual(self.prepare("plain", os.path.join(self.tmp.name, "run3")).returncode, 2)
        self.assertEqual(self.prepare("nope", os.path.join(self.tmp.name, "run4")).returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "run3")))


def toolchain_packages():
    with open(TOOLCHAIN, encoding="utf-8") as fh:
        match = re.search(r"PKG='(.*?)'", fh.read(), re.S)
    return json.loads(match.group(1))


class ToolchainTest(unittest.TestCase):
    def run_toolchain(self, folder, npm_log):
        bin_dir = os.path.join(folder, "..", "bin")
        os.makedirs(bin_dir, exist_ok=True)
        fake = os.path.join(bin_dir, "npm")
        with open(fake, "w") as fh:
            fh.write(f"#!/bin/sh\necho \"$@\" >> '{npm_log}'\n")
        os.chmod(fake, 0o755)
        env = dict(os.environ, COMPONENT_DESIGN_TOOLCHAIN=folder, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        return subprocess.run(["/bin/bash", TOOLCHAIN], capture_output=True, text=True, env=env)

    def npm_calls(self, npm_log):
        if not os.path.exists(npm_log):
            return ""
        with open(npm_log, encoding="utf-8") as fh:
            return fh.read()

    def test_prints_the_override_without_installing_when_node_modules_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "tc")
            os.makedirs(os.path.join(folder, "node_modules"))
            out = self.run_toolchain(folder, os.path.join(tmp, "npm.log"))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout.strip(), folder)
            self.assertFalse(os.path.exists(os.path.join(folder, "package.json")))
            self.assertEqual(self.npm_calls(os.path.join(tmp, "npm.log")), "")

    def test_installs_when_node_modules_are_missing_and_again_when_the_package_list_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, log = os.path.join(tmp, "tc"), os.path.join(tmp, "npm.log")
            out = self.run_toolchain(folder, log)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("install", self.npm_calls(log))
            with open(os.path.join(folder, "package.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), toolchain_packages())
            os.makedirs(os.path.join(folder, "node_modules"))
            os.remove(log)
            self.run_toolchain(folder, log)
            self.assertEqual(self.npm_calls(log), "")  # same list: nothing to do
            with open(os.path.join(folder, "package.json"), "w", encoding="utf-8") as fh:
                fh.write('{"devDependencies": {"react": "^17"}}\n')
            self.run_toolchain(folder, log)
            self.assertIn("install", self.npm_calls(log))  # a different list reinstalls


class RealFixtureTest(unittest.TestCase):
    """The shipped fixtures stay consistent with evals.json, the toolchain and the skill's own checks."""

    def setUp(self):
        with open(os.path.join(SKILL, "evals", "evals.json"), encoding="utf-8") as fh:
            self.evals = [e for e in json.load(fh)["evals"] if e.get("fixture")]
        self.assertTrue(self.evals)

    def fixture(self, ev):
        return os.path.join(SKILL, "evals", ev["fixture"])

    def test_every_fixture_eval_names_components_and_hooks_that_exist(self):
        for ev in self.evals:
            with open(os.path.join(self.fixture(ev), "src", "ui", "index.ts"), encoding="utf-8") as fh:
                index = fh.read()
            for component in ev["reuse"]["components"]:
                self.assertRegex(index, rf"\b{component}\b")
            for hook in ev["reuse"].get("hooks", []):
                self.assertTrue(os.path.isfile(os.path.join(self.fixture(ev), "src", "hooks", hook + ".ts")), hook)

    def test_fixture_dependencies_are_all_in_the_toolchain(self):
        toolchain = set(toolchain_packages()["devDependencies"])
        for ev in self.evals:
            with open(os.path.join(self.fixture(ev), "package.json"), encoding="utf-8") as fh:
                pkg = json.load(fh)
            wanted = set(pkg.get("dependencies") or {}) | set(pkg.get("devDependencies") or {})
            self.assertEqual(wanted - toolchain, set(), ev["id"])

    def test_fixture_primitives_have_one_test_per_contract_line_and_pass_lint(self):
        check = os.path.join(SKILL, "scripts", "check_contract.py")
        lint = os.path.join(SKILL, "scripts", "lint.py")
        for ev in self.evals:
            src = os.path.join(self.fixture(ev), "src")
            contracts = 0
            for name in sorted(os.listdir(os.path.join(src, "ui"))):
                readme = os.path.join(src, "ui", name, "README.md")
                if os.path.isfile(readme):
                    contracts += 1
                    tests = [os.path.join(src, "ui", name, f) for f in os.listdir(os.path.dirname(readme)) if ".test." in f]
                    out = subprocess.run([sys.executable, check, readme, *tests], capture_output=True, text=True)
                    self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertGreater(contracts, 0, ev["id"])
            out = subprocess.run([sys.executable, lint, src, "--business-words", ev.get("business_words", "")],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_fixture_keeps_no_dependencies_or_caches(self):
        for ev in self.evals:
            for forbidden in ("node_modules", ".vite-cache", "package-lock.json"):
                self.assertFalse(os.path.exists(os.path.join(self.fixture(ev), forbidden)), forbidden)


if __name__ == "__main__":
    unittest.main()
