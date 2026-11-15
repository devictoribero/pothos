import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "risk", "scripts", "risk.py")
sys.path.insert(0, os.path.dirname(SCRIPT))
import risk  # noqa: E402


class RiskRepoTest(unittest.TestCase):
    """A repository on a branch off main, with a private contract in a temporary Pothos home."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("remote", "add", "origin", "https://github.com/acme/shop.git")
        self.write("README.md", 1)
        self.commit("first")
        self.git("checkout", "-q", "-b", "feature")
        self.env = {**os.environ, "POTHOS_HOME": self.home}

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def write(self, rel, lines):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("".join(f"line {i}\n" for i in range(lines)))

    def commit(self, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def contract(self, **pr):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        run = pr.pop("run", None)
        data = {"version": 1, "verify": {"full": "true"}, "pr": {"base": "main", **pr}}
        if run:
            data["run"] = run
        with open(path, "w") as fh:
            json.dump(data, fh)

    def receipt(self, level, body):
        folder = os.path.join(self.home, "receipts", "github.com", "acme", "shop", self.git("rev-parse", "HEAD"))
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{level}.json"), "w") as fh:
            json.dump(body, fh)

    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def assess(self, *args):
        run = self.run_script("assess", "--json", *args)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return json.loads(run.stdout)


class ExitCodes(RiskRepoTest):
    def test_without_a_contract_it_exits_2_and_suggests_plant(self):
        run = self.run_script("assess")
        self.assertEqual(run.returncode, 2)
        self.assertIn("/pothos:plant", run.stderr)

    def test_usage_errors_exit_64(self):
        self.contract()
        self.assertEqual(self.run_script().returncode, 64)
        self.assertEqual(self.run_script("assess", "--bogus").returncode, 64)
        self.assertEqual(self.run_script("judge").returncode, 64)
        self.assertEqual(self.run_script("assess", "--base", "no-such-branch").returncode, 64)

    def test_help_exits_0(self):
        self.assertEqual(self.run_script("--help").returncode, 0)


class Classification(RiskRepoTest):
    def test_every_path_gets_one_class_first_match_wins(self):
        self.contract(risk={"generated": ["src/gen"]})
        for rel in ("pnpm-lock.yaml", "src/gen/client.ts", "src/gen/client.test.ts", "src/cart.test.ts",
                    "src/__tests__/helper.ts", "CHANGELOG.md", "apps/web/NOTES.md", "docs/guide.txt", "src/cart.ts"):
            self.write(rel, 2)
        self.commit()

        classes = {f["path"]: f["class"] for f in self.assess()["files"]}

        self.assertEqual(classes, {
            "pnpm-lock.yaml": "generated", "src/gen/client.ts": "generated", "src/gen/client.test.ts": "generated",
            "src/cart.test.ts": "test", "src/__tests__/helper.ts": "test", "CHANGELOG.md": "docs",
            "apps/web/NOTES.md": "docs", "docs/guide.txt": "docs", "src/cart.ts": "source"})

    def test_a_binary_file_counts_as_zero_lines(self):
        self.contract()
        with open(os.path.join(self.repo, "logo.png"), "wb") as fh:
            fh.write(b"\x89PNG\x00\x01\x02")
        self.commit()

        files = self.assess()["files"]

        self.assertEqual(files, [{"path": "logo.png", "added": 0, "removed": 0, "class": "source"}])

    def test_tests_docs_and_generated_files_stay_out_of_the_complexity(self):
        self.contract()
        self.write("src/a.ts", 10)
        self.write("src/a.test.ts", 700)
        self.write("docs/a.md", 700)
        self.write("package-lock.json", 700)
        self.commit()

        result = self.assess()

        self.assertEqual((result["complexity"]["files"], result["complexity"]["lines"]), (1, 10))
        self.assertEqual(result["tests"], {"files": 1, "added": 700, "removed": 0})


class Door(RiskRepoTest):
    def test_a_migration_is_one_way_by_default_and_names_the_reason(self):
        self.contract()
        self.write("db/migrations/0002_refunds.sql", 3)
        self.commit()

        run = self.run_script("assess")

        self.assertIn("- **Door:** one-way: database migration (`db/migrations/0002_refunds.sql`).", run.stdout)
        self.assertIn("default rule", run.stderr)

    def test_a_contract_entry_replaces_the_default_and_every_matching_reason_is_named(self):
        self.contract(risk={"one_way": [{"why": "data deleted", "paths": ["scripts/purge"]},
                                        {"why": "queue format", "paths": ["**/*.avsc"]},
                                        {"why": "never matched", "paths": ["infra"]}]})
        self.write("scripts/purge/run.py", 3)
        self.write("events/order.avsc", 3)
        self.write("db/migrations/0002.sql", 3)
        self.commit()

        door = self.assess()["door"]

        self.assertEqual(door["kind"], "one-way")
        self.assertEqual([r["why"] for r in door["reasons"]], ["data deleted", "queue format"])

    def test_without_a_matching_path_the_door_is_two_way(self):
        self.contract()
        self.write("src/a.ts", 3)
        self.commit()

        self.assertEqual(self.assess()["door"], {"kind": "two-way", "reasons": [], "default": True})


class BlastRadius(RiskRepoTest):
    def touch(self, *rels):
        for rel in rels:
            self.write(rel, 2)
        self.commit()
        return self.assess()["blast_radius"]

    def test_one_area_is_narrow(self):
        self.contract()
        self.assertEqual(self.touch("src/a.ts", "src/b/c.ts")["radius"], "narrow")

    def test_two_areas_are_medium(self):
        self.contract()
        radius = self.touch("api/a.ts", "web/b.ts")
        self.assertEqual((radius["radius"], radius["areas"]), ("medium", ["api", "web"]))

    def test_three_areas_are_wide(self):
        self.contract()
        self.assertEqual(self.touch("api/a.ts", "web/b.ts", "Makefile")["areas"], ["(root)", "api", "web"])

    def test_areas_are_the_contracts_apps_when_it_has_them(self):
        self.contract(run={"apps": [{"name": "api", "path": "apps/api"}, {"name": "web", "path": "apps/web"}]})
        radius = self.touch("apps/api/a.ts", "apps/api/b/c.ts", "apps/web/d.ts")
        self.assertEqual(radius["areas"], ["api", "web"])

    def test_a_contract_surface_alone_is_medium_and_may_be_a_generated_file(self):
        self.contract(risk={"generated": ["openapi.json"], "contract": [{"name": "API contract", "paths": ["openapi.json"]}]})
        radius = self.touch("api/a.ts", "openapi.json")
        self.assertEqual(radius["radius"], "medium")
        self.assertEqual(radius["contract"], [{"name": "API contract", "paths": ["openapi.json"]}])

    def test_a_contract_surface_and_a_core_area_together_are_wide(self):
        self.contract(risk={"contract": [{"name": "API contract", "paths": ["api/schema.graphql"]}],
                            "core": [{"name": "billing", "paths": ["api/billing"]}]})
        radius = self.touch("api/schema.graphql", "api/billing/charge.ts")
        self.assertEqual(radius["radius"], "wide")

    def test_a_core_area_is_named_in_the_markdown(self):
        self.contract(risk={"core": [{"name": "billing", "paths": ["api/billing"]}, {"name": "sign-in", "paths": ["api/auth"]}]})
        self.write("api/billing/charge.ts", 2)
        self.commit()
        self.assertIn("- **Core:** billing.", self.run_script("assess").stdout)

    def test_core_areas_declared_but_untouched_and_not_declared_read_differently(self):
        self.contract(risk={"core": [{"name": "billing", "paths": ["api/billing"]}]})
        self.write("api/cart.ts", 2)
        self.commit()
        self.assertIn("- **Core:** none touched.", self.run_script("assess").stdout)
        self.contract()
        run = self.run_script("assess")
        self.assertIn("- **Core:** none declared in the contract.", run.stdout)
        self.assertIn("pr.risk.core", run.stderr)


def files(count, lines):
    """Source files spread over one folder that add `lines` lines in all."""
    each = [lines // count + (1 if i < lines % count else 0) for i in range(count)]
    return [{"path": f"src/f{i}.ts", "added": n, "removed": 0, "class": "source"} for i, n in enumerate(each)]


class Complexity(unittest.TestCase):
    def test_bands_at_their_boundaries(self):
        cases = [((5, 150), "Low"), ((5, 151), "Medium"), ((6, 150), "Medium"), ((20, 600), "Medium"),
                 ((20, 601), "High"), ((21, 100), "High"), ((1, 0), "Low")]
        for (count, lines), level in cases:
            self.assertEqual(risk.complexity(files(count, lines))["level"], level, (count, lines))

    def test_removed_lines_count_and_folders_are_distinct(self):
        size = risk.complexity([{"path": "a/x.ts", "added": 100, "removed": 60, "class": "source"},
                                {"path": "a/y.ts", "added": 1, "removed": 0, "class": "source"},
                                {"path": "top.ts", "added": 1, "removed": 0, "class": "source"}])
        self.assertEqual((size["level"], size["lines"], size["folders"]), ("Medium", 162, 2))


def door(kind):
    return {"kind": kind, "reasons": [], "default": True}


def radius(level="narrow", core=False):
    return {"radius": level, "areas": [], "contract": [], "core": [{"name": "billing", "paths": []}] if core else [],
            "core_declared": True}


class SuggestedRisk(unittest.TestCase):
    def level(self, door_kind="two-way", radius_level="narrow", core=False, size="Low"):
        return risk.suggested_risk(door(door_kind), radius(radius_level, core), {"level": size})[0]

    def test_high(self):
        self.assertEqual(self.level("one-way", core=True), "High")
        self.assertEqual(self.level("one-way", "wide"), "High")
        self.assertEqual(self.level(core=True, size="High"), "High")

    def test_medium(self):
        self.assertEqual(self.level("one-way"), "Medium")
        self.assertEqual(self.level(core=True, size="Medium"), "Medium")
        self.assertEqual(self.level(radius_level="wide"), "Medium")
        self.assertEqual(self.level(size="High"), "Medium")

    def test_low(self):
        self.assertEqual(self.level(radius_level="medium", size="Medium"), "Low")

    def test_the_reasons_name_what_raised_it(self):
        _, reasons = risk.suggested_risk(door("one-way"), radius("wide"), {"level": "High"})
        self.assertEqual(reasons, ["one-way door with a wide blast radius"])
        _, reasons = risk.suggested_risk(door("two-way"), radius("wide"), {"level": "High"})
        self.assertEqual(reasons, ["wide blast radius", "high complexity"])


class ConfidenceCeiling(RiskRepoTest):
    def branch(self, tests=True, lines=10):
        self.contract()
        self.write("src/a.ts", lines)
        if tests:
            self.write("src/a.test.ts", 5)
        self.commit()

    def ceiling(self):
        return self.assess()["suggested"]["confidence_ceiling"]

    def test_no_full_receipt_for_head_is_low(self):
        self.branch()
        result = self.assess()
        self.assertEqual(result["evidence"]["full"], "none")
        self.assertEqual(result["suggested"]["confidence_ceiling"], "Low")

    def test_a_failed_or_dirty_full_receipt_is_low(self):
        self.branch()
        self.receipt("full", {"status": "failed", "dirty": False})
        self.assertEqual(self.ceiling(), "Low")
        self.receipt("full", {"status": "passed", "dirty": True})
        self.assertEqual(self.ceiling(), "Low")

    def test_a_passing_full_receipt_with_tests_is_high(self):
        self.branch()
        self.receipt("full", {"status": "passed", "dirty": False})
        self.assertEqual(self.ceiling(), "High")
        self.assertIn("full verify passed on " + self.git("rev-parse", "HEAD")[:12], self.run_script("assess").stdout)

    def test_a_receipt_for_another_commit_does_not_count(self):
        self.branch()
        self.receipt("full", {"status": "passed", "dirty": False})
        self.write("src/b.ts", 1)
        self.commit()
        self.assertEqual(self.ceiling(), "Low")

    def test_source_without_test_lines_is_medium(self):
        self.branch(tests=False)
        self.receipt("full", {"status": "passed", "dirty": False})
        result = self.assess()
        self.assertEqual(result["suggested"]["confidence_ceiling"], "Medium")
        self.assertEqual(result["suggested"]["ceiling_reasons"], ["source changed with no test lines changed"])

    def test_new_mutation_survivors_are_medium_and_inherited_ones_are_not(self):
        self.branch()
        self.receipt("full", {"status": "passed", "dirty": False})
        self.receipt("mutation", {"status": "findings", "findings": [{"kind": "inherited"}]})
        self.assertEqual(self.ceiling(), "High")
        self.receipt("mutation", {"status": "findings", "findings": [{"kind": "new"}, {"kind": "new"}, {"kind": "inherited"}]})
        result = self.assess()
        self.assertEqual(result["evidence"]["mutation"], {"status": "findings", "new_survivors": 2})
        self.assertEqual(result["suggested"]["confidence_ceiling"], "Medium")
        self.assertIn("mutation: 2 new survivors", self.run_script("assess").stdout)

    def test_high_complexity_is_medium(self):
        self.branch(lines=700)
        self.receipt("full", {"status": "passed", "dirty": False})
        self.assertEqual(self.ceiling(), "Medium")


class Output(RiskRepoTest):
    def test_markdown_is_a_section_ready_for_the_pull_request_body(self):
        self.contract(risk={"core": [{"name": "billing", "paths": ["api/billing"]}],
                            "contract": [{"name": "API contract", "paths": ["api/openapi.json"]}]})
        self.write("api/billing/migrations/0002_refunds.sql", 4)
        self.write("api/billing/refund.ts", 20)
        self.write("api/billing/refund.test.ts", 30)
        self.write("web/refund.ts", 6)
        self.commit()
        self.receipt("full", {"status": "passed", "dirty": False})
        os.makedirs(os.path.join(self.home, "evidence", "github.com", "acme", "shop", "feature"))
        with open(os.path.join(self.home, "evidence", "github.com", "acme", "shop", "feature", "evidence.md"), "w") as fh:
            fh.write("## Evidence\n")

        run = self.run_script("assess")

        self.assertEqual(run.returncode, 0, run.stderr)
        head = self.git("rev-parse", "HEAD")[:12]
        self.assertEqual(run.stdout.strip().splitlines()[:9], [
            "## Risk",
            "",
            "**Risk:** High · **Complexity:** Low · **Confidence:** High",
            "",
            "- **Door:** one-way: database migration (`api/billing/migrations/0002_refunds.sql`).",
            "- **Blast radius:** medium: api, web.",
            "- **Core:** billing.",
            "- **Size:** 3 source files, +30 / -0 in 3 folders; tests +30 / -0.",
            f"- **Evidence:** full verify passed on {head}; mutation: none; evidence: captured.",
        ])
        self.assertRegex(run.stdout, r"<!-- Confidence ceiling High: .*what would raise it\. -->")

    def test_json_carries_every_signal_and_both_suggestions(self):
        self.contract()
        self.write("src/a.ts", 3)
        self.commit()

        result = self.assess("--base", "main")

        self.assertEqual(set(result), {"base", "merge_base", "head", "dirty", "files", "door", "blast_radius",
                                       "complexity", "tests", "evidence", "suggested"})
        self.assertEqual(result["base"], "main")
        self.assertEqual(set(result["suggested"]), {"risk", "risk_reasons", "confidence_ceiling", "ceiling_reasons"})
        self.assertEqual(result["suggested"]["ceiling_reasons"], ["no full verify receipt for HEAD"])

    def test_uncommitted_changes_are_not_assessed_and_the_output_says_so(self):
        self.contract()
        self.write("src/a.ts", 3)
        self.commit()
        self.write("src/b.ts", 900)

        run = self.run_script("assess", "--json")

        self.assertIn("uncommitted changes", run.stderr)
        result = json.loads(run.stdout)
        self.assertTrue(result["dirty"])
        self.assertEqual([f["path"] for f in result["files"]], ["src/a.ts"])

    def test_without_pr_base_it_falls_back_to_origin_head(self):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, "verify": {"full": "true"}}, fh)
        main = self.git("rev-parse", "main")
        self.git("update-ref", "refs/remotes/origin/main", main)
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.write("src/a.ts", 3)
        self.commit()

        result = self.assess()

        self.assertEqual((result["base"], result["merge_base"]), ("origin/HEAD", main))

    def test_without_any_base_it_exits_3(self):
        path = os.path.join(self.home, "contracts", "github.com", "acme", "shop.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"version": 1, "verify": {"full": "true"}}, fh)
        run = self.run_script("assess")
        self.assertEqual(run.returncode, 3)
        self.assertIn("--base", run.stderr)


if __name__ == "__main__":
    unittest.main()
