#!/usr/bin/env python3
"""Ensure an import decision is supported by required checks and evidence."""
import json
import sys
from pathlib import Path

REQUIRED_CHECKS = {
    "artifact-structure", "secret-scan", "dependency-review", "test-results",
    "side-effect-review", "rollback-review",
}
CHECK_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
DECISIONS = {"IMPORTABLE", "REVIEW_REQUIRED", "REJECTED", "UNVERIFIED"}


def main():
    if len(sys.argv) != 2:
        print("Usage: validate-result-gate-report.py <report.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: Cannot read report: {exc}", file=sys.stderr)
        return 2

    errors = []
    checks = data.get("checks", {})
    missing = REQUIRED_CHECKS - checks.keys() if isinstance(checks, dict) else REQUIRED_CHECKS
    if missing:
        errors.append("Missing checks: " + ", ".join(sorted(missing)))
    if not isinstance(checks, dict):
        errors.append("checks must be an object.")
        checks = {}
    for name, check in checks.items():
        if not isinstance(check, dict) or check.get("status") not in CHECK_STATUSES:
            errors.append(f"Invalid status for check: {name}")
            continue
        if check.get("status") == "PASS" and not check.get("evidence"):
            errors.append(f"PASS without evidence: {name}")

    decision = data.get("decision")
    if decision not in DECISIONS:
        errors.append("Invalid decision.")
    statuses = {name: check.get("status") for name, check in checks.items() if isinstance(check, dict)}
    if decision == "IMPORTABLE":
        non_pass = [name for name in REQUIRED_CHECKS if statuses.get(name) != "PASS"]
        if non_pass:
            errors.append("IMPORTABLE requires every required check to PASS: " + ", ".join(sorted(non_pass)))
        if not data.get("evidence"):
            errors.append("IMPORTABLE requires top-level evidence.")
    if any(status == "FAIL" for status in statuses.values()) and decision != "REJECTED":
        errors.append("A failed check requires decision REJECTED.")
    if any(status in {"BLOCKED", "NOT_RUN"} for status in statuses.values()) and decision == "IMPORTABLE":
        errors.append("Blocked or unrun checks cannot produce IMPORTABLE.")
    for field in ("task_id", "artifact_root", "destination"):
        if not data.get(field) or "replace-me" in str(data.get(field)):
            errors.append(f"Replace required field: {field}.")

    if errors:
        print("Result-gate report validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Result-gate report validation PASSED: {decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
