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
VERIFY = os.path.join(SKILL, "scripts", "verify.sh")

FEATURE = ("import { Button, TextField } from '../../ui';\n"
           "import { useControllableState } from '../../hooks/useControllableState';\n"
           "export function NameEditor() { const [v] = useControllableState(); return <><TextField /><Button /></>; }\n")


def write(root, rel, text, mode=None):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if mode is not None:
        os.chmod(path, mode)


def tree(root):
    """Every file under root with its contents, to prove a script left a folder as it was."""
    out = {}
    for base, _, names in os.walk(root):
        for name in names:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root)] = fh.read()
    return out


class ReuseCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = os.path.join(self.tmp.name, "fixture")
        write(self.fixture, "src/ui/Button/Button.tsx", "export function Button() { return <button />; }\n")
        write(self.fixture, "src/ui/TextField/TextField.tsx", "export function TextField() { return <input />; }\n")
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
        return json.loads(out.stdout), out.stderr

    def test_scores_2_when_the_feature_renders_the_primitives_and_calls_the_hook(self):
        p = self.project("a")
        write(p, "src/features/projects/NameEditor.tsx", FEATURE)
        write(p, "src/features/projects/NameEditor.test.tsx", "<button>tests are not scored</button>\n")
        write(p, "src/features/projects/example/Usage.tsx", "<input />\n")
        result, stderr = self.check(p)
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["hooks"], {"useControllableState": True})
        self.assertEqual(result["raw_controls"], {})
        self.assertEqual(result["code_files"], ["src/features/projects/NameEditor.tsx"])
        self.assertEqual(result["used_in"]["Button"], ["src/features/projects/NameEditor.tsx"])
        self.assertEqual(stderr, "")

    def test_scores_0_when_the_feature_rebuilds_its_own_controls(self):
        p = self.project("b")
        write(p, "src/features/projects/NameEditor.tsx",
              "export function NameEditor() { return <><button /><input /><input /></>; }\n")
        write(p, "src/features/projects/Button.tsx", "export function Button() {}\n")
        write(p, "src/hooks/useControllableValue.ts", "export function useControllableValue() {}\n")
        result, _ = self.check(p)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["raw_controls"], {"button": 1, "input": 2})
        self.assertEqual(result["second_copies"], ["src/features/projects/Button.tsx", "src/hooks/useControllableValue.ts"])

    def test_scores_1_when_some_primitives_are_reused_and_the_rest_rebuilt(self):
        p = self.project("c")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { Button } from '../../ui';\nexport const field = <><Button /><input /></>;\n")
        result, _ = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["components"], {"Button": True, "TextField": False})
        self.assertEqual(result["raw_controls"], {"input": 1})

    def test_scores_1_when_the_hook_the_state_calls_for_is_not_used(self):
        p = self.project("g")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { useState } from 'react';\nimport { Button, TextField } from '../../ui';\n"
              "export const v = <><Button /><TextField /></>;\n")
        result, _ = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["hooks"], {"useControllableState": False})
        self.assertEqual(self.check(p, hooks="")[0]["score"], 2)  # an eval whose task calls for no hook

    def test_an_import_that_is_never_rendered_or_called_is_not_reuse(self):
        p = self.project("n")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n"
              "export function NameEditor() { return <span role=\"button\" />; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": False, "TextField": False})
        self.assertEqual(result["hooks"], {"useControllableState": False})
        self.assertEqual(result["score"], 0)

    def test_an_example_consumer_cannot_earn_the_score_for_the_feature(self):
        """The prompt asks for an example consumer; whatever the run names it (a folder, a dotted suffix or a
        CamelCase one), it is not the feature."""
        p = self.project("o")
        write(p, "src/features/projects/NameEditor.tsx", "export function NameEditor() { return <span role=\"button\" />; }\n")
        for consumer in ("NameEditorUsage.tsx", "ProjectNameExample.tsx", "Demo.tsx", "examples/Usage.tsx", "NameEditor.example.tsx"):
            write(p, f"src/features/projects/{consumer}", FEATURE)
        result, _ = self.check(p)
        self.assertEqual(result["code_files"], ["src/features/projects/NameEditor.tsx"])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["used_in"], {})

    def test_a_render_spread_over_lines_counts_like_one_on_a_line(self):
        """`<Button` alone occurs in the fixture file; a new multi-line `<Button …>` is still an addition."""
        one_line = "export const b = <Button variant=\"primary\" onClick={rename}>Rename</Button>;\n"
        spread = "export const b = (\n  <Button\n    variant=\"primary\"\n    onClick={rename}\n  >\n    Rename\n  </Button>\n);\n"
        scores = []
        for name, body in (("one", one_line), ("spread", spread)):
            p = self.project(name)
            write(p, "src/features/projects/ProjectActions.tsx", "import { Button } from '../../ui';\nexport const a = <Button />;\n" + body)
            result, _ = self.check(p)
            scores.append((result["score"], result["components"]["Button"]))
        self.assertEqual(scores, [(1, True), (1, True)])

    def test_a_feature_local_ui_folder_is_not_the_shared_one(self):
        p = self.project("v")
        write(p, "src/features/projects/ui/EditControls.tsx", "export function EditControls() { return <><button /><input /></>; }\n")
        write(p, "src/features/projects/ui/Button.tsx", "export function Button() { return <button />; }\n")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { EditControls } from './ui/EditControls';\nimport { Button } from './ui/Button';\n"
              "export function NameEditor() { return <><EditControls /><Button /></>; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": False, "TextField": False})
        self.assertEqual(result["raw_controls"], {"button": 2, "input": 1})
        self.assertEqual(result["second_copies"], ["src/features/projects/ui/Button.tsx"])
        self.assertEqual(result["score"], 0)

    def test_an_apostrophe_inside_a_word_is_not_a_quote(self):
        p = self.project("w")
        write(p, "src/features/projects/NameEditor.tsx",
              "import { Button, TextField } from '../../ui';\nimport { useControllableState } from '../../hooks/useControllableState';\n"
              "export function NameEditor() { useControllableState(); "
              "return <><TextField /><p>Couldn't save the project's name</p> <Button>Retry</Button></>; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["score"], 2)

    def test_scores_code_added_to_an_existing_fixture_file(self):
        p = self.project("h")
        write(p, "src/features/projects/ProjectActions.tsx",
              "import { Button, TextField } from '../../ui';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n"
              "export const a = <Button />;\nexport function ProjectNameEdit() { useControllableState(); return <><Button /><TextField /></>; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["changed_code_files"], ["src/features/projects/ProjectActions.tsx"])
        self.assertEqual(result["code_files"], [])

    def test_only_the_added_lines_of_a_changed_fixture_file_count(self):
        p = self.project("i")
        # The fixture's own `import { Button }` and `<Button />` lines stay; the run adds a raw input and nothing else.
        write(p, "src/features/projects/ProjectActions.tsx",
              "import { Button } from '../../ui';\nexport const a = <Button />;\nexport const b = <input />;\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": False, "TextField": False})
        self.assertEqual(result["raw_controls"], {"input": 1})
        self.assertEqual(result["score"], 0)

    def test_an_existing_import_counts_when_the_added_lines_render_it(self):
        p = self.project("p")
        write(p, "src/features/projects/ProjectActions.tsx",
              "import { Button } from '../../ui';\nexport const a = <Button />;\nexport const b = <Button>Rename</Button>;\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": True, "TextField": False})

    def test_a_reformat_of_a_fixture_file_adds_nothing(self):
        p = self.project("q")
        write(p, "src/features/projects/ProjectActions.tsx", "import {Button} from '../../ui';\nexport const a = (\n  <Button />\n);\n")
        write(p, "src/features/projects/NameEditor.tsx", "export function NameEditor() { return <span />; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": False, "TextField": False})
        self.assertEqual(result["raw_controls"], {})
        self.assertEqual(result["changed_fixture_files"], ["src/features/projects/ProjectActions.tsx"])

    def test_an_additive_change_to_a_shared_primitive_is_not_a_raw_control(self):
        p = self.project("r")
        write(p, "src/ui/Button/Button.tsx", "export function Button({ size }) { return <button data-size={size} />; }\n")
        write(p, "src/ui/TextField/TextField.tsx", "export function TextField({ compact }) {\n  return <input data-compact={compact} />;\n}\n")
        write(p, "src/features/projects/NameEditor.tsx", FEATURE)
        result, _ = self.check(p)
        self.assertEqual(result["raw_controls"], {})
        self.assertEqual(result["score"], 2)
        self.assertEqual(sorted(result["changed_code_files"]), ["src/ui/Button/Button.tsx", "src/ui/TextField/TextField.tsx"])

    def test_comments_and_strings_are_ignored(self):
        p = self.project("s")
        write(p, "src/features/projects/NameEditor.tsx",
              "// import { Button, TextField } from '../../ui';\n"
              "/* <UI.Button /> */\n"
              "export function NameEditor() { return <span>{'<input />'}</span>; }\n")
        write(p, "src/features/projects/Other.tsx",
              FEATURE + "// never a raw <button> here\nconst hint = \"<input> is banned\";\nconst url = 'https://example.test/ui';\n")
        result, _ = self.check(p)
        self.assertEqual(result["raw_controls"], {})
        self.assertEqual(result["used_in"]["Button"], ["src/features/projects/Other.tsx"])
        self.assertEqual(result["score"], 2)

    def test_a_relative_import_from_inside_the_shared_folder_counts(self):
        p = self.project("t")
        write(p, "src/ui/InlineEdit/InlineEdit.tsx",
              "import { Button } from '../Button/Button';\nimport { TextField } from '../TextField/TextField';\n"
              "import { useControllableState } from '../../hooks/useControllableState';\n"
              "export function InlineEdit() { useControllableState(); return <><TextField /><Button /></>; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["hooks"], {"useControllableState": True})
        self.assertEqual(result["score"], 2)

    def test_a_second_copy_in_the_shared_folder_costs_the_score_even_with_imports(self):
        p = self.project("d")
        write(p, "src/features/projects/NameEditor.tsx", FEATURE)
        write(p, "src/ui/IconButton/IconButton.tsx", "export function IconButton() {}\n")
        result, _ = self.check(p)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["second_copies"], ["src/ui/IconButton/IconButton.tsx"])

    def test_a_new_shared_component_with_another_name_is_not_a_copy(self):
        p = self.project("j")
        write(p, "src/features/projects/NameEditor.tsx", FEATURE)
        write(p, "src/ui/FieldGroup/FieldGroup.tsx", "export function FieldGroup() {}\n")
        result, _ = self.check(p)
        self.assertEqual(result["second_copies"], [])
        self.assertEqual(result["score"], 2)

    def test_previews_and_examples_are_excluded_by_folder_prefix_or_suffix_not_by_substring(self):
        p = self.project("k")
        write(p, "src/features/projects/NameEditor.tsx", FEATURE)
        write(p, "src/features/projects/ProjectNamePreview.tsx", "export const v = <button><input /></button>;\n")
        write(p, "src/features/projects/preview.build.tsx", "<input />\n")
        write(p, "src/features/projects/ProjectName.example.tsx", "<input />\n")
        write(p, "src/features/projects/examples/Usage.tsx", "<input />\n")
        result, _ = self.check(p)
        self.assertEqual(result["code_files"], ["src/features/projects/NameEditor.tsx", "src/features/projects/ProjectNamePreview.tsx"])
        self.assertEqual(result["raw_controls"], {"button": 1, "input": 1})
        self.assertEqual(result["score"], 1)

    def test_says_when_the_run_wrote_nothing_it_can_score(self):
        p = self.project("u")
        write(p, "src/features/projects/NameEditor.jsx", "export const v = <button />;\n")
        write(p, "src/features/projects/NameEditor.test.tsx", "it('x', () => {});\n")
        result, stderr = self.check(p)
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["scored"])
        self.assertIn("no code to score", stderr)

    def test_reports_fixture_files_the_run_changed_or_removed(self):
        p = self.project("e")
        write(p, "src/ui/index.ts", "export { Button } from './Button/Button';\n")
        os.remove(os.path.join(p, "src/ui/TextField/TextField.tsx"))
        write(p, "src/features/projects/NameEditor.tsx", "import { Button } from '../../ui';\nexport const v = <Button />;\n")
        result, _ = self.check(p)
        self.assertEqual(result["changed_fixture_files"], ["src/ui/index.ts"])
        self.assertEqual(result["removed_fixture_files"], ["src/ui/TextField/TextField.tsx"])

    def test_counts_named_imports_spread_over_lines_with_type_and_alias_forms(self):
        p = self.project("f")
        write(p, "src/features/projects/NameEditor.tsx",
              "import {\n  type ButtonProps,\n  Button as PrimaryButton,\n  TextField,\n} from '@/ui';\n"
              "import { useControllableState as useControllable } from '@/hooks/useControllableState';\n"
              "export function NameEditor() { useControllable(); return <><PrimaryButton /><TextField /></>; }\n")
        result, _ = self.check(p)
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["components"], {"Button": True, "TextField": True})
        self.assertEqual(result["hooks"], {"useControllableState": True})

    def test_counts_namespace_imports_used_as_alias_dot_name(self):
        p = self.project("l")
        write(p, "src/features/projects/NameEditor.tsx",
              "import * as UI from '../../ui';\nimport * as Hooks from '../../hooks/useControllableState';\n"
              "export const v = <UI.Button><UI.TextField /></UI.Button>;\nconst [x] = Hooks.useControllableState();\n")
        result, _ = self.check(p)
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
        write(p, "src/features/projects/NameEditor.tsx", FEATURE)
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

    def test_quotes_the_scorer_command_when_the_destination_has_a_space(self):
        dest = os.path.join(self.tmp.name, "run 1")
        out = self.prepare("demo", dest)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"reuse_check.py demo '{dest}' --evals", out.stderr)

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
    out = subprocess.run(["/bin/bash", TOOLCHAIN, "--packages"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class ToolchainTest(unittest.TestCase):
    def run_toolchain(self, folder, npm_log, npm_body=""):
        bin_dir = os.path.join(os.path.dirname(folder), "bin")
        os.makedirs(bin_dir, exist_ok=True)
        write(bin_dir, "npm", f"#!/bin/sh\necho \"$@\" >> '{npm_log}'\n{npm_body}\n", 0o755)
        env = dict(os.environ, COMPONENT_DESIGN_TOOLCHAIN=folder, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        return subprocess.run(["/bin/bash", TOOLCHAIN], capture_output=True, text=True, env=env)

    def npm_calls(self, npm_log):
        if not os.path.exists(npm_log):
            return ""
        with open(npm_log, encoding="utf-8") as fh:
            return fh.read()

    def test_packages_prints_the_list_and_installs_nothing(self):
        out = subprocess.run(["/bin/bash", TOOLCHAIN, "--packages"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("vitest", json.loads(out.stdout)["devDependencies"])

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
            out = self.run_toolchain(folder, log, "mkdir -p node_modules")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("install", self.npm_calls(log))
            with open(os.path.join(folder, "package.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), toolchain_packages())
            self.assertTrue(os.path.isdir(os.path.join(folder, "node_modules")))
            os.remove(log)
            self.run_toolchain(folder, log)
            self.assertEqual(self.npm_calls(log), "")  # same list: nothing to do
            with open(os.path.join(folder, "package.json"), "w", encoding="utf-8") as fh:
                fh.write('{"devDependencies": {"react": "^17"}}\n')
            self.run_toolchain(folder, log, "mkdir -p node_modules")
            self.assertIn("install", self.npm_calls(log))  # a different list reinstalls
            self.assertEqual(sorted(os.listdir(tmp)), ["bin", "npm.log", "tc"])  # no staging folder left behind

    def test_a_trailing_slash_or_a_relative_override_installs_in_place_and_prints_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, log = os.path.join(tmp, "tc"), os.path.join(tmp, "npm.log")
            self.run_toolchain(folder, log, "mkdir -p node_modules")  # writes the npm stub into tmp/bin
            shutil.rmtree(folder)
            for override in (folder + "/", "tc"):
                env = dict(os.environ, COMPONENT_DESIGN_TOOLCHAIN=override, PATH=os.path.join(tmp, "bin") + os.pathsep + os.environ["PATH"])
                out = subprocess.run(["/bin/bash", TOOLCHAIN], capture_output=True, text=True, env=env, cwd=tmp)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(os.path.realpath(out.stdout.strip()), os.path.realpath(folder), override)
                self.assertTrue(os.path.isdir(os.path.join(folder, "node_modules")), override)
                self.assertEqual(sorted(os.listdir(tmp)), ["bin", "npm.log", "tc"], override)  # no staging folder inside or beside
                shutil.rmtree(folder)

    def test_a_failed_install_leaves_no_cache_and_the_next_run_installs_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, log = os.path.join(tmp, "tc"), os.path.join(tmp, "npm.log")
            out = self.run_toolchain(folder, log, "mkdir -p node_modules/react; exit 1")
            self.assertEqual(out.returncode, 1)
            self.assertIn("npm install failed", out.stderr)
            self.assertFalse(os.path.exists(folder))
            self.assertEqual(sorted(os.listdir(tmp)), ["bin", "npm.log"])
            os.remove(log)
            out = self.run_toolchain(folder, log, "mkdir -p node_modules/react")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("install", self.npm_calls(log))
            self.assertTrue(os.path.isdir(os.path.join(folder, "node_modules", "react")))


class VerifyShTest(unittest.TestCase):
    """verify.sh against a project whose tsc and vitest are shell stubs that log their arguments."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = os.path.join(self.tmp.name, "my project")
        self.log = os.path.join(self.tmp.name, "calls.log")
        write(self.project, "package.json", "{}\n")
        write(self.project, "src/features/x/A.tsx", "export const a = 1;\n")
        write(self.project, "src/features/x/A.test.tsx", "it('a', () => {});\n")
        for tool in ("tsc", "vitest"):
            write(self.project, f"node_modules/.bin/{tool}", f"#!/bin/sh\necho \"{tool} $@\" >> \"$VERIFY_LOG\"\nexit \"${{VERIFY_{tool.upper()}_EXIT:-0}}\"\n", 0o755)
        write(self.project, "node_modules/react/package.json", "{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, *args, **env):
        return subprocess.run(["/bin/bash", VERIFY, *args], capture_output=True, text=True,
                              env=dict(os.environ, VERIFY_LOG=self.log, **env))

    def calls(self):
        with open(self.log, encoding="utf-8") as fh:
            return [line.strip() for line in fh]

    def test_without_an_overlay_runs_the_type_check_and_every_test(self):
        before = tree(self.project)
        out = self.verify(self.project)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.calls(), ["tsc --noEmit", "vitest run"])
        self.assertEqual(tree(self.project), before)

    def test_with_an_overlay_runs_only_its_test_files_and_leaves_the_project_alone(self):
        overlay = os.path.join(self.tmp.name, "my overlay")
        write(overlay, "src/features/x/B.tsx", "export const b = 1;\n")
        write(overlay, "src/features/x/B test.test.tsx", "it('b', () => {});\n")
        before = tree(self.project)
        out = self.verify(self.project, overlay)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.calls(), ["tsc --noEmit", "vitest run src/features/x/B test.test.tsx"])
        self.assertEqual(tree(self.project), before)

    def test_an_overlay_without_test_files_runs_every_test(self):
        overlay = os.path.join(self.tmp.name, "overlay")
        write(overlay, "src/features/x/B.tsx", "export const b = 1;\n")
        out = self.verify(self.project, overlay)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.calls(), ["tsc --noEmit", "vitest run"])

    def test_a_failing_type_check_or_test_fails_the_run(self):
        self.assertEqual(self.verify(self.project, VERIFY_TSC_EXIT="2").returncode, 2)
        self.assertEqual(self.verify(self.project, VERIFY_VITEST_EXIT="1").returncode, 1)

    def test_refuses_an_overlay_without_src_and_a_project_without_node_modules(self):
        overlay = os.path.join(self.tmp.name, "bare")
        os.makedirs(overlay)
        out = self.verify(self.project, overlay)
        self.assertEqual(out.returncode, 1)
        self.assertIn("has no src/", out.stderr)
        shutil.rmtree(os.path.join(self.project, "node_modules"))
        out = self.verify(self.project)
        self.assertEqual(out.returncode, 1)
        self.assertIn("No node_modules", out.stderr)
        self.assertFalse(os.path.exists(self.log))

    def test_minimal_refuses_a_folder_without_src(self):
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(bare)
        out = self.verify("--minimal", bare, COMPONENT_DESIGN_TOOLCHAIN=os.path.join(self.tmp.name, "never-installed"))
        self.assertEqual(out.returncode, 1)
        self.assertIn("has no src/", out.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "never-installed")))


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

    def test_fixture_follows_the_rules_the_skill_asks_of_an_agent(self):
        """Step 2 tells the agent to copy the test and the styles next to its own, so the fixture must obey
        accessibility.md (no opacity on text) and testing.md (user-event 14 goes through setup())."""
        for ev in self.evals:
            src = os.path.join(self.fixture(ev), "src")
            for base, _, names in os.walk(src):
                for name in names:
                    path = os.path.join(base, name)
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read()
                    if name.endswith(".css"):
                        self.assertNotIn("opacity", text, path)
                    if ".test." in name and "userEvent" in text:
                        self.assertIn("userEvent.setup()", text, path)
                        self.assertNotRegex(text, r"userEvent\.(click|type|tab|keyboard)\(", path)

    def test_fixture_keeps_no_dependencies_or_caches(self):
        for ev in self.evals:
            for forbidden in ("node_modules", ".vite-cache", "package-lock.json"):
                self.assertFalse(os.path.exists(os.path.join(self.fixture(ev), forbidden)), forbidden)


if __name__ == "__main__":
    unittest.main()
