#!/usr/bin/env python3
"""Validate a supervisor state transition against the canonical definition."""
import json
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"
DEFINITION = ASSETS / "state-machine.json"
sys.path.insert(0, str(ASSETS))
from state_machine_validation import validate_definition  # noqa: E402


def load_allowed(path=DEFINITION):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_definition(data)[3]
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid state-machine definition: {exc}") from exc


def main():
    if len(sys.argv) != 3:
        print("Usage: validate-transition.py <from> <to>", file=sys.stderr)
        return 2
    source, target = sys.argv[1:]
    try:
        allowed = load_allowed()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if (source, target) not in allowed:
        print(f"INVALID transition: {source} -> {target}", file=sys.stderr)
        return 1
    print(f"VALID transition: {source} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
