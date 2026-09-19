"""Validation, server enrichment, and durable recording service."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from .events import EventError, PersistedEvent, parse_producer, validate_id
from .projection import apply_event, replay
from .state_machine import load_state_machine
from .store import EventStore, StoreError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class RecordingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Recorder:
    """The sole append owner for one event root in this prototype."""

    def __init__(self, store: EventStore):
        self.store = store
        self.machine = load_state_machine()
        self._lock = threading.Lock()

    def record(self, data: Mapping[str, Any], source: str) -> PersistedEvent:
        validate_id(source, "source")
        producer = parse_producer(data)
        with self._lock:
            try:
                existing = self.store.read(producer.run_id)
            except StoreError as exc:
                raise RecordingError(exc.code, str(exc)) from exc
            current = replay(existing, self.machine)
            if existing and not current.is_valid:
                raise RecordingError("INTEGRITY_FAILURE", "existing event log has invalid ordering or projection")
            if producer.producer_event_id in current.producer_event_ids:
                raise RecordingError("DUPLICATE_PRODUCER_ID", "duplicate producer_event_id is unsupported")
            sequence = len(existing) + 1
            artifact_root = None
            allocated_artifact = False
            if producer.type == "RUN_CREATED":
                if existing:
                    raise RecordingError("DUPLICATE_CREATION", "RUN_CREATED may appear only once")
                try:
                    artifact_root = self.store.allocate_artifact_root(producer.run_id)
                    allocated_artifact = True
                except StoreError as exc:
                    raise RecordingError(exc.code, str(exc)) from exc
            event = PersistedEvent(
                producer=producer,
                source=source,
                sequence=sequence,
                recorded_at=utc_now(),
                event_id=str(uuid.uuid4()),
                artifact_root=artifact_root,
            )
            try:
                proposed = apply_event(current, event, self.machine)
                if not proposed.is_valid or proposed.last_sequence != sequence:
                    raise RecordingError("INVALID_EVENT", proposed.warnings[-1] if proposed.warnings else "event rejected")
                self.store.append(event)
            except (StoreError, RecordingError) as exc:
                if allocated_artifact:
                    try:
                        self.store.rollback_artifact_root(producer.run_id)
                    except StoreError as rollback_exc:
                        raise RecordingError(rollback_exc.code, str(rollback_exc)) from exc
                if isinstance(exc, StoreError):
                    raise RecordingError(exc.code, str(exc)) from exc
                raise
            return event
