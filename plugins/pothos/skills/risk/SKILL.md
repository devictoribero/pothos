---
name: risk
description: Assesses how risky a pull request is to merge, its blast radius, its complexity and the confidence that it brings no regression, for the Risk section of a pull request. Use before a pull request leaves draft, after verify, and when asked "how risky is this", "can we merge this safely" or "what's the blast radius".
---

# Risk

A reviewer deciding whether to merge needs three answers, each Low, Medium or High (levels, because a model's percentage is not calibrated):

- **Risk:** what breaks, and how hard it is to undo, if the change is wrong.
- **Complexity:** the size and spread of the source change, without tests, docs or generated files.
- **Confidence:** how well the change is backed against a regression or a new bug.

The section is advisory: it informs the merge decision and never blocks it. The script measures what a script can (door, blast radius, size, verify receipts, evidence); you add what only you know. The contract's optional `pr.risk` names the repository's core areas, one-way paths, public contracts and generated files; `risk.py --help` lists the rules.

## Steps

1. **Assess.** Run `verify` first: without a passing full receipt for HEAD, Confidence stays at Low. Then, from inside the repository, run `python3 "${CLAUDE_SKILL_DIR}/scripts/risk.py" assess [--base REF]`. It prints the `## Risk` section; `--json` prints every signal. It assesses commits only: when stderr says the tree has uncommitted changes, commit them and run it again. Done when the section printed for a clean tree.
2. **Raise, with a reason.** The printed Risk and Complexity are floors. Raise either one when you know something the diff does not show: a behaviour change hidden in a shared helper, a manual step at deploy time, a flag that turns the change on for everyone. Each raise adds one line under the bullets, `- **Raised:** Risk Medium to High: <reason>.` Done when every level is at or above what the script printed and every raise carries its reason.
3. **Set Confidence** at or below the printed ceiling, from what you know: a fresh-eyes review done or not, a test that failed before its fix and passes after, a device or manual pass, changed areas no test reaches. Replace the HTML comment with two lines at most: why it is not higher, and what would raise it. Done when the comment is gone and Confidence is at or below the ceiling.
4. **Place the section.** The repository's template wins: fill its risk section when it has one; otherwise put `## Risk` right before the test plan, or last when there is none. With the `pr` skill's template the same facts fill its Merge Danger section: the door line as Door, the blast radius line as Blast Radius, and the three levels with it. A pull request that is already open is published content: confirm with the person before updating its body.
5. **Report** the three levels and every raise. When the section says `none declared in the contract`, say so and suggest adding `pr.risk.core` with `/pothos:plant audit`, so the next assessment knows the core areas. The next step is the pull request itself, with `pr`.
