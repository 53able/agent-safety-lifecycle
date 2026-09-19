#!/usr/bin/env python3
"""Validate Agent Skill structure, metadata, references, and project invariants."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(
    r"^---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---\n",
    re.MULTILINE,
)
PATH_RE = re.compile(r"`((?:assets|references|scripts)/[^`\s]+)`")
ALLOWED_DIRS = {"assets", "references", "scripts"}
FORBIDDEN_DOCS = {"README.md", "CHANGELOG.md", "INSTALLATION.md", "INSTALLATION_GUIDE.md"}


def validate_skill(skill: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill / "SKILL.md"
    if not skill_file.is_file():
        return [f"{skill.name}: missing SKILL.md"]
    text = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return [f"{skill.name}: invalid frontmatter; expected one-line name and description"]
    name, description = match.groups()
    if name != skill.name:
        errors.append(f"{skill.name}: frontmatter name does not match directory: {name}")
    if not NAME_RE.fullmatch(name):
        errors.append(f"{skill.name}: invalid skill name")
    if len(description) > 1024:
        errors.append(f"{skill.name}: description exceeds 1024 characters")
    if "Use when" not in description or "Don't use for" not in description:
        errors.append(f"{skill.name}: description needs positive and negative triggers")
    if re.search(r"\b(?:I|me|my|you|your)\b", description, re.IGNORECASE):
        errors.append(f"{skill.name}: description must remain third person")
    if len(text.splitlines()) >= 500:
        errors.append(f"{skill.name}: SKILL.md must be under 500 lines")
    if "## Error Handling" not in text:
        errors.append(f"{skill.name}: missing Error Handling section")
    if not re.search(r"\*\*Step 1:", text):
        errors.append(f"{skill.name}: missing numbered chronological procedure")

    present_dirs = {p.name for p in skill.iterdir() if p.is_dir()}
    missing_dirs = ALLOWED_DIRS - present_dirs
    extra_dirs = present_dirs - ALLOWED_DIRS
    if missing_dirs:
        errors.append(f"{skill.name}: missing directories: {', '.join(sorted(missing_dirs))}")
    if extra_dirs:
        errors.append(f"{skill.name}: unexpected directories: {', '.join(sorted(extra_dirs))}")
    for forbidden in FORBIDDEN_DOCS:
        if (skill / forbidden).exists():
            errors.append(f"{skill.name}: human-centric file is not allowed inside a skill: {forbidden}")
    for directory in ALLOWED_DIRS:
        target = skill / directory
        if target.is_dir():
            nested = [
                p for p in target.rglob("*")
                if p.is_dir() and p.name != "__pycache__"
            ]
            if nested:
                errors.append(f"{skill.name}: {directory}/ must remain one level deep")
            if not any(p.is_file() for p in target.iterdir()):
                errors.append(f"{skill.name}: {directory}/ must contain at least one file")

    for relative in PATH_RE.findall(text):
        clean = relative.rstrip(".,;:)")
        if any(marker in clean for marker in ("<", ">", "path/to/")):
            continue
        if not (skill / clean).exists():
            errors.append(f"{skill.name}: referenced file does not exist: {clean}")
    if "\\" in text:
        errors.append(f"{skill.name}: use forward slashes in SKILL.md paths")
    return errors


def main() -> int:
    if not SKILLS.is_dir():
        print(f"ERROR: skills directory not found: {SKILLS}", file=sys.stderr)
        return 2
    skills = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    errors: list[str] = []
    for skill in skills:
        errors.extend(validate_skill(skill))
    if not skills:
        errors.append("No skills found")
    if errors:
        print("Project validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Project validation PASSED: {len(skills)} skills")
    for skill in skills:
        print(f"- {skill.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
