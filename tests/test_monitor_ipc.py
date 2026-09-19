import json
import os
import socket
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tools.safety_monitor.events import MAX_REQUEST_BYTES
from tools.safety_monitor.ipc import send, serve
from tools.safety_monitor.validator_adapter import AdapterError, validate_transition

HASH = "sha256:" + "0" * 64
TIME = "2026-09-19T08:00:00Z"


def creation(**extra):
    data = {
        "schema_version": "1.0", "producer_event_id": "producer-1", "task_id": "task-1",
        "run_id": "run-1", "occurred_at": TIME, "type": "RUN_CREATED",
        "summary": "created", "envelope_hash": HASH,
    }
    data.update(extra)
    return data


class IPCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.socket_path = self.root / "ipc/monitor.sock"
        self.events = self.root / "events"
        self.artifacts = self.root / "artifacts"
        self.token = "a" * 64

    def tearDown(self): self.temp.cleanup()

    def start_server(self, requests=1):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, self.token.encode())
        os.close(write_fd)
        errors = []
        def target():
            try: serve(self.socket_path, self.events, self.artifacts, self.root, read_fd, requests)
            except Exception as exc: errors.append(exc)
        thread = threading.Thread(target=target)
        thread.start()
        deadline = time.monotonic() + 3
        while not self.socket_path.exists() and thread.is_alive() and time.monotonic() < deadline: time.sleep(0.01)
        self.assertTrue(self.socket_path.exists(), errors)
        return thread, errors

    def finish(self, thread, errors):
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_authenticated_recording_and_socket_permissions(self):
        thread, errors = self.start_server()
        self.assertEqual(stat.S_IMODE(self.socket_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.socket_path.parent.stat().st_mode), 0o700)
        result = send(self.socket_path, self.token, creation())
        self.assertTrue(result["ok"])
        self.finish(thread, errors)
        line = json.loads((self.events / "run-1/events.ndjson").read_text())
        self.assertEqual(line["source"], "validator")

    def test_wrong_token_does_not_modify_primary_log(self):
        thread, errors = self.start_server()
        result = send(self.socket_path, "wrong", creation())
        self.assertFalse(result["ok"])
        self.finish(thread, errors)
        self.assertFalse((self.events / "run-1/events.ndjson").exists())

    def test_secret_shaped_adapter_id_is_digested_in_audit_metadata(self):
        malicious_id = "ghp_abcdefghijklmnopqrstuvwxyz123456"
        thread, errors = self.start_server()
        result = send(self.socket_path, self.token, creation(), malicious_id)
        self.assertFalse(result["ok"])
        self.finish(thread, errors)
        audit_text = (self.events / "_audit/invalid-events.ndjson").read_text(encoding="utf-8")
        record = json.loads(audit_text)
        self.assertNotIn(malicious_id, audit_text)
        self.assertRegex(record["adapter_id"], r"^sha256-[0-9a-f]{64}$")
        self.assertFalse((self.events / "run-1/events.ndjson").exists())

    def test_unknown_adapter_and_source_claim_are_rejected(self):
        for kwargs in ({"adapter_id": "unknown"}, {"event": creation(source="runtime")}):
            with self.subTest(kwargs=kwargs):
                thread, errors = self.start_server()
                event = kwargs.get("event", creation())
                result = send(self.socket_path, self.token, event, kwargs.get("adapter_id", "transition-validator"))
                self.assertFalse(result["ok"])
                self.finish(thread, errors)
                self.assertFalse((self.events / "run-1/events.ndjson").exists())

    def test_oversized_request_is_rejected(self):
        thread, errors = self.start_server()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(self.socket_path))
        client.sendall(b"x" * (MAX_REQUEST_BYTES + 1))
        response = b""
        while not response.endswith(b"\n"):
            response += client.recv(4096)
        client.close()
        self.assertFalse(json.loads(response)["ok"])
        self.finish(thread, errors)
        self.assertFalse((self.events / "run-1/events.ndjson").exists())

    def test_adapter_rejects_transition_validator_failure(self):
        event = creation()
        event.update({"type": "STATE_TRANSITION", "state": {"from": "COMPLETED", "to": "RUNNING"}})
        event.pop("envelope_hash")
        with self.assertRaises(AdapterError): validate_transition(event)


if __name__ == "__main__": unittest.main()
