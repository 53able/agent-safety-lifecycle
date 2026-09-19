"""Strict contracts for the two event types in the replay prototype."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

MAX_REQUEST_BYTES = 16 * 1024
MAX_ID_LENGTH = 128
MAX_SUMMARY_LENGTH = 512
MAX_JSON_DEPTH = 8
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
KNOWN_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)
BIDI_CONTROLS = frozenset(chr(value) for value in (
    0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
))
BASE_FIELDS = frozenset({
    "schema_version", "producer_event_id", "task_id", "run_id", "occurred_at", "type", "summary",
})
SERVER_FIELDS = frozenset({"source", "sequence", "recorded_at", "event_id", "artifact_root"})


class EventError(ValueError):
    """A safe, displayable contract violation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def json_depth(value: Any, level: int = 1) -> int:
    if isinstance(value, dict):
        return max([level, *(json_depth(v, level + 1) for v in value.values())])
    if isinstance(value, list):
        return max([level, *(json_depth(v, level + 1) for v in value)])
    return level


def _safe_string(value: Any, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise EventError("INVALID_FIELD", f"{name} must be a non-empty string of at most {maximum} characters")
    for char in value:
        point = ord(char)
        if char in BIDI_CONTROLS or char in "\r\n" or point == 0x1B or point < 0x20 or 0x7F <= point <= 0x9F:
            raise EventError("UNSAFE_STRING", f"{name} contains a forbidden control character")
        if unicodedata.category(char) == "Cf":
            raise EventError("UNSAFE_STRING", f"{name} contains a forbidden format character")
    if any(pattern.search(value) for pattern in KNOWN_SECRET_PATTERNS):
        raise EventError("SECRET_PATTERN", f"{name} contains a known secret pattern")
    return value


def validate_id(value: Any, name: str) -> str:
    text = _safe_string(value, name, MAX_ID_LENGTH)
    if not ID_RE.fullmatch(text) or ".." in text:
        raise EventError("INVALID_ID", f"{name} has an invalid format")
    return text


def validate_timestamp(value: Any, name: str) -> str:
    text = _safe_string(value, name, 64)
    if not UTC_RE.fullmatch(text):
        raise EventError("INVALID_TIMESTAMP", f"{name} must be a UTC RFC 3339 timestamp")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EventError("INVALID_TIMESTAMP", f"{name} must be a UTC RFC 3339 timestamp") from exc
    return text


@dataclass(frozen=True)
class ProducerEvent:
    schema_version: str
    producer_event_id: str
    task_id: str
    run_id: str
    occurred_at: str
    type: str
    summary: str
    envelope_hash: str | None = None
    state_from: str | None = None
    state_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "producer_event_id": self.producer_event_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "occurred_at": self.occurred_at,
            "type": self.type,
            "summary": self.summary,
        }
        if self.type == "RUN_CREATED":
            result["envelope_hash"] = self.envelope_hash
        else:
            result["state"] = {"from": self.state_from, "to": self.state_to}
        return result


@dataclass(frozen=True)
class PersistedEvent:
    producer: ProducerEvent
    source: str
    sequence: int
    recorded_at: str
    event_id: str
    artifact_root: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = self.producer.to_dict()
        result.update({
            "source": self.source,
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "event_id": self.event_id,
        })
        if self.artifact_root is not None:
            result["artifact_root"] = self.artifact_root
        return result


def parse_producer(data: Mapping[str, Any]) -> ProducerEvent:
    if not isinstance(data, dict) or json_depth(data) > MAX_JSON_DEPTH:
        raise EventError("INVALID_JSON", "event must be an object with nesting depth at most eight")
    event_type = data.get("type")
    if event_type == "RUN_CREATED":
        expected = BASE_FIELDS | {"envelope_hash"}
    elif event_type == "STATE_TRANSITION":
        expected = BASE_FIELDS | {"state"}
    else:
        raise EventError("UNSUPPORTED_TYPE", "only RUN_CREATED and STATE_TRANSITION are supported")
    if set(data) & SERVER_FIELDS:
        raise EventError("SERVER_FIELD", "server-assigned fields are not accepted")
    unknown = set(data) - expected
    missing = expected - set(data)
    if unknown or missing:
        raise EventError("INVALID_FIELDS", "event fields do not match the selected event type")
    schema = _safe_string(data["schema_version"], "schema_version", 16)
    if schema != "1.0":
        raise EventError("SCHEMA_VERSION", "schema_version must be 1.0")
    common = dict(
        schema_version=schema,
        producer_event_id=validate_id(data["producer_event_id"], "producer_event_id"),
        task_id=validate_id(data["task_id"], "task_id"),
        run_id=validate_id(data["run_id"], "run_id"),
        occurred_at=validate_timestamp(data["occurred_at"], "occurred_at"),
        type=event_type,
        summary=_safe_string(data["summary"], "summary", MAX_SUMMARY_LENGTH),
    )
    if event_type == "RUN_CREATED":
        envelope_hash = _safe_string(data["envelope_hash"], "envelope_hash", 71)
        if not HASH_RE.fullmatch(envelope_hash):
            raise EventError("INVALID_HASH", "envelope_hash must be sha256 plus 64 lowercase hexadecimal characters")
        return ProducerEvent(**common, envelope_hash=envelope_hash)
    state = data["state"]
    if not isinstance(state, dict) or set(state) != {"from", "to"}:
        raise EventError("INVALID_STATE", "state must contain exactly from and to")
    return ProducerEvent(
        **common,
        state_from=validate_id(state["from"], "state.from"),
        state_to=validate_id(state["to"], "state.to"),
    )


def parse_persisted(data: Mapping[str, Any]) -> PersistedEvent:
    if not isinstance(data, dict):
        raise EventError("INVALID_JSON", "persisted event must be an object")
    producer_data = {key: value for key, value in data.items() if key not in SERVER_FIELDS}
    producer = parse_producer(producer_data)
    required = {"source", "sequence", "recorded_at", "event_id"}
    allowed_server = required | ({"artifact_root"} if producer.type == "RUN_CREATED" else set())
    present_server = set(data) & SERVER_FIELDS
    if present_server != allowed_server:
        raise EventError("INVALID_PERSISTED_FIELDS", "persisted server fields are invalid")
    source = validate_id(data["source"], "source")
    sequence = data["sequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise EventError("INVALID_SEQUENCE", "sequence must be a positive integer")
    artifact_root = None
    if producer.type == "RUN_CREATED":
        artifact_root = validate_id(data["artifact_root"], "artifact_root")
        if artifact_root != producer.run_id:
            raise EventError("INVALID_ARTIFACT_ROOT", "artifact root identifier must match run_id")
    return PersistedEvent(
        producer=producer,
        source=source,
        sequence=sequence,
        recorded_at=validate_timestamp(data["recorded_at"], "recorded_at"),
        event_id=validate_id(data["event_id"], "event_id"),
        artifact_root=artifact_root,
    )
