"""Stable, plain-text, defense-in-depth snapshot rendering."""
from __future__ import annotations

import unicodedata

from .events import BIDI_CONTROLS
from .projection import RunProjection


def escape_text(value: object) -> str:
    text = str(value)
    output: list[str] = []
    for char in text:
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


def render_snapshot(projection: RunProjection) -> str:
    lines = [
        f"Task: {escape_text(projection.task_id or 'NONE')}",
        f"Run: {escape_text(projection.run_id or 'NONE')}",
        f"State: {escape_text(projection.run_state or 'NONE')}",
        f"Stream: {escape_text(projection.stream_integrity)}",
        f"Result: {escape_text(projection.result_gate_decision)}",
        f"Handoff: {escape_text(projection.handoff_status)}",
        f"Last sequence: {projection.last_sequence}",
        "Timeline:",
    ]
    for entry in projection.timeline:
        lines.append(
            f"  {entry.sequence} {escape_text(entry.event_type)} [{escape_text(entry.source)}] "
            f"{escape_text(entry.state)}: {escape_text(entry.summary)}"
        )
    for warning in projection.warnings:
        lines.append(f"Warning: {escape_text(warning)}")
    return "\n".join(lines) + "\n"
