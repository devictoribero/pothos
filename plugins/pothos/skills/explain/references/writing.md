# Writing the page

The reader knows the domain but did not watch you work. They will skim first and read later, possibly in another session.

## Structure

1. **Header.** The meta line (repository, date, commit), the title, and a lede that answers the question in two or three sentences.
2. **Sections in the order the reader needs them.** For a flow: what triggers it, the steps, where it can fail. For an architecture: the parts, how they talk, where the boundaries are. For a concept: what it is, why it exists, an example from this codebase, how it differs from what it is often confused with.
3. **One diagram per claim.** Put it right after the paragraph it supports. The caption says what the picture shows, in one or two sentences.
4. **Sources at the bottom.** Files with paths, the commit, docs and tickets.

## Components in the template

- `.read` keeps running text near 70 characters wide. Wrap paragraphs in it; leave diagrams and tables full width.
- `.table` wraps a table so it scrolls on narrow screens.
- `.callout` highlights the one thing the reader must not miss; `.callout.warn` marks a risk. Use at most two per page.
- `pre` for commands and snippets; `code` for names inside sentences.
- `.cards` is a grid of `.card` articles for a set of parallel things (the pieces of a system, the options of a decision). A card is a `header` (name, then its badges), a paragraph, and optionally a `.pc` list. Give a card a group colour with `style="--accent: …"` only when the colour already means something elsewhere on the page, such as a phase in the diagrams.
- Pros and cons go in `<dl class="pc"><div><dt>Pro</dt><dd>…</dd></div><div><dt>Con</dt><dd>…</dd></div></dl>`: two columns, the label above its reason, never label and reason on one line.
- A badge is `<span class="b"><span class="k">key:</span>value</span>`, one neutral style for every badge. The key says what the badge classifies (`author:`, `launch:`, `status:`) and the value is a lowercase slug (`pocock`, `los-dos`, `otra-skill`). Meaning comes from the key, not from a colour per value: a page with five badge colours plus phase colours reads as noise.
- A diagram is `<figure><div class="diagram"><iframe data-archify src="diagrams/NAME.html?theme=light" …></iframe></div><figcaption>…</figcaption></figure>`. The `data-archify` attribute lets the theme toggle switch the diagram too.

## Writing

- Lead with the answer. One idea per sentence.
- Name things the way the codebase and its glossary do.
- Prefer a table to a paragraph when you compare three or more things.
- No filler headers, no "In this page we will". Stop when the content stops.
