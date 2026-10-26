import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "verify", "scripts", "verify.py")


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("remote", "add", "origin", "https://github.com/acme/shop.git")
        self.commit("first")
        self.env = {**os.environ, "POTHOS_HOME": self.home}
        self.addCleanup(self.tmp.cleanup)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", cwd or self.repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, name):
        with open(os.path.join(self.repo, f"{name}.txt"), "w") as fh:
            fh.write(name)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", name)

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, **data}, fh)

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)

    def test_without_contract_exits_2(self):
        self.assertEqual(self.run_script("run", "full").returncode, 2)

    def test_repo_workflow_exits_3(self):
        self.contract({"workflow": "repo"})
        self.assertEqual(self.run_script("run", "full").returncode, 3)

    def test_repo_workflow_without_a_mutation_command_refuses_mutation_and_says_what_would_run(self):
        self.contract({"workflow": "repo"})
        run = self.run_script("run", "mutation")
        self.assertEqual(run.returncode, 3)
        self.assertIn("Only `run mutation` runs here", run.stderr)

    def test_repo_workflow_runs_mutation_on_a_clean_tree_without_a_receipt(self):
        self.contract({"workflow": "repo", "verify": {"mutation": {"command": "touch mutation-ran"}}})
        self.branch_with("src/a.js")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        self.assertEqual(json.loads(self.run_script("show").stdout)["receipts"]["mutation"]["status"], "ran")
        self.assertEqual(self.run_script("run", "full").returncode, 3)
        self.assertEqual(self.run_script("check").returncode, 3)

    def test_repo_workflow_refuses_mutation_on_a_dirty_tree(self):
        self.contract({"workflow": "repo", "verify": {"mutation": {"command": "touch mutation-ran"}}})
        self.branch_with("src/a.js")
        self.add_file("src/b.js")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: commit first", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))

    def test_passing_full_run_writes_a_receipt_and_check_passes(self):
        self.contract({"verify": {"full": "echo all good"}})
        self.assertEqual(self.run_script("run", "full").returncode, 0)
        check = self.run_script("check")
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertIn("verified: full passed", check.stdout)
        shown = json.loads(self.run_script("show").stdout)
        self.assertEqual(shown["receipts"]["full"]["status"], "passed")
        with open(shown["receipts"]["full"]["log"]) as fh:
            self.assertIn("all good", fh.read())

    def test_ui_findings_are_recorded_but_never_block(self):
        self.contract({"verify": {"full": "echo ok"}, "ui": {"tokens": ["theme"]}})
        self.git("checkout", "-q", "-b", "feature")
        os.makedirs(os.path.join(self.repo, "src"))
        with open(os.path.join(self.repo, "src", "a.css"), "w") as fh:
            fh.write(".a { color: #123456; }\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "raw color")
        run = self.run_script("run", "full")
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertIn("src/a.css:1 raw-color: #123456", run.stdout)
        self.assertIn("advisory, does not block", run.stdout)
        check = self.run_script("check")
        self.assertEqual(check.returncode, 0)
        self.assertIn("ui: 1 advisory finding(s)", check.stdout)
        shown = json.loads(self.run_script("show").stdout)
        self.assertEqual(shown["receipts"]["ui"]["status"], "findings")

    def test_ui_check_still_runs_and_records_when_full_fails(self):
        self.contract({"verify": {"full": "exit 1"}, "ui": {"icons": "lucide-react"}})
        run = self.run_script("run", "full")
        self.assertEqual(run.returncode, 1)
        self.assertIn("ui: clean", run.stdout)

    def test_without_ui_the_check_is_skipped(self):
        self.contract({"verify": {"full": "echo ok"}})
        run = self.run_script("run", "all")
        self.assertEqual(run.returncode, 0)
        self.assertIn("ui: skipped", run.stdout)

    def test_failing_run_exits_1_and_prints_the_tail(self):
        self.contract({"verify": {"full": "echo boom-line; exit 3"}})
        result = self.run_script("run", "full")
        self.assertEqual(result.returncode, 1)
        self.assertIn("boom-line", result.stdout)
        self.assertEqual(self.run_script("check").returncode, 1)

    def test_a_new_commit_needs_a_new_receipt(self):
        self.contract({"verify": {"full": "true"}})
        self.run_script("run", "full")
        self.commit("second")
        check = self.run_script("check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("no full receipt", check.stdout)

    def test_dirty_tree_run_does_not_count(self):
        self.contract({"verify": {"full": "true"}})
        with open(os.path.join(self.repo, "first.txt"), "w") as fh:
            fh.write("changed")
        result = self.run_script("run", "full")
        self.assertIn("does not count", result.stdout)
        self.git("checkout", "--", "first.txt")
        self.assertIn("ran on a dirty tree", self.run_script("check").stdout)

    def test_local_tracker_folder_does_not_make_the_tree_dirty(self):
        self.contract({"verify": {"full": "true"}, "tracker": {"kind": "local", "path": ".scratch"}})
        os.makedirs(os.path.join(self.repo, ".scratch", "login", "issues"))
        with open(os.path.join(self.repo, ".scratch", "login", "issues", "01-form.md"), "w") as fh:
            fh.write("Status: claimed")
        self.run_script("run", "full")
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_missing_e2e_is_skipped_and_does_not_block(self):
        self.contract({"verify": {"full": "true"}})
        result = self.run_script("run", "all")
        self.assertEqual(result.returncode, 0)
        self.assertIn("e2e: skipped", result.stdout)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_configured_e2e_is_required_by_check(self):
        self.contract({"verify": {"full": "true", "e2e": "true"}})
        self.run_script("run", "full")
        self.assertIn("no e2e receipt", self.run_script("check").stdout)
        self.run_script("run", "e2e")
        self.assertEqual(self.run_script("check").returncode, 0)
        self.assertEqual(self.run_script("check", "--no-e2e").returncode, 0)

    def test_environment_specific_e2e_needs_an_env(self):
        self.contract({"verify": {"full": "true"},
                       "run": {"environments": [{"name": "dev", "dev": "x", "e2e": "echo e2e-on-dev"},
                                                {"name": "demo", "dev": "y", "e2e": "echo e2e-on-demo"}]}})
        self.assertEqual(self.run_script("run", "e2e").returncode, 3)
        self.assertEqual(self.run_script("run", "e2e", "--env", "nope").returncode, 3)
        result = self.run_script("run", "e2e", "--env", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.run_script("show").stdout)["receipts"]["e2e"]["env"], "demo")

    def test_a_slow_run_outlives_the_caller_and_wait_picks_it_up(self):
        self.contract({"verify": {"full": "sleep 3 && echo slow but fine"}})
        first = self.run_script("run", "full", "--wait", "1")
        self.assertEqual(first.returncode, 4, first.stdout)
        self.assertIn("verify.py wait", first.stdout)
        again = self.run_script("run", "full", "--wait", "0")
        self.assertIn("already going", again.stdout)
        self.assertEqual(again.returncode, 4)
        waited = self.run_script("wait", "--wait", "30")
        self.assertEqual(waited.returncode, 0, waited.stdout)
        self.assertIn("full: passed", waited.stdout)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_wait_reports_a_failed_background_run(self):
        self.contract({"verify": {"full": "sleep 2 && exit 5"}})
        self.assertEqual(self.run_script("run", "full", "--wait", "0").returncode, 4)
        waited = self.run_script("wait", "--wait", "30")
        self.assertEqual(waited.returncode, 1)
        self.assertIn("full: failed", waited.stdout)

    def test_wait_without_a_run_exits_1(self):
        self.contract({"verify": {"full": "true"}})
        self.assertEqual(self.run_script("wait").returncode, 1)

    def test_mutation_refuses_to_start_without_a_passing_fast_or_full_receipt(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch mutation-ran"}}})

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: run fast or full first", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        self.assertNotIn("mutation", json.loads(self.run_script("show").stdout)["receipts"])

    def add_file(self, rel, text="x = 1\n", cwd=None):
        path = os.path.join(cwd or self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def branch_with(self, *files, message="change"):
        self.git("checkout", "-q", "-b", "feature")
        for rel in files:
            self.add_file(rel)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_mutation_is_skipped_when_only_test_files_or_excluded_files_changed(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch mutation-ran", "exclude": ["src/generated/*"]}}})
        self.branch_with("src/a.test.js", "src/b.spec.ts", "src/__tests__/c.js", "src/generated/f.js")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: skipped (no source files changed)", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "skipped")
        self.assertEqual(receipt["reason"], "no source files changed")

    def test_mutation_command_receives_the_changed_files_and_the_output_folder(self):
        command = ('printf "%s" "$POTHOS_CHANGED_FILES" > "$POTHOS_MUTATION_OUT/seen-files"; '
                   'printf "%s" "$POTHOS_MUTATION_OUT" > "$POTHOS_MUTATION_OUT/seen-out"; '
                   'printf "%s" {files} > "$POTHOS_MUTATION_OUT/seen-placeholder"')
        self.contract({"verify": {"full": "true", "mutation": {"command": command}}})
        self.branch_with("src/a.py", "src/sp ace.py", "src/a.test.py")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: ran in", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        folder = os.path.dirname(receipt["log"])
        with open(os.path.join(folder, "seen-files")) as fh:
            self.assertEqual(fh.read(), "src/a.py\nsrc/sp ace.py")
        with open(os.path.join(folder, "seen-out")) as fh:
            self.assertEqual(fh.read(), folder)
        with open(os.path.join(folder, "seen-placeholder")) as fh:
            self.assertEqual(fh.read(), "src/a.py,src/sp ace.py")
        self.assertEqual(receipt["status"], "ran")
        self.assertEqual(receipt["files"], ["src/a.py", "src/sp ace.py"])
        self.assertEqual(receipt["exit"], 0)
        self.assertIn("src/a.py,'src/sp ace.py'", receipt["command"])
        self.assertGreaterEqual(receipt["seconds"], 0)
        self.assertFalse(receipt["dirty_before"])
        self.assertFalse(receipt["dirty_after"])

    def test_a_file_moved_and_edited_on_the_branch_is_mutated_under_its_new_path(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "true"}}})
        self.add_file("src/old.py", "a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "seed")
        self.git("checkout", "-q", "-b", "feature")
        self.git("mv", "src/old.py", "src/new.py")
        self.add_file("src/new.py", "a = 1\nb = 2\nc = 3\nd = 4\ne = 6\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "move")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.mutation_receipt()["files"], ["src/new.py"])

    def test_mutation_command_that_fails_yields_an_error_receipt_and_the_log_tail(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "echo mutant-boom; exit 7"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutant-boom", run.stdout)
        self.assertIn("mutation: error in", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "error")
        self.assertEqual(receipt["exit"], 7)

    def test_mutation_command_that_leaves_a_file_behind_is_recorded_as_dirty_after(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch leftover.tmp"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: the command left changes in the working tree", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertFalse(receipt["dirty_before"])
        self.assertTrue(receipt["dirty_after"])

    def test_a_tree_dirty_before_the_command_gets_a_warning_that_says_so(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "true"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "full")
        self.add_file("notes.tmp", "uncommitted")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: the working tree has uncommitted changes, already there before the command", run.stdout)
        receipt = self.mutation_receipt()
        self.assertTrue(receipt["dirty_before"])
        self.assertTrue(receipt["dirty_after"])

    def test_mutation_measures_against_the_newer_of_local_and_remote_base(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "printf '%s' \"$POTHOS_CHANGED_FILES\" > \"$POTHOS_MUTATION_OUT/seen\""}}})
        # Stale local main: the branch builds on a commit origin/main has and the local main does not.
        self.add_file("src/old.js")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "landed upstream")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.branch_with("src/new.js")
        self.git("update-ref", "refs/heads/main", "main~1")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["files"], ["src/new.js"])

    def test_mutation_without_a_base_branch_is_an_error(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch mutation-ran"}}})
        self.git("branch", "-m", "main", "trunk")
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: no base branch found", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        self.assertEqual(json.loads(self.run_script("show").stdout)["receipts"]["mutation"]["status"], "error")

    def test_run_all_never_runs_mutation(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "touch mutation-ran; exit 1"}}})
        self.branch_with("src/a.py")

        run = self.run_script("run", "all")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("mutation", run.stdout)
        self.assertFalse(os.path.exists(self.repo + "/mutation-ran"))

    def test_check_ignores_a_mutation_receipt_in_error(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "exit 1"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "full")
        self.assertEqual(self.run_script("run", "mutation").returncode, 1)

        check = self.run_script("check")

        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertIn("verified: full passed", check.stdout)
        self.assertEqual(self.mutation_receipt()["status"], "error")

    def test_a_slow_mutation_run_is_picked_up_by_wait(self):
        self.contract({"verify": {"full": "true", "mutation": {"command": "sleep 3 && echo slow mutants"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "full")

        first = self.run_script("run", "mutation", "--wait", "1")

        self.assertEqual(first.returncode, 4, first.stdout)
        waited = self.run_script("wait", "--wait", "30")
        self.assertEqual(waited.returncode, 0, waited.stdout)
        self.assertIn("mutation: ran in", waited.stdout)
        self.assertEqual(json.loads(self.run_script("show").stdout)["receipts"]["mutation"]["status"], "ran")

    # A fake mutation tool: records what it finds in the cache, where the cache is, then writes its own entry.
    CACHE_COMMAND = ('cat "$POTHOS_MUTATION_CACHE/seen" > "$POTHOS_MUTATION_OUT/cache-before" 2>/dev/null; '
                     'printf "%s" "$POTHOS_MUTATION_CACHE" > "$POTHOS_MUTATION_OUT/cache-path"; '
                     'printf "%s" "$POTHOS_CHANGED_FILES" > "$POTHOS_MUTATION_CACHE/seen"')

    def second_worktree(self, *files):
        """Another worktree of the same repository, on its own branch off main, with its own passing fast receipt."""
        path = os.path.join(self.tmp.name, "worktree-2")
        self.git("worktree", "add", "-q", "-b", "feature-2", path, "main")
        for rel in files:
            self.add_file(rel, cwd=path)
        self.git("add", "-A", cwd=path)
        self.git("commit", "-q", "-m", "change in the second worktree", cwd=path)
        self.run_script("run", "fast", cwd=path)
        return path

    def mutation_receipt(self, cwd=None):
        return json.loads(self.run_script("show", cwd=cwd).stdout)["receipts"]["mutation"]

    def output_file(self, receipt, name):
        with open(os.path.join(os.path.dirname(receipt["log"]), name)) as fh:
            return fh.read()

    def test_a_second_worktree_sees_the_cache_a_successful_run_left_behind(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")
        first = self.run_script("run", "mutation")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        other = self.second_worktree("src/b.py")

        run = self.run_script("run", "mutation", cwd=other)

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        receipt = self.mutation_receipt(cwd=other)
        self.assertEqual(self.output_file(receipt, "cache-before"), "src/a.py")
        self.assertEqual(self.output_file(self.mutation_receipt(), "cache-before"), "")
        self.assertEqual(receipt["cache"], os.path.join(self.home, "mutation", "github.com", "acme", "shop"))
        self.assertEqual(receipt["cache"], self.mutation_receipt()["cache"])

    def test_a_failing_run_leaves_the_shared_cache_untouched(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")
        self.run_script("run", "mutation")
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND + "; exit 3"}}})
        other = self.second_worktree("src/b.py")

        run = self.run_script("run", "mutation", cwd=other)

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(self.output_file(self.mutation_receipt(cwd=other), "cache-before"), "src/a.py")
        with open(os.path.join(self.mutation_receipt()["cache"], "seen")) as fh:
            self.assertEqual(fh.read(), "src/a.py")

    def test_the_command_works_on_a_private_copy_under_its_own_receipt_folder(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        receipt = self.mutation_receipt()
        seen = self.output_file(receipt, "cache-path")
        self.assertEqual(seen, os.path.join(os.path.dirname(receipt["log"]), "mutation-cache"))
        self.assertNotEqual(seen, receipt["cache"])
        self.assertEqual(receipt["env"]["POTHOS_MUTATION_CACHE"], seen)

    def test_a_successful_run_removes_its_private_copy_once_the_cache_is_published(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        receipt = self.mutation_receipt()
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(receipt["log"]), "mutation-cache")))
        with open(os.path.join(receipt["cache"], "seen")) as fh:
            self.assertEqual(fh.read(), "src/a.py")

    def test_a_failing_run_removes_its_private_copy_too(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND + "; exit 3"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        receipt = self.mutation_receipt()
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(receipt["log"]), "mutation-cache")))
        self.assertEqual(receipt["cache"], os.path.join(self.home, "mutation", "github.com", "acme", "shop"))

    def test_publishing_covers_subfolders_and_leaves_no_temporary_name_behind(self):
        command = self.CACHE_COMMAND + '; mkdir -p "$POTHOS_MUTATION_CACHE/nested"; echo deep > "$POTHOS_MUTATION_CACHE/nested/deep"'
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": command}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        shared = self.mutation_receipt()["cache"]
        published = sorted(os.path.relpath(os.path.join(folder, name), shared)
                           for folder, _, names in os.walk(shared) for name in names)
        self.assertEqual(published, ["nested/deep", "seen"])

    def test_a_broken_shared_cache_is_an_error_receipt_and_the_command_never_runs(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": "touch mutation-ran"}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")
        shared = os.path.join(self.home, "mutation", "github.com", "acme", "shop")
        os.makedirs(os.path.dirname(shared))
        with open(shared, "w") as fh:
            fh.write("not a folder")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: could not prepare the cache", run.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "mutation-ran")))
        receipt = self.mutation_receipt()
        self.assertEqual(receipt["status"], "error")
        self.assertEqual(receipt["cache"], shared)
        self.assertIn("File exists", receipt["error"])

    def test_a_cache_that_cannot_be_published_is_an_error_receipt(self):
        self.contract({"verify": {"fast": "echo ok", "mutation": {"command": self.CACHE_COMMAND}}})
        self.branch_with("src/a.py")
        self.run_script("run", "fast")
        self.run_script("run", "mutation")
        shared = self.mutation_receipt()["cache"]
        other = self.second_worktree("src/b.py")
        os.chmod(shared, 0o555)
        self.addCleanup(os.chmod, shared, 0o755)

        run = self.run_script("run", "mutation", cwd=other)

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: could not publish the cache", run.stdout)
        receipt = self.mutation_receipt(cwd=other)
        self.assertEqual(receipt["status"], "error")
        self.assertEqual(receipt["exit"], 0)
        self.assertIn("Permission denied", receipt["error"])
        with open(os.path.join(shared, "seen")) as fh:
            self.assertEqual(fh.read(), "src/a.py")

    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_script("run").returncode, 64)
        self.assertEqual(self.run_script("frobnicate").returncode, 64)
        self.assertEqual(self.run_script().returncode, 64)

    def mutation_tool(self, report, name="report.json"):
        """A fake mutation command: a shell script that writes the given report into the run's output folder."""
        script = os.path.join(self.tmp.name, "mutate.sh")
        with open(script, "w") as fh:
            fh.write('#!/bin/sh\ncat > "$POTHOS_MUTATION_OUT/%s" <<\'REPORT\'\n%s\nREPORT\n' % (name, json.dumps(report)))
        os.chmod(script, 0o755)
        return script


    def modify_on_a_branch(self, rel, before, after):
        """A file committed on main with `before`, then changed to `after` on a feature branch."""
        self.add_file(rel, before)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "seed " + rel)
        self.git("checkout", "-q", "-b", "feature")
        self.add_file(rel, after)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change " + rel)


    @staticmethod
    def mutant(line, status, column=5, mutator="ArithmeticOperator", replacement="5"):
        return {"id": f"{line}-{status}", "mutatorName": mutator, "replacement": replacement, "status": status,
                "location": {"start": {"line": line, "column": column}, "end": {"line": line, "column": column + 1}}}


    def test_survivors_on_added_lines_are_new_and_printed_and_the_rest_inherited(self):
        source = "a = 1\nb = 2\nc = 3\nd = 4\n"
        self.modify_on_a_branch("src/a.py", "a = 1\nb = 2\nc = 3\n", source)
        report = {"schemaVersion": "2", "files": {"src/a.py": {"language": "python", "source": source,
                  "mutants": [self.mutant(1, "Survived"), self.mutant(4, "Survived")]}}}
        self.contract({"verify": {"full": "true", "mutation": {
            "command": self.mutation_tool(report), "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("src/a.py:4 ArithmeticOperator: 4 -> 5 (Survived)", run.stdout)
        self.assertNotIn("src/a.py:1", run.stdout)
        self.assertIn("mutation: 1 new surviving mutant(s) in 1 changed file(s); 1 inherited, see verify.py show. "
                      "Advisory, does not block. Each new one is a missing test or dead code.", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "findings")
        self.assertEqual(receipt["findings"], [
            {"file": "src/a.py", "line": 4, "kind": "new", "mutator": "ArithmeticOperator",
             "original": "4", "replacement": "5", "status": "Survived"},
            {"file": "src/a.py", "line": 1, "kind": "inherited", "mutator": "ArithmeticOperator",
             "original": "1", "replacement": "5", "status": "Survived"}])
        self.assertEqual(receipt["counts"], {"Survived": 2})
        self.assertEqual(receipt["report"], os.path.join(os.path.dirname(receipt["log"]), "report.json"))


    def test_report_keys_under_a_project_root_still_match_the_changed_files(self):
        self.branch_with("src/a.py", "src/b.py")
        report = {"schemaVersion": "2", "projectRoot": self.repo, "files": {
            os.path.join(self.repo, "src", "a.py"): {"language": "python", "mutants": [self.mutant(1, "Survived")]},
            "src/b.py": {"language": "python", "mutants": [self.mutant(1, "NoCoverage", replacement=None)]}}}
        self.contract({"verify": {"full": "true", "mutation": {
            "command": self.mutation_tool(report), "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("src/a.py:1 ArithmeticOperator: 5 (Survived)", run.stdout)
        self.assertIn("src/b.py:1 ArithmeticOperator (NoCoverage)", run.stdout)
        self.assertIn("mutation: 2 new surviving mutant(s) in 2 changed file(s); 0 inherited", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual([f["file"] for f in receipt["findings"]], ["src/a.py", "src/b.py"])
        self.assertNotIn("original", receipt["findings"][0])
        self.assertNotIn("replacement", receipt["findings"][1])


    def test_mutants_outside_the_changed_files_are_dropped_and_every_status_counted(self):
        self.add_file("src/legacy.py")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "legacy")
        self.branch_with("src/a.py")
        statuses = ["Killed", "Survived", "NoCoverage", "Timeout", "Ignored", "CompileError", "RuntimeError", "Pending",
                    "Ignored"]
        report = {"schemaVersion": "2", "files": {
            "src/a.py": {"language": "python", "mutants": [self.mutant(1, status) for status in statuses]},
            "src/legacy.py": {"language": "python", "mutants": [self.mutant(1, "Survived")]},
            "src/elsewhere.py": {"language": "python", "mutants": [self.mutant(1, "NoCoverage")]}}}
        self.contract({"verify": {"full": "true", "mutation": {
            "command": self.mutation_tool(report), "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("legacy", run.stdout)
        self.assertNotIn("elsewhere", run.stdout)
        self.assertIn("mutation: 2 new surviving mutant(s) in 1 changed file(s); 0 inherited", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["counts"], {"Killed": 1, "Survived": 1, "NoCoverage": 1, "Timeout": 1, "Ignored": 2,
                                             "CompileError": 1, "RuntimeError": 1, "Pending": 1})
        self.assertEqual([(f["file"], f["status"]) for f in receipt["findings"]],
                         [("src/a.py", "Survived"), ("src/a.py", "NoCoverage")])


    def test_an_empty_report_is_clean_and_check_carries_no_note(self):
        self.branch_with("src/a.py")
        self.contract({"verify": {"full": "true", "mutation": {
            "command": self.mutation_tool({"schemaVersion": "2", "files": {}}),
            "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: 0 new surviving mutant(s) in 1 changed file(s); 0 inherited", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "clean")
        self.assertEqual(receipt["findings"], [])
        self.assertEqual(receipt["counts"], {})
        check = self.run_script("check")
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertNotIn("mutation", check.stdout)


    def test_a_report_the_command_never_wrote_keeps_the_receipt_at_ran(self):
        self.branch_with("src/a.py")
        self.contract({"verify": {"full": "true", "mutation": {
            "command": self.mutation_tool({"schemaVersion": "2", "files": {}}, name="elsewhere.json"),
            "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("mutation: ran in", run.stdout)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "ran")
        self.assertNotIn("findings", receipt)
        self.assertNotIn("report", receipt)


    def test_a_report_that_is_not_json_is_an_error_without_a_traceback(self):
        self.branch_with("src/a.py")
        self.contract({"verify": {"full": "true", "mutation": {
            "command": 'echo "not json" > "$POTHOS_MUTATION_OUT/report.json"',
            "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")

        run = self.run_script("run", "mutation")

        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("mutation: could not read the report", run.stdout)
        self.assertNotIn("Traceback", run.stdout + run.stderr)
        receipt = json.loads(self.run_script("show").stdout)["receipts"]["mutation"]
        self.assertEqual(receipt["status"], "error")
        self.assertIn("report.json", receipt["error"])
        self.assertEqual(receipt["exit"], 0)


    def test_check_passes_and_its_verified_line_ends_with_the_mutation_note_when_new_survivors_exist(self):
        source = "a = 1\nb = 2\n"
        self.modify_on_a_branch("src/a.py", "a = 1\n", source)
        report = {"schemaVersion": "2", "files": {"src/a.py": {"language": "python", "source": source,
                  "mutants": [self.mutant(1, "Survived"), self.mutant(2, "Survived"), self.mutant(2, "NoCoverage")]}}}
        self.contract({"verify": {"full": "true", "mutation": {
            "command": self.mutation_tool(report), "report": "$POTHOS_MUTATION_OUT/report.json"}}})
        self.run_script("run", "full")
        self.run_script("run", "mutation")

        check = self.run_script("check")

        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertTrue(check.stdout.endswith("; mutation: 2 new survivor(s), see verify.py show\n"), check.stdout)
        self.assertIn("verified: full passed on", check.stdout)


if __name__ == "__main__":
    unittest.main()
