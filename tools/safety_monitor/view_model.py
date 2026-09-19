"""Immutable, sanitized presentation contract for safety monitor views."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import unicodedata

from .events import BIDI_CONTROLS
from .projection import RunProjection

SCHEMA = "monitor-view-model.v1"
FRAME_LIMIT = 512 * 1024
TIMELINE_LIMIT = 100


class ViewModelError(RuntimeError):
    """Raised when a view-model frame cannot be emitted safely."""


@dataclass(frozen=True)
class Availability:
    status: str
    reason: str


@dataclass(frozen=True)
class MonitorTimelineEntry:
    sequence: int
    event_type: str
    source: str
    state: str
    summary: str


@dataclass(frozen=True)
class MonitorViewModel:
    schema: str
    task_id: str
    run_id: str
    run_state: str
    stream_integrity: str
    result_gate_decision: str
    result_gate: Availability
    capabilities: Availability
    handoff_status: str
    last_sequence: int
    timeline: tuple[MonitorTimelineEntry, ...]
    warnings: tuple[str, ...]


def sanitize_text(value: object) -> str:
    """Make terminal controls visible, including controls JSON would otherwise restore."""
    output: list[str] = []
    for char in str(value):
        point = ord(char)
        if char == "\n":
            output.append("\\n")
        elif char == "\r":
            output.append("\\r")
        elif char in BIDI_CONTROLS or point == 0x1B or point < 0x20 or 0x7F <= point <= 0x9F or unicodedata.category(char) == "Cf":
            output.append(f"\\u{point:04x}")
        else:
            output.append(char)
    return "".join(output)


def from_projection(projection: RunProjection) -> MonitorViewModel:
    """Purely map a validated projection into the versioned display contract."""
    unavailable_result = Availability(
        "UNAVAILABLE", "result-gate events and v2 evidence are unavailable in the current schema",
    )
    unavailable_capabilities = Availability(
        "UNAVAILABLE", "capability events are unsupported in the current schema",
    )
    return MonitorViewModel(
        schema=SCHEMA,
        task_id=sanitize_text(projection.task_id or "NONE"),
        run_id=sanitize_text(projection.run_id or "NONE"),
        run_state=sanitize_text(projection.run_state or "NONE"),
        stream_integrity=sanitize_text(projection.stream_integrity),
        result_gate_decision=sanitize_text(projection.result_gate_decision),
        result_gate=unavailable_result,
        capabilities=unavailable_capabilities,
        handoff_status=sanitize_text(projection.handoff_status),
        last_sequence=projection.last_sequence,
        timeline=tuple(
            MonitorTimelineEntry(
                entry.sequence,
                sanitize_text(entry.event_type),
                sanitize_text(entry.source),
                sanitize_text(entry.state),
                sanitize_text(entry.summary),
            )
            for entry in projection.timeline[-TIMELINE_LIMIT:]
        ),
        warnings=tuple(sanitize_text(warning) for warning in projection.warnings),
    )


def serialize_jsonl(model: MonitorViewModel) -> str:
    """Serialize one deterministic bounded protocol frame, or fail closed."""
    line = json.dumps(asdict(model), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    if len(line.encode("utf-8")) > FRAME_LIMIT:
        raise ViewModelError("monitor view-model frame exceeds 512 KiB")
    return line
