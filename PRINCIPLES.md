# Principles

How this plugin is built. Every skill, script and hook follows these rules, and the checks in `scripts/` enforce the ones a script can check.

The rules for the code agents produce will live in the plugin itself, in `plugins/devflow/shared/engineering.md`, because agents load that file while they work. This file is for people and agents changing the plugin.

## The plugin knows how you work. The repository knows the project.

No skill names a project, a company, a person, a tracker key or a path on someone's machine. Everything project-specific reaches a skill through the repository's contract or through a skill that lives in that repository.

Contracts are private. They live in `~/.config/devflow/contracts/`, keyed by the repository's remote, never inside the repository, so using devflow changes nothing a teammate can see. `scripts/lint_skills.py` fails the build on known project terms.

When a plugin default and a repository convention disagree, the repository wins.

## Deterministic where it can be

If a script can check it, a script checks it: reading the contract, running verification, deciding whether a pull request may open. The model decides only where judgement is needed. A rule written in a prompt is a request; a rule enforced by a script, a hook or CI is a guarantee.

## One skill, one job, one checkable output

A skill does one thing and leaves something you can check: a contract, a verify receipt, screenshots, findings, a pull request. If its output cannot be checked, it cannot be evaluated or chained.

Skills never call the next skill. Each one ends by naming the next step. Chaining the whole cycle belongs in a workflow that calls skills in order, never in a bigger skill.

## Side effects need a person

Skills that write outside the conversation, such as creating tickets, pushing, opening pull requests or replying to reviews, set `disable-model-invocation: true`, so they only run when someone types them. Knowledge skills trigger on their own from their description.

## Small context

`SKILL.md` stays short: what the skill does, its rules and its steps. Detail lives in `references/`, loaded only when a step needs it. Every token in a skill competes with the user's code for the model's attention.

## The description is the trigger

A skill's description says what it does and when to use it, in the words a user would type. It decides whether the skill fires, so it is tested like code.

## Every skill has evals

Each skill ships cases under `evals/` with deterministic graders where possible and an LLM grader only for judgement. Check what the agent did, not what it says it did: a grader that reads `package.json` to confirm it is unchanged beats a judge asked whether the report claims changes. LLM judges also miss content at the end of long messages, so anything a regex can find goes to a regex. Run the evals before each release:

```bash
claude plugin eval plugins/devflow --scaffold
```

## Easy to change

Skills are small and versioned. `CHANGELOG.md` records every release, and the contract carries a `version` so a breaking change can be migrated by `onboard` instead of breaking repositories.

## Missing capabilities are skipped, never improvised

Repositories differ. One has no end-to-end suite, another cannot run without a real backend. When the contract does not declare a capability, skills skip that step and say so in their report. They never invent a substitute command or set up tooling on their own: that is a decision for the person, and the gap shows up in onboard's readiness report.

A repository can also declare that it follows its own workflow (`"workflow": "repo"`). devflow's cycle skills then stand aside there and point to the repository's process; only the knowledge skills apply.

## Third-party skills are pinned

Skills from other authors are copied into the plugin at a known commit, with source, commit and license recorded in `plugins/devflow/vendor.json`. Never edit them by hand. They never update on their own: `.github/workflows/vendor-sync.yml` runs `scripts/vendor_sync.py` every week and, when upstream moved, opens a pull request with the new copy; a person reviews the diff, runs the evals and decides. Updates arrive without surprises, and the evals always describe what actually runs.

## Portable

Scripts use only the Python standard library and POSIX shell, so they run on any machine and in cloud sandboxes without installing anything.
