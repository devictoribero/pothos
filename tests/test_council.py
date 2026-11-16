import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "plugins", "pothos", "skills", "council", "scripts", "council.py")

BRIEF = """## Question
Where should the purge read the pets of a household it ends?
## Options
- port: Identity owns a read port that PetManagement implements.
- import: Identity imports the pet repository directly.
## Stakes
A cycle between four contexts, hard to undo once more code leans on it.
## Recorded decisions
- docs/decisions/0001-contexts.md
## Why a test or prototype cannot settle this
Both options pass every test; the difference is what the next change costs.
## Sources
- src/purge.py:1-3
## Sealed lean
Lean: import
"""


def answer(pick="port", extra="", evidence=None):
    evidence = evidence or ['- src/purge.py:2 "pets = pet_repository.find"', '- docs/decisions/0001-contexts.md:3 "Identity imports no other context"']
    return (f"Pick: {pick}\n## Position\nThe port keeps Identity free of the pet model.\n{extra}\n"
            "## Evidence\n" + "\n".join(evidence) + "\n## Would change my mind\nA second caller of the repository.\n")


def critique(doubt="A", claim="false", pick="port", moved="nobody"):
    return (f"Doubt: {doubt}\nClaim: {claim}\nPick: {pick}\nMoved by: {moved}\n"
            "## Claim most likely false\nThat nothing else imports the pet model.\n"
            '## Check\n- src/other.py:1 "from pets import Pet"\n'
            "## Missed by all\n- The export also reads pets.\n")


def verdict(recommendation="port", why="The record forbids the import (E2).", dissent="none", first="Add the port."):
    return (f"Recommendation: {recommendation}\n## Why\n{why}\n## Confidence\nmedium: nobody ran it.\n"
            "## Where the council clashes\nCost now against cost later.\n## What every seat missed\nThe export.\n"
            "## What would flip this\nA second reader of pets in Identity.\n## Not verified\nThe migration.\n"
            f"## Dissent\n{dissent}\n## First step\n{first}\n")


class CouncilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/shop.git"], check=True)
        self.put("src/purge.py", "def purge(household):\n    pets = pet_repository.find(household)\n    return pets\n")
        self.put("src/other.py", "from pets import Pet\n")
        self.put("docs/decisions/0001-contexts.md", "# Contexts\n\nIdentity imports no other context.\n")
        self.env = {**os.environ, "POTHOS_HOME": self.home}

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def run_script(self, *args, stdin=""):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.repo, env=self.env, input=stdin,
                              capture_output=True, text=True, timeout=60)

    def open(self, brief=BRIEF, facts=("y", "y", "n"), slug="purge", size=None):
        args = ["open", "--slug", slug, "--revert", facts[0], "--wide", facts[1], "--decision", facts[2]]
        return self.run_script(*args, *(["--size", size] if size else []), stdin=brief)

    def folder(self, result):
        return re.search(r"^folder: (.+)$", result.stdout, re.M).group(1)

    def meta(self, folder):
        with open(os.path.join(folder, "meta.json")) as fh:
            return json.load(fh)

    def seat_all(self, folder, picks=None):
        for seat in self.meta(folder)["seats"]:
            result = self.run_script("answer", folder, seat, stdin=answer(
                (picks or {}).get(seat, "port"), "Data, security, migration: none found" if seat == "skeptic" else ""))
            self.assertEqual(result.stdout.strip(), "stored", result.stdout)

    def finished_full(self, picks=None):
        folder = self.folder(self.open())
        self.seat_all(folder, picks)
        self.assertEqual(self.run_script("review", folder).returncode, 0)
        for n in ("1", "2", "3"):
            self.assertEqual(self.run_script("critique", folder, n, stdin=critique()).stdout.strip(), "stored")
        self.assertEqual(self.run_script("tally", folder).returncode, 0)
        return folder

    # ---- size ----

    def test_no_yes_creates_nothing(self):
        result = self.open(facts=("n", "n", "n"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("size: none", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, "councils")))

    def test_one_yes_is_light_and_two_are_full(self):
        light = self.open(facts=("y", "n", "n"), slug="a")
        full = self.open(facts=("y", "n", "y"), slug="b")
        self.assertIn("size: light", light.stdout)
        self.assertEqual(light.stdout.count("spawn: advisor"), 3)
        self.assertIn("size: full", full.stdout)
        self.assertEqual(full.stdout.count("spawn: advisor"), 5)

    def test_a_forced_size_wins_over_the_facts(self):
        self.assertIn("size: light", self.open(facts=("y", "y", "y"), size="light").stdout)

    def test_light_goes_to_tally_and_full_to_review(self):
        self.assertRegex(self.open(facts=("y", "n", "n"), slug="a").stdout, r"next: .* tally ")
        self.assertRegex(self.open(slug="b").stdout, r"next: .* review ")

    # ---- brief ----

    def test_brief_without_a_section_is_refused_and_nothing_is_created(self):
        result = self.open(brief=BRIEF.replace("## Stakes", "## Other"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("## Stakes", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, "councils")))

    def test_brief_with_an_opinion_in_the_question_is_refused(self):
        result = self.open(brief=BRIEF.replace("Where should", "I think the port is right. Where should"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("opinion", result.stdout)

    def test_brief_needs_two_options_an_existing_source_and_a_lean(self):
        self.assertIn("at least two", self.open(brief=BRIEF.replace("- import: Identity imports the pet repository directly.\n", "")).stdout)
        self.assertIn("not a file", self.open(brief=BRIEF.replace("src/purge.py:1-3", "src/missing.py")).stdout)
        self.assertIn("Lean:", self.open(brief=BRIEF.replace("Lean: import", "Lean: whatever")).stdout)

    def test_brief_names_a_decision_record_that_exists_or_says_none_found(self):
        missing = BRIEF.replace("- docs/decisions/0001-contexts.md", "- docs/decisions/9999.md")
        self.assertIn("Recorded decisions", self.open(brief=missing).stdout)
        searched = BRIEF.replace("- docs/decisions/0001-contexts.md", "none found, searched: docs/")
        self.assertEqual(self.open(brief=searched).returncode, 0)

    def test_the_lean_never_reaches_a_prompt_nor_the_stored_brief(self):
        folder = self.folder(self.open())
        for name in ["brief.md"] + [f"prompts/{seat}.md" for seat in self.meta(folder)["seats"]]:
            with open(os.path.join(folder, name)) as fh:
                text = fh.read()
            self.assertNotIn("Lean:", text, name)
            self.assertNotIn("Sealed lean", text, name)

    def test_doing_nothing_is_always_an_option(self):
        folder = self.folder(self.open())
        self.assertIn("nothing", [key for key, _ in self.meta(folder)["options"]])

    def test_every_seat_sees_every_option_in_its_own_recorded_order(self):
        folder = self.folder(self.open())
        meta = self.meta(folder)
        for seat, order in meta["orders"].items():
            self.assertEqual(sorted(order), sorted(key for key, _ in meta["options"]))
            with open(os.path.join(folder, "prompts", f"{seat}.md")) as fh:
                shown = re.findall(r"^- `([a-z-]+)`:", fh.read().split("## Stakes")[0], re.M)
            self.assertEqual(shown, order)

    def test_the_prompt_carries_the_excerpt_with_line_numbers(self):
        folder = self.folder(self.open())
        with open(os.path.join(folder, "prompts", "skeptic.md")) as fh:
            self.assertIn("2:     pets = pet_repository.find(household)", fh.read())

    def test_the_same_slug_twice_in_a_day_is_refused(self):
        self.open()
        self.assertEqual(self.open().returncode, 1)

    # ---- answers ----

    def test_answer_with_a_quote_that_is_not_on_the_line_is_refused(self):
        folder = self.folder(self.open())
        bad = answer(evidence=['- src/purge.py:2 "this text is nowhere"', '- docs/decisions/0001-contexts.md:3 "Identity imports no other context"'])
        result = self.run_script("answer", folder, "reframer", stdin=bad)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not within three lines", result.stdout)

    def test_answer_citing_only_the_excerpts_is_refused(self):
        folder = self.folder(self.open())
        only = answer(evidence=['- src/purge.py:2 "pets = pet_repository.find"', '- src/purge.py:3 "return pets"'])
        result = self.run_script("answer", folder, "reframer", stdin=only)
        self.assertEqual(result.returncode, 1)
        self.assertIn("different files", result.stdout)

    def test_answer_needs_a_file_beyond_the_brief(self):
        brief = BRIEF.replace("- src/purge.py:1-3", "- src/purge.py:1-3\n- docs/decisions/0001-contexts.md")
        folder = self.folder(self.open(brief=brief))
        result = self.run_script("answer", folder, "reframer", stdin=answer())
        self.assertEqual(result.returncode, 1)
        self.assertIn("read beyond", result.stdout)

    def test_answer_needs_a_valid_pick_and_the_seat_line(self):
        folder = self.folder(self.open())
        self.assertIn("Pick:", self.run_script("answer", folder, "reframer", stdin=answer(pick="banana")).stdout)
        self.assertIn("Data, security, migration", self.run_script("answer", folder, "skeptic", stdin=answer()).stdout)
        self.assertIn("no seat", self.run_script("answer", folder, "poet", stdin=answer()).stdout)

    def test_answer_over_the_word_cap_is_refused(self):
        folder = self.folder(self.open())
        result = self.run_script("answer", folder, "reframer", stdin=answer(extra="word " * 300))
        self.assertIn("the cap is 250", result.stdout)

    def test_answers_close_once_the_review_starts(self):
        folder = self.folder(self.open())
        self.seat_all(folder)
        self.run_script("review", folder)
        self.assertIn("closed", self.run_script("answer", folder, "reframer", stdin=answer()).stdout)

    # ---- review ----

    def test_review_waits_for_every_answer(self):
        folder = self.folder(self.open())
        result = self.run_script("review", folder)
        self.assertEqual(result.returncode, 1)
        self.assertIn("skeptic", result.stdout)

    def test_light_council_has_no_review(self):
        folder = self.folder(self.open(facts=("y", "n", "n")))
        self.seat_all(folder)
        self.assertEqual(self.run_script("review", folder).returncode, 1)

    def test_packets_hide_the_seats_and_the_mapping_names_each_once(self):
        folder = self.folder(self.open())
        self.seat_all(folder)
        self.run_script("answer", folder, "operator", stdin=answer(extra="As the Operator I say the skeptic is wrong."))
        result = self.run_script("review", folder)
        self.assertEqual(result.stdout.count("spawn: reviewer"), 3)
        with open(os.path.join(folder, "mapping.json")) as fh:
            mapping = json.load(fh)
        seats = self.meta(folder)["seats"]
        for n in ("1", "2", "3"):
            self.assertEqual(sorted(mapping[n].values()), sorted(seats))
            with open(os.path.join(folder, "reviews", f"packet-{n}.md")) as fh:
                answers = fh.read().split("## The answers")[1].split("## What to answer")[0]
            for seat in seats:
                self.assertNotRegex(answers, rf"(?i)\b{seat}\b")

    def test_critique_shape_is_checked(self):
        folder = self.folder(self.open())
        self.seat_all(folder)
        self.run_script("review", folder)
        self.assertIn("Doubt:", self.run_script("critique", folder, "1", stdin=critique(doubt="Z")).stdout)
        self.assertIn("Claim:", self.run_script("critique", folder, "1", stdin=critique(claim="maybe")).stdout)
        self.assertIn("Moved by:", self.run_script("critique", folder, "1", stdin=critique(moved="Q")).stdout)
        self.assertIn("no review packet", self.run_script("critique", folder, "9", stdin=critique()).stdout)

    def test_a_claim_called_false_needs_a_citation_and_unverified_does_not(self):
        folder = self.folder(self.open())
        self.seat_all(folder)
        self.run_script("review", folder)
        bare = critique().replace('- src/other.py:1 "from pets import Pet"\n', "nothing\n")
        self.assertIn("needs its check", self.run_script("critique", folder, "1", stdin=bare).stdout)
        self.assertEqual(self.run_script("critique", folder, "1", stdin=bare.replace("Claim: false", "Claim: unverified")).stdout.strip(), "stored")

    # ---- tally and verdict ----

    def test_tally_waits_for_the_critiques(self):
        folder = self.folder(self.open())
        self.seat_all(folder)
        self.run_script("review", folder)
        self.assertIn("no stored critique", self.run_script("tally", folder).stdout)

    def test_full_tally_names_who_made_the_doubted_claim_and_spawns_a_chair(self):
        folder = self.finished_full()
        with open(os.path.join(folder, "packet.md")) as fh:
            packet = fh.read()
        with open(os.path.join(folder, "mapping.json")) as fh:
            mapping = json.load(fh)
        self.assertIn(f"said by {mapping['1']['A']}", packet)
        self.assertIn("E1 `src/purge.py:2`", packet)
        self.assertIn("The export also reads pets.", packet)
        self.assertEqual(packet.count("The export also reads pets."), 1)
        self.assertNotIn("Lean", packet)
        self.assertLess(packet.index("## Evidence"), packet.index("## Picks"))
        self.assertIn("spawn: chair", self.run_script("tally", folder).stdout)

    def test_light_tally_prints_the_packet_for_the_session(self):
        folder = self.folder(self.open(facts=("y", "n", "n")))
        self.seat_all(folder)
        result = self.run_script("tally", folder)
        self.assertIn("# Council packet", result.stdout)
        self.assertNotIn("spawn:", result.stdout)

    def test_verdict_must_cite_evidence_the_packet_has(self):
        folder = self.finished_full()
        self.assertIn("evidence ids", self.run_script("verdict", folder, stdin=verdict(why="Because it is cleaner.")).stdout)
        self.assertIn("E99", self.run_script("verdict", folder, stdin=verdict(why="See E99.")).stdout)

    def test_verdict_shape_is_checked(self):
        folder = self.finished_full()
        self.assertIn("Recommendation:", self.run_script("verdict", folder, stdin=verdict(recommendation="banana")).stdout)
        self.assertIn("one thing", self.run_script("verdict", folder, stdin=verdict(first="- one\n- two")).stdout)
        self.assertIn("Confidence", self.run_script("verdict", folder, stdin=verdict().replace("medium: nobody", "unsure: nobody")).stdout)

    def test_a_split_council_needs_a_dissent_that_names_the_seat(self):
        folder = self.finished_full(picks={"skeptic": "import"})
        self.assertIn("Dissent", self.run_script("verdict", folder, stdin=verdict()).stdout)
        named = verdict(dissent="The skeptic: the port is one more thing to keep in step.")
        self.assertEqual(self.run_script("verdict", folder, stdin=named).stdout.strip(), "stored")

    def test_decide_after_is_an_allowed_outcome(self):
        folder = self.finished_full()
        self.assertEqual(self.run_script("verdict", folder, stdin=verdict(recommendation="decide-after")).stdout.strip(), "stored")

    def test_check_passes_only_when_finished_and_says_whether_the_lean_moved(self):
        folder = self.finished_full()
        unfinished = self.run_script("check", folder)
        self.assertEqual(unfinished.returncode, 1)
        self.assertIn("verdict.md", unfinished.stdout)
        self.run_script("verdict", folder, stdin=verdict())
        done = self.run_script("check", folder)
        self.assertEqual(done.returncode, 0)
        self.assertIn("Recommendation: port", done.stdout)
        self.assertIn("moved the answer: the lean was `import`", done.stdout)
        with open(os.path.join(folder, "receipt.json")) as fh:
            self.assertEqual(json.load(fh)["moved"], "yes")

    def test_index_latest_and_decide_follow_the_council(self):
        folder = self.finished_full()
        self.run_script("verdict", folder, stdin=verdict())
        home = os.path.dirname(folder)
        self.assertEqual(os.path.realpath(os.path.join(home, "latest")), os.path.realpath(folder))
        self.assertIn("recommends `port`", self.run_script("list").stdout)
        decided = self.run_script("decide", folder, "import", "--note", "less code now")
        self.assertIn("against the council's `port`", decided.stdout)
        self.assertIn("chosen `import`", self.run_script("list").stdout)
        self.assertEqual(self.run_script("decide", folder, "banana").returncode, 1)

    def test_a_folder_outside_the_councils_is_refused(self):
        result = self.run_script("check", self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a council folder", result.stdout)

    def test_nothing_is_written_inside_the_repository(self):
        folder = self.finished_full()
        self.run_script("verdict", folder, stdin=verdict())
        status = subprocess.run(["git", "-C", self.repo, "status", "--porcelain"], capture_output=True, text=True).stdout
        self.assertEqual(sorted(line[3:] for line in status.splitlines()), ["docs/", "src/"])


if __name__ == "__main__":
    unittest.main()
