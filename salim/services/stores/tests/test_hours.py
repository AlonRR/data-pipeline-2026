"""Weekday and clock conversion for `branch_opening_hours`.

Three weekday vocabularies meet here and none of them agree:

- Yochananof's API is **0-based, Sunday = 0**
- `enrichers/base.day_name()` is **1-based, Sunday = 1** (how Israeli sites count)
- `branch_opening_hours.weekday` is **ISO: Monday = 1 … Sunday = 7**

An off-by-one between any two of them moves a branch's short Friday onto
Saturday and still reads as a plausible schedule, so the conversion is done
from the day *name* rather than by arithmetic on an index — and that is what
these tests pin.
"""
from __future__ import annotations

import unittest
from datetime import time

from hours import intervals_for, iso_weekday, to_clock_time


class WeekdayTests(unittest.TestCase):
    def test_sunday_is_seven_not_one(self):
        """The whole point: Sunday is the *first* day locally and the *last*
        day in ISO. Getting this backwards shifts the entire week."""
        self.assertEqual(iso_weekday("sunday"), 7)

    def test_monday_is_one(self):
        self.assertEqual(iso_weekday("monday"), 1)

    def test_friday_and_saturday_land_where_iso_puts_them(self):
        self.assertEqual(iso_weekday("friday"), 5)
        self.assertEqual(iso_weekday("saturday"), 6)

    def test_unknown_day_raises_rather_than_defaulting(self):
        with self.assertRaises(KeyError):
            iso_weekday("someday")


class ClockTests(unittest.TestCase):
    def test_parses_a_clock_string(self):
        self.assertEqual(to_clock_time("07:30"), time(7, 30))

    def test_midnight_is_valid_not_falsy(self):
        """`time(0, 0)` is falsy in Python; a truthiness check would drop a
        branch that opens at midnight."""
        self.assertEqual(to_clock_time("00:00"), time(0, 0))

    def test_rejects_a_non_clock(self):
        for bad in ("", "7:30pm", "0730", None):
            with self.assertRaises((ValueError, TypeError)):
                to_clock_time(bad)


class IntervalTests(unittest.TestCase):
    def test_builds_one_interval_per_open_day(self):
        hours = {
            "sunday": {"from": "07:30", "to": "21:00"},
            "friday": {"from": "06:00", "to": "13:30"},
        }
        self.assertEqual(
            sorted(intervals_for(hours)),
            [(5, 0, time(6, 0), time(13, 30)), (7, 0, time(7, 30), time(21, 0))],
        )

    def test_a_closed_day_produces_no_row_at_all(self):
        """Closed is the absence of an interval, not a zero-length one. A
        00:00-00:00 row would read as "open at midnight" to any consumer."""
        self.assertEqual(intervals_for({"saturday": None}), [])

    def test_a_day_that_is_simply_absent_produces_no_row(self):
        self.assertEqual(intervals_for({}), [])

    def test_no_hours_at_all_is_empty_not_an_error(self):
        self.assertEqual(intervals_for(None), [])

    def test_closing_at_midnight_means_end_of_day_not_start(self):
        """`08:00-00:00` is a supermarket open until midnight, not a zero-width
        window. Rami Levi publishes these; read literally, `00:00` sorts before
        every opening time and the day is silently dropped."""
        self.assertEqual(
            intervals_for({"wednesday": {"from": "08:00", "to": "00:00"}}),
            [(3, 0, time(8, 0), time(23, 59, 59))],
        )

    def test_twenty_four_hundred_is_the_other_spelling_of_end_of_day(self):
        """Chains write end-of-day as both `00:00` and `24:00`, sometimes in
        the same branch: one Rami Levi record closes Wednesday at `00:00` and
        Thursday at `24:00`. `24:00` is not a valid `time`, so parsing it
        before recognising it raises "hour must be in 0..23"."""
        self.assertEqual(
            intervals_for({"thursday": {"from": "07:30", "to": "24:00"}}),
            [(4, 0, time(7, 30), time(23, 59, 59))],
        )

    def test_an_inverted_window_is_skipped_without_losing_the_other_days(self):
        """Two Rami Levi branches publish a Friday as `13:30-06:30` — from and
        to swapped at the source. That day cannot be stored, but it must not
        cost the branch its other six: one bad day is not a bad branch."""
        rows = intervals_for({
            "friday": {"from": "13:30", "to": "06:30"},
            "sunday": {"from": "07:00", "to": "22:00"},
        })
        self.assertEqual(rows, [(7, 0, time(7, 0), time(22, 0))])

    def test_an_incomplete_window_is_skipped_not_half_written(self):
        self.assertEqual(intervals_for({"monday": {"from": "09:00", "to": None}}), [])
