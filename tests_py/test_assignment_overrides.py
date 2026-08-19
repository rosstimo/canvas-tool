import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.assignment_overrides import capture_assignment_overrides


class FakeClient:
    def paginate(self, endpoint):
        self.endpoint = endpoint
        return [{
            "id": 900,
            "title": "Alice and Bob",
            "student_ids": [11111, 22222],
            "due_at": "2026-09-01T05:00:00Z",
            "unlock_at": None,
            "lock_at": None,
        }]


class AssignmentOverrideTests(unittest.TestCase):
    def test_specific_student_ids_and_names_are_not_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            (snapshot / "manifest.json").write_text(json.dumps({"course_id": "123"}), encoding="utf-8")
            (snapshot / "assignments.json").write_text(json.dumps([{
                "id": 456,
                "name": "Differentiated assignment",
                "has_overrides": True,
                "only_visible_to_overrides": True,
            }]), encoding="utf-8")

            client = FakeClient()
            result = capture_assignment_overrides(client, snapshot)

            self.assertEqual(client.endpoint, "/api/v1/courses/123/assignments/456/overrides")
            self.assertEqual(result[0]["items"][0]["target_type"], "specific_students")
            self.assertEqual(result[0]["items"][0]["title"], "Specific students")
            self.assertEqual(result[0]["items"][0]["student_count"], 2)

            text = (snapshot / "assignment-overrides.json").read_text(encoding="utf-8")
            self.assertNotIn("student_ids", text)
            self.assertNotIn("11111", text)
            self.assertNotIn("22222", text)
            self.assertNotIn("Alice", text)
            self.assertNotIn("Bob", text)


if __name__ == "__main__":
    unittest.main()
