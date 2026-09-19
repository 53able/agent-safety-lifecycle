"""Authenticated, owner-only AF_UNIX ingress for the prototype recorder."""
from __future__ import annotations

import hmac
import json
import os
import socket
import stat
from pathlib import Path
from typing import Any

from .events import EventError, MAX_REQUEST_BYTES
from .recording import Recorder, RecordingError, utc_now
from .store import EventStore

MANIFEST_PATH = Path(__file__).with_name("monitor-manifest.json")
MAX_ACK_BYTES = 2048


class IPCError(RuntimeError):
    pass


def read_token_fd(descriptor: int) -> str:
    with os.fdopen(descriptor, "rb") as stream:
        token = stream.read(256)
    if not token or len(token) > 128:
        raise IPCError("invalid inherited token")
    try:
        return token.decode("ascii")
    except UnicodeDecodeError as exc:
        raise IPCError("invalid inherited token") from exc


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "1.0" or not isinstance(data.get("adapters"), dict):
        raise IPCError("invalid monitor manifest")
    return data


def _ack(ok: bool, code: str, **extra: Any) -> bytes:
    data = {"ok": ok, "code": code, **extra}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_ACK_BYTES:
        return b'{"code":"INTERNAL_ERROR","ok":false}\n'
    return encoded


def _receive_request(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = connection.recv(min(4096, MAX_REQUEST_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_REQUEST_BYTES:
            raise IPCError("REQUEST_TOO_LARGE")
        if b"\n" in chunk:
            break
    raw = b"".join(chunks)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise IPCError("INVALID_FRAME")
    return raw[:-1]


def serve(
    socket_path: Path,
    event_root: Path,
    artifact_root: Path,
    allowed_parent: Path,
    token_fd: int,
    max_requests: int = 2,
) -> None:
    if not hasattr(socket, "AF_UNIX"):
        raise IPCError("AF_UNIX is unavailable")
    token = read_token_fd(token_fd)
    manifest = load_manifest()
    store = EventStore(event_root, artifact_root, allowed_parent)
    recorder = Recorder(store)
    parent = socket_path.parent
    if parent.is_symlink():
        raise IPCError("socket directory must not be a symlink")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent.chmod(0o700)
    if socket_path.exists() or socket_path.is_symlink():
        mode = socket_path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise IPCError("socket path exists and is not a socket")
        socket_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        socket_path.chmod(0o600)
        server.listen(4)
        for _ in range(max_requests):
            connection, _ = server.accept()
            with connection:
                raw = b""
                adapter_id = "unknown"
                try:
                    raw = _receive_request(connection)
                    request = json.loads(raw)
                    if not isinstance(request, dict) or set(request) != {"adapter_id", "token", "event"}:
                        raise IPCError("INVALID_REQUEST")
                    adapter_id = request["adapter_id"]
                    supplied = request["token"]
                    if not isinstance(adapter_id, str) or not isinstance(supplied, str):
                        raise IPCError("INVALID_AUTH")
                    adapter = manifest["adapters"].get(adapter_id)
                    if not isinstance(adapter, dict) or not hmac.compare_digest(token, supplied):
                        raise IPCError("AUTH_FAILED")
                    event = request["event"]
                    if not isinstance(event, dict) or event.get("type") not in adapter["event_types"]:
                        raise IPCError("EVENT_NOT_ALLOWED")
                    persisted = recorder.record(event, adapter["source"])
                    connection.sendall(_ack(True, "RECORDED", sequence=persisted.sequence, event_id=persisted.event_id))
                except (json.JSONDecodeError, KeyError, TypeError, IPCError, EventError, RecordingError) as exc:
                    code = getattr(exc, "code", str(exc))
                    safe_code = code if isinstance(code, str) and code.replace("_", "").isalnum() else "INVALID_REQUEST"
                    store.audit_invalid(adapter_id if isinstance(adapter_id, str) else "unknown", safe_code, raw, utc_now())
                    connection.sendall(_ack(False, safe_code))
    finally:
        server.close()
        if socket_path.exists():
            socket_path.unlink()


def send(socket_path: Path, token: str, event: dict[str, Any], adapter_id: str = "transition-validator") -> dict[str, Any]:
    request = {"adapter_id": adapter_id, "token": token, "event": event}
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_REQUEST_BYTES:
        raise IPCError("REQUEST_TOO_LARGE")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(str(socket_path))
        client.sendall(encoded)
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(MAX_ACK_BYTES + 1 - len(response))
            if not chunk:
                break
            response += chunk
            if len(response) > MAX_ACK_BYTES:
                raise IPCError("ACK_TOO_LARGE")
        result = json.loads(response)
    finally:
        client.close()
    if not isinstance(result, dict):
        raise IPCError("INVALID_ACK")
    return result
