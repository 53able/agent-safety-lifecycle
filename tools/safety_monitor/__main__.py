"""Development CLI for replay-first safety monitoring."""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .ipc import IPCError, serve
from .presenter import escape_text, render_snapshot
from .projection import replay
from .store import StoreError, read_events, read_history
from .watch import WatchError, watch_run


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _snapshot(event_root: Path, run_id: str, allowed_parent: Path, artifact_root: Path | None = None) -> str:
    del artifact_root  # Kept internal for a stable call site; replay is strictly read-only.
    events = read_events(event_root, run_id, allowed_parent)
    if not events:
        raise StoreError("RUN_NOT_FOUND", "no events found for run")
    projection = replay(events)
    if not projection.is_valid:
        raise StoreError("INTEGRITY_FAILURE", "; ".join(projection.warnings))
    return render_snapshot(projection)


def _positive_interval(value: str) -> float:
    try:
        interval = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("poll interval must be a positive number") from exc
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("poll interval must be a positive number")
    return interval


def _pipe_with_token(token: str) -> tuple[int, int]:
    read_descriptor, write_descriptor = os.pipe()
    os.write(write_descriptor, token.encode("ascii"))
    os.close(write_descriptor)
    return read_descriptor, write_descriptor


def vertical_slice(arguments: argparse.Namespace) -> int:
    event_root = arguments.event_root
    artifact_root = arguments.artifact_root
    allowed_parent = arguments.allowed_parent
    token = secrets.token_hex(32)
    server_read, _ = _pipe_with_token(token)
    adapter_read, _ = _pipe_with_token(token)
    socket_dir = event_root / ".ipc"
    socket_path = socket_dir / "recorder.sock"
    now = _now()
    events = [
        {
            "schema_version": "1.0",
            "producer_event_id": f"{arguments.run_id}.created",
            "task_id": arguments.task_id,
            "run_id": arguments.run_id,
            "occurred_at": now,
            "type": "RUN_CREATED",
            "summary": "Run created",
            "envelope_hash": arguments.envelope_hash,
        },
        {
            "schema_version": "1.0",
            "producer_event_id": f"{arguments.run_id}.running",
            "task_id": arguments.task_id,
            "run_id": arguments.run_id,
            "occurred_at": now,
            "type": "STATE_TRANSITION",
            "summary": "Run started",
            "state": {"from": "PLANNED", "to": "RUNNING"},
        },
    ]
    server_command = [
        sys.executable, "-m", "tools.safety_monitor", "_serve",
        "--socket", str(socket_path), "--event-root", str(event_root),
        "--artifact-root", str(artifact_root), "--allowed-parent", str(allowed_parent),
        "--token-fd", str(server_read), "--max-requests", "2",
    ]
    server_process = subprocess.Popen(server_command, pass_fds=(server_read,))
    os.close(server_read)
    try:
        deadline = time.monotonic() + 5
        while not socket_path.exists():
            if server_process.poll() is not None:
                raise RuntimeError("recorder exited before creating its socket")
            if time.monotonic() >= deadline:
                raise RuntimeError("timed out waiting for recorder socket")
            time.sleep(0.01)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as stream:
            json.dump(events, stream)
            events_path = Path(stream.name)
        try:
            adapter_result = subprocess.run(
                [
                    sys.executable, "-m", "tools.safety_monitor.validator_adapter",
                    "--socket", str(socket_path), "--token-fd", str(adapter_read), "--events", str(events_path),
                ],
                pass_fds=(adapter_read,),
                check=False,
            )
        finally:
            os.close(adapter_read)
            events_path.unlink(missing_ok=True)
        if adapter_result.returncode != 0:
            raise RuntimeError("validator adapter failed")
        if server_process.wait(timeout=5) != 0:
            raise RuntimeError("recorder failed")
        sys.stdout.write(_snapshot(event_root, arguments.run_id, allowed_parent, artifact_root))
        return 0
    except Exception:
        server_process.terminate()
        try:
            server_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server_process.kill()
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay-first safety monitor development tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    vertical = subparsers.add_parser("vertical-slice", help="record and replay the two-event prototype flow")
    vertical.add_argument("--event-root", required=True, type=Path)
    vertical.add_argument("--artifact-root", required=True, type=Path)
    vertical.add_argument("--allowed-parent", required=True, type=Path)
    vertical.add_argument("--task-id", required=True)
    vertical.add_argument("--run-id", required=True)
    vertical.add_argument("--envelope-hash", required=True)
    snapshot = subparsers.add_parser("snapshot", help="read and replay one saved run")
    snapshot.add_argument("--event-root", required=True, type=Path)
    snapshot.add_argument("--allowed-parent", required=True, type=Path)
    snapshot.add_argument("--run-id", required=True)
    watch = subparsers.add_parser("watch", help="follow one saved run read-only until Ctrl-C")
    watch.add_argument("--event-root", required=True, type=Path)
    watch.add_argument("--allowed-parent", required=True, type=Path)
    watch.add_argument("--run-id", required=True)
    watch.add_argument("--poll-interval", type=_positive_interval, default=0.5)
    watch.add_argument("--format", choices=("text", "view-model-jsonl"), default="text")
    internal = subparsers.add_parser("_serve", help=argparse.SUPPRESS)
    internal.add_argument("--socket", required=True, type=Path)
    internal.add_argument("--event-root", required=True, type=Path)
    internal.add_argument("--artifact-root", required=True, type=Path)
    internal.add_argument("--allowed-parent", required=True, type=Path)
    internal.add_argument("--token-fd", required=True, type=int)
    internal.add_argument("--max-requests", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "vertical-slice":
            return vertical_slice(arguments)
        if arguments.command == "snapshot":
            sys.stdout.write(_snapshot(arguments.event_root, arguments.run_id, arguments.allowed_parent))
            return 0
        if arguments.command == "watch":
            reader = lambda run_id, cursor: read_history(
                arguments.event_root, run_id, arguments.allowed_parent, cursor,
            )
            ansi_redraw = (
                arguments.format == "text"
                and bool(sys.stdout.isatty())
                and "NO_COLOR" not in os.environ
            )
            try:
                watch_run(
                    arguments.run_id, reader, time.sleep, sys.stdout, sys.stderr,
                    poll_interval=arguments.poll_interval, ansi_redraw=ansi_redraw,
                    output_format=arguments.format,
                )
            except KeyboardInterrupt:
                return 130
            return 0
        if arguments.command == "_serve":
            serve(
                arguments.socket, arguments.event_root, arguments.artifact_root, arguments.allowed_parent,
                arguments.token_fd, arguments.max_requests,
            )
            return 0
    except (ValueError, OSError, RuntimeError, StoreError, WatchError, IPCError, subprocess.TimeoutExpired) as exc:
        print(f"safety-monitor failed: {escape_text(exc)}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
