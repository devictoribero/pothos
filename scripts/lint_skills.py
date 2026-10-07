#!/usr/bin/env python3
"""Check every skill in the plugin follows PRINCIPLES.md where a script can tell.

Checks:
- SKILL.md has frontmatter with a name that matches its directory and a description.
- The description fits in 1024 characters and SKILL.md stays under 300 lines.
- Files referenced as references/... or scripts/... from SKILL.md exist.
- No file under the plugin matches scripts/forbidden-terms.txt.

Exit 0 when clean, 1 when any check fails. Standard library only.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "development-flow")
MAX_SKILL_LINES = 300
MAX_DESCRIPTION = 1024
TEXT_EXTENSIONS = (".md", ".json", ".py", ".sh", ".yaml", ".yml", ".txt")


def frontmatter(text):
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
    return fields


def forbidden_patterns():
    with open(os.path.join(ROOT, "scripts", "forbidden-terms.txt"), encoding="utf-8") as fh:
        lines = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    return [re.compile(l, re.I) for l in lines]


def check_skills():
    errors = []
    skills_dir = os.path.join(PLUGIN, "skills")
    for name in sorted(os.listdir(skills_dir)):
        skill_dir = os.path.join(skills_dir, name)
        path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isdir(skill_dir):
            continue
        if not os.path.isfile(path):
            errors.append(f"skills/{name}: missing SKILL.md")
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        fields = frontmatter(text)
        if fields is None:
            errors.append(f"skills/{name}/SKILL.md: missing frontmatter")
            continue
        if fields.get("name") != name:
            errors.append(f"skills/{name}/SKILL.md: name '{fields.get('name')}' does not match directory")
        description = fields.get("description", "")
        if not description:
            errors.append(f"skills/{name}/SKILL.md: missing description")
        elif len(description) > MAX_DESCRIPTION:
            errors.append(f"skills/{name}/SKILL.md: description is {len(description)} chars, max {MAX_DESCRIPTION}")
        lines = text.count("\n") + 1
        if lines > MAX_SKILL_LINES:
            errors.append(f"skills/{name}/SKILL.md: {lines} lines, max {MAX_SKILL_LINES}; move detail to references/")
        for ref in sorted(set(re.findall(r"\b((?:references|scripts)/[\w./-]+\.\w+)", text))):
            if not os.path.exists(os.path.join(skill_dir, ref)):
                errors.append(f"skills/{name}/SKILL.md: references missing file {ref}")
    return errors


def check_forbidden():
    errors = []
    patterns = forbidden_patterns()
    for base, _, files in os.walk(PLUGIN):
        if "/evals" in base.replace(PLUGIN, ""):
            continue
        for file in files:
            if not file.endswith(TEXT_EXTENSIONS):
                continue
            path = os.path.join(base, file)
            with open(path, encoding="utf-8", errors="replace") as fh:
                for number, line in enumerate(fh, 1):
                    for pattern in patterns:
                        if pattern.search(line):
                            errors.append(f"{os.path.relpath(path, ROOT)}:{number}: project-specific term /{pattern.pattern}/")
    return errors


def main():
    errors = check_skills() + check_forbidden()
    for error in errors:
        print(error)
    print("ok" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
