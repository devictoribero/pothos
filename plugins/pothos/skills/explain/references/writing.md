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
- A diagram is `<figure><div class="diagram"><iframe data-archify src="diagrams/NAME.html?theme=light" …></iframe></div><figcaption>…</figcaption></figure>`. The `data-archify` attribute lets the theme toggle switch the diagram too.

## Writing

- Lead with the answer. One idea per sentence.
- Name things the way the codebase and its glossary do.
- Prefer a table to a paragraph when you compare three or more things.
- No filler headers, no "In this page we will". Stop when the content stops.
