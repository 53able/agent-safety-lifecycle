"""Stable, plain-text, defense-in-depth snapshot rendering."""
from __future__ import annotations

from .projection import RunProjection
from .view_model import MonitorViewModel, from_projection, sanitize_text

ANSI_REDRAW_PREFIX = "\x1b[2J\x1b[H"

# Compatibility name used by diagnostics and callers.
escape_text = sanitize_text


def render_view_model(model: MonitorViewModel) -> str:
    lines = [
        f"Task: {model.task_id}",
        f"Run: {model.run_id}",
        f"State: {model.run_state}",
        f"Stream: {model.stream_integrity}",
        f"Result: {model.result_gate_decision} ({model.result_gate.reason})",
        f"Capabilities: {model.capabilities.status} ({model.capabilities.reason})",
        f"Handoff: {model.handoff_status}",
        f"Last sequence: {model.last_sequence}",
        "Timeline:",
    ]
    for entry in model.timeline:
        lines.append(
            f"  {entry.sequence} {entry.event_type} [{entry.source}] "
            f"{entry.state}: {entry.summary}"
        )
    for warning in model.warnings:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines) + "\n"


def render_snapshot(projection: RunProjection) -> str:
    return render_view_model(from_projection(projection))


def render_frame(projection: RunProjection, ansi_redraw: bool = False) -> str:
    """Return one complete frame; ANSI bytes are a fixed presenter-owned prefix only."""
    snapshot = render_snapshot(projection)
    return (ANSI_REDRAW_PREFIX if ansi_redraw else "") + snapshot
