# AGENTS.md block

Insert this block verbatim, between and including the markers. On a re-run, replace everything between the markers and leave the rest of the file untouched.

```markdown
<!-- development-flow:contract:start -->
## Agent contract

`.agents/contract.json` tells agents how to verify, run and ship changes in this repo. It is the source of truth for those commands; keep it in sync when scripts or CI change, or re-run `/development-flow:onboard audit`.

- Before opening a pull request, `verify.full` must pass on the current commit.
- After editing code, `verify.fast` gives quick feedback when it is set.
- Domain language and decisions live at the paths under `docs`.
<!-- development-flow:contract:end -->
```
