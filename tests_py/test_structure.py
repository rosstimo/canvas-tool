import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.structure import audit_week_structure, declared_week_number


class StructureAuditTests(unittest.TestCase):
    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_declared_week_number_is_deliberately_narrow(self):
        self.assertEqual(declared_week_number("W07 - Shuffle The Deck"), 7)
        self.assertEqual(declared_week_number("W5"), 5)
        self.assertEqual(declared_week_number("Week 12: Math Contest"), 12)
        self.assertIsNone(declared_week_number("Chapter 7 Review"))
        self.assertIsNone(declared_week_number("Wavelength Lab"))

    def test_flags_empty_duplicate_mismatch_and_missing_week_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot / "modules.json", [
                {"id": 1, "name": "W05", "position": 1},
                {"id": 2, "name": "W08", "position": 2},
                {"id": 3, "name": "W5", "position": 3},
            ])
            self.write_json(snapshot / "module-items.json", [
                {
                    "source_id": "1",
                    "title": "W05",
                    "items": [{"id": 10, "type": "Assignment", "title": "W05 - Good"}],
                },
                {
                    "source_id": "2",
                    "title": "W08",
                    "items": [],
                },
                {
                    "source_id": "3",
                    "title": "W5",
                    "items": [{"id": 30, "type": "Assignment", "title": "W15 - StansGrocery"}],
                },
            ])

            report = audit_week_structure(snapshot)
            codes = [item["code"] for item in report["issues"]]

            self.assertIn("empty_week_module", codes)
            self.assertIn("duplicate_week_module", codes)
            self.assertIn("assignment_module_week_mismatch", codes)
            self.assertIn("missing_week_module", codes)
            self.assertEqual(report["summary"]["week_modules"], 3)
            self.assertEqual(report["summary"]["issues"], 4)


if __name__ == "__main__":
    unittest.main()
