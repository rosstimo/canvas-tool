import unittest

from canvas_tool.course import CourseTargetError, resolve_course


class CourseTargetTests(unittest.TestCase):
    BASE = "https://isu.instructure.com"

    def test_numeric(self):
        self.assertEqual(resolve_course("17600", self.BASE).course_id, "17600")

    def test_full_url(self):
        result = resolve_course("https://isu.instructure.com/courses/17600/modules", self.BASE)
        self.assertEqual(result.course_id, "17600")

    def test_schemeless_url(self):
        result = resolve_course("isu.instructure.com/courses/17600", self.BASE)
        self.assertEqual(result.base_url, self.BASE)

    def test_foreign_origin_rejected(self):
        with self.assertRaises(CourseTargetError):
            resolve_course("https://evil.example/courses/17600", self.BASE)
