# Questions about code: the vendored how method

When the question is how something in the current repository works (a subsystem, a feature flow, an architectural overview, a runtime trace), investigate with the method in `vendor/how/SKILL.md` (poteto/how, pinned in `vendor.json`). Read it and its `references/` prompts, then apply these adaptations, which win wherever they disagree. Questions about plans, concepts or decisions do not use this method.

## Agents and models

how was written for Cursor. In Claude Code:

| how says | Do this instead |
|---|---|
| explorers: `generalPurpose`, `gpt-5.4`, `readonly` | `subagent_type: Explore` (read-only by design). Inherit the session model. |
| explainer: `generalPurpose`, `claude-opus-4.6`, `readonly` | No explainer subagent: you write the synthesis yourself, because it goes straight into the page. Follow `vendor/how/references/explainer-prompt.md` for the structure and style. |
| critics A, B, C on three models | Critic A: `general-purpose`, inherited model. Critic B: `general-purpose`, `model: sonnet`. Critic C: if the `codex` CLI is installed, run it read-only with the critic prompt through Bash; otherwise a third `general-purpose` critic with `model: opus`. Every critic prompt says it is read-only. |

Keep how's simple versus complex judgement, applied to the code you would have to read:

- **Simple** (one module, a narrow question, or an area you can read in a few files): no subagents. Explore and explain yourself.
- **Complex** (a subsystem across several modules or services, a cross-cutting flow, a full overview): spawn 2 to 4 explorers in one message, each with `vendor/how/references/explorer-prompt.md` and its own angle, then synthesize their findings yourself. Do not read the whole area first to decide; decide from its shape (folders, entry points).

## Waiting for subagents

Explorers and critics run in the background and report back with a notification. Wait for those notifications: do not poll with `sleep`, and do not write the page or the critique until every report is in. Once the page is registered, make sure nothing you started is still running before your final reply, so no late notification arrives after it.

## Output goes to the page, not to the chat

- how's Step 4 ("present it to the user") is replaced by explain's steps: the explainer's text becomes the page.
- Map how's sections to page sections, in the conversation's language: Overview becomes the lede and a short first section; then Key Concepts, How It Works, Where Things Live, Gotchas.
- The explainer must not write Mermaid or ASCII diagrams. Add to its prompt: "Where a diagram would help, list it instead: its kind (architecture, workflow, sequence, dataflow, lifecycle), its parts and the labelled connections between them." You turn that list into archify diagrams, usually one for How It Works and, for broad areas, one architecture map for Where Things Live.
- Keep how's honesty rule: explorer gaps and open questions appear on the page, in Gotchas or a short "Not verified" note.

## Critique mode

Use it when the user asks for problems, risks, improvements or a critique, not only for understanding. Always spawn the critics, however small the code: the point of critique is independent judgement from agents that did not write the explanation, so never critique in your own voice instead. Write the explanation page first, then add a final section, "Critique" in the page's language, with your judgement as a table: Act on, Consider, Noted, Dismissed, each finding with its evidence (files) and impact. Dismissed findings keep a one-line reason. Put the top findings in `summary.md` too.

## Cost

Explorers and critics each read code in their own context. Use two explorers unless the area clearly has more independent slices, and do not run critique unless asked.
