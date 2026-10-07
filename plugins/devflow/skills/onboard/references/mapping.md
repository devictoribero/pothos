# Mapping the detection report to the contract

Apply these rules in order. Each one names the report field it reads.

## workflow

Leave it out (the default is `devflow`) unless the user says this repository follows its own workflow. Then save `{"version": 1, "workflow": "repo"}` and nothing else unless the user asks: devflow stands aside in that repo.

## verify.full (required unless workflow is repo)

If the report has `package_json_error`, say so first: the scripts could not be read, so no command can be trusted until package.json parses.


1. If `candidates.aggregate` has a script whose body runs lint, types and tests, use it. Prefer `verify`, then `validate`, then `check`. Skip a `check` that only builds.
2. Otherwise, if a CI workflow runs package scripts (`ci[].scripts_used_in_order`), chain those scripts with `&&` in that order, excluding scripts that deploy, publish or need secrets. This is what the pull request must pass anyway.
3. Otherwise chain the first candidate of `typecheck`, `lint` and `test`, in that order, using whichever exist.
4. If none of those exist, stop and ask. A contract without a real `verify.full` is worse than no contract.

Never put a script that writes files, such as `format` with `--write` or `lint:fix`, into any verify command. Read the script body to check.

## verify.fast

1. Use `candidates.fast` if present.
2. Otherwise chain the typecheck and lint candidates, when both exist and the body of neither runs a full build.
3. Leave it out when the only option takes longer than a test run.

## verify.e2e

Use the first `candidates.e2e` script, preferring a headless variant. `e2e_tools` and `e2e_config_paths` only confirm that a suite exists, including in monorepo apps. Leave the field out when there is no e2e script: many repos have no end-to-end suite, and the other skills skip the check when this field is missing.

## run

- `run.dev`: if `candidates.dev_mocked` has a script, use it, always, including in a monorepo. An agent that needs a real backend cannot check its own work, so the mocked script wins over every other consideration. Only when there is no mocked script, use a `dev` candidate; in a monorepo with several apps, pick the script that starts the app most changes touch, and say which one you picked.
- `run.mocked`: true only for a `dev_mocked` script, or when the docs state the dev mode needs no real backend or secrets. Otherwise false.
- `run.environments`: when `environment_variants` lists two or more backends a person would work against (such as dev and demo, not prod), add one entry per backend with its `dev` command, and ask the user what `note` each should carry, such as who works on it. Leave production out. Never pick a default: implement asks which one to use when work starts.
- `run.url`: only when the script body or the docs state the port.
- `run.login`: only when a doc explains how to sign in as a test user.

## docs

Use the first existing path of each `docs` entry. Leave out the empty ones. `GLOSSARY.md` and `CONTEXT.md` are the same thing under the old and new name; map either to `docs.glossary`.

## tracker

- `kind`: `jira` or `linear` only when the agent files describe using it. A mention such as "we do not use Jira" does not count. A GitHub remote with issues in use means `github`. When the repo plans work in markdown files (`tracker_hints.local_dir`, or docs that say so), use `local` with `path` set to that folder. When there is no tracker at all, propose `local` with `path` `.scratch`, but leave the folder uncreated and list it as an assumption. Use `none` only when the user rejects that.
- `project`: the key the docs or issue keys show, such as the prefix of `ABC-123`.
- `skill`: a repository skill in `.claude/skills` or `.agents/skills` whose description says it creates tickets for this tracker.

## review

List repository skills whose description says they review conventions, such as design-system primitives, i18n or specs. Leave out generic review skills, because devflow's review already does that.

## pr

- `base`: `default_branch`. When it is null, ask; without a user, use `main` only if that branch exists and list it as an assumption.
- `template`: `pr_template`.
- `evidence`: a script that uploads screenshots, when one exists under `scripts/`.
