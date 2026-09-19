"""Host-only launcher for a read-only viewer of an existing run."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from .events import EventError, validate_id
from .projection import replay
from .store import StoreError, _open_configured_root, _validate_configuration, read_events

CONTROL_DIRECTORY = ".safety-monitor-viewer-control"
CONTROL_SCHEMA = "safety-monitor-viewer-control.v1"
RESULT_SCHEMA = "safety-monitor-open-viewer-result.v1"
CONTROL_LIMIT = 16 * 1024
TMUX_TIMEOUT = 3
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TRUSTED_BOOTSTRAP = REPOSITORY_ROOT / "tools/safety_monitor_bootstrap.py"
OPENTUI_ENTRY = REPOSITORY_ROOT / "tools/opentui_monitor/src/main.ts"
OPENTUI_PACKAGE = REPOSITORY_ROOT / "tools/opentui_monitor/package.json"
OPENTUI_LOCK = REPOSITORY_ROOT / "tools/opentui_monitor/bun.lock"
OPENTUI_DEPENDENCY = REPOSITORY_ROOT / "tools/opentui_monitor/node_modules/@opentui/core/package.json"
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_CONTROL_NAME = re.compile(r"^[0-9a-f]{32}\.json$")
_TMUX_IDENTITY = re.compile(r"^([^,\r\n]+),([1-9][0-9]*),(0|[1-9][0-9]*)$")
_TMUX_PANE = re.compile(r"^%[0-9]+$")
_ENVIRONMENT_NAMES = {"PATH", "HOME", "TERM", "COLORTERM", "LANG", "TMPDIR", "NO_COLOR"}


class ViewerError(RuntimeError):
    """A safe launcher or control-file contract failure."""


def _roots_are_disjoint(control: Path, *roots: Path) -> bool:
    return all(control != root and control not in root.parents and root not in control.parents for root in roots)


def _validated_run(
    allowed_parent: Path, event_root: Path, artifact_root: Path, run_id: str,
) -> tuple[Path, Path, Path, str]:
    validate_id(run_id, "run_id")
    event, artifact, parent = _validate_configuration(event_root, artifact_root, allowed_parent)
    assert artifact is not None
    descriptors: list[int] = []
    try:
        descriptors.append(_open_configured_root(event, parent, create=False))
        descriptors.append(_open_configured_root(artifact, parent, create=False))
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
    control = parent / CONTROL_DIRECTORY
    if not _roots_are_disjoint(control, event, artifact):
        raise ViewerError("event and artifact roots must be disjoint from the reserved control directory")
    events = read_events(event, run_id, parent)
    if not events:
        raise StoreError("RUN_NOT_FOUND", "no events found for run")
    projection = replay(events)
    if not projection.is_valid or projection.run_id != run_id or projection.run_state is None:
        warning = "; ".join(projection.warnings) or "RUN_CREATED projection is unavailable"
        raise StoreError("INTEGRITY_FAILURE", warning)
    return parent, event, artifact, run_id


def _viewer_argv(allowed_parent: Path, event_root: Path, run_id: str) -> tuple[list[str], list[str]]:
    common = ["--allowed-parent", str(allowed_parent), "--event-root", str(event_root), "--run-id", run_id]
    bun = ["bun", "run", str(OPENTUI_ENTRY), "--python", sys.executable, *common]
    python = [sys.executable, "-I", str(TRUSTED_BOOTSTRAP), "watch", *common]
    return bun, python


def _manual_commands(allowed_parent: Path, event_root: Path, run_id: str) -> dict[str, str]:
    bun, python = _viewer_argv(allowed_parent, event_root, run_id)
    return {"bun": shlex.join(bun), "python": shlex.join(python)}


def _result(
    mode: str,
    run_id: str,
    parent: Path,
    event: Path,
    artifact: Path,
    status: str,
    reason: str,
    *,
    viewer_started: bool = False,
    pane_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "reason": reason,
        "viewer_started": viewer_started,
        "pane_id": pane_id,
        "artifact_root": str(artifact),
        "manual_commands": _manual_commands(parent, event, run_id),
    }


def _ensure_control_directory(parent: Path, event_root: Path, artifact_root: Path) -> tuple[int, Path]:
    control = parent / CONTROL_DIRECTORY
    if not _roots_are_disjoint(control, event_root, artifact_root):
        raise ViewerError("control directory must be disjoint from event and artifact roots")
    parent_fd = os.open(parent, _DIRECTORY_FLAGS)
    try:
        try:
            os.mkdir(CONTROL_DIRECTORY, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        directory_fd = os.open(CONTROL_DIRECTORY, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ViewerError("control directory is unsafe") from exc
    finally:
        os.close(parent_fd)
    details = os.fstat(directory_fd)
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) != 0o700:
        os.close(directory_fd)
        raise ViewerError("control directory must be owner-only and owned by the current user")
    return directory_fd, control


def _write_control(parent: Path, event_root: Path, artifact_root: Path, run_id: str) -> Path:
    directory_fd, control_directory = _ensure_control_directory(parent, event_root, artifact_root)
    name = f"{os.urandom(16).hex()}.json"
    payload = json.dumps(
        {
            "schema_version": CONTROL_SCHEMA,
            "allowed_parent": str(parent),
            "event_root": str(event_root),
            "artifact_root": str(artifact_root),
            "run_id": run_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    descriptor = -1
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=directory_fd)
        if os.write(descriptor, payload) != len(payload):
            raise ViewerError("control manifest write was incomplete")
        os.fsync(descriptor)
        os.fsync(directory_fd)
        return control_directory / name
    except Exception:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)


def _remove_control(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _tmux(executable: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *arguments], capture_output=True, text=True, check=False, timeout=TMUX_TIMEOUT,
    )


def _confirmed_tmux(tmux: str, pane: str, identity: str) -> bool:
    match = _TMUX_IDENTITY.fullmatch(identity)
    if match is None or _TMUX_PANE.fullmatch(pane) is None:
        return False
    expected_session = f"${match.group(3)}"
    result = _tmux(tmux, ["display-message", "-p", "-t", pane, "#{pane_id}|#{session_id}"])
    if result.returncode != 0:
        return False
    fields = result.stdout.rstrip("\n").split("|")
    return len(fields) == 2 and fields[0] == pane and fields[1] == expected_session


def _run_key(parent: Path, event_root: Path, artifact_root: Path, run_id: str) -> str:
    identity = "\0".join((str(parent), str(event_root), str(artifact_root), run_id)).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def open_viewer(
    allowed_parent: Path, event_root: Path, artifact_root: Path, run_id: str, mode: str,
) -> dict[str, Any]:
    """Validate an existing run, then optionally launch its viewer in a new tmux pane."""
    parent, event, artifact, run_id = _validated_run(allowed_parent, event_root, artifact_root, run_id)
    if mode == "off":
        return _result(mode, run_id, parent, event, artifact, "off", "viewer launch is disabled")
    if mode == "manual":
        return _result(mode, run_id, parent, event, artifact, "manual", "manual launch requested")

    tmux = shutil.which("tmux")
    pane = os.environ.get("TMUX_PANE", "")
    identity = os.environ.get("TMUX", "")
    if not tmux or not identity or not pane:
        return _result(mode, run_id, parent, event, artifact, "manual", "confirmed current tmux pane is unavailable")
    control: Path | None = None
    new_pane: str | None = None
    try:
        if not _confirmed_tmux(tmux, pane, identity):
            return _result(mode, run_id, parent, event, artifact, "manual", "current tmux pane could not be confirmed")
        key = _run_key(parent, event, artifact, run_id)
        panes = _tmux(tmux, ["list-panes", "-a", "-F", "#{pane_id}|#{@safety_monitor_run}"])
        if panes.returncode != 0:
            return _result(mode, run_id, parent, event, artifact, "manual", "tmux panes could not be queried")
        for line in panes.stdout.splitlines():
            fields = line.split("|", 1)
            if len(fields) == 2 and fields[1] == key:
                return _result(mode, run_id, parent, event, artifact, "duplicate", "viewer pane already exists", viewer_started=True, pane_id=fields[0])

        control = _write_control(parent, event, artifact, run_id)
        entry = [sys.executable, "-I", str(TRUSTED_BOOTSTRAP), "_viewer-entry", "--control", str(control)]
        split = _tmux(tmux, [
            "split-window", "-d", "-P", "-F", "#{pane_id}", "-c", str(REPOSITORY_ROOT),
            "-t", pane, shlex.join(entry),
        ])
        if split.returncode != 0:
            _remove_control(control)
            return _result(mode, run_id, parent, event, artifact, "manual", "tmux could not create a detached pane")
        new_pane = split.stdout.strip()
        if not new_pane or new_pane == pane:
            _remove_control(control)
            if new_pane:
                _tmux(tmux, ["kill-pane", "-t", new_pane])
            return _result(mode, run_id, parent, event, artifact, "manual", "tmux did not return a distinct viewer pane")
        tagged = _tmux(tmux, ["set-option", "-p", "-t", new_pane, "@safety_monitor_run", key])
        if tagged.returncode != 0:
            _tmux(tmux, ["kill-pane", "-t", new_pane])
            _remove_control(control)
            return _result(mode, run_id, parent, event, artifact, "manual", "viewer pane ownership tag could not be set")
        return _result(mode, run_id, parent, event, artifact, "launched", "detached read-only viewer pane created", viewer_started=True, pane_id=new_pane)
    except (OSError, ViewerError, subprocess.TimeoutExpired):
        if new_pane and new_pane != pane:
            try:
                _tmux(tmux, ["kill-pane", "-t", new_pane])
            except (OSError, subprocess.TimeoutExpired):
                pass
        if control is not None:
            _remove_control(control)
        return _result(mode, run_id, parent, event, artifact, "manual", "tmux launch failed or timed out")


def _read_control(path: Path) -> tuple[Path, Path, Path, str]:
    if not path.is_absolute() or path.parent.name != CONTROL_DIRECTORY or not _CONTROL_NAME.fullmatch(path.name):
        raise ViewerError("invalid control manifest path")
    try:
        directory_fd = os.open(path.parent, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise ViewerError("control directory is unsafe") from exc
    descriptor = -1
    opened: os.stat_result | None = None
    try:
        directory = os.fstat(directory_fd)
        if directory.st_uid != os.geteuid() or stat.S_IMODE(directory.st_mode) != 0o700:
            raise ViewerError("control directory permissions are unsafe")
        try:
            descriptor = os.open(path.name, _FILE_FLAGS, dir_fd=directory_fd)
        except OSError as exc:
            raise ViewerError("control manifest path is unsafe") from exc
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) & 0o077:
            raise ViewerError("control manifest permissions are unsafe")
        payload = os.read(descriptor, CONTROL_LIMIT + 1)
        if len(payload) > CONTROL_LIMIT or os.read(descriptor, 1):
            raise ViewerError("control manifest is too large")
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ViewerError("control manifest is not valid JSON") from exc
        expected = {"schema_version", "allowed_parent", "event_root", "artifact_root", "run_id"}
        if not isinstance(data, dict) or set(data) != expected or data.get("schema_version") != CONTROL_SCHEMA:
            raise ViewerError("control manifest schema is invalid")
        if not all(isinstance(data.get(field), str) for field in expected):
            raise ViewerError("control manifest fields are invalid")
        parent_text = data["allowed_parent"]
        event_text = data["event_root"]
        artifact_text = data["artifact_root"]
        run_id = data["run_id"]
        if not all(Path(value).is_absolute() for value in (parent_text, event_text, artifact_text)):
            raise ViewerError("control manifest paths must be absolute")
        parent, event, artifact, run_id = _validated_run(
            Path(parent_text), Path(event_text), Path(artifact_text), run_id,
        )
        if (
            str(parent) != parent_text or str(event) != event_text or str(artifact) != artifact_text
            or path.parent != parent / CONTROL_DIRECTORY
        ):
            raise ViewerError("control manifest paths must be canonical and bound to its parent")
        return parent, event, artifact, run_id
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if opened is not None:
            try:
                current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
                    os.unlink(path.name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


def _bun_available(environment: dict[str, str] | None = None) -> str | None:
    bun = shutil.which("bun")
    if not bun or not OPENTUI_ENTRY.is_file() or not OPENTUI_PACKAGE.is_file() or not OPENTUI_LOCK.is_file() or not OPENTUI_DEPENDENCY.is_file():
        return None
    try:
        result = subprocess.run(
            [bun, "--version"], capture_output=True, text=True, check=False,
            timeout=TMUX_TIMEOUT, env=environment,
        )
        version = tuple(int(part) for part in result.stdout.strip().split(".")[:3])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or len(version) != 3 or version < (1, 3, 0):
        return None
    try:
        dependency = json.loads(OPENTUI_DEPENDENCY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return bun if isinstance(dependency, dict) and dependency.get("version") == "0.5.11" else None


def _viewer_environment() -> dict[str, str]:
    return {
        name: value for name, value in os.environ.items()
        if name in _ENVIRONMENT_NAMES or name.startswith("LC_")
    }


def viewer_entry(control: Path) -> int:
    """Consume one strict control manifest and replace this process with a viewer."""
    parent, event, _artifact, run_id = _read_control(control)
    environment = _viewer_environment()
    bun = _bun_available(environment)
    bun_argv, python_argv = _viewer_argv(parent, event, run_id)
    os.chdir(REPOSITORY_ROOT)
    if bun:
        bun_argv[0] = bun
        os.execve(bun, bun_argv, environment)
    os.execve(sys.executable, python_argv, environment)
    return 1  # pragma: no cover - execve does not return
