---
name: explain
description: Explain a flow, an architecture, a codebase area, a plan or a concept as a local HTML page that opens in the browser and stays available to later sessions and other agents. Light theme by default with a dark toggle, diagrams drawn with the archify skill. Use when the user asks to explain, visualize, map, diagram or help them understand something ("explícame", "ayúdame a entender", "how does X work", "show me the architecture", "make me a visual of the plan"), or when an answer needs a diagram or more than a screen of text. Also use it to find an earlier explanation before writing a new one.
argument-hint: "[topic]"
---

# explain

Turn an explanation into a local HTML page the user can open any time, from any session, without Claude. Pages are private and persistent: they live under the devflow home, next to the contracts, never inside the repository.

**Output:** a folder with `index.html`, its `diagrams/`, a `summary.md` other agents can read in a few lines, a line in the repository's `INDEX.md`, and the page open in the browser.

```bash
A="${CLAUDE_SKILL_DIR}/scripts/artifact.py"
```

## Rules

- Write the page in the language of the conversation. Keep code identifiers as they are.
- Ground every claim in what you read: files, commits, docs, the conversation. List the sources at the bottom. Never invent behaviour to make a diagram look complete.
- Write every file of the page with `python3 "$A" put <folder> <relpath>` and a heredoc, never with the file-editing tools. The folder is outside the project on purpose, where those tools prompt or are denied; `put` is the intended path, not a workaround. To change a file, read it and `put` the whole new version.
- Light theme by default with the dark toggle from the template. Do not remove the toggle or hardcode colours outside the template's tokens.
- Diagrams come from the archify skill. If archify is not available, say so and use a table or a list instead of drawing SVG by hand.
- One page answers one question. A second topic gets its own page.

## Steps

1. **Look for an earlier page.** Run `python3 "$A" list`. If a page already covers the topic, update it instead of starting a new one, and say what changed.
2. **Gather the material.** Read the code, docs or conversation the explanation needs. Note the files and the commit.
3. **Create the folder.** `python3 "$A" new --slug <kebab-slug> --title "<Title>"` prints the folder path.
4. **Draw the diagrams.** For each picture the explanation needs, invoke the archify skill. Write its candidate JSON with `put` into `<folder>/diagrams/`, run archify's commands from inside the artifact folder so its working files stay there, and set its output to `diagrams/<name>.html`. Then run `python3 "$A" light <folder>/diagrams/*.html` so they open in the light theme. Choose the archify type by the question: architecture for parts, workflow for steps, sequence for back-and-forth, dataflow for where data goes, lifecycle for states.
5. **Write the page.** Read the template the folder already has, then `put` the filled `index.html`, following `references/writing.md`: the answer first, then sections, each diagram in a figure with its caption.
6. **Write `summary.md`** with `put`. First line: the answer in one sentence. Then at most fifteen lines of key facts, names and decisions, and the sources. This is what other agents read, so it must stand alone.
7. **Register and open.** `python3 "$A" register <folder>`, then `python3 "$A" open <folder>/index.html`.
8. **Reply** with the page path, the one-sentence answer and anything you could not verify.

## Reading earlier pages

Any skill or agent that needs earlier context can run `python3 "$A" list` and read the relevant `summary.md`. Open the HTML only when the summary is not enough.
