import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "shared", "pr_assignee.py")
URL = "https://github.com/acme/shop/pull/42"


class PrAssigneeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, "bin")
        self.log = os.path.join(self.tmp.name, "gh.log")
        os.makedirs(self.bin)
        self.fake_gh(exit_code=0)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_gh(self, exit_code):
        """A `gh` that records its arguments, one call per line, and exits with `exit_code`."""
        path = os.path.join(self.bin, "gh")
        with open(path, "w") as fh:
            fh.write(f'#!/bin/sh\necho "$*" >> "{self.log}"\necho "gh failed" >&2\nexit {exit_code}\n'
                     if exit_code else f'#!/bin/sh\necho "$*" >> "{self.log}"\n')
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def run_hook(self, command, stdout, tool="Bash"):
        event = {"hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": {"command": command},
                 "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False}}
        env = {**os.environ, "PATH": self.bin + os.pathsep + os.environ["PATH"]}
        result = subprocess.run([sys.executable, SCRIPT], input=json.dumps(event), capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        return payload["hookSpecificOutput"]["additionalContext"]

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as fh:
            return fh.read().splitlines()

    def test_assigns_a_created_pull_request_to_whoever_opened_it(self):
        note = self.run_hook('gh pr create --base main --title "Add x" --body "..."', f"\nCreating pull request\n{URL}\n")
        self.assertEqual(self.calls(), [f"pr edit {URL} --add-assignee @me"])
        self.assertIn(f"Assigned {URL}", note)

    def test_assigns_every_pull_request_of_a_stack(self):
        second = "https://github.com/acme/shop/pull/43"
        self.run_hook("gh pr create --fill && git checkout top && gh pr create --fill", f"{URL}\n{second}\n")
        self.assertEqual(self.calls(), [f"pr edit {URL} --add-assignee @me", f"pr edit {second} --add-assignee @me"])

    def test_ignores_commands_that_do_not_create_a_pull_request(self):
        self.assertIsNone(self.run_hook("gh pr view --web", f"{URL}\n"))
        self.assertEqual(self.calls(), [])

    def test_ignores_other_tools(self):
        self.assertIsNone(self.run_hook("gh pr create --fill", f"{URL}\n", tool="Read"))
        self.assertEqual(self.calls(), [])

    def test_does_nothing_when_no_pull_request_was_created(self):
        self.assertIsNone(self.run_hook("gh pr create --fill", "aborted: you must first push the current branch\n"))
        self.assertEqual(self.calls(), [])

    def test_ignores_urls_inside_other_output(self):
        self.assertIsNone(self.run_hook("gh pr create --dry-run", f"would mention {URL} in the body\n"))
        self.assertEqual(self.calls(), [])

    def test_a_failed_assignment_asks_the_agent_to_assign_it(self):
        self.fake_gh(exit_code=1)
        note = self.run_hook("gh pr create --fill", f"{URL}\n")
        self.assertIn(f"gh pr edit {URL} --add-assignee @me", note)
        self.assertIn("gh failed", note)

    def test_unreadable_input_never_breaks_the_session(self):
        result = subprocess.run([sys.executable, SCRIPT], input="not json", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("assign the pull request", json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
