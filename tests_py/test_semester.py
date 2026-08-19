import unittest
from datetime import date

from canvas_tool.semester import build_semester_days, build_semester_weeks, render_day_text, week_for_date


class SemesterTests(unittest.TestCase):
    def test_break_week_is_visible_but_does_not_consume_week_number(self):
        breaks = [
            {"name": "Thanksgiving Break", "start": "2026-11-23", "end": "2026-11-27"}
        ]
        weeks = build_semester_weeks(date(2026, 8, 24), date(2026, 12, 18), breaks)

        before = week_for_date(weeks, date(2026, 11, 16))
        break_week = week_for_date(weeks, date(2026, 11, 23))
        after = week_for_date(weeks, date(2026, 11, 30))
        finals = week_for_date(weeks, date(2026, 12, 14))

        self.assertEqual(before.week_number, 13)
        self.assertIsNone(break_week.week_number)
        self.assertEqual(break_week.label, "Thanksgiving Break")
        self.assertEqual(after.week_number, 14)
        self.assertEqual(finals.week_number, 16)

    def test_daily_view_has_week_day_date_and_blank_week_during_break(self):
        breaks = [
            {"name": "Thanksgiving Break", "start": "2026-11-23", "end": "2026-11-27"}
        ]
        holidays = [
            {"name": "Labor Day holiday", "start": "2026-09-07", "end": "2026-09-07"}
        ]
        days = build_semester_days(
            date(2026, 8, 24),
            date(2026, 12, 18),
            break_weeks=breaks,
            holidays=holidays,
        )

        first = next(item for item in days if item.day == date(2026, 8, 24))
        labor_day = next(item for item in days if item.day == date(2026, 9, 7))
        thanksgiving = next(item for item in days if item.day == date(2026, 11, 23))
        after = next(item for item in days if item.day == date(2026, 11, 30))

        self.assertEqual((first.week_number, first.day.strftime("%A")), (1, "Monday"))
        self.assertEqual(labor_day.week_number, 3)
        self.assertIn("Labor Day holiday", labor_day.notes)
        self.assertIsNone(thanksgiving.week_number)
        self.assertIn("Thanksgiving Break", thanksgiving.notes)
        self.assertEqual(after.week_number, 14)

        text = render_day_text(days)
        self.assertIn("WEEK  DAY", text)
        self.assertIn("Monday      August 24, 2026", text)
        self.assertIn("November 23, 2026     Thanksgiving Break", text)


if __name__ == "__main__":
    unittest.main()
