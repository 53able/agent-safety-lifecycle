#!/usr/bin/env python3
"""Validate a task-scoped autonomy envelope."""
import hashlib
import json
import sys
from pathlib import Path

REQUIRED = {
    "task_id", "profile", "execution_host", "inputs", "allowed", "denied",
    "network", "credentials", "limits", "outputs",
}
PROFILES = {
    "no-exec", "read-only", "isolated-execution", "brokered-write",
    "human-gated-impact",
}
FORBIDDEN_AMBIENT = {
    "read-host-home", "inherit-host-environment", "use-ssh-agent",
    "access-control-socket", "access-production", "arbitrary-external-network",
    "git-push", "deploy",
}
HOSTS_BY_PROFILE = {
    "no-exec": {"none", "restricted-interpreter"},
    "read-only": {"restricted-interpreter", "guest-vm"},
    "isolated-execution": {"guest-vm"},
    "brokered-write": {"guest-vm"},
    "human-gated-impact": {"guest-vm"},
}
WILDCARD_DESTINATIONS = {"*", "0.0.0.0/0", "::/0", "any"}


def main():
    if len(sys.argv) != 2:
        print("Usage: validate-envelope.py <envelope.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: Envelope not found: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON at line {exc.lineno}: {exc.msg}", file=sys.stderr)
        return 2

    errors = []
    missing = REQUIRED - data.keys()
    if missing:
        errors.append("Missing keys: " + ", ".join(sorted(missing)))

    profile = data.get("profile")
    host = data.get("execution_host")
    if profile not in PROFILES:
        errors.append("Unknown profile.")
    elif host not in HOSTS_BY_PROFILE[profile]:
        allowed_hosts = ", ".join(sorted(HOSTS_BY_PROFILE[profile]))
        errors.append(f"Profile {profile} requires execution_host in: {allowed_hosts}.")

    allowed_raw = data.get("allowed", [])
    denied_raw = data.get("denied", [])
    if not isinstance(allowed_raw, list) or not all(isinstance(x, str) for x in allowed_raw):
        errors.append("allowed must be an array of capability names.")
        allowed = set()
    else:
        allowed = set(allowed_raw)
    if not isinstance(denied_raw, list) or not all(isinstance(x, str) for x in denied_raw):
        errors.append("denied must be an array of capability names.")
        denied = set()
    else:
        denied = set(denied_raw)
    if allowed & denied:
        errors.append("Capabilities appear in both allowed and denied: " + ", ".join(sorted(allowed & denied)))
    leaked = allowed & FORBIDDEN_AMBIENT
    if leaked:
        errors.append("Forbidden ambient capabilities are allowed: " + ", ".join(sorted(leaked)))

    inputs = data.get("inputs", [])
    if not isinstance(inputs, list) or not inputs:
        errors.append("inputs must contain at least one bounded input.")
    else:
        for item in inputs:
            if not isinstance(item, dict) or item.get("mode") != "read-only":
                errors.append("Every host-provided input must use mode: read-only.")
                break

    network = data.get("network", {})
    if network.get("default") != "deny":
        errors.append("network.default must be deny.")
    allow_entries = network.get("allow", [])
    if not isinstance(allow_entries, list):
        errors.append("network.allow must be an array.")
    else:
        for entry in allow_entries:
            destination = entry if isinstance(entry, str) else entry.get("destination") if isinstance(entry, dict) else None
            if destination in WILDCARD_DESTINATIONS:
                errors.append(f"Wildcard network destination is not allowed: {destination}.")

    credentials = data.get("credentials", {})
    if credentials.get("mode") != "none" and not credentials.get("task_scoped_broker"):
        errors.append("Credentials require task_scoped_broker: true.")

    for key in ("wall_time_seconds", "retry_count", "output_bytes"):
        value = data.get("limits", {}).get(key)
        if not isinstance(value, int) or value < 0 or (key != "retry_count" and value == 0):
            errors.append(f"limits.{key} must be a valid bounded integer.")

    outputs = data.get("outputs", [])
    if not isinstance(outputs, list) or not outputs or not all(isinstance(x, str) and x for x in outputs):
        errors.append("outputs must contain at least one named artifact.")
    if "replace-me" in str(data.get("task_id")):
        errors.append("Replace the task_id placeholder.")

    if errors:
        print("Envelope validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    print(f"Envelope validation PASSED: {path}\nsha256:{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
