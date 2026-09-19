import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASH = "sha256:" + "0" * 64


class VerticalSliceTests(unittest.TestCase):
    def test_vertical_slice_and_read_only_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events"
            artifacts = root / "artifacts"
            command = [
                sys.executable, "-m", "tools.safety_monitor", "vertical-slice",
                "--event-root", str(events), "--artifact-root", str(artifacts),
                "--allowed-parent", str(root), "--task-id", "task-1", "--run-id", "run-1", "--envelope-hash", HASH,
            ]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            for expected in ("State: RUNNING", "Stream: OK", "Result: NONE", "Handoff: NONE", "Last sequence: 2"):
                self.assertIn(expected, result.stdout)
            path = events / "run-1/events.ndjson"
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            records = [json.loads(line) for line in lines]
            self.assertEqual([item["sequence"] for item in records], [1, 2])
            self.assertEqual([item["source"] for item in records], ["validator", "validator"])
            before = path.read_bytes()
            snapshot = subprocess.run(
                [sys.executable, "-m", "tools.safety_monitor", "snapshot", "--event-root", str(events), "--allowed-parent", str(root), "--run-id", "run-1"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
            self.assertEqual(snapshot.stdout, result.stdout)
            self.assertEqual(path.read_bytes(), before)

    def test_snapshot_fails_closed_on_corrupt_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events/run-1"
            events.mkdir(parents=True)
            events.parent.chmod(0o700)
            (events / "events.ndjson").write_bytes(b'{"partial":')
            result = subprocess.run(
                [sys.executable, "-m", "tools.safety_monitor", "snapshot", "--event-root", str(events.parent), "--allowed-parent", str(Path(directory)), "--run-id", "run-1"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("incomplete tail", result.stderr)

    def test_watch_is_not_exposed(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.safety_monitor", "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertNotIn("--watch", result.stdout)


if __name__ == "__main__": unittest.main()
