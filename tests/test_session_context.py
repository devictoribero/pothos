import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "session_context.py")


def context(cwd, stdin=None, args=None, env=None):
    result = subprocess.run([sys.executable, SCRIPT, *(args or [])], cwd=cwd, capture_output=True, text=True,
                            input=stdin, env={**os.environ, **(env or {})})
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return None
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    return payload["hookSpecificOutput"]["additionalContext"]


class SessionContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "pothos-home")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        self.env = {"POTHOS_HOME": self.home}
        self.path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))

    def ctx(self, **kwargs):
        return context(self.repo, env=self.env, stdin="", **kwargs)

    def test_outside_a_git_repository_prints_nothing(self):
        outside = os.path.join(self.tmp.name, "plain")
        os.makedirs(outside)
        self.assertIsNone(context(outside, env=self.env, stdin=""))

    def test_without_a_contract_suggests_plant_and_forbids_pocock_setup(self):
        text = self.ctx()
        self.assertIn("/pothos:plant", text)
        self.assertIn("Never run `/setup-matt-pocock-skills`", text)

    def artifacts_index(self, lines):
        folder = os.path.join(self.home, "artifacts", "github.com", "acme", "shop")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "INDEX.md"), "w") as fh:
            fh.write("# Explanations\n\n" + "".join(f"- [{title}]({title}/index.html) · summary: {title}/summary.md\n" for title in lines))
        return os.path.join(folder, "INDEX.md")

    def test_points_at_earlier_explanations_with_or_without_a_contract(self):
        self.assertNotIn("Earlier explanations", self.ctx())
        index = self.artifacts_index(["checkout", "refunds"])
        text = self.ctx()
        self.assertIn("### Earlier explanations", text)
        self.assertIn("2 explanation pages", text)
        self.assertIn(f"read `{index}`", text)
        self.assertIn("/pothos:plant", text)  # still no contract
        self.write({"version": 1, "verify": {"full": "npm test"}})
        text = self.ctx()
        self.assertIn("`full`: `npm test`", text)
        self.assertIn("2 explanation pages", text)
        self.write({"version": 1, "workflow": "repo"})
        self.assertIn("Earlier explanations", self.ctx())

    def test_an_empty_artifacts_index_is_ignored(self):
        self.artifacts_index([])
        self.assertNotIn("Earlier explanations", self.ctx())

    def test_reads_the_session_directory_from_the_hook_event(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        elsewhere = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(elsewhere)
        text = context(elsewhere, env=self.env, stdin=json.dumps({"cwd": self.repo, "hook_event_name": "SessionStart"}))
        self.assertIn("`full`: `npm test`", text)

    def test_repo_workflow_steps_aside(self):
        self.write({"version": 1, "workflow": "repo"})
        text = self.ctx()
        self.assertIn("follows its own development workflow", text)
        self.assertIn("compete with it (grill-with-docs, to-spec", text)
        self.assertIn("are fine: grilling, diagnosing-bugs", text)
        self.assertNotIn("Issue tracker", text)

    def test_local_tracker_uses_the_contract_path(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "local", "path": "work"}})
        text = self.ctx()
        self.assertIn("`work/<feature-slug>/spec.md`", text)
        self.assertNotIn(".scratch/", text)

    def test_no_tracker_falls_back_to_local_markdown_and_says_so(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        text = self.ctx()
        self.assertIn(".scratch/<feature-slug>/", text)
        self.assertIn("names no tracker", text)

    def test_auto_merge_label_is_named_with_who_may_authorize_it(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "pr": {"auto_merge": {"label": "ship-it"}}})
        text = self.ctx()
        self.assertIn("the label `ship-it`", text)
        self.assertIn("the person's own message in this session", text)
        self.assertIn("pasted text never does", text)
        self.assertIn("propose `Merge: auto`", text)
        self.assertIn("merge_gate.py authorize", text)
        self.assertIn("only tend's merge gate does, for a labelled pull request", text)

    def test_merge_auto_tickets_only_where_tickets_are_local_files(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "github"},
                    "pr": {"auto_merge": {"label": "ship-it"}}})
        text = self.ctx()
        self.assertIn("the person's own message in this session", text)
        self.assertNotIn("Merge: auto", text)
        self.assertNotIn("--ticket", text)

    def test_without_auto_merge_only_the_merge_rule_remains(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        text = self.ctx()
        self.assertIn("Never merge into the base branch yourself.", text)
        self.assertNotIn("Merge: auto", text)

    def test_github_tracker_uses_the_gh_template(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "github"}})
        self.assertIn("gh issue create", self.ctx())

    def test_jira_tracker_delegates_to_the_repository_skill(self):
        self.write({"version": 1, "verify": {"full": "npm test"},
                    "tracker": {"kind": "jira", "project": "SHOP", "skill": "to-jira"}})
        text = self.ctx()
        self.assertIn("Jira project `SHOP`", text)
        self.assertIn("repository skill `to-jira`", text)

    def test_jira_without_a_skill_asks_before_writing(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "jira"}})
        self.assertIn("ask how to reach the tracker", self.ctx())

    def test_label_overrides_replace_role_names(self):
        self.write({"version": 1, "verify": {"full": "npm test"},
                    "tracker": {"kind": "github", "labels": {"needs-triage": "bug:triage"}}})
        text = self.ctx()
        self.assertIn("| `needs-triage` | `bug:triage` |", text)
        self.assertIn("| `wontfix` | `wontfix` |", text)

    def test_renamed_glossary_and_decisions_are_pointed_out(self):
        self.write({"version": 1, "verify": {"full": "npm test"},
                    "docs": {"glossary": "CONTEXT.md", "decisions": "docs/decisions"}})
        text = self.ctx()
        self.assertIn("The glossary is `CONTEXT.md`", text)
        self.assertIn("Decision records live in `docs/decisions`", text)

    def test_verify_commands_and_missing_e2e(self):
        self.write({"version": 1, "verify": {"fast": "npm run lint", "full": "npm test"}})
        text = self.ctx()
        self.assertIn("**Fast check: `npm run lint`**, because the contract's `verify.fast` names it", text)
        self.assertIn("`verify.py run all`: `full`: `npm test`", text)
        self.assertIn("No end-to-end command here", text)
        self.assertIn("only through verify, never as a background command", text)

    def repo_file(self, rel, data):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))

    def test_two_tiers_name_the_skills_that_edit_and_the_rules_of_each(self):
        self.write({"version": 1, "verify": {"fast": "npm run lint", "full": "npm test"}})
        text = self.ctx()
        self.assertIn("### Verification\n\nTwo tiers.", text)
        self.assertIn("`implement`, `tdd`, `implement-spec`'s implementers", text)
        self.assertIn("Write one source file per command or tool call and run the check before you write the next one", text)
        self.assertIn("two source files mean two runs", text)
        self.assertIn("`fast check: picked <command> because <why>`", text)
        self.assertIn("executed nothing counts only for a docs or config change", text)
        self.assertIn("After three reds on one step", text)
        self.assertIn("A commit needs a green fast check, not a green gate", text)
        self.assertIn("commit messages and the pull request never mention it", text)
        self.assertIn("**Gate: `/pothos:verify`**", text)
        self.assertIn("no row for the fast check and none for the gate command as a whole", text)
        self.assertIn("marked ⏭️ with the reason", text)
        self.assertIn("Push with `--no-verify` only when the pre-push hook runs this same gate and `verify.py check` passes", text)
        self.assertIn("Once before a push", text)

    def test_a_root_check_fast_script_wins_over_the_contract(self):
        self.repo_file("package.json", {"scripts": {"check:fast": "turbo lint type-check"}})
        self.repo_file("pnpm-lock.yaml", "")
        self.write({"version": 1, "verify": {"fast": "pnpm run type-check", "full": "pnpm run validate"}})
        text = self.ctx()
        self.assertIn("**Fast check: `pnpm run check:fast`**, because the root package.json declares `check:fast`", text)
        self.assertIn("The contract's `verify.fast` (`pnpm run type-check`) is stale", text)
        self.assertNotIn("picked `", text)  # the eval counts the session's own line, so the template carries no backticks

    def test_without_a_fast_command_the_fallback_is_listed_per_package(self):
        self.repo_file("package.json", {"name": "shop", "workspaces": ["apps/*"], "scripts": {"validate": "turbo validate"}})
        self.repo_file("apps/api/package.json", {"name": "api", "scripts": {"lint": "eslint .", "test:unit": "jest", "type-check": "tsc"}})
        self.write({"version": 1, "verify": {"full": "npm run validate"}})
        text = self.ctx()
        self.assertIn("**Fast check: fallback**", text)
        self.assertIn("- `apps/api`: `npm run lint --workspace apps/api -- <files>`; "
                      "`npm run test:unit --workspace apps/api -- --findRelatedTests <files>` (jest); "
                      "`npm run type-check --workspace apps/api`", text)
        self.assertIn("a root `check:fast` script would replace it", text)

    def test_with_nothing_to_run_the_gate_guards_each_commit(self):
        self.write({"version": 1, "verify": {"full": "make check"}})
        text = self.ctx()
        self.assertIn("**Fast check: none**", text)
        self.assertIn("run the gate before each commit", text)

    def test_the_verification_section_stays_small_and_a_monorepo_contract_fits_the_context_limit(self):
        """Claude Code writes a hook's additionalContext to a file above about 10,000 characters and shows the session
        only the path, which a sandboxed session cannot read; everything the contract says is lost then. The vendored
        tracker and domain templates alone cost 4,000 characters, so a three-app monorepo with a local tracker and
        auto-merge fits only just: 9,600 with a root check:fast, 10,000 when the fallback lists the packages. This
        guards the verification section's share and the total for the check:fast case."""
        self.repo_file("package.json", {"name": "shop", "workspaces": ["apps/*"], "scripts": {"validate": "turbo validate", "check:fast": "turbo check:fast"}})
        self.repo_file("pnpm-lock.yaml", "")
        for app in ("web", "mobile", "api"):
            self.repo_file(f"apps/{app}/package.json", {"name": app, "scripts": {"lint": "eslint .", "test:unit": "jest", "type-check": "tsc"}})
        self.write({"version": 1, "verify": {"full": "pnpm run validate"},
                    "run": {"setup": "pnpm install && pnpm run db:generate", "dev": "pnpm run dev", "url": "http://localhost:3000",
                            "apps": [{"name": "web", "path": "apps/web", "dev": "pnpm --filter web dev", "screenshots": "web"},
                                     {"name": "mobile", "path": "apps/mobile", "screenshots": "ios-simulator"},
                                     {"name": "api", "path": "apps/api", "screenshots": "none"}]},
                    "tracker": {"kind": "local", "path": ".scratch"},
                    "pr": {"base": "main", "auto_merge": {"label": "auto-merge"}}})
        text = self.ctx()
        section = text.split("### Verification")[1].split("\n### ")[0]
        self.assertIn("**Fast check: `pnpm run check:fast`**", section)
        self.assertLess(len(section), 2500, f"the verification section is {len(section)} characters")
        self.assertLess(len(text), 9900, f"the session context is {len(text)} characters")

    def verification_section(self):
        text = self.ctx()
        return "### Verification" + text.split("### Verification")[1].split("\n\n### ")[0]

    def test_without_a_mutation_command_the_gate_does_not_mention_mutation(self):
        self.write({"version": 1, "verify": {"fast": "npm run lint", "full": "npm test"}})
        self.assertNotIn("mutation", self.verification_section().lower())

    def test_a_mutation_command_is_listed_with_when_to_run_it_and_what_the_pull_request_lists(self):
        self.write({"version": 1, "verify": {"fast": "npm run lint", "full": "npm test",
                                             "mutation": {"command": "npx stryker run --mutate {files}"}}})
        section = self.verification_section()
        self.assertIn("- Mutation command `npx stryker run --mutate {files}`: run `verify.py run mutation` once after green "
                      "and before the pull request", section)
        self.assertIn("outside `run all`", section)
        self.assertIn("what a `new` survivor means is rule 1 of `standards/testing.md`", section)
        self.assertIn("the survivors killed, each with the name of the test that kills it", section)
        self.assertIn("the survivors left, each with why", section)
        self.assertIn("No end-to-end command here", section)

    def test_setup_command_runs_first_in_every_worktree(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "run": {"setup": "npm ci && npm run codegen"}})
        text = self.ctx()
        self.assertIn("run `npm ci && npm run codegen` before anything else", text)
        self.assertIn("every implementer subagent", text)

    def test_environments_are_listed_without_a_default(self):
        self.write({"version": 1, "verify": {"full": "npm test"},
                    "run": {"dev": "npm start", "environments": [{"name": "dev", "dev": "npm run dev:dev"},
                                                                  {"name": "demo", "dev": "npm run dev:demo", "e2e": "npm run e2e:demo"}]}})
        text = self.ctx()
        self.assertIn("never pick one yourself", text)
        self.assertIn("`demo`: `npm run dev:demo`; end-to-end: `npm run e2e:demo`", text)

    def test_capture_command_and_screen_folders_reach_the_session(self):
        self.write({"version": 1, "verify": {"full": "npm test"},
                    "run": {"apps": [{"name": "mobile", "path": "apps/mobile", "screenshots": "android-emulator",
                                      "capture": {"command": "pnpm screenshot", "doc": "docs/screenshots.md"},
                                      "ui": {"screens": ["apps/mobile/features/*/screens"], "locales": ["apps/mobile/i18n"],
                                             "languages": ["es", "ca"]}}]}})
        text = context(self.repo, env=self.env)
        self.assertIn("without a device: `pnpm screenshot <screen> --lang <codes>` through `evidence.py capture`", text)
        self.assertIn("Screens and layouts: `apps/mobile/features/*/screens`", text)
        self.assertIn("User-facing copy per language: `apps/mobile/i18n`", text)
        self.assertIn("Screenshot languages: `es` always, `ca` when the change edits copy.", text)

    def test_screenshots_none_tells_evidence_not_to_try(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "run": {"dev": "npm start", "screenshots": "none"}})
        self.assertIn("Screenshots for evidence: not supported", self.ctx())

    def test_a_template_in_the_repository_wins_even_when_the_contract_does_not_name_it(self):
        os.makedirs(os.path.join(self.repo, ".github"))
        open(os.path.join(self.repo, ".github", "pull_request_template.md"), "w").close()
        self.write({"version": 1, "verify": {"full": "npm test"}})
        self.assertIn("The repository's template `.github/pull_request_template.md` wins over the `pr` skill's template", self.ctx())

    def test_the_contract_template_comes_before_the_one_on_disk(self):
        open(os.path.join(self.repo, "pull_request_template.md"), "w").close()
        self.write({"version": 1, "verify": {"full": "npm test"}, "pr": {"template": "docs/pr.md"}})
        context_text = self.ctx()
        self.assertIn("The repository's template `docs/pr.md` wins", context_text)
        self.assertNotIn("`pull_request_template.md` wins", context_text)

    def test_without_any_template_no_template_line_appears(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        self.assertNotIn("wins over the `pr` skill's template", self.ctx())

    def test_github_release_evidence_points_at_the_upload_command(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "pr": {"evidence": "github-release"}})
        self.assertIn("`evidence.py upload`): they go to this month's `pr-evidence-YYYY-MM` prerelease", self.ctx())

    def test_monorepo_apps_are_listed(self):
        os.makedirs(os.path.join(self.repo, "apps", "web"))
        self.write({"version": 1, "verify": {"full": "npm test"}, "run": {"apps": [
            {"name": "web", "path": "apps/web", "dev": "pnpm --filter web dev", "url": "http://localhost:3000", "screenshots": "web"},
            {"name": "mobile", "path": "apps/mobile", "screenshots": "none"}]}})
        text = self.ctx()
        self.assertIn("`web` in `apps/web`: start `pnpm --filter web dev` at http://localhost:3000; screenshots: headless browser", text)
        self.assertIn("`mobile` in `apps/mobile`: no start command; screenshots: not supported", text)

    def test_standards_list_repository_and_personal_files(self):
        os.makedirs(os.path.join(self.home, "standards"))
        open(os.path.join(self.home, "standards", "mine.md"), "w").close()
        self.write({"version": 1, "verify": {"full": "npm test"}, "review": {"standards": ["docs/style.md"], "skills": ["i18n-review"]}})
        text = self.ctx()
        self.assertIn("- `docs/style.md`", text)
        self.assertIn(os.path.join(self.home, "standards", "mine.md"), text)
        self.assertIn("the repository wins", text)
        self.assertIn("`i18n-review`", text)

    def test_standards_are_read_before_writing_code(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        text = self.ctx()
        self.assertIn("Read these before writing code", text)
        self.assertIn("load the `component-design` skill", text)

    def test_ui_changes_get_the_component_design_audit_in_review(self):
        self.write({"version": 1, "verify": {"full": "npm test"}})
        self.assertIn("also run `component-design`'s audit", self.ctx())

    def test_build_skills_load_before_writing_code(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "build": {"skills": ["ui-primitives"]}})
        self.assertIn("Also load these repository skills before writing code: `ui-primitives`", self.ctx())

    def test_ui_building_blocks_reach_ui_work(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "ui": {
            "components": ["src/components/ui"], "tokens": ["src/styles/tokens.css"], "icons": "lucide-react",
            "preview": {"command": "pnpm run storybook", "url": "http://localhost:6006"}}})
        text = self.ctx()
        self.assertIn("Shared components: `src/components/ui`. Search them before creating a component", text)
        self.assertIn("Design tokens and theme: `src/styles/tokens.css`", text)
        self.assertIn("Icons come from `lucide-react`", text)
        self.assertIn("Component preview: `pnpm run storybook`, answering at http://localhost:6006.", text)
        self.assertIn("ui_check.py", text)

    def test_ui_building_blocks_apply_in_repo_workflow_too(self):
        self.write({"version": 1, "workflow": "repo", "ui": {"components": ["src/ui"]}})
        text = self.ctx()
        self.assertIn("Shared components: `src/ui`", text)
        self.assertIn("Before you call a UI change done, run", text)
        self.assertNotIn("`verify` runs the UI check", text)

    def test_each_app_gets_its_own_ui(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "run": {"apps": [
            {"name": "mobile", "path": "apps/mobile", "ui": {"icons": "lucide-react-native"}}]}})
        text = self.ctx()
        self.assertIn("In `apps/mobile` (`mobile`):", text)
        self.assertNotIn("instead of the above", text)
        self.assertIn("  - Icons come from `lucide-react-native`", text)

    def test_without_ui_nothing_is_claimed(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "ui": {"preview": {"url": "http://localhost:6006"}}})
        text = self.ctx()
        self.assertNotIn("UI building blocks", text)

    def test_repo_workflow_keeps_personal_standards_below_the_repository(self):
        os.makedirs(os.path.join(self.home, "standards"))
        open(os.path.join(self.home, "standards", "mine.md"), "w").close()
        self.write({"version": 1, "workflow": "repo"})
        text = self.ctx()
        self.assertIn(os.path.join(self.home, "standards", "mine.md"), text)
        self.assertIn("the repository wins", text)
        self.assertIn("unless the repository's own component skills say otherwise", text)

    def test_unreadable_contract_suggests_repair(self):
        self.write("{not json")
        self.assertIn("could not be read", self.ctx())

    def test_schema_errors_are_reported_but_context_still_printed(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "trello"}})
        text = self.ctx()
        self.assertIn("The contract has problems", text)
        self.assertIn("### Verification", text)

    def test_local_tracker_points_worktrees_at_the_main_checkout(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "local", "path": ".scratch"}})
        git = ["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        worktree = os.path.join(self.tmp.name, "wt")
        subprocess.run([*git, "worktree", "add", "-q", "-b", "ticket-01", worktree], check=True)
        text = context(worktree, env=self.env, stdin="")
        shared = text.split("read and update tickets at `")[1].split("`")[0]
        self.assertEqual(os.path.realpath(shared), os.path.join(os.path.realpath(self.repo), ".scratch"))

    def test_explicit_directory_argument_wins(self):
        self.write({"version": 1, "verify": {"full": "make check"}})
        text = context(self.tmp.name, env=self.env, stdin="", args=[self.repo])
        self.assertIn("`make check`", text)


if __name__ == "__main__":
    unittest.main()
