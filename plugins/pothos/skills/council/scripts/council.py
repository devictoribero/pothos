#!/usr/bin/env python3
"""Run a decision through a council: independent advisors, an anonymous review and one verdict.

Everything a script can decide is decided here, so the model only argues and concludes: the size of
the council, the prompt of every seat, the order each seat sees the options in, the anonymous packets,
whether a citation is real, the count of picks and the shape of the verdict.

A council is private, like a receipt: $POTHOS_HOME/councils/<host>/<owner>/<repo>/<YYYY-MM-DD>-<slug>/
(councils/general/ outside a git repository). The folder is the bus: advisors, reviewers and the chair
store their own text through this script and answer the session with one line.

Usage:
  council.py open --slug SLUG --revert y|n --wide y|n --decision y|n [--size light|full] [--repo DIR]
                                    brief on stdin. Sizes the council from the three facts (costly to revert,
                                    crosses a module or a public contract, creates or contradicts a recorded
                                    decision): none, light or full. Then checks the brief, creates the folder
                                    and writes one prompt per seat. Prints the agents to spawn.
  council.py answer FOLDER SEAT     an advisor stores its answer (stdin); refused until its shape is valid
  council.py review FOLDER          full only: shuffles the answers into anonymous packets, one per reviewer
  council.py critique FOLDER N      a reviewer stores its critique (stdin)
  council.py tally FOLDER           builds the chair's packet: evidence, checked claims, positions, picks last
  council.py verdict FOLDER         the chair stores the verdict (stdin); validated, then `check` runs
  council.py check FOLDER           exit 0 only when every file the size needs is there and valid; prints the verdict
  council.py decide FOLDER CHOICE [--note TEXT]
                                    records what the person chose (an option, `none` or `deferred`)
  council.py list [--repo DIR]      earlier councils of this repository

Exit codes: 0 ok, 1 refused (the reasons are printed), 64 usage error. Standard library only.
"""
import datetime
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))
import contract  # noqa: E402  (shared location and repo-key logic)

SEATS_FILE = os.path.join(HERE, "..", "seats.json")
SCRIPT = os.path.abspath(__file__)
BRIEF_SECTIONS = ["question", "options", "stakes", "recorded decisions",
                  "why a test or prototype cannot settle this", "sources", "sealed lean"]
VERDICT_SECTIONS = ["why", "confidence", "where the council clashes", "what every seat missed",
                    "what would flip this", "not verified", "dissent", "first step"]
OPINION = re.compile(r"\b(i lean|we lean|i prefer|we prefer|i think|we think|we should|i would|obviously|clearly)\b", re.I)
CITATION = re.compile(r'^\s*-\s+(\S+?):(\d+)\s+"(.+)"\s*$')
KEY = re.compile(r"^[a-z][a-z0-9-]*$")
NOTHING = "nothing"
BRIEF_FORM = """## Question
<the decision, as a neutral question>
## Options
- <key>: <what this option is>
- <key>: <what this option is>
## Stakes
<what a wrong call costs, and how hard it is to undo>
## Recorded decisions
- <path of each decision record or glossary entry that bears on it>   (or: none found, searched: <folders>)
## Why a test or prototype cannot settle this
<one or two sentences>
## Sources
- <path>:<start>-<end>   (what you already read; every advisor gets these excerpts)
## Sealed lean
Lean: <the option key you or the person lean towards, or none>   (never shown to the council)
"""


class Refused(Exception):
    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def config():
    with open(SEATS_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def flag(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            print(f"{name} needs a value", file=sys.stderr)
            raise SystemExit(64)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return default


def councils_root():
    return os.path.realpath(os.path.join(contract.pothos_home(), "councils"))


def repo_folder(start):
    if not contract.git(["rev-parse", "--show-toplevel"], start):
        return os.path.join(councils_root(), "general")
    return os.path.join(councils_root(), contract.key_for(start, "councils"))


def session(folder):
    """The council folder, which must be one this script created under $POTHOS_HOME/councils."""
    real = os.path.realpath(folder)
    if not real.startswith(councils_root() + os.sep) or not os.path.isfile(os.path.join(real, "meta.json")):
        raise Refused([f"{folder} is not a council folder under {councils_root()}"])
    return real


def read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fh:
        return fh.read()


def write(folder, name, text):
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    return path


def load(folder, name):
    return json.loads(read(folder, name))


def save(folder, name, data):
    write(folder, name, json.dumps(data, indent=2, sort_keys=True))


def sections(text):
    """`## Heading` blocks as {lowercase heading: body}; what precedes the first heading is under ''."""
    out, current = {"": []}, ""
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).lower()
            out[current] = []
        else:
            out[current].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def words(text):
    return len(re.findall(r"\S+", text))


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


# ---------- brief ----------

def size_for(revert, wide, decision):
    yes = [revert, wide, decision].count(True)
    return "none" if yes == 0 else "light" if yes == 1 else "full"


def parse_options(body):
    options = []
    for line in body.splitlines():
        match = re.match(r"^\s*-\s+([^:\s]+)\s*:\s*(.+?)\s*$", line)
        if match:
            options.append((match.group(1), match.group(2)))
    return options


def parse_sources(body, root):
    """`- path` or `- path:start-end` lines as (relative path, start, end); errors name what is wrong."""
    sources, errors = [], []
    for line in body.splitlines():
        match = re.match(r"^\s*-\s+(\S+?)(?::(\d+)-(\d+))?\s*$", line)
        if not match:
            continue
        rel = match.group(1)
        if not inside_repo(root, rel):
            errors.append(f"Sources: {rel} is not a file of this repository")
            continue
        sources.append((rel, int(match.group(2) or 1), int(match.group(3) or 10 ** 9)))
    return sources, errors


def inside_repo(root, rel):
    path = os.path.realpath(os.path.join(root, rel))
    return path.startswith(os.path.realpath(root) + os.sep) and os.path.isfile(path)


def check_brief(text, root):
    """Returns the parsed brief, or raises Refused with every problem found."""
    parts, errors = sections(text), []
    for name in BRIEF_SECTIONS:
        if not parts.get(name):
            errors.append(f"missing or empty section: ## {name.capitalize()}")
    if errors:
        raise Refused(errors)
    slip = OPINION.search(parts["question"])
    if slip:
        errors.append(f"the Question carries an opinion (`{slip.group(0)}`): state it neutrally and put the lean under Sealed lean")
    options = parse_options(parts["options"])
    keys = [key for key, _ in options]
    for key in keys:
        if not KEY.match(key) or key == "none":
            errors.append(f"option key `{key}` must be one lowercase word (letters, digits, hyphens) and not `none`")
    if len(set(keys)) != len(keys):
        errors.append("two options share a key")
    if len([k for k in keys if k != NOTHING]) < 2:
        errors.append("Options needs at least two, as `- <key>: <what it is>`")
    if NOTHING not in keys:
        options.append((NOTHING, "Do nothing for now: leave it as it is and decide later."))
    sources, source_errors = parse_sources(parts["sources"], root)
    errors += source_errors
    if not sources and not source_errors:
        errors.append("Sources needs at least one `- path` or `- path:start-end` you already read")
    decisions = parts["recorded decisions"]
    listed = [m.group(1) for m in re.finditer(r"^\s*-\s+(\S+)", decisions, re.M)]
    if not re.search(r"none found", decisions, re.I) and not any(inside_repo(root, rel) for rel in listed):
        errors.append("Recorded decisions must list a file that exists, or say `none found, searched: <folders>`")
    lean = re.search(r"^Lean:\s*(\S+)", parts["sealed lean"], re.M)
    if not lean or lean.group(1) not in [key for key, _ in options] + ["none"]:
        errors.append("Sealed lean needs a line `Lean: <option key>` or `Lean: none`")
    if errors:
        raise Refused(errors)
    return {"question": parts["question"], "options": options, "stakes": parts["stakes"],
            "decisions": decisions, "sources": sources, "lean": lean.group(1)}


def build_pack(root, sources, cap):
    """The excerpts every advisor starts from, read once, with line numbers, cut at `cap` lines."""
    out, used = [], 0
    for rel, start, end in sources:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        chunk = list(enumerate(lines, 1))[start - 1:end]
        if used + len(chunk) > cap:
            chunk = chunk[:max(cap - used, 0)]
        if not chunk:
            break
        out.append(f"### {rel}:{chunk[0][0]}-{chunk[-1][0]}\n```\n" + "\n".join(f"{n}: {t}" for n, t in chunk) + "\n```")
        used += len(chunk)
    return "\n\n".join(out)


def seat_prompt(folder, seat, spec, brief, order, pack, caps):
    lines = "\n".join(f"- `{key}`: {text}" for key, text in order)
    extra = f"\n- Include {spec['require_hint']}." if spec.get("require_hint") else ""
    return f"""# Council seat: {seat}

You are one advisor of a council. The others answer in parallel and none of you sees another's answer. Hold your angle fully; balance is the chair's job, not yours.

**Your angle.** {spec['looks_for']}

## The decision

{brief['question']}

## Options (in an order drawn for you)

{lines}

## Stakes

{brief['stakes']}

## Recorded decisions the brief found

{brief['decisions']}

## Excerpts every advisor starts from

{pack}

## How to answer

- Read the repository yourself, read-only: at most {caps['lookups']} further lookups. Cite at least two places, in two different files, one of them outside the excerpts above.
- A citation is `- <path>:<line> "<words copied from that line>"`. The script checks the words are there.{extra}
- At most {caps['answer_words']} words outside the evidence.

Store your answer with this command, and fix what it refuses:

```
python3 "{SCRIPT}" answer "{folder}" {seat} <<'COUNCIL'
Pick: <one option key, or none>
## Position
<your case, from your angle>
## Evidence
- <path>:<line> "<words copied from that line>"
- <path>:<line> "<words copied from that line>"
## Would change my mind
<the fact that would move you to another option>
COUNCIL
```

Reply with only the line the command prints.
"""


def cmd_open(args):
    repo = flag(args, "--repo", os.getcwd())
    slug, forced = flag(args, "--slug"), flag(args, "--size")
    facts = {name: flag(args, f"--{name}") for name in ("revert", "wide", "decision")}
    if not slug or not re.match(r"^[a-z0-9][a-z0-9-]*$", slug) or forced not in (None, "light", "full") \
            or any(v not in ("y", "n") for v in facts.values()):
        print("usage: council.py open --slug SLUG --revert y|n --wide y|n --decision y|n [--size light|full] < brief",
              file=sys.stderr)
        return 64
    cfg = config()
    size = forced or size_for(*(v == "y" for v in facts.values()))
    if size == "none":
        print("size: none. Not costly to revert, inside one module, and no recorded decision involved: "
              "decide it and say why. Nothing was created.")
        return 0
    root = contract.repo_root(repo)
    text = sys.stdin.read()
    try:
        brief = check_brief(text, root)
    except Refused as refusal:
        print("brief refused:\n" + "\n".join(f"- {r}" for r in refusal.reasons) + "\n\nThe brief form:\n" + BRIEF_FORM)
        return 1
    home = repo_folder(repo)
    folder = os.path.join(home, f"{datetime.date.today().isoformat()}-{slug}")
    if os.path.isfile(os.path.join(folder, "meta.json")):
        print(f"refused:\n- a council named {slug} was already opened today: {folder}. Pick another slug.")
        return 1
    os.makedirs(os.path.join(folder, "prompts"), exist_ok=True)
    seats = cfg["sizes"][size]["seats"]
    rng = random.SystemRandom()
    orders = {}
    pack = build_pack(root, brief["sources"], cfg["caps"]["pack_lines"])
    for seat in seats:
        order = brief["options"][:]
        rng.shuffle(order)
        orders[seat] = [key for key, _ in order]
        write(folder, f"prompts/{seat}.md", seat_prompt(folder, seat, cfg["seats"][seat], brief, order, pack, cfg["caps"]))
    write(folder, "brief.md", re.split(r"^##\s+Sealed lean\s*$", text, flags=re.M | re.I)[0].rstrip())
    save(folder, "prior.json", {"lean": brief["lean"]})
    save(folder, "meta.json", {"slug": slug, "size": size, "facts": facts, "forced": bool(forced), "root": os.path.realpath(root),
                               "created": datetime.date.today().isoformat(), "seats": seats, "orders": orders,
                               "options": brief["options"], "sources": [s[0] for s in brief["sources"]],
                               "question": brief["question"], "stakes": brief["stakes"]})
    print(f"folder: {folder}\nsize: {size}")
    earlier = index_lines(home)
    if earlier:
        print("earlier councils here:\n" + "\n".join(earlier))
    print_spawns(folder, [(seat, f"prompts/{seat}.md") for seat in seats], cfg["models"]["advisor"], "advisor")
    nxt = "review" if cfg["sizes"][size]["reviewers"] else "tally"
    print(f'next: spawn them all in one message; when each has replied `stored`, run: python3 "{SCRIPT}" {nxt} "{folder}"')
    return 0


def print_spawns(folder, items, model, role):
    for name, rel in items:
        print(f'spawn: {role} {name} | model: {model} | prompt: Read {os.path.join(folder, rel)} and follow it.')


# ---------- evidence ----------

def check_citations(body, root, need, sources=None, files=1):
    """Every `- path:line "words"` line of `body`, verified against the working tree. Returns the list of
    (path, line, words); raises Refused when one is not there or the set is too thin."""
    found, errors = [], []
    for line in body.splitlines():
        match = CITATION.match(line)
        if not match:
            continue
        rel, number, quote = match.group(1), int(match.group(2)), squash(match.group(3))
        if not inside_repo(root, rel):
            errors.append(f"{rel}: not a file of this repository")
            continue
        if len(quote) < 10:
            errors.append(f"{rel}:{number}: quote at least ten characters from the line")
            continue
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        near = squash(" ".join(lines[max(number - 4, 0):number + 3]))
        if quote not in near:
            errors.append(f'{rel}:{number}: "{quote}" is not within three lines of that line')
            continue
        found.append((rel, number, quote))
    if len(found) < need:
        errors.append(f'needs at least {need} citation(s) as `- <path>:<line> "<words copied from that line>"`')
    elif len({rel for rel, _, _ in found}) < files:
        errors.append(f"the citations must come from at least {files} different files")
    elif sources is not None and all(rel in sources for rel, _, _ in found):
        errors.append("cite at least one file the brief's excerpts do not include: read beyond what you were handed")
    if errors:
        raise Refused(errors)
    return found


def pick_of(text, keys, label="Pick"):
    match = re.search(rf"^{label}:\s*(\S+)\s*$", text, re.M)
    return match.group(1) if match and match.group(1) in keys + ["none"] else None


def stdin_or_refuse():
    text = sys.stdin.read()
    if not text.strip():
        raise Refused(["nothing on stdin"])
    return text


def cmd_answer(args):
    if len(args) != 2:
        print("usage: council.py answer FOLDER SEAT < answer", file=sys.stderr)
        return 64
    folder, seat = session(args[0]), args[1]
    meta, cfg = load(folder, "meta.json"), config()
    if seat not in meta["seats"]:
        raise Refused([f"`{seat}` has no seat in this council: {', '.join(meta['seats'])}"])
    if os.path.isfile(os.path.join(folder, "mapping.json")):
        raise Refused(["the review has started: answers are closed"])
    text, errors = stdin_or_refuse(), []
    keys = [key for key, _ in meta["options"]]
    parts = sections(text)
    if not pick_of(text, keys):
        errors.append(f"first line must be `Pick: <key>` with one of: {', '.join(keys)}, none")
    for name in ("position", "evidence", "would change my mind"):
        if not parts.get(name):
            errors.append(f"missing or empty section: ## {name.capitalize()}")
    spec = cfg["seats"][seat]
    if spec.get("require_line") and not re.search(spec["require_line"], text, re.M):
        errors.append(f"this seat must include {spec['require_hint']}")
    cap = cfg["caps"]["answer_words"]
    count = words(parts.get("position", "")) + words(parts.get("would change my mind", ""))
    if count > cap:
        errors.append(f"{count} words outside the evidence; the cap is {cap}")
    try:
        check_citations(parts.get("evidence", ""), meta["root"], 2, meta["sources"], files=2)
    except Refused as refusal:
        errors += refusal.reasons
    if errors:
        raise Refused(errors)
    write(folder, f"answers/{seat}.md", text.strip())
    print("stored")
    return 0


# ---------- review ----------

def missing_answers(folder, meta):
    return [seat for seat in meta["seats"] if not os.path.isfile(os.path.join(folder, "answers", f"{seat}.md"))]


def scrub(text, seats):
    return re.sub(r"\b(" + "|".join(seats) + r")\b", "an advisor", text, flags=re.I)


def review_prompt(folder, n, meta, lettered, cfg):
    answers = "\n\n".join(f"### Answer {letter}\n\n{text}" for letter, text in lettered)
    options = "\n".join(f"- `{key}`: {text}" for key, text in meta["options"])
    letters = ", ".join(letter for letter, _ in lettered)
    questions = "\n".join(f"{i}. {q}" for i, q in enumerate(cfg["review_questions"], 1))
    return f"""# Council review {n}

Advisors answered this decision independently. Their answers are below without names, in an order drawn for you. Judge the arguments.

## The decision

{meta['question']}

## Options

{options}

## The answers

{answers}

## What to answer

{questions}

Check the claim you doubt in the repository yourself, read-only. At most {cfg['caps']['critique_words']} words outside the evidence.

Store your review with this command, and fix what it refuses:

```
python3 "{SCRIPT}" critique "{folder}" {n} <<'COUNCIL'
Doubt: <letter of the answer that makes the claim: {letters}>
Claim: <false, holds or unverified>
Pick: <one option key, or none>
Moved by: <letter, or nobody>
## Claim most likely false
<the claim, in one sentence>
## Check
- <path>:<line> "<words copied from that line>"
## Missed by all
- <one point per line>
COUNCIL
```

Reply with only the line the command prints.
"""


def cmd_review(args):
    if len(args) != 1:
        print("usage: council.py review FOLDER", file=sys.stderr)
        return 64
    folder = session(args[0])
    meta, cfg = load(folder, "meta.json"), config()
    count = cfg["sizes"][meta["size"]]["reviewers"]
    if not count:
        raise Refused([f"a {meta['size']} council has no review: run tally"])
    missing = missing_answers(folder, meta)
    if missing:
        raise Refused([f"no stored answer yet from: {', '.join(missing)}"])
    rng, mapping = random.SystemRandom(), {}
    for n in range(1, count + 1):
        seats = meta["seats"][:]
        rng.shuffle(seats)
        letters = [chr(ord("A") + i) for i in range(len(seats))]
        mapping[str(n)] = dict(zip(letters, seats))
        lettered = [(letter, scrub(read(folder, f"answers/{seat}.md"), meta["seats"])) for letter, seat in zip(letters, seats)]
        write(folder, f"reviews/packet-{n}.md", review_prompt(folder, n, meta, lettered, cfg))
    save(folder, "mapping.json", mapping)
    print_spawns(folder, [(str(n), f"reviews/packet-{n}.md") for n in range(1, count + 1)], cfg["models"]["reviewer"], "reviewer")
    print(f'next: spawn them all in one message; when each has replied `stored`, run: python3 "{SCRIPT}" tally "{folder}"')
    return 0


def cmd_critique(args):
    if len(args) != 2:
        print("usage: council.py critique FOLDER N < critique", file=sys.stderr)
        return 64
    folder, n = session(args[0]), args[1]
    meta, cfg = load(folder, "meta.json"), config()
    if not os.path.isfile(os.path.join(folder, "mapping.json")) or n not in load(folder, "mapping.json"):
        raise Refused([f"no review packet {n} in this council"])
    letters = list(load(folder, "mapping.json")[n])
    text, errors = stdin_or_refuse(), []
    keys = [key for key, _ in meta["options"]]
    parts = sections(text)
    doubt = re.search(r"^Doubt:\s*(\S+)\s*$", text, re.M)
    claim = re.search(r"^Claim:\s*(\S+)\s*$", text, re.M)
    moved = re.search(r"^Moved by:\s*(\S+)\s*$", text, re.M)
    if not doubt or doubt.group(1) not in letters:
        errors.append(f"`Doubt:` must name one answer: {', '.join(letters)}")
    if not claim or claim.group(1) not in ("false", "holds", "unverified"):
        errors.append("`Claim:` must be false, holds or unverified")
    if not pick_of(text, keys):
        errors.append(f"`Pick:` must be one of: {', '.join(keys)}, none")
    if not moved or moved.group(1) not in letters + ["nobody"]:
        errors.append(f"`Moved by:` must be a letter ({', '.join(letters)}) or nobody")
    if not parts.get("claim most likely false"):
        errors.append("missing or empty section: ## Claim most likely false")
    if not re.search(r"^\s*-\s+\S", parts.get("missed by all", ""), re.M):
        errors.append("## Missed by all needs at least one `- point`")
    cap = cfg["caps"]["critique_words"]
    count = words(parts.get("claim most likely false", "")) + words(parts.get("missed by all", ""))
    if count > cap:
        errors.append(f"{count} words outside the evidence; the cap is {cap}")
    if claim and claim.group(1) != "unverified":
        try:
            check_citations(parts.get("check", ""), meta["root"], 1)
        except Refused as refusal:
            errors += [f"a claim called {claim.group(1)} needs its check: {r}" for r in refusal.reasons]
    if errors:
        raise Refused(errors)
    write(folder, f"reviews/critique-{n}.md", text.strip())
    print("stored")
    return 0


# ---------- tally and verdict ----------

def verdict_form(folder, keys):
    return f"""python3 "{SCRIPT}" verdict "{folder}" <<'COUNCIL'
Recommendation: <one of: {', '.join(keys)}, none, decide-after>
## Why
<the reasons, each tied to evidence by its id, like E3>
## Confidence
<low, medium or high>: <why not higher>
## Where the council clashes
<the real disagreements, both sides>
## What every seat missed
<from the reviews, or what you see none of them saw>
## What would flip this
<the fact that would change the recommendation>
## Not verified
<what nobody checked>
## Dissent
<the seat that disagrees and its strongest point, or: none>
## First step
<one thing; for decide-after, the one measurement to take>
COUNCIL"""


def cmd_tally(args):
    if len(args) != 1:
        print("usage: council.py tally FOLDER", file=sys.stderr)
        return 64
    folder = session(args[0])
    meta, cfg = load(folder, "meta.json"), config()
    keys = [key for key, _ in meta["options"]]
    missing = missing_answers(folder, meta)
    if missing:
        raise Refused([f"no stored answer yet from: {', '.join(missing)}"])
    reviewers = cfg["sizes"][meta["size"]]["reviewers"]
    mapping = load(folder, "mapping.json") if reviewers else {}
    absent = [str(n) for n in range(1, reviewers + 1) if not os.path.isfile(os.path.join(folder, "reviews", f"critique-{n}.md"))]
    if reviewers and (not mapping or absent):
        raise Refused(["run review first" if not mapping else f"no stored critique yet from reviewer: {', '.join(absent)}"])

    evidence, ids = [], {}

    def cite(rel, number, quote, who):
        if (rel, number) not in ids:
            ids[(rel, number)] = f"E{len(ids) + 1}"
            evidence.append(f'- {ids[(rel, number)]} `{rel}:{number}` "{quote}" ({who})')
        return ids[(rel, number)]

    positions, picks = [], {}
    for seat in meta["seats"]:
        text = read(folder, f"answers/{seat}.md")
        parts = sections(text)
        picks[seat] = pick_of(text, keys)
        refs = [cite(rel, number, quote, seat) for rel, number, quote in check_citations(parts["evidence"], meta["root"], 0)]
        positions.append(f"### {seat} (picks `{picks[seat]}`; cites {', '.join(refs)})\n\n{parts['position']}\n\n"
                         f"Would change its mind: {parts['would change my mind']}")
    claims, missed, review_picks = [], [], {}
    for n in range(1, reviewers + 1):
        text = read(folder, f"reviews/critique-{n}.md")
        parts = sections(text)
        about = mapping[str(n)][re.search(r"^Doubt:\s*(\S+)", text, re.M).group(1)]
        status = re.search(r"^Claim:\s*(\S+)", text, re.M).group(1)
        refs = [cite(rel, number, quote, f"reviewer {n}") for rel, number, quote in check_citations(parts.get("check", ""), meta["root"], 0)]
        claims.append(f"- **{status}**, said by {about}: {squash(parts['claim most likely false'])}" + (f" ({', '.join(refs)})" if refs else ""))
        missed += [squash(m.group(1)) for m in re.finditer(r"^\s*-\s+(.+)$", parts["missed by all"], re.M)]
        review_picks[str(n)] = pick_of(text, keys)
        mover = re.search(r"^Moved by:\s*(\S+)", text, re.M).group(1)
        if mover != "nobody":
            claims.append(f"- reviewer {n} picks `{review_picks[str(n)]}`, moved by {mapping[str(n)][mover]}")
    split = len(set(picks.values())) > 1
    counts = {key: sum(1 for p in picks.values() if p == key) for key in keys + ["none"]}
    count_line = ", ".join(f"`{key}` {n}" for key, n in counts.items() if n)
    options = "\n".join(f"- `{key}`: {text}" for key, text in meta["options"])
    packet = f"""# Council packet: {meta['slug']}

You chair this council. Decide from what is below: the evidence first, the counts last. A lone seat with the stronger evidence beats the majority.

## The decision

{meta['question']}

## Options

{options}

## Stakes

{meta['stakes']}

## Evidence the script verified in the repository

{chr(10).join(evidence) or '- none'}

## Claims the reviewers checked

{chr(10).join(claims) or '- no review in a light council'}

## Positions

{(chr(10) + chr(10)).join(positions)}

## Missed by every answer

{chr(10).join('- ' + m for m in dict.fromkeys(missed)) or '- no review in a light council'}

## Picks (a count, not a rule)

Advisors: {count_line}. {'The seats are split: the verdict needs a Dissent.' if split else 'The seats agree: say what could still be wrong.'}

## Store the verdict

At most {cfg['caps']['verdict_words']} words. `decide-after` is the honest answer when one measurement would settle it.

```
{verdict_form(folder, keys)}
```
"""
    write(folder, "packet.md", packet)
    save(folder, "tally.json", {"picks": picks, "review_picks": review_picks, "split": split, "evidence": sorted(ids.values())})
    if cfg["sizes"][meta["size"]]["chair"] == "agent":
        print_spawns(folder, [("chair", "packet.md")], cfg["models"]["chair"], "chair")
        print(f'next: when it has replied `stored`, run: python3 "{SCRIPT}" check "{folder}"')
    else:
        print(packet)
    return 0


def check_verdict(text, folder, meta, cfg):
    tally, errors = load(folder, "tally.json"), []
    keys = [key for key, _ in meta["options"]]
    parts = sections(text)
    match = re.search(r"^Recommendation:\s*(\S+)\s*$", text, re.M)
    allowed = keys + ["none", "decide-after"]
    if not match or match.group(1) not in allowed:
        errors.append(f"first line must be `Recommendation: <one of {', '.join(allowed)}>`")
    for name in VERDICT_SECTIONS:
        if not parts.get(name):
            errors.append(f"missing or empty section: ## {name.capitalize()}")
    cited = set(re.findall(r"\bE\d+\b", parts.get("why", "")))
    if not cited:
        errors.append("## Why must tie its reasons to evidence ids from the packet, like E3")
    unknown = sorted(cited - set(tally["evidence"]))
    if unknown:
        errors.append(f"## Why cites evidence the packet does not have: {', '.join(unknown)}")
    if not re.match(r"^(low|medium|high)\b", parts.get("confidence", ""), re.I):
        errors.append("## Confidence must start with low, medium or high")
    if tally["split"] and not re.search(r"\b(" + "|".join(meta["seats"]) + r")\b", parts.get("dissent", ""), re.I):
        errors.append("the seats were split: ## Dissent must name the seat that disagrees")
    if len(re.findall(r"^\s*(?:-|\d+\.)\s+\S", parts.get("first step", ""), re.M)) > 1:
        errors.append("## First step is one thing, not a list")
    cap = cfg["caps"]["verdict_words"]
    if words(text) > cap:
        errors.append(f"{words(text)} words; the cap is {cap}")
    if errors:
        raise Refused(errors)
    return match.group(1)


def index_lines(home):
    path = os.path.join(home, "INDEX.md")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh if line.startswith("- ")]


def index_set(folder, line):
    """One line per council in <repo folder>/INDEX.md, and `latest` pointing at this one."""
    home, name = os.path.dirname(folder), os.path.basename(folder)
    kept = [l for l in index_lines(home) if not l.startswith(f"- {name}:")]
    with open(os.path.join(home, "INDEX.md"), "w", encoding="utf-8") as fh:
        fh.write("# Councils\n\n" + "\n".join(sorted(kept + [f"- {name}: {line}"])) + "\n")
    latest = os.path.join(home, "latest")
    if os.path.islink(latest) or not os.path.exists(latest):
        tmp = latest + ".tmp"
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(name, tmp)
        os.replace(tmp, latest)


def cmd_verdict(args):
    if len(args) != 1:
        print("usage: council.py verdict FOLDER < verdict", file=sys.stderr)
        return 64
    folder = session(args[0])
    meta, cfg = load(folder, "meta.json"), config()
    if not os.path.isfile(os.path.join(folder, "tally.json")):
        raise Refused(["run tally first"])
    text = stdin_or_refuse()
    recommendation = check_verdict(text, folder, meta, cfg)
    lean = load(folder, "prior.json")["lean"]
    moved = "no lean" if lean == "none" else "no" if lean == recommendation else "yes"
    write(folder, "verdict.md", text.strip())
    save(folder, "receipt.json", {"recommendation": recommendation, "lean": lean, "moved": moved, "size": meta["size"],
                                  "split": load(folder, "tally.json")["split"], "date": datetime.date.today().isoformat()})
    index_set(folder, f"{meta['size']} council, recommends `{recommendation}`: {squash(meta['question'])[:120]}")
    print("stored")
    return 0


def cmd_check(args):
    if len(args) != 1:
        print("usage: council.py check FOLDER", file=sys.stderr)
        return 64
    folder = session(args[0])
    meta, cfg = load(folder, "meta.json"), config()
    need = [f"answers/{seat}.md" for seat in meta["seats"]]
    need += [f"reviews/critique-{n}.md" for n in range(1, cfg["sizes"][meta["size"]]["reviewers"] + 1)]
    need += ["packet.md", "verdict.md", "receipt.json"]
    missing = [name for name in need if not os.path.isfile(os.path.join(folder, name))]
    if missing:
        raise Refused([f"this council is not finished, missing: {', '.join(missing)}"])
    text = read(folder, "verdict.md")
    check_verdict(text, folder, meta, cfg)
    receipt = load(folder, "receipt.json")
    moved = {"yes": f"The council moved the answer: the lean was `{receipt['lean']}`.",
             "no": f"The council confirmed the lean, `{receipt['lean']}`.", "no lean": "No lean was sealed."}[receipt["moved"]]
    print(f"{text}\n\n---\n{moved}\ncouncil: {folder}")
    return 0


def cmd_decide(args):
    note = flag(args, "--note", "")
    if len(args) != 2:
        print("usage: council.py decide FOLDER CHOICE [--note TEXT]", file=sys.stderr)
        return 64
    folder, choice = session(args[0]), args[1]
    meta = load(folder, "meta.json")
    keys = [key for key, _ in meta["options"]] + ["none", "deferred"]
    if choice not in keys:
        raise Refused([f"the choice must be one of: {', '.join(keys)}"])
    if not os.path.isfile(os.path.join(folder, "receipt.json")):
        raise Refused(["this council has no verdict yet"])
    receipt = load(folder, "receipt.json")
    save(folder, "decision.json", {"chosen": choice, "note": note, "date": datetime.date.today().isoformat()})
    said = receipt["recommendation"]
    outcome = f"chosen `{choice}`" + ("" if choice == said else f", against the council's `{said}`")
    index_set(folder, f"{meta['size']} council, {outcome}: {squash(meta['question'])[:120]}")
    print(f"recorded: {outcome}")
    return 0


def cmd_list(args):
    lines = index_lines(repo_folder(flag(args, "--repo", os.getcwd())))
    print("\n".join(lines) if lines else "no council yet for this repository")
    return 0


COMMANDS = {"open": cmd_open, "answer": cmd_answer, "review": cmd_review, "critique": cmd_critique,
            "tally": cmd_tally, "verdict": cmd_verdict, "check": cmd_check, "decide": cmd_decide, "list": cmd_list}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(__doc__, file=sys.stderr)
        return 64
    try:
        return COMMANDS[argv[1]](argv[2:])
    except Refused as refusal:
        print("refused:\n" + "\n".join(f"- {r}" for r in refusal.reasons))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
