import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.safety_monitor.state_machine import StateMachineError, load_state_machine

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/agent-run-supervisor/scripts/validate-transition.py"
DEFINITION = ROOT / "skills/agent-run-supervisor/assets/state-machine.json"


class TransitionPolicyTests(unittest.TestCase):
    def run_cli(self, source, target, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), source, target], cwd=cwd,
            capture_output=True, text=True, check=False,
        )

    def test_documented_nonterminal_edges(self):
        edges = [
            ("PLANNED", "RUNNING"), ("RUNNING", "RETRYING"), ("RETRYING", "RUNNING"),
            ("RUNNING", "AWAITING_ELEVATION"), ("AWAITING_ELEVATION", "RUNNING"),
            ("RUNNING", "AWAITING_RESULT_GATE"), ("AWAITING_RESULT_GATE", "COMPLETED"),
        ]
        for edge in edges:
            with self.subTest(edge=edge):
                self.assertEqual(self.run_cli(*edge).returncode, 0)

    def test_all_active_states_reach_failure_terminals(self):
        machine = load_state_machine()
        for source in machine.active:
            for target in ("FAILED", "BLOCKED", "STOPPED"):
                with self.subTest(source=source, target=target):
                    self.assertEqual(self.run_cli(source, target).returncode, 0)

    def test_cli_matches_canonical_definition_for_every_pair(self):
        machine = load_state_machine()
        for source in machine.states | {"UNKNOWN"}:
            for target in machine.states | {"UNKNOWN"}:
                expected = (source, target) in machine.transitions
                self.assertEqual(self.run_cli(source, target).returncode == 0, expected, (source, target))

    def test_terminal_states_have_no_outgoing_transition(self):
        machine = load_state_machine()
        for source in machine.terminal:
            for target in machine.states:
                self.assertNotEqual(self.run_cli(source, target).returncode, 0)

    def test_cli_works_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_cli("PLANNED", "RUNNING", cwd=directory).returncode, 0)

    def test_malformed_definitions_are_rejected_identically(self):
        spec = importlib.util.spec_from_file_location("validate_transition_test", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        cli_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli_module)
        base = json.loads(DEFINITION.read_text(encoding="utf-8"))
        variants = []
        duplicate_state = json.loads(json.dumps(base)); duplicate_state["states"].append(duplicate_state["states"][0]); variants.append(duplicate_state)
        duplicate_edge = json.loads(json.dumps(base)); duplicate_edge["allowed_transitions"].append(duplicate_edge["allowed_transitions"][0]); variants.append(duplicate_edge)
        unknown = json.loads(json.dumps(base)); unknown["allowed_transitions"].append(["UNKNOWN", "RUNNING"]); variants.append(unknown)
        wrong_version = json.loads(json.dumps(base)); wrong_version["schema_version"] = "999"; variants.append(wrong_version)
        extra_field = json.loads(json.dumps(base)); extra_field["unexpected"] = True; variants.append(extra_field)
        bad_state_fields = json.loads(json.dumps(base)); bad_state_fields["states"][0]["unexpected"] = True; variants.append(bad_state_fields)
        variants.append({"states": []})
        with tempfile.TemporaryDirectory() as directory:
            for index, variant in enumerate(variants):
                path = Path(directory) / f"bad-{index}.json"
                path.write_text(json.dumps(variant), encoding="utf-8")
                with self.subTest(index=index):
                    with self.assertRaises(StateMachineError):
                        load_state_machine(path)
                    with self.assertRaises(ValueError):
                        cli_module.load_allowed(path)

    def test_usage_and_output_contract(self):
        usage = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(usage.returncode, 2)
        self.assertIn("Usage:", usage.stderr)
        valid = self.run_cli("PLANNED", "RUNNING")
        self.assertEqual(valid.stdout, "VALID transition: PLANNED -> RUNNING\n")
        invalid = self.run_cli("UNKNOWN", "RUNNING")
        self.assertEqual(invalid.stderr, "INVALID transition: UNKNOWN -> RUNNING\n")


if __name__ == "__main__":
    unittest.main()
