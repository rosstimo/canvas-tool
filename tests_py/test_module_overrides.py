import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.module_overrides import capture_module_overrides


class FakeClient:
    def paginate(self, endpoint):
        if endpoint.endswith("/modules/10/assignment_overrides"):
            return [
                {"id": 1, "title": "Student Name", "student_ids": [111, 222]},
                {"id": 2, "title": "Section A", "course_section_id": 7},
            ]
        return []


class ModuleOverrideTests(unittest.TestCase):
    def test_specific_student_ids_are_not_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            (snapshot / "manifest.json").write_text(json.dumps({"course_id": "1"}), encoding="utf-8")
            (snapshot / "modules.json").write_text(json.dumps([
                {"id": 10, "name": "Module A", "position": 1},
            ]), encoding="utf-8")

            result = capture_module_overrides(FakeClient(), snapshot)
            raw_text = (snapshot / "module-overrides.json").read_text(encoding="utf-8")
            saved = json.loads(raw_text)

            self.assertEqual(len(result), 1)
            self.assertNotIn("111", raw_text)
            self.assertNotIn("222", raw_text)
            self.assertNotIn("Student Name", raw_text)
            self.assertEqual(saved[0]["items"][0]["title"], "Specific students")
            self.assertEqual(saved[0]["items"][0]["student_count"], 2)
            self.assertEqual(saved[0]["items"][1]["course_section_id"], 7)


if __name__ == "__main__":
    unittest.main()
