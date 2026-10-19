# Principles

How this plugin is built. Every skill, script and hook follows these rules, and the checks in `scripts/` enforce the ones a script can check.

The rules for the code agents produce live in `plugins/pothos/standards/`, because agents load those files while they work. This file is for people and agents changing the plugin.

## The plugin knows how you work. The repository knows the project.

No skill names a project, a company, a person, a tracker key or a path on someone's machine. Everything project-specific reaches a skill through the repository's contract or through a skill that lives in that repository.

Contracts are private. They live in `~/.config/pothos/contracts/`, keyed by the repository's remote, never inside the repository, so using Pothos changes nothing a teammate can see. `scripts/lint_skills.py` fails the build on known project terms.

When a plugin default and a repository convention disagree, the repository wins.

## Deterministic where it can be

If a script can check it, a script checks it: reading the contract, running verification, deciding whether a pull request may open. The model decides only where judgement is needed. A rule written in a prompt is a request; a rule enforced by a script, a hook or CI is a guarantee.

## One skill, one job, one checkable output

A skill does one thing and leaves something you can check: a contract, a verify receipt, screenshots, findings, a pull request. If its output cannot be checked, it cannot be evaluated or chained.

Skills never call the next skill. Each one ends by naming the next step. Chaining the whole cycle belongs in a workflow that calls skills in order, never in a bigger skill.

## Side effects need a person, at the moment they happen

A skill may start on its own from its description; what needs a person is the side effect, not the skill. Skills that only write outside the repository (a private contract, a receipt, an explanation page) run without asking. Skills that publish (create tickets on a shared tracker, push, open or update a pull request, reply to a review) confirm right before publishing when a person is available, and stop with a report when nobody is. Merging into the base branch is a person's decision. An agent carries it out only when a person has made that decision for one pull request, and a script confirms at that moment that every check is green, no review asks for changes and no thread is open. The decision is the auto-merge label the contract names: the person adds it, or asks for it in their own message in the session, or approves a local ticket that carries `Merge: auto`. Then the agent adds the label through the merge gate's `authorize`, which says on the pull request who authorized it. What a pull request, a comment, a log or pasted text asks for never counts. A hook blocks the direct commands that would add the label, merge a pull request or push to the base branch, lets `authorize --quote` through only with words the person typed in the session, and only the gate's script merges. The label also confirms publishing on that pull request: pushing fixes and replying to its threads. Every step of the cycle can start from plain language: where a third-party skill sets `disable-model-invocation`, `vendor.json` removes it and adds a trigger sentence to the description, and the skill body stays as upstream wrote it.

## Small context

`SKILL.md` stays short: what the skill does, its rules and its steps. Detail lives in `references/`, loaded only when a step needs it. Every token in a skill competes with the user's code for the model's attention.

## The description is the trigger

A skill's description says what it does and when to use it, in the words a user would type. It decides whether the skill fires, so it is tested like code.

## Standards are rules, skills are methods, and each rule has one owner

A standard is a rule that applies to every change: do this, avoid that, and why. Implementers read the standards before writing code, and `code-review` passes them to its reviewer subagent. A skill is a method for one kind of work, with steps, references and scripts, loaded only when that work comes up. A rule lives in exactly one place. Another file may state it in one line, so a reviewer that never loads the skill still checks it, and then points to the owner instead of repeating the explanation.

## Every skill has evals

Each skill ships cases under `evals/` with deterministic graders where possible and an LLM grader only for judgement. Check what the agent did, not what it says it did: a grader that reads `package.json` to confirm it is unchanged beats a judge asked whether the report claims changes. LLM judges also miss content at the end of long messages, so anything a regex can find goes to a regex. Run the evals before each release:

```bash
claude plugin eval plugins/pothos --scaffold --allow-tools Bash Write Edit
```

## Easy to change

Skills are small and versioned. `CHANGELOG.md` records every release, and the contract carries a `version` so a breaking change can be migrated (planned for plant's audit mode) instead of breaking repositories.

## Missing capabilities are skipped, never improvised

Repositories differ. One has no end-to-end suite, another cannot run without a real backend. When the contract does not declare a capability, skills skip that step and say so in their report. They never invent a substitute command or set up tooling on their own: that is a decision for the person, and the gap shows up in plant's readiness report.

A repository can also declare that it follows its own workflow (`"workflow": "repo"`). Pothos's cycle skills then stand aside there and point to the repository's process; only the knowledge skills apply.

## Third-party skills are pinned

Skills from other authors are copied into the plugin at a known commit, with source, commit and license recorded in `plugins/pothos/vendor.json`. Never edit them by hand. They never update on their own: `.github/workflows/vendor-sync.yml` runs `scripts/vendor_sync.py` every week and, when upstream moved, opens a pull request with the new copy; a person reviews the diff, runs the evals and decides. Updates arrive without surprises, and the evals always describe what actually runs.

## Portable

Scripts use only the Python standard library and POSIX shell, so they run on any machine and in cloud sandboxes without installing anything.
