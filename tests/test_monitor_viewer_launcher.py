import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.safety_monitor.recording import Recorder
from tools.safety_monitor.store import EventStore
from tools.safety_monitor import viewer_launcher as launcher

ROOT = Path(__file__).resolve().parents[1]
HASH = "sha256:" + "0" * 64
TIME = "2026-09-19T08:00:00Z"


def created(run_id="run-1"):
    return {
        "schema_version": "1.0", "producer_event_id": "created-1", "task_id": "task-1",
        "run_id": run_id, "occurred_at": TIME, "type": "RUN_CREATED", "summary": "created",
        "envelope_hash": HASH,
    }


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class ViewerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self.temporary.name)
        self.events = self.parent / "events"
        self.artifacts = self.parent / "artifacts"
        self.recorder = Recorder(EventStore(self.events, self.artifacts, self.parent))
        self.recorder.record(created(), "validator")

    def tearDown(self):
        self.temporary.cleanup()

    def test_manual_and_off_validate_run_but_start_nothing(self):
        for mode, status in (("manual", "manual"), ("off", "off")):
            with mock.patch.object(launcher, "_tmux") as tmux:
                result = launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", mode)
            self.assertEqual(result["status"], status)
            self.assertFalse(result["viewer_started"])
            self.assertIn("bun run", result["manual_commands"]["bun"])
            python_command = result["manual_commands"]["python"]
            self.assertIn(" -I ", python_command)
            self.assertIn(str(launcher.TRUSTED_BOOTSTRAP), python_command)
            self.assertIn(" watch ", python_command)
            self.assertNotIn(" -m tools.safety_monitor", python_command)
            tmux.assert_not_called()

    def test_missing_corrupt_and_hostile_run_never_launch(self):
        cases = ["missing", "../bad", "bad;touch-pwned"]
        for run_id in cases:
            with self.subTest(run_id=run_id), mock.patch.object(launcher, "_tmux") as tmux:
                with self.assertRaises((ValueError, RuntimeError)):
                    launcher.open_viewer(self.parent, self.events, self.artifacts, run_id, "auto")
                tmux.assert_not_called()
        log = self.events / "run-1/events.ndjson"
        record = json.loads(log.read_text(encoding="utf-8"))
        record["type"] = "STATE_TRANSITION"
        record["state"] = {"from": "PLANNED", "to": "RUNNING"}
        del record["envelope_hash"]
        del record["artifact_root"]
        log.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with mock.patch.object(launcher, "_tmux") as tmux, self.assertRaises(RuntimeError):
            launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
        tmux.assert_not_called()

        with log.open("ab") as stream:
            stream.write(b'{"partial":')
        with mock.patch.object(launcher, "_tmux") as tmux, self.assertRaises(RuntimeError):
            launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
        tmux.assert_not_called()

    def test_auto_without_confirmed_tmux_returns_manual(self):
        for environment in ({}, {"TMUX": "/tmp/tmux-501/default,123,1", "TMUX_PANE": "%1"}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(launcher.shutil, "which", return_value=None):
                result = launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
            self.assertEqual(result["status"], "manual")
            self.assertFalse(result["viewer_started"])

    def test_malformed_tmux_and_cross_session_pane_are_rejected(self):
        environments = (
            {"TMUX": "socket", "TMUX_PANE": "%1"},
            {"TMUX": "/tmp/socket,123,1,extra", "TMUX_PANE": "%1"},
            {"TMUX": "/tmp/socket,123,1", "TMUX_PANE": "1"},
        )
        for environment in environments:
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(launcher.shutil, "which", return_value="tmux"), \
                    mock.patch.object(launcher, "_tmux") as tmux:
                result = launcher.open_viewer(
                    self.parent, self.events, self.artifacts, "run-1", "auto",
                )
            self.assertEqual(result["status"], "manual")
            if environment["TMUX"] == "/tmp/socket,123,1" and environment["TMUX_PANE"] == "1":
                tmux.assert_not_called()

        with mock.patch.dict(
            os.environ, {"TMUX": "/tmp/socket,123,1", "TMUX_PANE": "%7"}, clear=True,
        ), mock.patch.object(launcher.shutil, "which", return_value="tmux"), mock.patch.object(
            launcher, "_tmux", return_value=completed([], stdout="%7|$2\n"),
        ) as tmux:
            result = launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
        self.assertEqual(result["status"], "manual")
        tmux.assert_called_once()

    def test_confirmed_tmux_creates_detached_distinct_pane_and_tags_it(self):
        calls = []
        responses = iter([
            completed([], stdout="%1|$1\n"),
            completed([], stdout="%1|\n"),
            completed([], stdout="%2\n"),
            completed([]),
        ])
        def fake_tmux(executable, arguments):
            calls.append(arguments)
            return next(responses)
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-501/default,123,1", "TMUX_PANE": "%1"}, clear=True), \
                mock.patch.object(launcher.shutil, "which", return_value="/usr/bin/tmux"), \
                mock.patch.object(launcher, "_tmux", side_effect=fake_tmux):
            result = launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
        self.assertEqual(result["status"], "launched")
        self.assertEqual(result["pane_id"], "%2")
        split = calls[2]
        self.assertIn("-d", split)
        self.assertEqual(split[split.index("-t") + 1], "%1")
        self.assertEqual(split[split.index("-c") + 1], str(ROOT))
        command = split[-1]
        self.assertIn(f"-I {launcher.TRUSTED_BOOTSTRAP}", command)
        self.assertIn("_viewer-entry --control", command)
        self.assertNotIn("-m tools.safety_monitor", command)
        self.assertNotIn("run-1", command)
        self.assertNotIn(str(self.events), command)
        self.assertEqual(calls[3][-2], "@safety_monitor_run")

    def test_duplicate_tag_suppresses_split(self):
        key = launcher._run_key(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        calls = []
        responses = iter([
            completed([], stdout="%1|$1\n"),
            completed([], stdout=f"%7|{key}\n"),
        ])
        def fake_tmux(executable, arguments):
            calls.append(arguments)
            return next(responses)
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-501/default,123,1", "TMUX_PANE": "%1"}, clear=True), \
                mock.patch.object(launcher.shutil, "which", return_value="tmux"), \
                mock.patch.object(launcher, "_tmux", side_effect=fake_tmux):
            result = launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["pane_id"], "%7")
        self.assertEqual(len(calls), 2)

    def test_hostile_path_is_quoted_data_and_not_in_tmux_viewer_argv(self):
        hostile_parent = self.parent / "space ; $(touch nope)"
        hostile_parent.mkdir(mode=0o700)
        events = hostile_parent / "event root"
        artifacts = hostile_parent / "artifacts"
        Recorder(EventStore(events, artifacts, hostile_parent)).record(created(), "validator")
        responses = iter([
            completed([], stdout="%1|$1\n"), completed([], stdout=""),
            completed([], stdout="%2\n"), completed([]),
        ])
        calls = []
        def fake_tmux(executable, arguments):
            calls.append(arguments); return next(responses)
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-501/default,123,1", "TMUX_PANE": "%1"}, clear=True), \
                mock.patch.object(launcher.shutil, "which", return_value="tmux"), \
                mock.patch.object(launcher, "_tmux", side_effect=fake_tmux):
            result = launcher.open_viewer(hostile_parent, events, artifacts, "run-1", "auto")
        self.assertEqual(result["status"], "launched")
        self.assertNotIn(str(events), calls[2][-1])
        self.assertNotIn("--run-id", calls[2][-1])
        self.assertIn("'", calls[2][-1])
        self.assertIn("'", result["manual_commands"]["python"])

    def test_control_manifest_is_owner_only_consumed_and_revalidated(self):
        control = launcher._write_control(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        self.assertEqual(stat.S_IMODE(control.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(control.stat().st_mode), 0o600)
        values = launcher._read_control(control)
        self.assertEqual(values, (
            self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1",
        ))
        self.assertFalse(control.exists())

    def test_control_symlink_permissions_schema_and_path_attacks_fail(self):
        control = launcher._write_control(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        control.chmod(0o644)
        with self.assertRaises(launcher.ViewerError): launcher._read_control(control)

        control = launcher._write_control(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        control.write_text(json.dumps({"schema_version": launcher.CONTROL_SCHEMA}), encoding="utf-8")
        with self.assertRaises(launcher.ViewerError): launcher._read_control(control)

        target = self.parent / "target.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o600)
        symlink = self.parent / launcher.CONTROL_DIRECTORY / ("a" * 32 + ".json")
        symlink.symlink_to(target)
        with self.assertRaises(launcher.ViewerError): launcher._read_control(symlink)

        control = launcher._write_control(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        data = json.loads(control.read_text(encoding="utf-8"))
        data["event_root"] = str(self.parent / "events/../events")
        control.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(launcher.ViewerError): launcher._read_control(control)

    def test_missing_bun_or_dependencies_selects_isolated_trusted_python_watch(self):
        control = launcher._write_control(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        environment = {
            "PATH": "/usr/bin", "HOME": "/nonexistent-viewer-home", "TERM": "xterm-256color",
            "LANG": "C.UTF-8", "LC_ALL": "C", "NO_COLOR": "1",
            "AWS_SECRET_ACCESS_KEY": "must-not-leak", "UNRELATED": "must-not-leak",
        }
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(launcher, "_bun_available", return_value=None), \
                mock.patch.object(launcher.os, "chdir"), \
                mock.patch.object(launcher.os, "execve", side_effect=RuntimeError) as execute, \
                self.assertRaises(RuntimeError):
            launcher.viewer_entry(control)
        executable, argv, child_environment = execute.call_args.args
        self.assertEqual(executable, sys.executable)
        self.assertEqual(argv[1:4], ["-I", str(launcher.TRUSTED_BOOTSTRAP), "watch"])
        self.assertEqual(
            child_environment,
            {name: environment[name] for name in ("PATH", "HOME", "TERM", "LANG", "LC_ALL", "NO_COLOR")},
        )
        self.assertFalse(control.exists())

        with mock.patch.object(launcher.shutil, "which", return_value=None):
            self.assertIsNone(launcher._bun_available())
        with mock.patch.object(launcher.shutil, "which", return_value="bun"), \
                mock.patch.object(launcher, "OPENTUI_DEPENDENCY", self.parent / "absent"):
            self.assertIsNone(launcher._bun_available())

    def test_valid_bun_selects_public_opentui_entry(self):
        control = launcher._write_control(self.parent.resolve(), self.events.resolve(), self.artifacts.resolve(), "run-1")
        with mock.patch.object(launcher, "_bun_available", return_value="/bin/bun"), \
                mock.patch.object(launcher.os, "chdir"), \
                mock.patch.object(launcher.os, "execve", side_effect=RuntimeError) as execute, \
                self.assertRaises(RuntimeError):
            launcher.viewer_entry(control)
        argv = execute.call_args.args[1]
        self.assertEqual(argv[:3], ["/bin/bun", "run", str(launcher.OPENTUI_ENTRY)])
        self.assertIn("--python", argv)

    def test_roots_must_preexist_and_remain_owner_only(self):
        missing = self.parent / "missing-artifacts"
        with self.assertRaises(RuntimeError):
            launcher.open_viewer(self.parent, self.events, missing, "run-1", "manual")
        self.assertFalse(missing.exists())

        self.artifacts.chmod(0o755)
        try:
            with self.assertRaises(RuntimeError):
                launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "manual")
            self.assertEqual(stat.S_IMODE(self.artifacts.stat().st_mode), 0o755)
        finally:
            self.artifacts.chmod(0o700)

    def test_reserved_control_directory_rejects_exact_and_nested_roots(self):
        control = self.parent / launcher.CONTROL_DIRECTORY
        control.mkdir(mode=0o700)
        nested = control / "nested"
        nested.mkdir(mode=0o700)
        for artifact_root in (control, nested):
            with self.subTest(artifact_root=artifact_root), mock.patch.object(launcher, "_tmux") as tmux, \
                    self.assertRaises(launcher.ViewerError):
                launcher.open_viewer(self.parent, self.events, artifact_root, "run-1", "auto")
            tmux.assert_not_called()

        for event_root in (control, control / "events"):
            event_root.mkdir(mode=0o700, exist_ok=True)
            run = event_root / "run-1"
            run.mkdir(mode=0o700)
            shutil.copyfile(self.events / "run-1/events.ndjson", run / "events.ndjson")
            with self.subTest(event_root=event_root), mock.patch.object(launcher, "_tmux") as tmux, \
                    self.assertRaises(launcher.ViewerError):
                launcher.open_viewer(self.parent, event_root, self.artifacts, "run-1", "auto")
            tmux.assert_not_called()

    def test_public_open_viewer_does_not_mutate_event_or_artifact_trees_and_metadata(self):
        def snapshot(root):
            entries = [root, *sorted(root.rglob("*"))]
            return tuple(
                (
                    path.relative_to(root).as_posix(), stat.S_IFMT(path.lstat().st_mode),
                    stat.S_IMODE(path.lstat().st_mode), path.lstat().st_uid, path.lstat().st_gid,
                    path.lstat().st_size, path.lstat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None,
                    hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
                )
                for path in entries
            )
        before = (snapshot(self.events), snapshot(self.artifacts))
        environment = dict(os.environ)
        environment.pop("TMUX", None); environment.pop("TMUX_PANE", None)
        result = subprocess.run(
            [sys.executable, "-I", str(launcher.TRUSTED_BOOTSTRAP), "open-viewer",
             "--allowed-parent", str(self.parent), "--event-root", str(self.events),
             "--artifact-root", str(self.artifacts), "--run-id", "run-1"],
            cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "manual")
        self.assertEqual((snapshot(self.events), snapshot(self.artifacts)), before)

    def test_public_bootstrap_ignores_hostile_cwd_and_pythonpath_in_manual_path(self):
        shadow = self.parent / "shadow"
        package = shadow / "tools/safety_monitor"
        package.mkdir(parents=True)
        (shadow / "tools/__init__.py").write_text("", encoding="utf-8")
        (package / "__init__.py").write_text("", encoding="utf-8")
        sentinel = self.parent / "shadow-executed"
        (package / "__main__.py").write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(shadow)
        environment.pop("TMUX", None)
        environment.pop("TMUX_PANE", None)
        result = subprocess.run(
            [sys.executable, "-I", str(launcher.TRUSTED_BOOTSTRAP), "open-viewer",
             "--allowed-parent", str(self.parent), "--event-root", str(self.events),
             "--artifact-root", str(self.artifacts), "--run-id", "run-1", "--mode", "manual"],
            cwd=shadow, env=environment, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "manual")
        self.assertFalse(sentinel.exists(), "shadow tools.safety_monitor executed")

    @unittest.skipUnless(os.environ.get("RUN_REAL_TMUX_TESTS") == "1" and shutil.which("tmux"), "opt-in real tmux test")
    def test_real_tmux_detached_split(self):
        session = "safety-monitor-test-" + os.urandom(4).hex()
        shadow = self.parent / "shadow"
        package = shadow / "tools/safety_monitor"
        package.mkdir(parents=True)
        (shadow / "tools/__init__.py").write_text("", encoding="utf-8")
        sentinel = self.parent / "shadow-executed"
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        subprocess.run(["tmux", "new-session", "-d", "-c", str(shadow), "-s", session], check=True)
        try:
            pane = subprocess.run(["tmux", "display-message", "-p", "-t", session, "#{pane_id}"], capture_output=True, text=True, check=True).stdout.strip()
            tmux_environment = subprocess.run(
                ["tmux", "display-message", "-p", "-t", session, "#{socket_path},#{pid},#{session_id}"],
                capture_output=True, text=True, check=True,
            ).stdout.strip().replace(",$", ",")
            environment = dict(os.environ)
            environment.update({
                "TMUX": tmux_environment, "TMUX_PANE": pane, "PYTHONPATH": str(shadow),
            })
            process = subprocess.run(
                [sys.executable, "-I", str(launcher.TRUSTED_BOOTSTRAP), "open-viewer",
                 "--allowed-parent", str(self.parent), "--event-root", str(self.events),
                 "--artifact-root", str(self.artifacts), "--run-id", "run-1", "--mode", "auto"],
                cwd=shadow, env=environment, capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result["status"], "launched")
            self.assertNotEqual(result["pane_id"], pane)
            self.assertFalse(sentinel.exists(), "shadow tools.safety_monitor executed")
            pane_cwd = subprocess.run(
                ["tmux", "display-message", "-p", "-t", result["pane_id"], "#{pane_current_path}"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(pane_cwd, str(ROOT))
        finally:
            subprocess.run(["tmux", "kill-session", "-t", session], check=False)

    @unittest.skipUnless(os.environ.get("RUN_REAL_TMUX_TESTS") == "1" and shutil.which("tmux"), "opt-in real tmux test")
    def test_real_tmux_rejects_cross_session_pane_on_same_server(self):
        first = "safety-monitor-first-" + os.urandom(4).hex()
        second = "safety-monitor-second-" + os.urandom(4).hex()
        subprocess.run(["tmux", "new-session", "-d", "-s", first], check=True)
        subprocess.run(["tmux", "new-session", "-d", "-s", second], check=True)
        try:
            pane = subprocess.run(
                ["tmux", "display-message", "-p", "-t", second, "#{pane_id}"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            identity = subprocess.run(
                ["tmux", "display-message", "-p", "-t", first, "#{socket_path},#{pid},#{session_id}"],
                capture_output=True, text=True, check=True,
            ).stdout.strip().replace(",$", ",")
            with mock.patch.dict(os.environ, {"TMUX": identity, "TMUX_PANE": pane}, clear=False):
                result = launcher.open_viewer(self.parent, self.events, self.artifacts, "run-1", "auto")
            self.assertEqual(result["status"], "manual")
            self.assertFalse(result["viewer_started"])
        finally:
            subprocess.run(["tmux", "kill-session", "-t", first], check=False)
            subprocess.run(["tmux", "kill-session", "-t", second], check=False)


if __name__ == "__main__": unittest.main()
