---
name: explain
description: Explain a flow, an architecture, a codebase area, a plan or a concept as a local HTML page that opens in the browser and stays available to later sessions and other agents. Light theme by default with a dark toggle, diagrams drawn with the archify skill. Use when the user asks to explain, visualize, map, diagram or help them understand something ("explícame", "ayúdame a entender", "how does X work", "show me the architecture", "make me a visual of the plan"). Also use it to find an earlier explanation before writing a new one.
argument-hint: "[topic]"
---

# explain

Turn an explanation into a local HTML page the user can open any time, from any session, without Claude. Pages are private and persistent: they live under the devflow home, next to the contracts, never inside the repository.

Every page loads `../nav.js`, a sidebar with all pages of the repository, children nested under their parent, and the current page's sections and diagrams. `register` rebuilds it, so older pages always show the newest list.

**Output:** a folder with `index.html`, its `diagrams/`, a `summary.md` other agents can read in a few lines, a line in the repository's `INDEX.md`, and the page open in the browser.

Every command below calls `"${CLAUDE_SKILL_DIR}/scripts/artifact.py"`. Write that full path in each command: shell variables do not survive between tool calls.

## Rules

- Write the page in the language of the conversation. Keep code identifiers as they are.
- Ground every claim in what you read: files, commits, docs, the conversation. List the sources at the bottom. Never invent behaviour to make a diagram look complete.
- Write every file of the page with `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" put <folder> <relpath>` and a heredoc, never with the file-editing tools. The folder is outside the project on purpose, where those tools prompt or are denied; `put` is the intended path, not a workaround. To change a file, read it and `put` the whole new version.
- Light theme by default with the dark toggle from the template. Do not remove the toggle or hardcode colours outside the template's tokens.
- Diagrams come from the archify skill bundled in this plugin (`/devflow:archify`, pinned in `vendor.json`). If it cannot run, for example because Node is missing, say so and use a table or a list instead of drawing SVG by hand.
- One page answers one question. A second topic gets its own page.

## Steps

1. **Look for an earlier page.** Run `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" list`. If a page already covers the topic, update it instead of starting a new one, and say what changed.
2. **Gather the material.** Read the code, docs or conversation the explanation needs. Note the files and the commit.
3. **Create the folder.** `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" new --slug <kebab-slug> --title "<Title>" --lang <language code of the conversation>` prints the folder path. When the page goes deeper into a topic an earlier page covers, add `--parent <that page's folder name>` so the sidebar nests it there; link from the parent page to it as well. `parent <folder> <parent folder|none>` moves a page later.
4. **Draw the diagrams.** For each picture the explanation needs, invoke the `devflow:archify` skill. Write its candidate JSON with `put` into `<folder>/diagrams/`, run archify's commands from inside the artifact folder so its working files stay there, and set its output to `diagrams/<name>.html`. Then run `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" light <folder>/diagrams/*.html` so they open in the light theme. Choose the archify type by the question: architecture for parts, workflow for steps, sequence for back-and-forth, dataflow for where data goes, lifecycle for states.
5. **Write the page.** Remove the `data-devflow-placeholder` notice: it is only there so a page opened too early does not look empty. Read the template the folder already has, then `put` the filled `index.html`, following `references/writing.md`: the answer first, then sections, each diagram in a figure with its caption.
6. **Write `summary.md`** with `put`. First line: the answer in one sentence. Then at most fifteen lines of key facts, names and decisions, and the sources. This is what other agents read, so it must stand alone.
7. **Register and open.** `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" register <folder>`, then `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" open <folder>/index.html`.
8. **Reply** with the page path, the one-sentence answer and anything you could not verify.

## Reading earlier pages

Any skill or agent that needs earlier context can run `python3 "${CLAUDE_SKILL_DIR}/scripts/artifact.py" list` and read the relevant `summary.md`. Open the HTML only when the summary is not enough.
