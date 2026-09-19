import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.safety_monitor.events import EventError, PersistedEvent, parse_producer
from tools.safety_monitor.recording import Recorder, RecordingError
from tools.safety_monitor.store import (
    MAX_REPLAY_BYTES, MAX_REPLAY_LINE_BYTES, EventStore, StoreError, read_events, read_history,
)

HASH = "sha256:" + "0" * 64
TIME = "2026-09-19T08:00:00Z"


def event(event_type="RUN_CREATED", event_id="producer-1"):
    data = {
        "schema_version": "1.0", "producer_event_id": event_id, "task_id": "task-1",
        "run_id": "run-1", "occurred_at": TIME, "type": event_type, "summary": "summary",
    }
    if event_type == "RUN_CREATED": data["envelope_hash"] = HASH
    else: data["state"] = {"from": "PLANNED", "to": "RUNNING"}
    return data


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.root = root
        self.events = root / "events"
        self.artifacts = root / "artifacts"
        self.store = EventStore(self.events, self.artifacts, root)
        self.recorder = Recorder(self.store)

    def tearDown(self): self.temporary.cleanup()

    def test_durable_append_and_owner_permissions(self):
        created = self.recorder.record(event(), "validator")
        transition = self.recorder.record(event("STATE_TRANSITION", "producer-2"), "validator")
        reopened = EventStore(self.events, self.artifacts, self.root)
        loaded = reopened.read("run-1")
        self.assertEqual([item.sequence for item in loaded], [1, 2])
        self.assertEqual([item.source for item in loaded], ["validator", "validator"])
        self.assertEqual(created.artifact_root, "run-1")
        self.assertEqual(stat.S_IMODE((self.events / "run-1/events.ndjson").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.artifacts / "run-1").stat().st_mode), 0o700)

    def test_server_fields_are_rejected_without_primary_append(self):
        claimed = event(); claimed["sequence"] = 9
        with self.assertRaises(EventError): self.recorder.record(claimed, "validator")
        self.assertFalse((self.events / "run-1/events.ndjson").exists())

    def test_duplicate_producer_id_is_rejected(self):
        self.recorder.record(event(), "validator")
        duplicate = event("STATE_TRANSITION", "producer-1")
        with self.assertRaises(RecordingError): self.recorder.record(duplicate, "validator")
        self.assertEqual(len(self.store.read("run-1")), 1)

    def test_invalid_transition_does_not_append(self):
        self.recorder.record(event(), "validator")
        invalid = event("STATE_TRANSITION", "producer-2")
        invalid["state"] = {"from": "PLANNED", "to": "COMPLETED"}
        with self.assertRaises(RecordingError): self.recorder.record(invalid, "validator")
        self.assertEqual(len(self.store.read("run-1")), 1)

    def test_incomplete_tail_blocks_writes(self):
        self.recorder.record(event(), "validator")
        with (self.events / "run-1/events.ndjson").open("ab") as stream: stream.write(b'{"broken":')
        with self.assertRaises(RecordingError) as caught:
            self.recorder.record(event("STATE_TRANSITION", "producer-2"), "validator")
        self.assertEqual(caught.exception.code, "INCOMPLETE_TAIL")

    def test_symlink_artifact_target_is_rejected(self):
        target = Path(self.temporary.name) / "target"
        target.mkdir()
        os.symlink(target, self.artifacts / "run-1")
        with self.assertRaises(RecordingError): self.recorder.record(event(), "validator")
        self.assertFalse((self.events / "run-1/events.ndjson").exists())

    def test_audit_contains_no_raw_payload(self):
        payload = b'secret raw payload'
        self.store.audit_invalid("adapter", "BAD", payload, TIME)
        record = json.loads((self.events / "_audit/invalid-events.ndjson").read_text())
        self.assertNotIn("secret", json.dumps(record))
        self.assertEqual(set(record), {"recorded_at", "adapter_id", "error_code", "payload_sha256"})

    def test_unsafe_roots_are_rejected_without_chmod(self):
        preexisting = self.root / "preexisting"
        preexisting.mkdir(mode=0o755)
        before = stat.S_IMODE(preexisting.stat().st_mode)
        cases = [
            (Path("/"), self.root / "a", self.root),
            (Path.home(), self.root / "a", self.root),
            (self.root / "same", self.root / "same", self.root),
            (self.root / "outer", self.root / "outer/inner", self.root),
            (preexisting, self.root / "other", self.root),
            (self.root / "a", self.root / "b", Path("/")),
        ]
        for event_root, artifact_root, parent in cases:
            with self.subTest(event_root=event_root, artifact_root=artifact_root, parent=parent):
                with self.assertRaises(StoreError):
                    EventStore(event_root, artifact_root, parent)
        self.assertEqual(stat.S_IMODE(preexisting.stat().st_mode), before)

    def test_audit_directory_symlink_is_rejected(self):
        target = self.root / "audit-target"
        target.mkdir()
        os.symlink(target, self.events / "_audit")
        with self.assertRaises(StoreError):
            self.store.audit_invalid("adapter", "BAD", b"payload", TIME)
        self.assertFalse((target / "invalid-events.ndjson").exists())

    def test_audit_file_symlink_is_rejected(self):
        audit = self.events / "_audit"
        audit.mkdir(mode=0o700)
        target = self.root / "audit-target"
        target.write_text("unchanged", encoding="utf-8")
        os.symlink(target, audit / "invalid-events.ndjson")
        with self.assertRaises(StoreError):
            self.store.audit_invalid("adapter", "BAD", b"payload", TIME)
        self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

    def test_first_append_failure_rolls_back_artifact_and_can_retry(self):
        with mock.patch("tools.safety_monitor.store.os.fsync", side_effect=[OSError("forced fsync failure"), None]) as fsync:
            with self.assertRaises(RecordingError) as caught:
                self.recorder.record(event(), "validator")
        self.assertEqual(caught.exception.code, "APPEND_FAILED")
        self.assertEqual(fsync.call_count, 2)
        self.assertFalse((self.artifacts / "run-1").exists())
        recorded = self.recorder.record(event(), "validator")
        self.assertEqual(recorded.sequence, 1)
        self.assertEqual(len(self.store.read("run-1")), 1)

    def test_short_write_is_durably_rolled_back_and_can_retry(self):
        real_write = os.write
        short_write_used = False

        def write_short_once(descriptor, data):
            nonlocal short_write_used
            if not short_write_used:
                short_write_used = True
                return real_write(descriptor, data[: len(data) // 2])
            return real_write(descriptor, data)

        with (
            mock.patch("tools.safety_monitor.store.os.write", side_effect=write_short_once),
            mock.patch("tools.safety_monitor.store.os.fsync", wraps=os.fsync) as fsync,
        ):
            with self.assertRaises(RecordingError) as caught:
                self.recorder.record(event(), "validator")
        self.assertEqual(caught.exception.code, "APPEND_FAILED")
        self.assertEqual(fsync.call_count, 1)
        self.assertEqual((self.events / "run-1/events.ndjson").read_bytes(), b"")
        self.assertFalse((self.artifacts / "run-1").exists())
        recorded = self.recorder.record(event(), "validator")
        self.assertEqual(recorded.sequence, 1)
        self.assertEqual(len(self.store.read("run-1")), 1)

    def test_append_accepts_exact_replay_limit_and_rejects_crossing(self):
        created = PersistedEvent(parse_producer(event()), "validator", 1, TIME, "stored-1", "run-1")
        encoded = json.dumps(
            created.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with mock.patch("tools.safety_monitor.store.MAX_REPLAY_BYTES", len(encoded)):
            self.store.append(created)
            before = (self.events / "run-1/events.ndjson").read_bytes()
            self.assertEqual(len(before), len(encoded))
            with self.assertRaises(RecordingError) as caught:
                self.recorder.record(event("STATE_TRANSITION", "producer-2"), "validator")
            self.assertEqual(caught.exception.code, "LOG_TOO_LARGE")
            self.assertEqual((self.events / "run-1/events.ndjson").read_bytes(), before)
            self.assertEqual(len(self.store.read("run-1")), 1)

    def test_cursor_filters_only_after_validating_the_whole_log(self):
        self.recorder.record(event(), "validator")
        self.recorder.record(event("STATE_TRANSITION", "producer-2"), "validator")
        self.assertEqual([item.sequence for item in read_events(self.events, "run-1", self.root, 0)], [1, 2])
        self.assertEqual([item.sequence for item in read_events(self.events, "run-1", self.root, 1)], [2])
        self.assertEqual(read_events(self.events, "run-1", self.root, 2), [])
        batch = read_history(self.events, "run-1", self.root, 1)
        self.assertEqual(batch.after_sequence, 1)
        self.assertEqual([item.sequence for item in batch.history], [1, 2])
        self.assertEqual([item.sequence for item in batch.suffix], [2])
        for cursor in (-1, True, 1.5):
            with self.subTest(cursor=cursor), self.assertRaises(StoreError) as caught:
                read_events(self.events, "run-1", self.root, cursor)  # type: ignore[arg-type]
            self.assertEqual(caught.exception.code, "INVALID_CURSOR")
        with self.assertRaises(StoreError) as caught:
            read_events(self.events, "run-1", self.root, 3)
        self.assertEqual(caught.exception.code, "CURSOR_AHEAD")

    def test_cursor_does_not_hide_corrupt_prefix_or_truncation(self):
        self.recorder.record(event(), "validator")
        self.recorder.record(event("STATE_TRANSITION", "producer-2"), "validator")
        path = self.events / "run-1/events.ndjson"
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        records[0]["sequence"] = 9
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        with self.assertRaises(StoreError) as caught:
            read_events(self.events, "run-1", self.root, 1)
        self.assertEqual(caught.exception.code, "CORRUPT_LOG")
        path.unlink()
        with self.assertRaises(StoreError) as truncated:
            read_events(self.events, "run-1", self.root, 1)
        self.assertEqual(truncated.exception.code, "CURSOR_AHEAD")

    def test_cursor_read_is_filesystem_read_only(self):
        self.recorder.record(event(), "validator")
        path = self.events / "run-1/events.ndjson"
        before_bytes = path.read_bytes()
        before_entries = sorted(str(item.relative_to(self.root)) for item in self.root.rglob("*"))
        read_events(self.events, "run-1", self.root, 0)
        self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(sorted(str(item.relative_to(self.root)) for item in self.root.rglob("*")), before_entries)

    def test_replay_rejects_line_and_total_byte_overflow(self):
        run = self.events / "run-1"
        run.mkdir(mode=0o700)
        log = run / "events.ndjson"
        log.write_bytes(b"x" * (MAX_REPLAY_LINE_BYTES + 1) + b"\n")
        with self.assertRaises(StoreError) as line_error:
            read_events(self.events, "run-1", self.root)
        self.assertEqual(line_error.exception.code, "LINE_TOO_LARGE")
        with log.open("wb") as stream:
            stream.truncate(MAX_REPLAY_BYTES + 1)
        with self.assertRaises(StoreError) as total_error:
            read_events(self.events, "run-1", self.root)
        self.assertEqual(total_error.exception.code, "LOG_TOO_LARGE")


if __name__ == "__main__": unittest.main()
