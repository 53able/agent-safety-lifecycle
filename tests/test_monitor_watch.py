import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.safety_monitor.__main__ import main
from tools.safety_monitor.events import PersistedEvent, parse_producer
from tools.safety_monitor.presenter import ANSI_REDRAW_PREFIX, render_frame, render_snapshot
from tools.safety_monitor.projection import RunProjection, TimelineEntry
from tools.safety_monitor.recording import Recorder
from tools.safety_monitor.store import EventStore, HistoryBatch, StoreError, read_history
from tools.safety_monitor.watch import WatchError, watch_run

HASH = "sha256:" + "0" * 64
TIME = "2026-09-19T08:00:00Z"


def created(run_id="run-1", sequence=1):
    data = {
        "schema_version": "1.0", "producer_event_id": f"{run_id}-created", "task_id": "task-1",
        "run_id": run_id, "occurred_at": TIME, "type": "RUN_CREATED", "summary": "created",
        "envelope_hash": HASH,
    }
    return PersistedEvent(parse_producer(data), "validator", sequence, TIME, f"stored-{run_id}-{sequence}", run_id)


def transition(sequence, source, target, run_id="run-1", summary=None):
    data = {
        "schema_version": "1.0", "producer_event_id": f"{run_id}-event-{sequence}", "task_id": "task-1",
        "run_id": run_id, "occurred_at": TIME, "type": "STATE_TRANSITION", "summary": summary or f"to {target}",
        "state": {"from": source, "to": target},
    }
    return PersistedEvent(parse_producer(data), "validator", sequence, TIME, f"stored-{run_id}-{sequence}")


class StopAfter:
    def __init__(self, calls):
        self.remaining = calls

    def __call__(self, _interval):
        self.remaining -= 1
        if self.remaining == 0:
            raise KeyboardInterrupt


def run_until_interrupt(reader, *, ansi=False, waits=1, output_format="text"):
    stdout, stderr = io.StringIO(), io.StringIO()
    with unittest.TestCase().assertRaises(KeyboardInterrupt):
        watch_run(
            "run-1", reader, StopAfter(waits), stdout, stderr,
            poll_interval=0.01, ansi_redraw=ansi, output_format=output_format,
        )
    return stdout.getvalue(), stderr.getvalue()


class WatchTests(unittest.TestCase):
    def test_initial_replay_and_idle_poll_do_not_duplicate_frames(self):
        cursors = []
        events = (created(), transition(2, "PLANNED", "RUNNING"))

        def reader(run_id, cursor):
            self.assertEqual(run_id, "run-1")
            cursors.append(cursor)
            return HistoryBatch(events, cursor)

        output, _ = run_until_interrupt(reader, waits=2)
        self.assertEqual(cursors, [0, 2])
        self.assertEqual(output.count("Last sequence:"), 1)
        self.assertIn("Last sequence: 2", output)

    def test_jsonl_initial_frame_idle_suppression_and_recovery(self):
        first = (created(), transition(2, "PLANNED", "RUNNING"))
        outcomes = [first, StoreError("INCOMPLETE_TAIL", "partial"), first + (transition(3, "RUNNING", "RETRYING"),)]

        def reader(_run_id, cursor):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return HistoryBatch(outcome, cursor)

        output, errors = run_until_interrupt(reader, waits=3, output_format="view-model-jsonl")
        frames = [json.loads(line) for line in output.splitlines()]
        self.assertEqual([frame["last_sequence"] for frame in frames], [2, 3])
        self.assertTrue(all(frame["schema"] == "monitor-view-model.v1" for frame in frames))
        self.assertNotIn("Task:", output)
        self.assertIn("read recovered", errors)

    def test_jsonl_invalid_batch_emits_no_partial_frame(self):
        first = (created(), transition(2, "PLANNED", "RUNNING"))
        invalid = first + (transition(4, "RUNNING", "RETRYING"),)
        stdout = io.StringIO()
        batches = [first, invalid]
        with self.assertRaises(WatchError):
            watch_run(
                "run-1", lambda _run, cursor: HistoryBatch(batches.pop(0), cursor),
                StopAfter(5), stdout, io.StringIO(), poll_interval=1, ansi_redraw=False,
                output_format="view-model-jsonl",
            )
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(stdout.getvalue())["last_sequence"], 2)

    def test_transient_failure_preserves_cursor_and_recovers_once(self):
        cursors = []
        first = (created(), transition(2, "PLANNED", "RUNNING"))
        outcomes = [
            first,
            StoreError("INCOMPLETE_TAIL", "partial"),
            first + (transition(3, "RUNNING", "RETRYING"),),
        ]

        def reader(_run_id, cursor):
            cursors.append(cursor)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return HistoryBatch(outcome, cursor)

        output, errors = run_until_interrupt(reader, waits=3)
        self.assertEqual(cursors, [0, 2, 2])
        self.assertEqual(output.count("Last sequence:"), 2)
        self.assertEqual(output.count("Last sequence: 2"), 1)
        self.assertEqual(output.count("Last sequence: 3"), 1)
        self.assertEqual(errors.count("retryable read failure"), 1)
        self.assertEqual(errors.count("read recovered"), 1)

    def test_repeated_os_failure_has_one_diagnostic_per_episode(self):
        outcomes = [OSError("down\x1b"), OSError("still down"), [created()]]

        def reader(_run_id, cursor):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return HistoryBatch(tuple(outcome), cursor)

        output, errors = run_until_interrupt(reader, waits=3)
        self.assertIn("Last sequence: 1", output)
        self.assertEqual(errors.count("retryable read failure"), 1)
        self.assertNotIn("\x1b", errors)
        self.assertIn("\\u001b", errors)

    def test_duplicate_suffix_is_suppressed_but_invalid_batch_is_atomic(self):
        first = (created(), transition(2, "PLANNED", "RUNNING"))
        invalid = first + (transition(3, "RUNNING", "RETRYING"), transition(5, "RETRYING", "RUNNING"))
        batches = [first, first, invalid]
        stdout, stderr = io.StringIO(), io.StringIO()
        waits = StopAfter(10)

        def reader(_run_id, cursor):
            return HistoryBatch(tuple(batches.pop(0)), cursor)

        with self.assertRaises(WatchError) as caught:
            watch_run("run-1", reader, waits, stdout, stderr, poll_interval=1, ansi_redraw=False)
        self.assertEqual(caught.exception.code, "INVALID_HISTORY")
        self.assertEqual(stdout.getvalue().count("Last sequence:"), 1)
        self.assertIn("Last sequence: 2", stdout.getvalue())
        self.assertNotIn("Last sequence: 3", stdout.getvalue())

    def test_state_machine_invalid_prefix_rewrite_fails_without_new_frame(self):
        first = (created(), transition(2, "PLANNED", "RUNNING"))
        rewritten = (created(), transition(2, "PLANNED", "AWAITING_RESULT_GATE"))
        batches = [first, rewritten]
        stdout = io.StringIO()

        with self.assertRaises(WatchError) as caught:
            watch_run(
                "run-1", lambda _run, cursor: HistoryBatch(batches.pop(0), cursor),
                StopAfter(10), stdout, io.StringIO(), poll_interval=1, ansi_redraw=False,
            )

        self.assertEqual(caught.exception.code, "INVALID_HISTORY")
        self.assertEqual(stdout.getvalue().count("Last sequence:"), 1)
        self.assertIn("State: RUNNING", stdout.getvalue())

    def test_legal_prefix_content_rewrite_fails_without_suffix_frame(self):
        first = (created(), transition(2, "PLANNED", "RUNNING"))
        rewritten = (
            created(), transition(2, "PLANNED", "RUNNING", summary="rewritten prior content"),
            transition(3, "RUNNING", "RETRYING"),
        )
        batches = [first, rewritten]
        stdout = io.StringIO()

        with self.assertRaises(WatchError) as caught:
            watch_run(
                "run-1", lambda _run, cursor: HistoryBatch(batches.pop(0), cursor),
                StopAfter(10), stdout, io.StringIO(), poll_interval=1, ansi_redraw=False,
            )

        self.assertEqual(caught.exception.code, "HISTORY_REWRITTEN")
        self.assertEqual(stdout.getvalue().count("Last sequence:"), 1)
        self.assertIn("Last sequence: 2", stdout.getvalue())
        self.assertNotIn("Last sequence: 3", stdout.getvalue())

    def test_tty_redraw_and_plain_modes_have_exact_ansi_contract(self):
        for ansi in (False, True):
            with self.subTest(ansi=ansi):
                output, _ = run_until_interrupt(
                    lambda _run, cursor: HistoryBatch((created(),), cursor), ansi=ansi,
                )
                if ansi:
                    self.assertTrue(output.startswith(ANSI_REDRAW_PREFIX))
                    self.assertEqual(output.count(ANSI_REDRAW_PREFIX), 1)
                    self.assertNotIn("\x1b", output[len(ANSI_REDRAW_PREFIX):])
                else:
                    self.assertNotIn("\x1b", output)

    def test_terminal_injection_is_escaped_even_for_direct_projection(self):
        malicious = "x\x1b[2J\x9b\x00\n\u202ey"
        projection = RunProjection(
            task_id=malicious, run_id=malicious, run_state=malicious,
            warnings=(malicious,), timeline=(TimelineEntry(1, malicious, malicious, malicious, malicious),),
        )
        plain = render_snapshot(projection)
        self.assertNotIn("\x1b", plain)
        frame = render_frame(projection, ansi_redraw=True)
        self.assertEqual(frame[:len(ANSI_REDRAW_PREFIX)], ANSI_REDRAW_PREFIX)
        self.assertNotIn("\x1b", frame[len(ANSI_REDRAW_PREFIX):])
        self.assertIn("\\u001b", plain)
        self.assertIn("\\n", plain)

    def test_timeline_is_bounded_and_placeholders_are_honest(self):
        events = [created()]
        state = "PLANNED"
        for sequence in range(2, 103):
            target = "RUNNING" if state in {"PLANNED", "RETRYING"} else "RETRYING"
            events.append(transition(sequence, state, target))
            state = target
        output, _ = run_until_interrupt(lambda _run, cursor: HistoryBatch(tuple(events), cursor))
        timeline_lines = [line for line in output.splitlines() if line.startswith("  ")]
        self.assertEqual(len(timeline_lines), 100)
        self.assertIn("Last sequence: 102", output)
        self.assertIn("Capabilities: UNAVAILABLE", output)
        self.assertIn("result-gate events and v2 evidence are unavailable", output)
        self.assertNotIn("IMPORTABLE", output)

    def test_other_run_is_rejected_and_requested_run_is_isolated(self):
        requested = []

        def reader(run_id, cursor):
            requested.append((run_id, cursor))
            return HistoryBatch((created("run-2"),), cursor)

        with self.assertRaises(WatchError):
            watch_run("run-1", reader, StopAfter(2), io.StringIO(), io.StringIO(), poll_interval=1, ansi_redraw=False)
        self.assertEqual(requested, [("run-1", 0)])

    def test_real_store_watch_and_ctrl_c_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_root = root / "events"
            store = EventStore(event_root, root / "artifacts", root)
            recorder = Recorder(store)
            for data in (created().producer.to_dict(), transition(2, "PLANNED", "RUNNING").producer.to_dict()):
                recorder.record(data, "validator")
            log = event_root / "run-1/events.ndjson"
            before_bytes = log.read_bytes()
            before_tree = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            reader = lambda run_id, cursor: read_history(event_root, run_id, root, cursor)
            output, _ = run_until_interrupt(reader)
            self.assertIn("Last sequence: 2", output)
            self.assertEqual(log.read_bytes(), before_bytes)
            self.assertEqual(sorted(str(path.relative_to(root)) for path in root.rglob("*")), before_tree)

    def test_cli_ctrl_c_returns_130_and_mode_respects_no_color(self):
        class Output(io.StringIO):
            def isatty(self): return True

        for environment, expected_ansi in (({}, True), ({"NO_COLOR": ""}, False)):
            with self.subTest(environment=environment):
                output = Output()
                with (
                    mock.patch("tools.safety_monitor.__main__.sys.stdout", output),
                    mock.patch("tools.safety_monitor.__main__.watch_run", side_effect=KeyboardInterrupt) as called,
                    mock.patch.dict("tools.safety_monitor.__main__.os.environ", environment, clear=True),
                ):
                    status = main(["watch", "--event-root", "/tmp/events", "--allowed-parent", "/tmp", "--run-id", "run-1"])
                self.assertEqual(status, 130)
                self.assertEqual(called.call_args.kwargs["ansi_redraw"], expected_ansi)
                self.assertEqual(called.call_args.kwargs["output_format"], "text")

    def test_cli_jsonl_never_enables_ansi(self):
        class Output(io.StringIO):
            def isatty(self): return True

        with (
            mock.patch("tools.safety_monitor.__main__.sys.stdout", Output()),
            mock.patch("tools.safety_monitor.__main__.watch_run", side_effect=KeyboardInterrupt) as called,
        ):
            status = main([
                "watch", "--event-root", "/tmp/events", "--allowed-parent", "/tmp",
                "--run-id", "run-1", "--format", "view-model-jsonl",
            ])
        self.assertEqual(status, 130)
        self.assertFalse(called.call_args.kwargs["ansi_redraw"])
        self.assertEqual(called.call_args.kwargs["output_format"], "view-model-jsonl")


if __name__ == "__main__":
    unittest.main()
