#!/usr/bin/env python3
import json
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[1] not in {"signals", "wait"}:
        raise SystemExit("usage: pty_harness.py signals|wait PID_RECORD COMMAND...")
    mode = sys.argv[1]
    pid_record = sys.argv[2]
    command = sys.argv[3:]
    master, slave = pty.openpty()
    slave_probe = os.dup(slave)
    terminal_before = termios.tcgetattr(slave_probe)
    process = subprocess.Popen(
        command,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
        env=os.environ.copy(),
        close_fds=True,
    )
    os.close(slave)
    transcript = bytearray()
    child_pid = None
    deadline = time.monotonic() + 12
    timed_out = False
    try:
        while time.monotonic() < deadline and child_pid is None:
            try:
                with open(pid_record, encoding="utf-8") as handle:
                    child_pid = int(handle.read().strip())
            except (FileNotFoundError, ValueError):
                pass
            _drain(master, transcript, 0.02)
        if child_pid is None:
            raise RuntimeError("child pid was not recorded")
        if mode == "signals":
            time.sleep(0.2)
            os.kill(process.pid, signal.SIGINT)
            time.sleep(0.1)
            os.kill(process.pid, signal.SIGINT)
        while process.poll() is None and time.monotonic() < deadline:
            _drain(master, transcript, 0.05)
        if process.poll() is None:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
        status = process.wait(timeout=2)
        _drain(master, transcript, 0.05)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        if child_pid is not None and _alive(child_pid):
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    terminal_after = termios.tcgetattr(slave_probe)
    terminal_restored = terminal_after == terminal_before
    os.close(slave_probe)
    try:
        os.close(master)
    except OSError:
        pass
    child_gone = child_pid is not None and not _alive(child_pid)
    print(json.dumps({
        "status": status,
        "timed_out": timed_out,
        "child_pid": child_pid,
        "child_gone": child_gone,
        "terminal_restored": terminal_restored,
        "canonical_restored": bool(terminal_after[3] & termios.ICANON) == bool(terminal_before[3] & termios.ICANON),
        "echo_restored": bool(terminal_after[3] & termios.ECHO) == bool(terminal_before[3] & termios.ECHO),
        "transcript": transcript.decode("utf-8", "replace"),
    }))
    return 0


def _drain(master: int, output: bytearray, timeout: float) -> None:
    readable, _, _ = select.select([master], [], [], timeout)
    if not readable:
        return
    try:
        chunk = os.read(master, 65536)
    except OSError:
        return
    output.extend(chunk)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
