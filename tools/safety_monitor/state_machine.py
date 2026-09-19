"""Reader and validator for the canonical supervisor state machine."""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DEFINITION_PATH = Path(__file__).resolve().parents[2] / "skills" / "agent-run-supervisor" / "assets" / "state-machine.json"
VALIDATOR_PATH = DEFINITION_PATH.with_name("state_machine_validation.py")


class StateMachineError(ValueError):
    pass


@dataclass(frozen=True)
class StateMachine:
    states: frozenset[str]
    active: frozenset[str]
    terminal: frozenset[str]
    transitions: frozenset[tuple[str, str]]

    def allows(self, source: str, target: str) -> bool:
        return (source, target) in self.transitions


def _shared_validator() -> Callable[[Any], tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[tuple[str, str]]]]:
    spec = importlib.util.spec_from_file_location("agent_run_supervisor_state_machine_validation", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise StateMachineError("cannot load shared state-machine validator")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.validate_definition
    except (AttributeError, OSError) as exc:
        raise StateMachineError(f"cannot load shared state-machine validator: {exc}") from exc


def load_state_machine(path: Path = DEFINITION_PATH) -> StateMachine:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateMachineError(f"cannot load state-machine definition: {exc}") from exc
    try:
        names, active, terminal, edges = _shared_validator()(data)
    except ValueError as exc:
        raise StateMachineError(str(exc)) from exc
    return StateMachine(names, active, terminal, edges)
