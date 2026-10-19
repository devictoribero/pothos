# Evals

Each folder is one case for `claude plugin eval`: `case.yaml` sets the run, `prompt.md` is what the user types, `seed.sh` builds the repository the agent works in, and `graders/` score the result. Graders are deterministic (file existence, file content, the final message, tool calls). Add an LLM grader only for judgement a regex cannot make, and keep what it reads short: judges miss content at the end of long messages.

```bash
claude plugin eval plugins/pothos --scaffold --allow-tools Bash Write Edit
claude plugin eval plugins/pothos --scaffold --allow-tools Bash Write Edit --case 'plant-*' --runs 1
```

`--scaffold` runs the seed scripts, which only write files inside the case workspace.

In Claude Code the subagent tool is `Agent` (use `tool: Agent` in `tool_used` graders), subagents report back through notifications, and grader regexes are JavaScript: no inline flags such as `(?i)`, use `flags: i`. Pages written by explain are graded through `<repo folder>/latest/`, which points at the last registered page.

The `tend-*` cases never reach GitHub: each seed puts a logging stand-in for `gh` first on `PATH` through the shell profiles of the eval's home folder, answers from `.fakegh/*.json`, and sends pushes to a local bare repository. Graders read `.fakegh/calls.log` and `.fakegh/pushes.log` (written by the bare repository's `post-receive` hook), so they check what the agent ran and pushed, not what it says it did.
