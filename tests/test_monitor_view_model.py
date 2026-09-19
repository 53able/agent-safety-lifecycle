import json
import unittest
from dataclasses import replace

from tools.safety_monitor.projection import RunProjection, TimelineEntry
from tools.safety_monitor.view_model import (
    FRAME_LIMIT,
    SCHEMA,
    MonitorViewModel,
    ViewModelError,
    from_projection,
    serialize_jsonl,
)


class MonitorViewModelTests(unittest.TestCase):
    def projection(self, value="safe"):
        return RunProjection(
            task_id=value,
            run_id="run-1",
            run_state="RUNNING",
            last_sequence=1,
            timeline=(TimelineEntry(1, "RUN_CREATED", value, "validator", "PLANNED"),),
            warnings=(value,),
        )

    def test_mapping_is_immutable_bounded_and_has_honest_availability(self):
        projection = replace(
            self.projection(),
            timeline=tuple(TimelineEntry(i, "EVENT", str(i), "validator", "RUNNING") for i in range(1, 103)),
        )
        model = from_projection(projection)
        self.assertEqual(model.schema, SCHEMA)
        self.assertEqual(model.last_sequence, 1)
        self.assertEqual(len(model.timeline), 100)
        self.assertEqual(model.timeline[0].sequence, 3)
        self.assertEqual(model.capabilities.status, "UNAVAILABLE")
        self.assertEqual(model.result_gate.status, "UNAVAILABLE")
        with self.assertRaises((AttributeError, TypeError)):
            model.run_state = "FAILED"

    def test_jsonl_is_deterministic_single_line_and_sanitized_after_parse(self):
        malicious = "x\x1b\x00\x9b\n\r\u202e\u2066\ufeffy"
        model = from_projection(self.projection(malicious))
        first = serialize_jsonl(model)
        self.assertEqual(first, serialize_jsonl(model))
        self.assertEqual(first.count("\n"), 1)
        parsed = json.loads(first)

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for item in value.values():
                    yield from strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)

        for value in strings(parsed):
            for char in value:
                point = ord(char)
                self.assertFalse(point == 0x1B or point < 0x20 or 0x7F <= point <= 0x9F)
                self.assertNotIn(point, {0x202E, 0x2066, 0xFEFF})
        self.assertIn("\\u001b", parsed["task_id"])
        self.assertIn("\\n", parsed["task_id"])

    def test_oversized_frame_fails_closed(self):
        base = from_projection(self.projection())
        oversized = replace(base, warnings=("x" * FRAME_LIMIT,))
        with self.assertRaises(ViewModelError):
            serialize_jsonl(oversized)

    def test_frame_at_normal_size_is_below_limit(self):
        self.assertLessEqual(len(serialize_jsonl(from_projection(self.projection())).encode()), FRAME_LIMIT)


if __name__ == "__main__":
    unittest.main()
