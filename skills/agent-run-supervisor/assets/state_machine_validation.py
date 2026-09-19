"""Exact schema validation shared by state-machine consumers."""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"
TOP_LEVEL_FIELDS = {"schema_version", "states", "allowed_transitions"}
STATE_FIELDS = {"name", "classification"}
CLASSIFICATIONS = {"active", "terminal"}


def validate_definition(data: Any) -> tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[tuple[str, str]]]:
    """Return normalized policy sets or raise ValueError for any schema deviation."""
    if not isinstance(data, dict) or set(data) != TOP_LEVEL_FIELDS:
        raise ValueError("state-machine definition has invalid fields")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("state-machine definition has an unsupported schema version")
    if not isinstance(data["states"], list) or not isinstance(data["allowed_transitions"], list):
        raise ValueError("state-machine definition has invalid types")

    names: list[str] = []
    active: set[str] = set()
    terminal: set[str] = set()
    for item in data["states"]:
        if not isinstance(item, dict) or set(item) != STATE_FIELDS:
            raise ValueError("state definition is malformed")
        name = item["name"]
        classification = item["classification"]
        if not isinstance(name, str) or not name or classification not in CLASSIFICATIONS:
            raise ValueError("state definition is malformed")
        if name in names:
            raise ValueError("state definition contains a duplicate state")
        names.append(name)
        (active if classification == "active" else terminal).add(name)

    edges: list[tuple[str, str]] = []
    for raw in data["allowed_transitions"]:
        if not isinstance(raw, list) or len(raw) != 2 or not all(isinstance(value, str) for value in raw):
            raise ValueError("transition definition is malformed")
        edge = (raw[0], raw[1])
        if edge[0] not in names or edge[1] not in names:
            raise ValueError("transition references an unknown state")
        if edge in edges:
            raise ValueError("state-machine definition contains a duplicate transition")
        edges.append(edge)

    return frozenset(names), frozenset(active), frozenset(terminal), frozenset(edges)
