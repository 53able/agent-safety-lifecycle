"""Pure replay and projection logic."""
from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from typing import Iterable

from .events import PersistedEvent
from .state_machine import StateMachine, load_state_machine

TIMELINE_LIMIT = 100


@dataclass(frozen=True)
class TimelineEntry:
    sequence: int
    event_type: str
    summary: str
    source: str
    state: str


@dataclass(frozen=True)
class RunProjection:
    task_id: str | None = None
    run_id: str | None = None
    run_state: str | None = None
    stream_integrity: str = "OK"
    result_gate_decision: str = "NONE"
    handoff_status: str = "NONE"
    last_sequence: int = 0
    warnings: tuple[str, ...] = ()
    timeline: tuple[TimelineEntry, ...] = ()
    producer_event_ids: frozenset[str] = frozenset()

    @property
    def is_valid(self) -> bool:
        return self.stream_integrity == "OK"


def _warn(projection: RunProjection, integrity: str, warning: str) -> RunProjection:
    return replace(projection, stream_integrity=integrity, warnings=projection.warnings + (warning,))


class _ProducerIdAccumulator:
    """Mutable producer-ID state used only while replaying a history."""

    def __init__(self) -> None:
        self.ids: set[str] = set()

    def add(self, producer_event_id: str) -> None:
        self.ids.add(producer_event_id)

    def freeze(self) -> frozenset[str]:
        return frozenset(self.ids)


def _apply_event(
    projection: RunProjection,
    event: PersistedEvent,
    machine: StateMachine,
    producer_event_ids: AbstractSet[str],
    *,
    freeze_ids: bool,
) -> RunProjection:
    expected = projection.last_sequence + 1
    if event.sequence > expected:
        return _warn(projection, "INCOMPLETE", f"missing sequence {expected}")
    if event.sequence < expected:
        return _warn(projection, "INVALID", f"duplicate or reversed sequence {event.sequence}")
    producer = event.producer
    if producer.producer_event_id in producer_event_ids:
        return _warn(projection, "INVALID", "duplicate producer_event_id")
    if projection.last_sequence == 0:
        if producer.type != "RUN_CREATED" or event.sequence != 1:
            return _warn(projection, "INVALID", "RUN_CREATED must be sequence 1")
        entry = TimelineEntry(event.sequence, producer.type, producer.summary, event.source, "PLANNED")
        return replace(
            projection,
            task_id=producer.task_id,
            run_id=producer.run_id,
            run_state="PLANNED",
            last_sequence=1,
            timeline=(entry,),
            producer_event_ids=(
                frozenset({producer.producer_event_id})
                if freeze_ids else projection.producer_event_ids
            ),
        )
    if producer.task_id != projection.task_id or producer.run_id != projection.run_id:
        return _warn(projection, "INVALID", "event identity does not match the run")
    if producer.type == "RUN_CREATED":
        return _warn(projection, "INVALID", "RUN_CREATED may appear only once")
    if projection.run_state in machine.terminal:
        return _warn(projection, "INVALID", "events after a terminal state are unsupported")
    if producer.state_to == "COMPLETED":
        return _warn(projection, "INVALID", "result-gate v2 binding unavailable; COMPLETED is unsupported")
    if producer.state_from != projection.run_state:
        return _warn(projection, "INVALID", "transition source does not match current state")
    if not machine.allows(producer.state_from or "", producer.state_to or ""):
        return _warn(projection, "INVALID", "state transition is not allowed")
    entry = TimelineEntry(event.sequence, producer.type, producer.summary, event.source, producer.state_to or "")
    return replace(
        projection,
        run_state=producer.state_to,
        last_sequence=event.sequence,
        timeline=(projection.timeline + (entry,))[-TIMELINE_LIMIT:],
        producer_event_ids=(
            projection.producer_event_ids | {producer.producer_event_id}
            if freeze_ids else projection.producer_event_ids
        ),
    )


def apply_event(
    projection: RunProjection,
    event: PersistedEvent,
    machine: StateMachine | None = None,
) -> RunProjection:
    """Apply one event while preserving the projection's immutable public state."""
    resolved = machine or load_state_machine()
    return _apply_event(
        projection,
        event,
        resolved,
        projection.producer_event_ids,
        freeze_ids=True,
    )


def replay(events: Iterable[PersistedEvent], machine: StateMachine | None = None) -> RunProjection:
    """Replay a history with one mutable ID accumulator and one final freeze."""
    projection = RunProjection()
    resolved = machine or load_state_machine()
    producer_ids = _ProducerIdAccumulator()
    for event in events:
        proposed = _apply_event(
            projection,
            event,
            resolved,
            producer_ids.ids,
            freeze_ids=False,
        )
        if proposed.last_sequence != projection.last_sequence:
            producer_ids.add(event.producer.producer_event_id)
        projection = proposed
    return replace(projection, producer_event_ids=producer_ids.freeze())
