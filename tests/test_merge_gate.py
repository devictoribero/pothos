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
    sys.exit(0 if os.path.exists(os.path.join(d, "branch-exists")) else 1)
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
        failed = [{"__typename": "StatusContext", "context": "ci/build", "state": "ERROR"}]
        self.assertIn("failed checks: ci/build", self.verdict(pr(statusCheckRollup=failed))[2])

    def test_no_checks_needs_a_verify_receipt(self):
        self.assertEqual(self.verdict(pr(statusCheckRollup=[]))[0], merge_gate.WAITING)
        self.assertEqual(self.verdict(pr(statusCheckRollup=[]), receipt_ok=True)[0], merge_gate.READY)

    def test_changes_requested_needs_a_person(self):
        reviews = [{"author": {"login": "ana"}, "state": "CHANGES_REQUESTED"}, {"author": {"login": "bo"}, "state": "APPROVED"}]
        verdict, _, reasons = self.verdict(pr(latestReviews=reviews))
        self.assertEqual(verdict, merge_gate.NEEDS_PERSON)
        self.assertIn("changes requested by ana", reasons)

    def test_unresolved_threads_wait(self):
        verdict, _, reasons = self.verdict(pr(unresolvedThreads=2))
        self.assertEqual(verdict, merge_gate.WAITING)
        self.assertIn("2 unresolved review thread(s)", reasons)

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


if __name__ == "__main__":
    unittest.main()
