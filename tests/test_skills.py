import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def run_script(skill, script, *args):
    return subprocess.run(
        ["python3", str(SKILLS / skill / "scripts" / script), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


class ProjectValidationTests(unittest.TestCase):
    def test_project_structure(self):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts" / "validate-project.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("10 skills", result.stdout)


class RiskClassifierTests(unittest.TestCase):
    def classify(self, **overrides):
        data = {
            "task_id": "case",
            "needs_command_execution": False,
            "needs_file_write": False,
            "needs_secrets": False,
            "needs_external_network": False,
            "needs_external_write": False,
            "irreversible_or_high_impact": False,
            "unknown_fields": [],
        }
        data.update(overrides)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = run_script("agent-task-risk-classifier", "classify-task.py", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_no_exec(self):
        self.assertEqual(self.classify()["profile"], "no-exec")

    def test_isolated_execution(self):
        self.assertEqual(self.classify(needs_command_execution=True)["profile"], "isolated-execution")

    def test_brokered_write(self):
        self.assertEqual(self.classify(needs_external_write=True)["profile"], "brokered-write")

    def test_human_gate_wins(self):
        output = self.classify(needs_command_execution=True, irreversible_or_high_impact=True)
        self.assertEqual(output["profile"], "human-gated-impact")
        self.assertTrue(output["requires_human_gate"])


class EnvelopeTests(unittest.TestCase):
    def envelope(self):
        template = SKILLS / "agent-autonomy-envelope" / "assets" / "autonomy-envelope.template.json"
        data = json.loads(template.read_text(encoding="utf-8"))
        data["task_id"] = "case"
        return data

    def validate(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "envelope.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return run_script("agent-autonomy-envelope", "validate-envelope.py", path)

    def test_accepts_bounded_envelope(self):
        result = self.validate(self.envelope())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sha256:", result.stdout)

    def test_rejects_ambient_host_capability(self):
        data = self.envelope()
        data["allowed"].append("read-host-home")
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Forbidden ambient", result.stderr)

    def test_rejects_allow_deny_overlap(self):
        data = self.envelope()
        data["allowed"].append("deploy")
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("both allowed and denied", result.stderr)

    def test_rejects_non_vm_for_isolated_execution(self):
        data = self.envelope()
        data["execution_host"] = "restricted-interpreter"
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires execution_host", result.stderr)

    def test_rejects_writable_host_input(self):
        data = self.envelope()
        data["inputs"][0]["mode"] = "read-write"
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("read-only", result.stderr)

    def test_rejects_wildcard_network_destination(self):
        data = self.envelope()
        data["network"]["allow"] = ["*"]
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Wildcard network", result.stderr)


class SupervisorTests(unittest.TestCase):
    def test_valid_transition(self):
        result = run_script("agent-run-supervisor", "validate-transition.py", "RUNNING", "RETRYING")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_transition(self):
        result = run_script("agent-run-supervisor", "validate-transition.py", "COMPLETED", "RUNNING")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID", result.stderr)


class ResultGateTests(unittest.TestCase):
    def test_regular_artifact_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "change.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
            result = run_script("agent-result-gate", "inspect-artifacts.py", root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "REVIEW_REQUIRED")

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target").write_text("x", encoding="utf-8")
            os.symlink(root / "target", root / "link")
            result = run_script("agent-result-gate", "inspect-artifacts.py", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stdout)


class ResultGateReportTests(unittest.TestCase):
    def report(self):
        return {
            "task_id": "case",
            "artifact_root": "artifacts/case",
            "checks": {
                name: {"status": "PASS", "evidence": [f"logs/{name}.txt"]}
                for name in (
                    "artifact-structure", "secret-scan", "dependency-review",
                    "test-results", "side-effect-review", "rollback-review"
                )
            },
            "decision": "IMPORTABLE",
            "evidence": ["logs/result-gate.txt"],
            "destination": "worktrees/case",
        }

    def validate(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return run_script("agent-result-gate", "validate-result-gate-report.py", path)

    def test_importable_requires_all_checks(self):
        result = self.validate(self.report())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_importable_rejects_unrun_check(self):
        data = self.report()
        data["checks"]["secret-scan"] = {"status": "NOT_RUN", "evidence": []}
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires every required check", result.stderr)

    def test_failed_check_requires_rejection(self):
        data = self.report()
        data["checks"]["test-results"] = {"status": "FAIL", "evidence": ["logs/test.txt"]}
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires decision REJECTED", result.stderr)


class BoundaryReportTests(unittest.TestCase):
    def test_pass_requires_evidence(self):
        report = {
            "configuration_id": "case",
            "tests": [
                {"class": name, "status": "PASS", "evidence": [f"logs/{name}.txt"]}
                for name in (
                    "mount", "credential", "network", "command", "resource",
                    "supply-chain", "side-effect", "duplicate-execution", "cleanup"
                )
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = run_script("agent-boundary-adversary", "validate-adversarial-report.py", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["PASS"], 9)

    def test_pass_without_evidence_fails(self):
        report = {
            "configuration_id": "case",
            "tests": [
                {"class": name, "status": "PASS", "evidence": []}
                for name in (
                    "mount", "credential", "network", "command", "resource",
                    "supply-chain", "side-effect", "duplicate-execution", "cleanup"
                )
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = run_script("agent-boundary-adversary", "validate-adversarial-report.py", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PASS without evidence", result.stderr)


class GuardrailTests(unittest.TestCase):
    def test_verified_requires_positive_and_negative_evidence(self):
        template = SKILLS / "failure-to-guardrail" / "assets" / "guardrail-record.template.json"
        data = json.loads(template.read_text(encoding="utf-8"))
        data["failure_id"] = "case"
        data["status"] = "VERIFIED"
        data["evidence"] = ["logs/failure.txt"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = run_script("failure-to-guardrail", "validate-guardrail-record.py", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("negative and positive", result.stderr)


class HostIsolationTests(unittest.TestCase):
    def manifest(self):
        template = SKILLS / "agent-host-isolation" / "assets" / "isolation-manifest.template.json"
        data = json.loads(template.read_text(encoding="utf-8"))
        data["task_id"] = "case"
        data["resource_limits"]["cpu"] = "1"
        data["result_gate"]["audit_record"] = "audit/case.json"
        data["supply_chain"]["image_digest"] = "sha256:" + "0" * 64
        data["supply_chain"]["tool_commit"] = "na"
        return data

    def validate(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return run_script("agent-host-isolation", "validate-manifest.py", path)

    def test_manifest_passes(self):
        result = self.validate(self.manifest())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_writable_host_mount_fails(self):
        data = self.manifest()
        data["input_mounts"][0]["read_only"] = False
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Writable host mount", result.stderr)


class SupportingValidatorTests(unittest.TestCase):
    def test_safety_case_template_needs_task_id(self):
        source = SKILLS / "agent-safety-lifecycle" / "assets" / "agent-safety-case.template.md"
        result = run_script("agent-safety-lifecycle", "validate-safety-case.py", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder", result.stderr)

    def test_near_miss_template_structure(self):
        source = SKILLS / "agent-near-miss-review" / "assets" / "near-miss.template.md"
        result = run_script("agent-near-miss-review", "validate-near-miss.py", source)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_onboarding_pass_requires_evidence(self):
        source = SKILLS / "agent-safety-onboarding" / "assets" / "onboarding-progress.template.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        data["participant"] = "case"
        data["levels"][0]["status"] = "PASS"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = run_script("agent-safety-onboarding", "validate-onboarding-progress.py", path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PASS without evidence", result.stderr)


if __name__ == "__main__":
    unittest.main()
