# Evals

Each folder is one case for `claude plugin eval`: `case.yaml` sets the run, `prompt.md` is what the user types, `seed.sh` builds the repository the agent works in, and `graders/` score the result. Graders are deterministic (file existence, file content, the final message, tool calls). Add an LLM grader only for judgement a regex cannot make, and keep what it reads short: judges miss content at the end of long messages.

```bash
claude plugin eval plugins/pothos --scaffold --allow-tools Bash Write Edit
claude plugin eval plugins/pothos --scaffold --allow-tools Bash Write Edit --case 'plant-*' --runs 1
```

`--scaffold` runs the seed scripts, which only write files inside the case workspace.

In Claude Code the subagent tool is `Agent` (use `tool: Agent` in `tool_used` graders), subagents report back through notifications, and grader regexes are JavaScript: no inline flags such as `(?i)`, use `flags: i`. Pages written by explain are graded through `<repo folder>/latest/`, which points at the last registered page.

The `tend-*` cases never reach GitHub: each seed puts a logging stand-in for `gh` first on `PATH` through the shell profiles of the eval's home folder, answers from `.fakegh/*.json`, and sends pushes to a local bare repository. Graders read `.fakegh/calls.log` and `.fakegh/pushes.log` (written by the bare repository's `post-receive` hook), so they check what the agent ran and pushed, not what it says it did.

The `deps-*` cases share `_shared/deps-seed.sh`: a node repository whose `node_modules` is written by the seed (never an install), a contract with a `deps` section, and stand-ins for `npm` and `gh` first on `PATH`. The `npm` stand-in answers `view` and `audit` from `.fakenpm/registry.json` (publish dates are set relative to the run, so the cooling-off window behaves the same on any day) and applies `install <pkg>@<version>` to `package.json`, the lockfile and `node_modules`; the `gh` stand-in logs to `.fakegh/calls.log` and keeps the body of a created pull request in `.fakegh/pr-body.md`. A post-commit hook logs the branch of every commit to `.loop/commits.log`. Graders read the run record through `.pothos-home/deps/github.com/acme/ledger/latest`, which `deps.py` points at the newest record.

The `implement-fast-check*` cases check the two tiers of verification from the fixture's own logs: every check script is a stand-in that appends its name and the source files changed since the base commit to `.loop/log`, the post-commit and post-receive hooks append `commit` and `push` lines, the pre-push hook runs the gate (so a push without `--no-verify` logs a second `validate`), and the `gh` stand-in saves the pull request body to `.loop/pr-body.md`. Graders assert order and count on those files; the one sentence the session must say once is counted in the `trace`.
