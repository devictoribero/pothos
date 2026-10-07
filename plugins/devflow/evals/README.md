# Evals

Each folder is one case for `claude plugin eval`: `case.yaml` sets the run, `prompt.md` is what the user types, `seed.sh` builds the repository the agent works in, and `graders/` score the result. Deterministic graders (file content, trace) carry the weight; an LLM grader judges only the report.

```bash
claude plugin eval plugins/devflow --scaffold --allow-tools Bash Write Edit
claude plugin eval plugins/devflow --scaffold --allow-tools Bash Write Edit --case 'onboard-*' --runs 1
```

`--scaffold` runs the seed scripts, which only write files inside the case workspace.
