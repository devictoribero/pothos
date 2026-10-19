import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "ui_check.py")


class UiCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "git@github.com:acme/shop.git"], check=True)
        self.write("README.md", "x\n")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.git("checkout", "-qb", "feature")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True)

    def write(self, rel, content):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, "verify": {"full": "x"}, **data}, fh)

    def check(self):
        env = {**os.environ, "POTHOS_HOME": self.home}
        return subprocess.run([sys.executable, SCRIPT], cwd=self.repo, capture_output=True, text=True, env=env)

    def test_an_unreadable_contract_exits_2(self):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("{not json")
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_paths_survive_diff_noprefix(self):
        self.contract({"ui": {"tokens": ["src/tokens.css"]}})
        self.git("config", "diff.noprefix", "true")
        self.write("src/tokens.css", ":root { --ink: #111111; }\n")
        self.write("src/a.css", ".b { color: #123456; }\n")
        result = self.check()
        self.assertIn("src/a.css:1", result.stdout)
        self.assertNotIn("tokens.css", result.stdout)

    def test_universal_css_selectors_are_not_comments(self):
        self.contract({"ui": {"tokens": ["src/tokens.css"]}})
        self.write("src/tokens.css", ":root { --ink: #111111; }\n")
        self.write("src/reset.css", "* { color: #123456; }\n*, *::before { background: rgb(1, 2, 3); }\n * ok\n")
        result = self.check()
        self.assertIn("src/reset.css:1", result.stdout)
        self.assertIn("src/reset.css:2", result.stdout)
        self.assertNotIn("src/reset.css:3", result.stdout)

    def test_no_contract_exits_2(self):
        self.assertEqual(self.check().returncode, 2)

    def test_without_ui_section_it_skips(self):
        self.contract({})
        result = self.check()
        self.assertEqual(result.returncode, 0)
        self.assertIn("skipped", result.stdout)

    def test_raw_colors_across_stacks(self):
        self.contract({"ui": {"tokens": ["src/theme"]}})
        self.write("src/a.css", ".a { color: #fff; background: rgb(0, 0, 0); }\n")
        self.write("src/b.tsx", "export const B = () => <div className=\"bg-[#1a2b3c] p-4\" />\n")
        self.write("src/c.ts", "const s = StyleSheet.create({ box: { borderColor: '#abc' } })\n")
        self.write("src/d.styled.ts", "const D = styled.div`\n  color: hsl(200, 50%, 50%);\n`\n")
        self.write("src/e.vue", "<style scoped>\n.e { color: #ff000080 }\n</style>\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        for expected in ["src/a.css:1 raw-color: #fff", "src/a.css:1 raw-color: rgb(0", "src/b.tsx:1 raw-color: #1a2b3c",
                         "src/c.ts:1 raw-color: #abc", "src/d.styled.ts:2 raw-color: hsl(2", "src/e.vue:2 raw-color: #ff000080"]:
            self.assertIn(expected, result.stdout)

    def test_hash_words_that_are_not_colors_pass(self):
        self.contract({"ui": {"tokens": ["src/theme"]}})
        self.write("src/a.ts", "class A {\n  #add = 1\n  run() { return this.#add }\n}\n// see issue #123\n")
        self.write("src/b.css", "#fed { color: var(--color-text); }\n")
        self.write("src/c.tsx", "export const L = () => <a href=\"#faq\">FAQ</a>\n")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_docs_and_comments_are_not_styles(self):
        self.contract({"ui": {"tokens": ["src/theme"]}})
        self.write("docs/report.html", "<style>body { color: #123456 }</style>\n")
        self.write("src/a.ts", "// the brand grey #808080 misses AA\n  * old value: #737373\n")
        self.assertEqual(self.check().returncode, 0)

    def test_token_files_tests_and_ui_ok_are_exempt(self):
        self.contract({"ui": {"tokens": ["src/theme"]}})
        self.write("src/theme/colors.ts", "export const brand = '#123456'\n")
        self.write("src/a.test.tsx", "expect(el).toHaveStyle({ color: '#123456' })\n")
        self.write("src/a.tsx", "const brandOfPartner = '#123456' // ui-ok: partner logo color\n")
        self.assertEqual(self.check().returncode, 0)

    def test_only_added_lines_count(self):
        self.contract({"ui": {"tokens": ["src/theme"]}})
        self.write("src/old.css", ".a { color: #123456; }\n")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "old")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "feature")
        self.git("checkout", "-qb", "next")
        self.write("src/old.css", ".a { color: #123456; }\n.b { color: var(--x); }\n")
        self.assertEqual(self.check().returncode, 0)

    def test_fonts(self):
        self.contract({"ui": {"tokens": ["src/theme"]}})
        self.write("src/a.css", "@import url('https://fonts.googleapis.com/css2?family=Inter');\nbody { font-family: 'Inter', sans-serif; }\n"
                   "p { font-family: var(--font-body); }\n")
        self.write("src/b.tsx", "import { Inter } from 'next/font/google'\nconst s = { fontFamily: 'Inter' }\n")
        out = self.check().stdout
        self.assertIn("src/a.css:1 font", out)
        self.assertIn("src/a.css:2 font", out)
        self.assertNotIn("src/a.css:3", out)
        self.assertIn("src/b.tsx:1 font", out)
        self.assertIn("src/b.tsx:2 font", out)

    def test_other_icon_sets(self):
        self.contract({"ui": {"icons": "lucide-react"}})
        self.write("src/a.tsx", "import { Plus } from 'lucide-react'\nimport { FaX } from 'react-icons/fa'\n")
        self.write("package.json", '{\n  "dependencies": {\n    "@heroicons/react": "2.0.0"\n  }\n}\n')
        out = self.check().stdout
        self.assertIn("src/a.tsx:2 icon-set: react-icons", out)
        self.assertIn("package.json:3 icon-set: @heroicons/react", out)
        self.assertNotIn("src/a.tsx:1", out)

    def test_icon_sets_are_recognised_by_name_and_scope(self):
        self.contract({"ui": {"icons": "@fortawesome/react-native-fontawesome"}})
        self.write("src/a.tsx", "import { faX } from '@fortawesome/pro-light-svg-icons'\n"
                   "import { Icon } from '@acme/icons'\nimport { X } from '@/components/icons'\nimport Y from './icons/Y'\n")
        out = self.check().stdout
        self.assertNotIn("src/a.tsx:1", out)
        self.assertIn("src/a.tsx:2 icon-set: @acme/icons", out)
        self.assertNotIn("src/a.tsx:3", out)
        self.assertNotIn("src/a.tsx:4", out)

    def test_each_app_uses_its_own_ui(self):
        self.contract({"run": {"apps": [
            {"name": "mobile", "path": "apps/mobile", "ui": {"icons": "lucide-react-native"}},
            {"name": "web", "path": "apps/web", "ui": {"icons": "lucide-react", "tokens": ["apps/web/src/tokens.css"]}}]}})
        self.write("apps/mobile/a.tsx", "import { X } from 'lucide-react-native'\nconst c = '#123456'\n")
        self.write("apps/web/a.tsx", "import { X } from 'lucide-react-native'\n")
        self.write("packages/shared/a.ts", "const c = '#123456'\n")
        out = self.check().stdout
        self.assertNotIn("apps/mobile", out)
        self.assertIn("apps/web/a.tsx:1 icon-set: lucide-react-native", out)
        self.assertNotIn("packages/shared", out)


if __name__ == "__main__":
    unittest.main()
