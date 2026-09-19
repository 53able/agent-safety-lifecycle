"""Host-side adapter for the existing transition validator."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from .ipc import IPCError, read_token_fd, send

VALIDATOR = Path(__file__).resolve().parents[2] / "skills" / "agent-run-supervisor" / "scripts" / "validate-transition.py"


class AdapterError(RuntimeError):
    pass


def validate_transition(event: dict[str, Any]) -> None:
    if event.get("type") != "STATE_TRANSITION":
        return
    state = event.get("state")
    if not isinstance(state, dict):
        raise AdapterError("transition state is malformed")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(state.get("from", "")), str(state.get("to", ""))],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AdapterError("transition validator rejected the event")


def emit_events(socket_path: Path, token: str, events: Iterable[dict[str, Any]]) -> None:
    for event in events:
        validate_transition(event)
        acknowledgement = send(socket_path, token, event)
        if not acknowledgement.get("ok"):
            raise AdapterError(f"recorder rejected event: {acknowledgement.get('code', 'UNKNOWN')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated host-side transition validator adapter")
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--token-fd", required=True, type=int)
    parser.add_argument("--events", required=True, type=Path, help="JSON file containing an event array")
    arguments = parser.parse_args(argv)
    try:
        token = read_token_fd(arguments.token_fd)
        data = json.loads(arguments.events.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise AdapterError("events file must contain an event array")
        emit_events(arguments.socket, token, data)
    except (OSError, json.JSONDecodeError, IPCError, AdapterError) as exc:
        print(f"adapter failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
