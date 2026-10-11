#!/usr/bin/env python3
"""Check that every bullet in a contract's State, Behavior and Accessibility sections has a test.

Usage: check_contract.py <README.md> <test file or folder> [...]
A bullet counts as covered when some test name (it/test('...')) shares most of its meaningful
words. Contract bullets are written as facts ("Focus stays on the header after sorting") and
tests in their own voice ("keeps focus on the header after sorting"), so matching is by words,
not exact text. Exit code 1 when a bullet has no test. Review the pairs it prints: a low-score
match may be a different test.
"""
import os, re, sys

SECTIONS = ("state", "behavior", "accessibility")
STOP = set("""a an the and or of to in on at by for with without from into is are be it its it's as given shown should
that this these those when while then than every each any all no not never only also so can cannot
does do doesn't don't has have their there them they which who whose what will would should must
own one same until after before over under""".split())

def words(text):
    text = re.sub(r"`([^`]*)`", r" \1 ", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower()  # onOpen -> on open, so it meets "opens"
    toks = re.findall(r"[a-z0-9]+", text)
    out = set()
    for t in toks:
        if t in STOP or len(t) < 3:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if t.endswith(suf) and len(t) - len(suf) >= 3:
                t = t[: -len(suf)]; break
        out.add(t)
    return out

def contract_bullets(readme):
    text = open(readme, encoding="utf-8").read()
    bullets, current = [], None
    for line in text.splitlines():
        head = re.match(r"^\s*(?:#{2,6}\s*|\*\*)([^*:\n]+?)\s*(?:\*\*|:|$)", line)
        if head and not line.lstrip().startswith("-"):
            name = head.group(1).strip().lower()
            current = next((s for s in SECTIONS if name.startswith(s)), None)
            continue
        if current and re.match(r"^\s*[-*]\s+", line):
            bullets.append((current, re.sub(r"^\s*[-*]\s+", "", line).strip()))
    return bullets

def test_names(paths):
    names = []
    for root in paths:
        files = [root] if os.path.isfile(root) else [
            os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if re.search(r"\.(test|spec)\.[jt]sx?$", f)]
        for f in files:
            src = open(f, encoding="utf-8", errors="replace").read()
            # A Given lives in a describe block; join each test with the closest "given" describe before it,
            # so "given a card without onOpen" + "has no interactive element" matches the contract bullet.
            given = ""
            for m in re.finditer(r"""\b(describe|it|test)(?:\.each\([^)]*\))?\(\s*(['"`])(.+?)\2""", src):
                kind, title = m.group(1), m.group(3)
                if kind == "describe":
                    if title.lower().startswith("given"): given = title
                else:
                    names.append((given + " " + title).strip())
    return names

def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    bullets = contract_bullets(argv[0])
    tests = test_names(argv[1:])
    if not bullets:
        print("No bullets found under State, Behavior or Accessibility. Write one fact per bullet."); return 1
    tw = [(t, words(t)) for t in tests]
    missing = 0
    for section, b in bullets:
        bw = words(b)
        best, score = None, 0.0
        for t, w in tw:
            if not bw or not w: continue
            shared = len(bw & w)
            # recall: how much of the bullet the test covers; precision: how much of the test is about the bullet.
            # A bullet that adds an explanation after the fact still matches a test that names the fact.
            s = max(shared / len(bw), (shared / len(w)) if shared >= 3 else 0.0)
            if s > score: best, score = t, s
        ok = score >= 0.5
        missing += not ok
        mark = "ok " if ok else "MISSING"
        print(f"[{mark}] {section}: {b[:100]}")
        if best: print(f"        best test ({score:.0%}): {best[:100]}")
    print(f"{len(bullets) - missing}/{len(bullets)} contract bullets have a matching test ({len(tests)} tests read)")
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
