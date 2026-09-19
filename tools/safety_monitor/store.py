"""Single-process, single-writer append-only NDJSON storage."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path

from .events import EventError, PersistedEvent, parse_persisted, validate_id, validate_timestamp

MAX_REPLAY_LINE_BYTES = 64 * 1024
MAX_REPLAY_BYTES = 8 * 1024 * 1024
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


class StoreError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HistoryBatch:
    """One bounded, coherent full-history read for a requested cursor."""

    history: tuple[PersistedEvent, ...]
    after_sequence: int

    @property
    def suffix(self) -> tuple[PersistedEvent, ...]:
        return self.history[self.after_sequence:]


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _validate_configuration(event_root: Path | str, artifact_root: Path | str | None, allowed_parent: Path | str) -> tuple[Path, Path | None, Path]:
    try:
        parent = Path(allowed_parent).resolve(strict=True)
    except OSError as exc:
        raise StoreError("UNSAFE_ROOT", "allowed parent must be an existing directory") from exc
    home = Path.home().resolve()
    if not parent.is_dir() or parent in {Path(parent.anchor), home}:
        raise StoreError("UNSAFE_ROOT", "allowed parent must not be the filesystem root or home directory")
    raw_event = _absolute(event_root)
    raw_artifact = _absolute(artifact_root) if artifact_root is not None else None
    if raw_event.is_symlink() or (raw_artifact is not None and raw_artifact.is_symlink()):
        raise StoreError("UNSAFE_ROOT", "configured roots must not be symlinks")
    event = raw_event.resolve(strict=False)
    artifact = raw_artifact.resolve(strict=False) if raw_artifact is not None else None
    roots = (event,) if artifact is None else (event, artifact)
    for root in roots:
        if root in {Path(root.anchor), home} or parent not in root.parents:
            raise StoreError("UNSAFE_ROOT", "configured roots must be beneath the allowed parent")
    if artifact is not None and (event == artifact or event in artifact.parents or artifact in event.parents):
        raise StoreError("UNSAFE_ROOT", "event and artifact roots must be distinct and non-overlapping")
    return event, artifact, parent


def _open_configured_root(path: Path, parent: Path, create: bool) -> int:
    relative = path.relative_to(parent)
    descriptor = os.open(parent, _DIRECTORY_FLAGS)
    try:
        for index, component in enumerate(relative.parts):
            final = index == len(relative.parts) - 1
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
                created = False
            except FileNotFoundError:
                if not create:
                    raise StoreError("RUN_NOT_FOUND", "configured event root does not exist")
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except OSError as exc:
                    raise StoreError("UNSAFE_ROOT", "configured root could not be created safely") from exc
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
                created = True
            except OSError as exc:
                raise StoreError("UNSAFE_ROOT", "configured root path contains a symlink or non-directory") from exc
            os.close(descriptor)
            descriptor = child
            if final:
                details = os.fstat(descriptor)
                if details.st_uid != os.geteuid():
                    raise StoreError("UNSAFE_ROOT", "configured root must be owned by the current user")
                if not created and stat.S_IMODE(details.st_mode) & 0o077:
                    raise StoreError("UNSAFE_ROOT", "pre-existing configured root must already be owner-only")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_child_directory(parent_fd: int, name: str, create: bool = False) -> tuple[int | None, bool]:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd), False
    except FileNotFoundError:
        if not create:
            return None, False
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd), True
        except OSError as exc:
            raise StoreError("UNSAFE_RUN_PATH", "directory could not be created safely") from exc
    except OSError as exc:
        raise StoreError("UNSAFE_RUN_PATH", "directory path is a symlink or non-directory") from exc


def _validate_cursor(after_sequence: int) -> int:
    if not isinstance(after_sequence, int) or isinstance(after_sequence, bool) or after_sequence < 0:
        raise StoreError("INVALID_CURSOR", "after_sequence must be a non-negative integer")
    return after_sequence


def _read_history_fd(root_fd: int, run_id: str, after_sequence: int = 0) -> HistoryBatch:
    after_sequence = _validate_cursor(after_sequence)
    run_fd, _ = _open_child_directory(root_fd, run_id)
    if run_fd is None:
        if after_sequence:
            raise StoreError("CURSOR_AHEAD", "after_sequence is beyond the validated log end")
        return HistoryBatch((), after_sequence)
    try:
        try:
            descriptor = os.open("events.ndjson", os.O_RDONLY | _FILE_NOFOLLOW, dir_fd=run_fd)
        except FileNotFoundError:
            if after_sequence:
                raise StoreError("CURSOR_AHEAD", "after_sequence is beyond the validated log end")
            return HistoryBatch((), after_sequence)
        except OSError as exc:
            raise StoreError("CORRUPT_LOG", "event log path is unsafe") from exc
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise StoreError("CORRUPT_LOG", "event log is not a regular file")
            if details.st_size > MAX_REPLAY_BYTES:
                raise StoreError("LOG_TOO_LARGE", "event log exceeds the replay byte limit")
            events: list[PersistedEvent] = []
            total = 0
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                while True:
                    line = stream.readline(MAX_REPLAY_LINE_BYTES + 1)
                    if not line:
                        break
                    total += len(line)
                    if total > MAX_REPLAY_BYTES:
                        raise StoreError("LOG_TOO_LARGE", "event log exceeds the replay byte limit")
                    if len(line) > MAX_REPLAY_LINE_BYTES:
                        raise StoreError("LINE_TOO_LARGE", "event log line exceeds the replay line limit")
                    if not line.endswith(b"\n"):
                        raise StoreError("INCOMPLETE_TAIL", "event log has an incomplete tail")
                    if line == b"\n":
                        raise StoreError("CORRUPT_LOG", "event log contains an empty line")
                    try:
                        data = json.loads(line)
                        event = parse_persisted(data)
                    except (json.JSONDecodeError, UnicodeDecodeError, EventError) as exc:
                        raise StoreError("CORRUPT_LOG", "event log contains an invalid event") from exc
                    if event.producer.run_id != run_id:
                        raise StoreError("CORRUPT_LOG", "event log contains a different run_id")
                    expected_sequence = len(events) + 1
                    if event.sequence != expected_sequence:
                        raise StoreError("CORRUPT_LOG", "event log sequence is not contiguous from one")
                    events.append(event)
            if after_sequence > len(events):
                raise StoreError("CURSOR_AHEAD", "after_sequence is beyond the validated log end")
            return HistoryBatch(tuple(events), after_sequence)
        finally:
            os.close(descriptor)
    finally:
        os.close(run_fd)


def read_history(
    event_root: Path | str,
    run_id: str,
    allowed_parent: Path | str,
    after_sequence: int = 0,
) -> HistoryBatch:
    """Return one bounded full-history read tied to the requested sequence cursor."""
    validate_id(run_id, "run_id")
    _validate_cursor(after_sequence)
    event, _, parent = _validate_configuration(event_root, None, allowed_parent)
    root_fd = _open_configured_root(event, parent, create=False)
    try:
        return _read_history_fd(root_fd, run_id, after_sequence)
    finally:
        os.close(root_fd)


def read_events(
    event_root: Path | str,
    run_id: str,
    allowed_parent: Path | str,
    after_sequence: int = 0,
) -> list[PersistedEvent]:
    """Validate a complete run log and return events after the sequence cursor."""
    return list(read_history(event_root, run_id, allowed_parent, after_sequence).suffix)


class EventStore:
    """A single-writer store. Multiple EventStore writers are unsupported."""

    def __init__(self, event_root: Path | str, artifact_root: Path | str, allowed_parent: Path | str):
        event, artifact, parent = _validate_configuration(event_root, artifact_root, allowed_parent)
        assert artifact is not None
        self.event_root, self.artifact_root, self.allowed_parent = event, artifact, parent
        self._lock = threading.Lock()
        self._event_fd = _open_configured_root(event, parent, create=True)
        try:
            self._artifact_fd = _open_configured_root(artifact, parent, create=True)
        except Exception:
            os.close(self._event_fd)
            raise

    def _run_directory(self, run_id: str, create: bool = False) -> tuple[int | None, bool]:
        validate_id(run_id, "run_id")
        return _open_child_directory(self._event_fd, run_id, create)

    def event_path(self, run_id: str) -> Path:
        validate_id(run_id, "run_id")
        return self.event_root / run_id / "events.ndjson"

    def allocate_artifact_root(self, run_id: str) -> str:
        validate_id(run_id, "run_id")
        try:
            os.mkdir(run_id, 0o700, dir_fd=self._artifact_fd)
        except FileExistsError as exc:
            raise StoreError("ARTIFACT_EXISTS", "artifact directory already exists") from exc
        except OSError as exc:
            raise StoreError("UNSAFE_ARTIFACT_PATH", "artifact directory could not be allocated safely") from exc
        return run_id

    def rollback_artifact_root(self, run_id: str) -> None:
        """Remove only the empty directory allocated for an uncommitted RUN_CREATED."""
        validate_id(run_id, "run_id")
        try:
            os.rmdir(run_id, dir_fd=self._artifact_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StoreError("ROLLBACK_FAILED", "new artifact directory could not be rolled back") from exc

    def read(self, run_id: str, after_sequence: int = 0) -> list[PersistedEvent]:
        validate_id(run_id, "run_id")
        return list(_read_history_fd(self._event_fd, run_id, after_sequence).suffix)

    @staticmethod
    def _open_append_file(directory_fd: int, name: str) -> tuple[int, bool]:
        flags = os.O_WRONLY | os.O_APPEND | _FILE_NOFOLLOW
        try:
            descriptor = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
            return descriptor, True
        except FileExistsError:
            try:
                descriptor = os.open(name, flags, dir_fd=directory_fd)
            except OSError as exc:
                raise StoreError("CORRUPT_LOG", "append target is unsafe") from exc
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                os.close(descriptor)
                raise StoreError("CORRUPT_LOG", "append target is not a regular file")
            return descriptor, False
        except OSError as exc:
            raise StoreError("CORRUPT_LOG", "append target is unsafe") from exc

    @staticmethod
    def _write_and_sync(descriptor: int, line: bytes, start: int, error_code: str, message: str) -> None:
        try:
            written = os.write(descriptor, line)
            if written != len(line):
                raise OSError(errno.EIO, "short append")
            os.fsync(descriptor)
        except OSError as exc:
            try:
                os.ftruncate(descriptor, start)
                os.fsync(descriptor)
            except OSError as rollback_exc:
                raise StoreError("ROLLBACK_FAILED", "failed append could not be durably rolled back") from rollback_exc
            raise StoreError(error_code, message) from exc

    @staticmethod
    def _audit_identifier(value: str, name: str) -> str:
        try:
            return validate_id(value, name)
        except EventError:
            digest = hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()
            return f"sha256-{digest}"

    def append(self, event: PersistedEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._lock:
            run_fd, _ = self._run_directory(event.producer.run_id, create=True)
            assert run_fd is not None
            descriptor = -1
            try:
                descriptor, _ = self._open_append_file(run_fd, "events.ndjson")
                start = os.fstat(descriptor).st_size
                if start + len(line) > MAX_REPLAY_BYTES:
                    raise StoreError("LOG_TOO_LARGE", "event would exceed the replay byte limit")
                self._write_and_sync(
                    descriptor, line, start, "APPEND_FAILED", "event could not be durably appended",
                )
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                os.close(run_fd)

    def audit_invalid(self, adapter_id: str, error_code: str, payload: bytes, timestamp: str) -> None:
        record = {
            "recorded_at": validate_timestamp(timestamp, "recorded_at"),
            "adapter_id": self._audit_identifier(adapter_id, "adapter_id"),
            "error_code": self._audit_identifier(error_code, "error_code"),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        with self._lock:
            audit_fd, _ = _open_child_directory(self._event_fd, "_audit", create=True)
            assert audit_fd is not None
            descriptor = -1
            try:
                descriptor, _ = self._open_append_file(audit_fd, "invalid-events.ndjson")
                start = os.fstat(descriptor).st_size
                self._write_and_sync(
                    descriptor, line, start, "AUDIT_FAILED", "invalid-event audit could not be written",
                )
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                os.close(audit_fd)
