"""Read-only, one-run sequence-cursor watch application."""
from __future__ import annotations

from collections.abc import Callable
import math
from typing import TextIO

from .events import PersistedEvent
from .presenter import escape_text, render_frame
from .projection import RunProjection, replay
from .state_machine import StateMachine, load_state_machine
from .store import HistoryBatch, StoreError

RETRYABLE_STORE_CODES = frozenset({"RUN_NOT_FOUND", "INCOMPLETE_TAIL"})


class WatchError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


Reader = Callable[[str, int], HistoryBatch]
Waiter = Callable[[float], None]


def _diagnostic(stream: TextIO, message: object) -> None:
    stream.write(f"safety-monitor watch: {escape_text(message)}\n")
    stream.flush()


def _validated_projection(
    history: tuple[PersistedEvent, ...],
    run_id: str,
    machine: StateMachine,
) -> RunProjection:
    """Fully replay one coherent history; never validate only its suffix."""
    for event in history:
        if event.producer.run_id != run_id:
            raise WatchError("RUN_MISMATCH", "reader returned an event for a different run")
    candidate = replay(history, machine)
    expected_sequence = history[-1].sequence if history else 0
    if not candidate.is_valid or candidate.last_sequence != expected_sequence:
        warning = candidate.warnings[-1] if candidate.warnings else "history event was not committed"
        raise WatchError("INVALID_HISTORY", warning)
    return candidate


def watch_run(
    run_id: str,
    reader: Reader,
    waiter: Waiter,
    stdout: TextIO,
    stderr: TextIO,
    *,
    poll_interval: float,
    ansi_redraw: bool,
    machine: StateMachine | None = None,
) -> None:
    """Poll one run until interrupted, committing only complete valid batches."""
    if (
        not isinstance(poll_interval, (int, float))
        or isinstance(poll_interval, bool)
        or not math.isfinite(poll_interval)
        or poll_interval <= 0
    ):
        raise WatchError("INVALID_INTERVAL", "poll interval must be positive")

    resolved = machine or load_state_machine()
    committed = RunProjection()
    committed_history: tuple[PersistedEvent, ...] = ()
    cursor = 0
    failure_active = False

    while True:
        try:
            batch = reader(run_id, cursor)
            if not isinstance(batch, HistoryBatch) or batch.after_sequence != cursor:
                raise WatchError("INVALID_READER_BATCH", "reader did not return the requested full-history batch")
            history = batch.history
            if not history and cursor == 0:
                raise StoreError("RUN_NOT_FOUND", "no events found for run")
        except StoreError as exc:
            if exc.code not in RETRYABLE_STORE_CODES:
                raise WatchError(exc.code, str(exc)) from exc
            if not failure_active:
                _diagnostic(stderr, f"retryable read failure ({exc.code}): {exc}")
                failure_active = True
            waiter(poll_interval)
            continue
        except OSError as exc:
            if not failure_active:
                _diagnostic(stderr, f"retryable read failure (OS_ERROR): {exc}")
                failure_active = True
            waiter(poll_interval)
            continue

        if failure_active:
            _diagnostic(stderr, f"read recovered at sequence {cursor}")
            failure_active = False

        candidate = _validated_projection(history, run_id, resolved)
        if len(history) < cursor or history[:cursor] != committed_history:
            raise WatchError("HISTORY_REWRITTEN", "committed event history changed before the sequence cursor")
        if candidate.last_sequence > cursor:
            # Commit projection, exact history, and cursor together only after the
            # complete bounded history and unchanged prefix have passed validation.
            committed = candidate
            committed_history = history
            cursor = candidate.last_sequence
            stdout.write(render_frame(committed, ansi_redraw=ansi_redraw))
            stdout.flush()
        waiter(poll_interval)
