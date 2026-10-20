import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "pothos", "skills", "tend", "scripts")
SCRIPT = os.path.join(SCRIPTS, "merge_gate.py")
sys.path.insert(0, SCRIPTS)
import merge_gate  # noqa: E402

SHA = "a" * 40
CONTRACT = {"pr": {"base": "main", "auto_merge": {"label": "auto-merge"}}}

# A stand-in for gh: answers from JSON files in $FAKE_GH and logs every call to $FAKE_GH/calls.log.
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_GH"]
args = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(" ".join(args) + "\n")
with open(os.path.join(d, "hosts.log"), "a") as fh:
    fh.write(os.environ.get("GH_HOST", "-") + "\n")
def answer(name):
    with open(os.path.join(d, name)) as fh:
        print(fh.read())
if args[:2] == ["pr", "view"]:
    answer("pr.json")
elif args[:2] == ["api", "graphql"]:
    answer("threads.json")
elif args[:2] == ["pr", "list"]:
    answer("dependants.json") if os.path.exists(os.path.join(d, "dependants.json")) else print("[]")
elif args[:1] == ["api"] and "/git/ref/heads/" in args[-1]:
    if os.path.exists(os.path.join(d, "branch-exists")):
        sys.exit(0)
    print("gh: Not Found (HTTP 404)" if not os.path.exists(os.path.join(d, "api-down")) else "gh: connect: network is unreachable", file=sys.stderr)
    sys.exit(1)
elif args[:3] == ["api", "-X", "DELETE"] and os.path.exists(os.path.join(d, "delete-fails")):
    with open(os.path.join(d, "delete-fails")) as fh:
        print(fh.read(), file=sys.stderr)
    sys.exit(1)
elif args[:2] == ["pr", "merge"] and os.path.exists(os.path.join(d, "merge-fails")):
    print("Head branch was modified", file=sys.stderr); sys.exit(1)
'''


def pr(**changes):
    base = {"number": 7, "url": "https://github.com/acme/shop/pull/7", "state": "OPEN", "isDraft": False,
            "baseRefName": "main", "headRefName": "fix-total", "headRefOid": SHA, "isCrossRepository": False,
            "labels": [{"name": "auto-merge"}], "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
            "latestReviews": [], "unresolvedThreads": 0,
            "statusCheckRollup": [{"__typename": "CheckRun", "name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
    base.update(changes)
    return base


def run(name, status, conclusion=None):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


class EvaluateTest(unittest.TestCase):
    def verdict(self, pr_data, contract=CONTRACT, receipt_ok=False):
        return merge_gate.evaluate(pr_data, contract, receipt_ok)

    def test_green_labelled_pull_request_is_ready(self):
        verdict, facts, reasons = self.verdict(pr())
        self.assertEqual(verdict, merge_gate.READY)
        self.assertEqual(reasons, [])
        self.assertIn("candidate: yes, label 'auto-merge'", facts)

    def test_without_auto_merge_in_the_contract_nothing_is_a_candidate(self):
        verdict, _, reasons = self.verdict(pr(), contract={"pr": {"base": "main"}})
        self.assertEqual(verdict, merge_gate.NOT_CANDIDATE)
        self.assertIn("the contract has no pr.auto_merge", reasons)

    def test_the_label_comes_from_the_contract(self):
        contract = {"pr": {"auto_merge": {"label": "ship-it"}}}
        self.assertEqual(self.verdict(pr(), contract=contract)[0], merge_gate.NOT_CANDIDATE)
        self.assertEqual(self.verdict(pr(labels=[{"name": "ship-it"}]), contract=contract)[0], merge_gate.READY)

    def test_drafts_closed_and_other_bases_are_not_candidates(self):
        for changes in ({"isDraft": True}, {"state": "MERGED"}, {"baseRefName": "feature/x"}, {"labels": []}):
            self.assertEqual(self.verdict(pr(**changes))[0], merge_gate.NOT_CANDIDATE, changes)

    def test_a_non_candidate_verdict_still_says_what_else_is_missing(self):
        _, _, reasons = self.verdict(pr(labels=[]))
        self.assertEqual(reasons[-1], "otherwise ready")
        _, _, reasons = self.verdict(pr(labels=[], statusCheckRollup=[run("lint", "COMPLETED", "FAILURE")]))
        self.assertEqual(reasons[-1], "otherwise waiting: failed checks: lint")
        _, _, reasons = self.verdict(pr(labels=[], mergeable="CONFLICTING"))
        self.assertEqual(reasons[-1], "otherwise needs a person: the branch conflicts with the base")

    def test_the_label_matches_regardless_of_case(self):
        self.assertEqual(self.verdict(pr(labels=[{"name": "Auto-Merge"}]))[0], merge_gate.READY)

    def test_a_fork_is_named_in_the_facts(self):
        self.assertIn("from a fork", self.verdict(pr(isCrossRepository=True))[1][0])

    def test_a_failed_or_running_check_waits(self):
        failed = self.verdict(pr(statusCheckRollup=[run("lint", "COMPLETED", "FAILURE"), run("test", "COMPLETED", "SUCCESS")]))
        self.assertEqual(failed[0], merge_gate.WAITING)
        self.assertIn("failed checks: lint", failed[2])
        running = self.verdict(pr(statusCheckRollup=[run("test", "IN_PROGRESS")]))
        self.assertEqual(running[0], merge_gate.WAITING)
        self.assertIn("checks still running: test", running[2])

    def test_neutral_and_skipped_checks_count_as_green(self):
        checks = [run("a", "COMPLETED", "NEUTRAL"), run("b", "COMPLETED", "SKIPPED")]
        self.assertEqual(self.verdict(pr(statusCheckRollup=checks))[0], merge_gate.READY)

    def test_commit_statuses_are_read_too(self):
        pending = [{"__typename": "StatusContext", "context": "ci/build", "state": "PENDING"}]
        self.assertEqual(self.verdict(pr(statusCheckRollup=pending))[0], merge_gate.WAITING)
        untyped = [{"context": "ci/build", "state": "SUCCESS"}]
        self.assertEqual(self.verdict(pr(statusCheckRollup=untyped))[0], merge_gate.READY)
        failed = [{"__typename": "StatusContext", "context": "ci/build", "state": "ERROR"}]
        self.assertIn("failed checks: ci/build", self.verdict(pr(statusCheckRollup=failed))[2])

    def test_no_checks_needs_a_verify_receipt(self):
        self.assertEqual(self.verdict(pr(statusCheckRollup=[]))[0], merge_gate.WAITING)
        self.assertEqual(self.verdict(pr(statusCheckRollup=[]), receipt_ok=True)[0], merge_gate.READY)

    def test_no_checks_waits_when_the_repository_has_workflows(self):
        verdict, facts, reasons = merge_gate.evaluate(pr(statusCheckRollup=[]), CONTRACT, True, checks_expected=True)
        self.assertEqual(verdict, merge_gate.WAITING)
        self.assertIn("the workflows have not reported on this commit yet", reasons)
        self.assertIn("checks: none reported yet on this commit (the repository has workflows that run on it)", facts)

    def test_changes_requested_needs_a_person(self):
        reviews = [{"author": {"login": "ana"}, "state": "CHANGES_REQUESTED"}, {"author": {"login": "bo"}, "state": "APPROVED"}]
        verdict, _, reasons = self.verdict(pr(latestReviews=reviews))
        self.assertEqual(verdict, merge_gate.NEEDS_PERSON)
        self.assertIn("changes requested by ana", reasons)

    def test_a_bot_requesting_changes_does_not_need_a_person(self):
        reviews = [{"author": {"login": "coderabbitai"}, "state": "CHANGES_REQUESTED"}]
        self.assertEqual(self.verdict(pr(latestReviews=reviews))[0], merge_gate.NEEDS_PERSON)
        self.assertEqual(self.verdict(pr(latestReviews=reviews, botReviewers=["coderabbitai"]))[0], merge_gate.READY)

    def test_unresolved_threads_wait(self):
        verdict, _, reasons = self.verdict(pr(unresolvedThreads=2))
        self.assertEqual(verdict, merge_gate.WAITING)
        self.assertIn("2 unresolved review thread(s)", reasons)

    def test_threads_beyond_the_first_page_wait(self):
        verdict, facts, reasons = self.verdict(pr(moreThreads=True))
        self.assertEqual(verdict, merge_gate.WAITING)
        self.assertIn("more than 100 review threads: cannot tell they are all resolved", reasons)
        self.assertIn("threads: 0 unresolved of the first 100; there are more", facts)

    def test_conflicts_need_a_person_and_behind_waits(self):
        self.assertEqual(self.verdict(pr(mergeable="CONFLICTING", mergeStateStatus="DIRTY"))[0], merge_gate.NEEDS_PERSON)
        verdict, _, reasons = self.verdict(pr(mergeStateStatus="BEHIND"))
        self.assertEqual(verdict, merge_gate.WAITING)
        self.assertIn("the branch is behind main: update it", reasons)

    def test_branch_rules_blocking_a_green_pull_request_wait(self):
        verdict, _, reasons = self.verdict(pr(mergeStateStatus="BLOCKED"))
        self.assertEqual(verdict, merge_gate.WAITING)
        self.assertIn("GitHub's branch rules block the merge (a required review or check)", reasons)


class MergeGateCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.repo, self.home, self.fake, self.bin = (os.path.join(t, n) for n in ("repo", "home", "fake", "bin"))
        for folder in (self.fake, self.bin):
            os.makedirs(folder)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        gh = os.path.join(self.bin, "gh")
        with open(gh, "w") as fh:
            fh.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.env = {**os.environ, "POTHOS_HOME": self.home, "FAKE_GH": self.fake, "PATH": self.bin + os.pathsep + os.environ["PATH"]}
        self.answer("threads.json", {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [{"isResolved": True}]}}}}})

    def tearDown(self):
        self.tmp.cleanup()

    def answer(self, name, data):
        with open(os.path.join(self.fake, name), "w") as fh:
            json.dump(data, fh)

    def contract(self, data):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, "verify": {"full": "true"}, **data}, fh)

    def gate(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def calls(self):
        path = os.path.join(self.fake, "calls.log")
        if not os.path.exists(path):
            return ""
        with open(path) as fh:
            return fh.read()

    def pull_request(self, **changes):
        data = pr(**changes)
        data.pop("unresolvedThreads")
        self.answer("pr.json", data)

    def test_without_contract_exits_2(self):
        self.assertEqual(self.gate("status", "7").returncode, 2)

    def test_usage(self):
        self.contract(CONTRACT)
        self.assertEqual(self.gate("merge", "seven").returncode, 64)
        self.assertEqual(self.gate().returncode, 64)

    def test_status_never_merges(self):
        self.contract(CONTRACT)
        self.pull_request()
        result = self.gate("status", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verdict: ready", result.stdout)
        self.assertNotIn("pr merge", self.calls())

    def test_merge_pins_the_head_commit_and_deletes_the_branch(self):
        self.contract(CONTRACT)
        self.pull_request()
        open(os.path.join(self.fake, "branch-exists"), "w").close()
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"pr merge 7 --squash --match-head-commit {SHA}", self.calls())
        self.assertIn("api -X DELETE repos/acme/shop/git/refs/heads/fix-total", self.calls())
        self.assertIn("deleted fix-total on the remote", result.stdout)

    def test_merge_uses_the_contract_method_and_skips_a_branch_github_deleted(self):
        self.contract({"pr": {"auto_merge": {"label": "auto-merge", "method": "rebase"}}})
        self.pull_request()
        result = self.gate("merge", "7")
        self.assertIn("pr merge 7 --rebase", self.calls())
        self.assertNotIn("DELETE", self.calls())
        self.assertIn("already deleted", result.stdout)

    def test_a_branch_github_deletes_between_the_read_and_the_delete_counts_as_deleted(self):
        self.contract(CONTRACT)
        self.pull_request()
        open(os.path.join(self.fake, "branch-exists"), "w").close()
        with open(os.path.join(self.fake, "delete-fails"), "w") as fh:
            fh.write("gh: Reference does not exist (HTTP 422)")
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("fix-total already deleted on the remote", result.stdout)

    def test_a_branch_the_api_refuses_to_delete_is_kept_after_the_merge(self):
        self.contract(CONTRACT)
        self.pull_request()
        open(os.path.join(self.fake, "branch-exists"), "w").close()
        with open(os.path.join(self.fake, "delete-fails"), "w") as fh:
            fh.write("gh: Cannot delete this protected branch (HTTP 422)")
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("merged: #7", result.stdout)
        self.assertIn("kept fix-total: could not delete it on the remote (gh: Cannot delete this protected branch", result.stdout)

    def hosts(self, gh_host):
        self.contract(CONTRACT)
        self.pull_request()
        result = subprocess.run([sys.executable, SCRIPT, "status", "7"], cwd=self.repo, capture_output=True, text=True,
                                env={**self.env, "GH_HOST": gh_host})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(os.path.join(self.fake, "hosts.log")) as fh:
            return set(fh.read().split())

    def test_a_gh_host_no_remote_points_at_is_left_out_of_gh(self):
        self.assertEqual(self.hosts("github.example.com"), {"-"})

    def test_a_gh_host_set_to_an_ssh_alias_is_left_out_of_gh(self):
        self.assertEqual(self.hosts("github.com-work"), {"-"})

    def test_a_gh_host_a_remote_points_at_reaches_gh(self):
        subprocess.run(["git", "-C", self.repo, "remote", "add", "work", "git@GitHub.example.com:acme/shop.git"], check=True)
        self.assertEqual(self.hosts("github.example.com"), {"github.example.com"})

    def test_a_branch_the_api_cannot_read_is_kept(self):
        self.contract(CONTRACT)
        self.pull_request()
        open(os.path.join(self.fake, "api-down"), "w").close()
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("kept fix-total: could not read it on the remote", result.stdout)
        self.assertNotIn("DELETE", self.calls())

    def test_repo_flag_names_the_checkout(self):
        self.contract(CONTRACT)
        self.pull_request()
        result = subprocess.run([sys.executable, SCRIPT, "status", "7", "--repo", self.repo], cwd=self.tmp.name,
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verdict: ready", result.stdout)

    def test_bot_reviews_come_from_graphql(self):
        self.contract(CONTRACT)
        self.pull_request(latestReviews=[{"author": {"login": "coderabbitai"}, "state": "CHANGES_REQUESTED"}])
        self.answer("threads.json", {"data": {"repository": {"pullRequest": {
            "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "latestOpinionatedReviews": {"nodes": [{"state": "CHANGES_REQUESTED", "author": {"login": "coderabbitai", "__typename": "Bot"}}]}}}}})
        result = self.gate("status", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("reviews: none asking for changes", result.stdout)

    def test_branch_other_pull_requests_target_is_kept(self):
        self.contract(CONTRACT)
        self.pull_request()
        open(os.path.join(self.fake, "branch-exists"), "w").close()
        self.answer("dependants.json", [{"number": 9}])
        self.assertIn("kept fix-total: open pull requests target it (#9)", self.gate("merge", "7").stdout)
        self.assertNotIn("DELETE", self.calls())

    def test_merge_does_nothing_when_not_ready(self):
        self.contract(CONTRACT)
        self.pull_request(labels=[])
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 3)
        self.assertNotIn("pr merge", self.calls())

    def test_open_threads_from_graphql_block_the_merge(self):
        self.contract(CONTRACT)
        self.pull_request()
        self.answer("threads.json", {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [{"isResolved": False}]}}}}})
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 1)
        self.assertIn("threads: 1 unresolved", result.stdout)
        self.assertNotIn("pr merge", self.calls())

    def test_a_refused_merge_reports_gh_failure(self):
        self.contract(CONTRACT)
        self.pull_request()
        open(os.path.join(self.fake, "merge-fails"), "w").close()
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 5)
        self.assertIn("Head branch was modified", result.stderr)

    def ticket(self, text):
        path = os.path.join(self.repo, "01-copy.md")
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def test_authorize_with_a_quote_labels_and_says_who_authorized(self):
        self.contract(CONTRACT)
        self.pull_request(labels=[])
        result = self.gate("authorize", "7", "--quote", "and merge it when green")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pr edit 7 --add-label auto-merge", self.calls())
        self.assertIn("pr comment 7 --body Auto-merge authorized by the person, in their own words:\n\n> and merge it when green",
                      self.calls())
        self.assertNotIn("pr merge", self.calls())

    def test_authorize_with_a_ticket_needs_merge_auto_in_its_header(self):
        self.contract(CONTRACT)
        self.pull_request(labels=[])
        late = self.ticket("# Copy\n\nStatus: ready\n\n## Comments\n\nMerge: auto\n")
        self.assertEqual(self.gate("authorize", "7", "--ticket", late).returncode, 3)
        self.assertEqual(self.gate("authorize", "7", "--ticket", "missing.md").returncode, 3)
        self.assertNotIn("pr edit", self.calls())
        ticket = self.ticket("# Copy\n\nStatus: ready\nMerge: Auto\n\n## What to build\n")
        result = self.gate("authorize", "7", "--ticket", ticket)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pr edit 7 --add-label auto-merge", self.calls())
        self.assertIn("which carries `Merge: auto`", self.calls())

    def test_authorize_does_nothing_twice_or_without_auto_merge(self):
        self.contract(CONTRACT)
        self.pull_request()
        result = self.gate("authorize", "7", "--quote", "merge it")
        self.assertEqual(result.returncode, 0)
        self.assertIn("already carries", result.stdout)
        self.assertNotIn("pr edit", self.calls())
        self.contract({"pr": {"base": "main"}})
        self.assertEqual(self.gate("authorize", "7", "--quote", "merge it").returncode, 3)

    def test_authorize_needs_exactly_one_source(self):
        self.contract(CONTRACT)
        for args in (("authorize", "7"), ("authorize", "7", "--quote", " "), ("authorize", "7", "--quote"),
                     ("authorize", "7", "--quote", "merge it", "--ticket", "01-copy.md"), ("status", "7", "--quote", "merge it")):
            self.assertEqual(self.gate(*args).returncode, 64, args)

    def test_no_checks_reads_the_verify_receipt_for_the_head_commit(self):
        self.contract(CONTRACT)
        self.pull_request(statusCheckRollup=[])
        self.assertEqual(self.gate("status", "7").returncode, 1)
        folder = os.path.join(self.home, "receipts", "github.com", "acme", "shop", SHA)
        os.makedirs(folder)
        with open(os.path.join(folder, "full.json"), "w") as fh:
            json.dump({"status": "passed", "dirty": False}, fh)
        result = self.gate("status", "7")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("verify receipt passed", result.stdout)

    def test_a_receipt_does_not_replace_checks_the_workflows_will_report(self):
        self.contract(CONTRACT)
        self.pull_request(statusCheckRollup=[])
        folder = os.path.join(self.home, "receipts", "github.com", "acme", "shop", SHA)
        os.makedirs(folder)
        with open(os.path.join(folder, "full.json"), "w") as fh:
            json.dump({"status": "passed", "dirty": False}, fh)
        workflows = os.path.join(self.repo, ".github", "workflows")
        os.makedirs(workflows)
        with open(os.path.join(workflows, "cron.yml"), "w") as fh:
            fh.write("on:\n  schedule:\n    - cron: '0 7 * * 1'\n")
        self.assertEqual(self.gate("status", "7").returncode, 0)  # no workflow runs on this commit
        with open(os.path.join(workflows, "check.yml"), "w") as fh:
            fh.write("on:\n  pull_request:\n  push:\n    branches: [main]\n")
        result = self.gate("merge", "7")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not reported on this commit yet", result.stdout)
        self.assertNotIn("pr merge", self.calls())


class ExpectsChecksTest(unittest.TestCase):
    def test_reads_the_trigger_shapes_github_accepts(self):
        yes = ("on:\n  push:\n    branches: [main]\n  pull_request:\n", "on: [push, pull_request]\n",
               "on: pull_request\n", "on:\n  pull_request_target:\n    types: [opened]\n",
               "on: {push: {branches: [main]}, pull_request: {}}\n", "on: pull_request_target\n",
               "on: [pull_request_target]\n", '"on":\n  push:\n', "name: ci\r\non:\r\n  pull_request:\r\n",
               "on:\n\n  # runs on every push\n  push:\n", "on: push # every push\n")
        no = ("on:\n  schedule:\n    - cron: '0 7 * * 1'\n  workflow_dispatch:\n",
              "on:\n  workflow_dispatch:\njobs:\n  b:\n    steps:\n      - uses: docker/build-push-action@v5\n"
              "        with:\n          push: true\n",
              "on:\n  workflow_dispatch:\njobs:\n  push:\n    runs-on: ubuntu-latest\n",
              "on: workflow_dispatch # not on push\n", "jobs:\n  a:\n    steps:\n      - run: echo on\n")
        for text in yes:
            self.assertTrue(merge_gate.runs_on_pushes(text), text)
        for text in no:
            self.assertFalse(merge_gate.runs_on_pushes(text), text)

    def test_without_a_workflows_folder_nothing_is_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(merge_gate.expects_checks(tmp))


if __name__ == "__main__":
    unittest.main()
