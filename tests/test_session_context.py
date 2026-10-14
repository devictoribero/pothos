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
        self.assertIn("`fast`: `npm run lint`", text)
        self.assertIn("no end-to-end command", text)
        self.assertIn("only through verify, in the foreground", text)

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

    def test_screenshots_none_tells_evidence_not_to_try(self):
        self.write({"version": 1, "verify": {"full": "npm test"}, "run": {"dev": "npm start", "screenshots": "none"}})
        self.assertIn("Screenshots for evidence: not supported", self.ctx())

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

    def test_ui_building_blocks_apply_in_repo_workflow_too(self):
        self.write({"version": 1, "workflow": "repo", "ui": {"components": ["src/ui"]}})
        self.assertIn("Shared components: `src/ui`", self.ctx())

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
