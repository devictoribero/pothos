import datetime
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "devflow", "skills", "explain", "scripts", "artifact.py")


def run(args, cwd):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, capture_output=True, text=True)


class ArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "git@github.com:acme/shop.git"], check=True)
        os.environ["DEVFLOW_HOME"] = self.home
        os.environ["DEVFLOW_NO_OPEN"] = "1"
        self.base = os.path.join(self.home, "artifacts", "github.com", "acme", "shop")

    def tearDown(self):
        os.environ.pop("DEVFLOW_HOME", None)
        os.environ.pop("DEVFLOW_NO_OPEN", None)
        self.tmp.cleanup()

    def new(self, slug="checkout-flow", title="Checkout flow"):
        result = run(["new", "--slug", slug, "--title", title], self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_new_creates_a_private_folder_from_the_template(self):
        folder = self.new()
        self.assertEqual(folder, os.path.join(self.base, f"{datetime.date.today().isoformat()}-checkout-flow"))
        page = open(os.path.join(folder, "index.html")).read()
        self.assertIn("<title>Checkout flow</title>", page)
        self.assertIn('data-theme="light"', page)
        self.assertIn('id="theme-toggle"', page)
        self.assertTrue(os.path.isdir(os.path.join(folder, "diagrams")))
        self.assertEqual(os.listdir(self.repo), [".git"])

    def test_new_rejects_bad_slugs_and_reuses_existing_folders(self):
        self.assertEqual(run(["new", "--slug", "Bad Slug", "--title", "x"], self.repo).returncode, 64)
        first = self.new()
        again = run(["new", "--slug", "checkout-flow", "--title", "Checkout flow"], self.repo)
        self.assertEqual(again.stdout.strip(), first)
        self.assertIn("update it", again.stderr)

    def test_light_patches_archify_defaults(self):
        path = os.path.join(self.tmp.name, "d.html")
        with open(path, "w") as fh:
            fh.write('<html data-theme="dark"><script>t = window.matchMedia(\'(prefers-color-scheme: light)\').matches ? \'light\' : \'dark\'; f = function (e) { apply(e.matches ? \'light\' : \'dark\'); };</script>')
        self.assertEqual(run(["light", path], self.repo).returncode, 0)
        text = open(path).read()
        self.assertIn('data-theme="light"', text)
        self.assertIn("t = 'light';", text)
        self.assertNotIn("e.matches ? 'light' : 'dark'", text)

    def test_register_writes_one_line_per_artifact_and_list_prints_it(self):
        folder = self.new()
        self.assertEqual(run(["register", folder], self.repo).returncode, 1)
        with open(os.path.join(folder, "summary.md"), "w") as fh:
            fh.write("# Checkout charges the card after stock is reserved.\n\nMore facts.\n")
        self.assertEqual(run(["register", folder], self.repo).returncode, 0)
        self.assertEqual(run(["register", folder], self.repo).returncode, 0)
        index = open(os.path.join(self.base, "INDEX.md")).read()
        self.assertEqual(index.count("Checkout flow"), 1)
        self.assertIn("Checkout charges the card after stock is reserved.", index)
        self.assertIn("Checkout flow", run(["list"], self.repo).stdout)

    def test_put_writes_inside_the_folder_only(self):
        folder = self.new()
        ok = subprocess.run([sys.executable, SCRIPT, "put", folder, "summary.md"], input="# Hi\n", capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(open(os.path.join(folder, "summary.md")).read(), "# Hi\n")
        escape = subprocess.run([sys.executable, SCRIPT, "put", folder, "../../evil.md"], input="x", capture_output=True, text=True)
        self.assertEqual(escape.returncode, 1)
        outside = subprocess.run([sys.executable, SCRIPT, "put", self.repo, "x.md"], input="x", capture_output=True, text=True)
        self.assertEqual(outside.returncode, 1)
        self.assertEqual(os.listdir(self.repo), [".git"])

    def test_light_works_on_real_archify_output_and_refuses_unknown_pages(self):
        examples = os.path.join(ROOT, "plugins", "devflow", "skills", "archify", "examples")
        real = next(os.path.join(examples, f) for f in sorted(os.listdir(examples)) if f.endswith(".html"))
        copy = os.path.join(self.tmp.name, "real.html")
        with open(real) as src, open(copy, "w") as dst:
            dst.write(src.read())
        self.assertEqual(run(["light", copy], self.repo).returncode, 0)
        text = open(copy).read()
        self.assertNotIn("matches ? 'light' : 'dark'", text)
        self.assertEqual(run(["light", copy], self.repo).returncode, 0)  # idempotent
        plain = os.path.join(self.tmp.name, "plain.html")
        with open(plain, "w") as fh:
            fh.write("<html>x</html>")
        self.assertEqual(run(["light", plain], self.repo).returncode, 1)

    def test_index_is_sorted_newest_first(self):
        base = self.base
        for folder, title in [("2026-01-01-zebra", "Zebra old"), ("2026-10-08-alpha", "Alpha new")]:
            path = os.path.join(base, folder)
            os.makedirs(path)
            with open(os.path.join(path, "meta.json"), "w") as fh:
                fh.write('{"title": "%s", "created": "%s"}' % (title, folder[:10]))
            with open(os.path.join(path, "summary.md"), "w") as fh:
                fh.write("x\n")
            run(["register", path], self.repo)
        index = open(os.path.join(base, "INDEX.md")).read()
        self.assertLess(index.index("Alpha new"), index.index("Zebra old"))

    def test_put_refuses_folders_that_are_not_artifacts(self):
        folder = self.new()
        parent = os.path.dirname(folder)
        result = subprocess.run([sys.executable, SCRIPT, "put", parent, "INDEX.md"], input="pwned", capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_usage_errors_exit_64_and_lang_is_set(self):
        self.assertEqual(run(["new", "--slug"], self.repo).returncode, 64)
        folder = run(["new", "--slug", "en-page", "--title", "T", "--lang", "en"], self.repo).stdout.strip()
        self.assertIn('<html lang="en"', open(os.path.join(folder, "index.html")).read())

    def test_open_respects_no_open(self):
        folder = self.new()
        result = run(["open", os.path.join(folder, "index.html")], self.repo)
        self.assertIn("not opened", result.stdout)

    def test_outside_a_repository_uses_the_general_folder(self):
        outside = os.path.join(self.tmp.name, "loose")
        os.makedirs(outside)
        result = run(["new", "--slug", "idea", "--title", "Idea"], outside)
        self.assertIn(os.path.join("artifacts", "general"), result.stdout)


if __name__ == "__main__":
    unittest.main()
