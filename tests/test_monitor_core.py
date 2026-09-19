import unittest
from unittest import mock

from tools.safety_monitor import projection as projection_module
from tools.safety_monitor.events import EventError, PersistedEvent, parse_producer
from tools.safety_monitor.presenter import ANSI_REDRAW_PREFIX, escape_text, render_frame, render_snapshot
from tools.safety_monitor.projection import RunProjection, apply_event, replay

HASH = "sha256:" + "0" * 64
TIME = "2026-09-19T08:00:00Z"


def producer(event_type="RUN_CREATED", event_id="event-1", **overrides):
    data = {
        "schema_version": "1.0", "producer_event_id": event_id, "task_id": "task-1",
        "run_id": "run-1", "occurred_at": TIME, "type": event_type,
        "summary": "safe summary",
    }
    if event_type == "RUN_CREATED":
        data["envelope_hash"] = HASH
    else:
        data["state"] = {"from": "PLANNED", "to": "RUNNING"}
    data.update(overrides)
    return data


def persisted(data, sequence, event_id):
    parsed = parse_producer(data)
    return PersistedEvent(parsed, "validator", sequence, TIME, event_id, parsed.run_id if parsed.type == "RUN_CREATED" else None)


class EventContractTests(unittest.TestCase):
    def test_rejects_unknown_type_and_fields(self):
        with self.assertRaises(EventError): parse_producer(producer(type="OTHER"))
        with self.assertRaises(EventError): parse_producer(producer(extra=True))
        with self.assertRaises(EventError): parse_producer(producer(source="validator"))

    def test_rejects_path_traversal_and_bad_hash(self):
        with self.assertRaises(EventError): parse_producer(producer(run_id="../escape"))
        with self.assertRaises(EventError): parse_producer(producer(envelope_hash="sha256:ABC"))

    def test_rejects_controls_bidi_and_non_utc_timestamp(self):
        for value in ("line\nbreak", "\x1b[31m", "right\u202eto-left", "x\x85y"):
            with self.subTest(value=repr(value)), self.assertRaises(EventError):
                parse_producer(producer(summary=value))
        with self.assertRaises(EventError): parse_producer(producer(occurred_at="2026-01-01T00:00:00+01:00"))

    def test_summary_and_id_limits(self):
        with self.assertRaises(EventError): parse_producer(producer(summary="x" * 513))
        with self.assertRaises(EventError): parse_producer(producer(run_id="x" * 129))

    def test_known_secret_patterns_are_rejected_before_persistence(self):
        secret_like = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "token ghp_abcdefghijklmnopqrstuvwxyz123456",
            "token sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            "key AKIAABCDEFGHIJKLMNOP",
        )
        for summary in secret_like:
            with self.subTest(summary=summary), self.assertRaises(EventError) as caught:
                parse_producer(producer(summary=summary))
            self.assertEqual(caught.exception.code, "SECRET_PATTERN")


class ProjectionTests(unittest.TestCase):
    def creation(self): return persisted(producer(), 1, "store-1")
    def transition(self, sequence=2, target="RUNNING", event_id="event-2"):
        data = producer("STATE_TRANSITION", event_id)
        data["state"] = {"from": "PLANNED", "to": target}
        return persisted(data, sequence, f"store-{sequence}")

    def test_happy_path(self):
        projection = replay([self.creation(), self.transition()])
        self.assertEqual((projection.run_state, projection.last_sequence, projection.stream_integrity), ("RUNNING", 2, "OK"))
        self.assertEqual(projection.result_gate_decision, "NONE")
        self.assertEqual(projection.handoff_status, "NONE")

    def test_missing_sequence_does_not_change_state(self):
        projection = replay([self.creation(), self.transition(sequence=3)])
        self.assertEqual((projection.run_state, projection.last_sequence, projection.stream_integrity), ("PLANNED", 1, "INCOMPLETE"))

    def test_duplicate_creation_does_not_change_state(self):
        projection = replay([self.creation(), persisted(producer(event_id="another"), 2, "store-2")])
        self.assertEqual((projection.run_state, projection.last_sequence, projection.stream_integrity), ("PLANNED", 1, "INVALID"))

    def test_invalid_and_completion_transitions_do_not_change_state(self):
        invalid = self.transition(target="AWAITING_RESULT_GATE")
        completed_data = producer("STATE_TRANSITION", "complete")
        completed_data["state"] = {"from": "PLANNED", "to": "COMPLETED"}
        completed = persisted(completed_data, 2, "store-complete")
        for event in (invalid, completed):
            with self.subTest(target=event.producer.state_to):
                projection = replay([self.creation(), event])
                self.assertEqual(projection.run_state, "PLANNED")
                self.assertEqual(projection.last_sequence, 1)
                self.assertEqual(projection.stream_integrity, "INVALID")

    def test_terminal_mutation_does_not_change_terminal_state(self):
        failed = self.transition(target="FAILED")
        after_data = producer("STATE_TRANSITION", "after")
        after_data["state"] = {"from": "FAILED", "to": "RUNNING"}
        projection = replay([self.creation(), failed, persisted(after_data, 3, "store-3")])
        self.assertEqual((projection.run_state, projection.last_sequence), ("FAILED", 2))
        self.assertEqual(projection.stream_integrity, "INVALID")

    def test_large_replay_accumulates_ids_once_and_freezes_once(self):
        event_count = 16_000
        events = [self.creation()]
        state = "PLANNED"
        for sequence in range(2, event_count + 1):
            target = "RUNNING" if state in {"PLANNED", "RETRYING"} else "RETRYING"
            events.append(persisted(
                producer(
                    "STATE_TRANSITION",
                    f"event-{sequence}",
                    state={"from": state, "to": target},
                ),
                sequence,
                f"store-{sequence}",
            ))
            state = target

        accumulator = projection_module._ProducerIdAccumulator
        original_add = accumulator.add
        original_freeze = accumulator.freeze
        with (
            mock.patch.object(accumulator, "add", autospec=True, side_effect=original_add) as add,
            mock.patch.object(accumulator, "freeze", autospec=True, side_effect=original_freeze) as freeze,
        ):
            projection = replay(events)

        self.assertEqual(projection.last_sequence, event_count)
        self.assertEqual(len(projection.producer_event_ids), event_count)
        self.assertIsInstance(projection.producer_event_ids, frozenset)
        self.assertEqual(add.call_count, event_count)
        freeze.assert_called_once_with(mock.ANY)

    def test_single_event_apply_keeps_both_projections_immutable(self):
        initial = RunProjection()
        created_projection = apply_event(initial, self.creation())
        transitioned_projection = apply_event(created_projection, self.transition())
        self.assertEqual(initial.producer_event_ids, frozenset())
        self.assertEqual(created_projection.producer_event_ids, frozenset({"event-1"}))
        self.assertEqual(transitioned_projection.producer_event_ids, frozenset({"event-1", "event-2"}))
        self.assertIsInstance(transitioned_projection.producer_event_ids, frozenset)

    def test_presenter_has_no_raw_terminal_controls(self):
        self.assertEqual(escape_text("x\x1b\u202ey"), "x\\u001b\\u202ey")
        projection = RunProjection(task_id="x\x1b", run_id="run", run_state="PLANNED")
        output = render_snapshot(projection)
        self.assertNotIn("\x1b", output)
        self.assertIn("\\u001b", output)
        self.assertIn("Capabilities: UNAVAILABLE", output)
        self.assertIn("result-gate events and v2 evidence are unavailable", output)
        frame = render_frame(projection, ansi_redraw=True)
        self.assertEqual(frame[:len(ANSI_REDRAW_PREFIX)], ANSI_REDRAW_PREFIX)
        self.assertNotIn("\x1b", frame[len(ANSI_REDRAW_PREFIX):])


if __name__ == "__main__": unittest.main()
