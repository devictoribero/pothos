# Mapping the detection report to the contract

Apply these rules in order. Each one names the report field it reads.

## workflow

Leave it out (the default is `pothos`) unless the user says this repository follows its own workflow. Then save `{"version": 1, "workflow": "repo"}` and nothing else unless the user asks: Pothos stands aside in that repo.

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

## verify.mutation

Read `mutation_tools`. Leave the whole field out when the list is empty: most repositories have no mutation tool, and verify skips the level and says so. Every command comes from a tool the report found: one draft per detected tool; with two tools, ask which one the team runs. verify sets `{files}` (the changed source files, comma-separated and shell-quoted), `POTHOS_CHANGED_FILES` (the same list, one per line), `POTHOS_MUTATION_CACHE` (a folder shared by every clone and worktree, for what the tool reuses between runs) and `POTHOS_MUTATION_OUT` (the receipt folder of the commit, for what the tool writes about this run). Nothing the command writes may land inside the repository: an untracked file makes the next receipt not count. `mutation_temp_ignored` is a gap for the report, never something to fix: Pothos does not edit the ignore file.

- `stryker`: `command` is `npx stryker run --incremental --incrementalFile "$POTHOS_MUTATION_CACHE/stryker-incremental.json" --reporters json --mutate {files} --concurrency <N>` and `report` is `"$POTHOS_MUTATION_OUT/mutation.json"`. Only the `json` reporter: the progress reporter fills the log with a bar nobody watches. `<N>` is about half the machine's cores (`getconf _NPROCESSORS_ONLN`); propose the number and have the user confirm it, since two worktrees often run at once and it stays in the contract as a tunable. Stryker takes no file name for the json reporter on the command line, so the file name goes in the Stryker config as `jsonReporter.fileName`: the config reads `process.env.POTHOS_MUTATION_OUT` and points the file at `$POTHOS_MUTATION_OUT/mutation.json`. Say so in the report when the config is a JSON file or does not set it; until then the reporter writes under `reports/` inside the repository. A config that already narrows `mutate` from `POTHOS_CHANGED_FILES` can drop `--mutate {files}`.
- `mutmut`: `command` is `mutmut run --max-children <N>`, no `report`, and no `{files}`: mutmut 3 reads `paths_to_mutate` from its config and its positional argument is a pattern of mutant names, not a list of files, so `mutmut run {files}` is wrong. Whether the run is narrowed to the changed files, by a positional pattern or by something that reads `POTHOS_CHANGED_FILES`, is the user's decision; without a user, leave `mutmut run` over the configured paths and list it as an assumption. mutmut writes its own results, not the report schema, so the receipt stays at `ran`.
- `cosmic-ray`: detection only confirms the config file. The tool runs as a session (`init`, then `exec`), so ask the user for the command they run and use it as given; no `report`, because its output is not the report schema. Without a user, leave the field out and list the tool as a gap.
- `pit`: the environment-variable form, no `report`. The command is the build's own target, `mvn -q org.pitest:pitest-maven:mutationCoverage` for Maven or `./gradlew pitest` for Gradle, with `-DreportsDirectory="$POTHOS_MUTATION_OUT"` for Maven so the report leaves the repository. PIT takes class names, not file paths, so `{files}` has no place in it; narrowing to the changed files is done by whatever in the build reads `POTHOS_CHANGED_FILES`, and that is the user's decision. PIT writes XML and HTML, not the report schema, so the receipt stays at `ran`.
- `exclude`: only globs the user names, such as generated code. Test files are already excluded by verify.

## run

- `run.dev`: if `candidates.dev_mocked` has a script, use it, always, including in a monorepo. An agent that needs a real backend cannot check its own work, so the mocked script wins over every other consideration. Only when there is no mocked script, use a `dev` candidate; in a monorepo with several apps, pick the script that starts the app most changes touch, and say which one you picked.
- `run.mocked`: true only for a `dev_mocked` script, or when the docs state the dev mode needs no real backend or secrets. Otherwise false.
- `run.setup`: what a fresh worktree needs before the checks can run. Chain the install command with the code-generation steps from `ci[].setup_steps` (or a `setup` candidate that only installs and generates), e.g. `pnpm install --frozen-lockfile && pnpm --filter api db:generate`. Leave out steps that touch a real database or network service. Without it, every implementer worktree fails its first verify.
- `run.environments`: when `environment_variants` lists two or more backends a person would work against (such as dev and demo, not prod), add one entry per backend with its `dev` command, and ask the user what `note` each should carry, such as who works on it. Leave production out. Never pick a default: implement asks which one to use when work starts.
- `run.url`: only when the script body or the docs state the port.
- `run.login`: only when a doc explains how to sign in as a test user.
- `run.screenshots`: whether evidence can take screenshots of the running app: `web` (headless browser at `run.url`), `ios-simulator`, `android-emulator` or `none`. Detection cannot settle this, so always ask, with a proposal: `web` for a web app with `run.dev` and `run.url`, `none` for a backend or library, and ask without proposing for a mobile app. Without a user, leave it out and list it as an assumption.
- `run.apps`: only when `monorepo` is true. One entry per folder in `apps` that a change can touch and that someone would look at running (skip shared packages): `name`, `path`, and its own `dev`, `url`, `mocked` and `screenshots`, with the same rules as the top-level fields. `dev` runs from the repository root, so use a filtered command such as `pnpm --filter <package> dev`. Leave `run.dev` and `run.url` at the top level for the app most changes touch, or out when no app clearly dominates. `verify` and `run.setup` stay at the top level: they cover the whole repository.

## docs

Use the first existing path of each `docs` entry. Leave out the empty ones. `GLOSSARY.md` and `CONTEXT.md` are the same thing under the old and new name; map either to `docs.glossary`.

## tracker

If the repository already has Matt Pocock's setup output (`docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/agents/domain.md`, or an `## Agent skills` block in CLAUDE.md or AGENTS.md), it is the strongest signal: map its tracker, labels and doc layout into the contract, and never edit or delete those files.

- `kind`: `jira` or `linear` only when the agent files describe using it. A mention such as "we do not use Jira" does not count. A GitHub remote with issues in use means `github`; a GitLab remote with issues in use means `gitlab`. When the repo plans work in markdown files (`tracker_hints.local_dir`, or docs that say so), use `local` with `path` set to that folder. When there is no tracker at all, propose `local` with `path` `.scratch`, but leave the folder uncreated and list it as an assumption. Use `none` only when the user rejects that.
- `project`: the key the docs or issue keys show, such as the prefix of `ABC-123`.
- `skill`: a repository skill in `.claude/skills` or `.agents/skills` whose description says it creates tickets for this tracker.
- `labels`: only for roles whose label differs from the role name (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), taken from `docs/agents/triage-labels.md` or labels already in use on the tracker. Leave it out otherwise.

## review

- `skills`: repository skills whose description says they review conventions, such as design-system primitives, i18n or specs. Leave out generic review skills, because `code-review` already does that.
- `standards`: repository files that document how code should be written but that `code-review` would not find by name, such as `docs/conventions.md` or a style guide under `docs/`. Leave out `CODING_STANDARDS.md` and `CONTRIBUTING.md`, which it always reads.

## build

- `skills`: repository skills that guide how code is written rather than checked afterwards, such as design-system or component rules whose description says to use them when creating or editing files. A skill can be in both `build.skills` and `review.skills`.

## ui

Read `ui` in the report. Every value is a candidate found on disk; nothing in it is chosen yet. Skip the whole section for a repository with no UI.

In a monorepo, each app gets its own `ui` inside its `run.apps` entry, built from the candidates under that app's path and the icon packages `declared_in` it. Use the top-level `ui` only for UI shared by several apps, such as a `packages/ui` design system.

- `components`: the folders whose components every feature may use, such as design-system primitives and common UI. Never take a `feature_scoped` folder: it belongs to one feature. When a parent and its child are both listed (`src/components` and `src/components/primitives`), keep the folders a reader would search first, usually the children that hold primitives and common pieces, and ask when it is not clear.
- `tokens`: the files that define the theme or the tokens new code must use. Open each candidate: a file that only consumes values, or a single component's local tokens, does not count. Leave the field out when no file defines a shared scale.
- `icons`: the package in `icon_packages` with clearly the most imports. When two packages are both in real use, ask which one new code takes; without a user, leave it out and list it as an assumption.
- `preview`: a `preview_scripts` entry, with `command` as given and `url` only when it carries a port. `storybook_config` without a script means the preview cannot be started; leave it out and report the gap.

## pr

- `base`: `default_branch`. When it is null, ask; without a user, use `main` only if that branch exists and list it as an assumption.
- `template`: `pr_template`.
- `evidence`: a script that uploads screenshots, when one exists under `scripts/`. Otherwise, for a GitHub repository whose apps take screenshots, ask whether to use `github-release` (a `pr-evidence-YYYY-MM` prerelease per month, kept forever); it publishes to the repository, so never set it without a yes.
- `auto_merge`: only when the user asks for it, since it lets labelled pull requests merge without a person at the end (the person still authorizes each one: the label, "and merge it", or a `Merge: auto` ticket). Ask for the label (suggest `auto-merge`, or the one the team already uses) and leave `method` out unless the repository merges another way than squash.
