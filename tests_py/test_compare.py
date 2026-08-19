import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.compare import compare_snapshots


class CompareTests(unittest.TestCase):
    def test_compact_changed_areas(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, b = root / "a", root / "b"
            a.mkdir(); b.mkdir()
            (a / "manifest.json").write_text(json.dumps({"course_id":"1","course_name":"A","course_code":"A"}))
            (b / "manifest.json").write_text(json.dumps({"course_id":"2","course_name":"B","course_code":"B"}))
            (a / "normalized.json").write_text(json.dumps({"assignments":[{"name":"A"}],"pages":[]}))
            (b / "normalized.json").write_text(json.dumps({"assignments":[{"name":"A"},{"name":"B"}],"pages":[{"title":"P"}]}))
            summary, detail, changed = compare_snapshots(a, b, root)
            self.assertTrue(summary.is_file())
            self.assertTrue(detail.is_file())
            self.assertIn(("assignments", "1", "2"), changed)
            self.assertIn(("pages", "0", "1"), changed)
