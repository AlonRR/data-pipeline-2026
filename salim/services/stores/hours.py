"""Turning a locator's weekly schedule into ``branch_opening_hours`` rows.

The conversion is small but it sits on top of three weekday vocabularies that
do not agree:

- Yochananof's API numbers weekdays **0-based from Sunday**;
- ``enrichers/base.day_name`` numbers them **1-based from Sunday**, which is how
  Israeli sites count;
- ``branch_opening_hours.weekday`` is **ISO — Monday = 1 … Sunday = 7**.

Sunday is therefore the *first* day in two of them and the *last* in the third.
An off-by-one moves a branch's short Friday onto Saturday and still reads as a
plausible schedule, so nothing here does arithmetic on an index: a
``LocatorRecord.opening_hours`` dict is keyed by day *name*, and that name is
what gets mapped.
"""
from __future__ import annotations

import logging
from datetime import time

log = logging.getLogger("salim.stores.hours")

# The latest instant this column can hold; see the midnight note in intervals_for.
_END_OF_DAY = time(23, 59, 59)
# How the sources spell "end of day" as a closing time.
_END_OF_DAY_SPELLINGS = {"00:00", "24:00"}

# ISO 8601 weekday numbers, matching branch_opening_hours.weekday.
_ISO_WEEKDAY = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}


def iso_weekday(day_name: str) -> int:
    """Day name -> ISO weekday. Raises on anything unrecognized."""
    return _ISO_WEEKDAY[str(day_name).strip().lower()]


def to_clock_time(clock: str) -> time:
    """``"07:30"`` -> ``time(7, 30)``. Raises on anything else."""
    if not isinstance(clock, str):
        raise TypeError(f"expected a clock string, got {type(clock).__name__}")
    hours, _, minutes = clock.partition(":")
    if not hours or not minutes:
        raise ValueError(f"not a HH:MM clock: {clock!r}")
    return time(int(hours), int(minutes))


def intervals_for(opening_hours: dict | None) -> list[tuple[int, int, time, time]]:
    """Weekly schedule -> ``(weekday, interval_index, opens_at, closes_at)`` rows.

    A day the branch is shut yields **no row**, rather than a zero-length one:
    closed is the absence of an interval, and a 00:00-00:00 row reads as "open
    at midnight" to anything downstream.

    ``interval_index`` is always 0 here. The column exists for split shifts —
    a branch that closes midday and reopens — and none of the four locators
    publishes one today; the first that does will need this to emit two rows
    for that weekday rather than one.
    """
    if not opening_hours:
        return []

    intervals: list[tuple[int, int, time, time]] = []
    for day_name, window in opening_hours.items():
        if not isinstance(window, dict):
            continue  # None = closed that day; anything else is not a window
        start, end = window.get("from"), window.get("to")
        if not start or not end:
            # Half a window is not a window. Writing one side would imply a
            # closing time the source never gave.
            continue

        opens = to_clock_time(start)

        if str(end).strip() in _END_OF_DAY_SPELLINGS and start.strip() not in _END_OF_DAY_SPELLINGS:
            # "Open until midnight". Chains write it as both "00:00" and
            # "24:00" — one Rami Levi branch uses each, on different days of
            # the same week. "24:00" is not a valid time at all, and "00:00"
            # read literally sorts before every opening time, so both have to
            # be recognised before parsing rather than after. 23:59:59 is the
            # closest this column can hold; the one-second shortfall is not
            # worth a second column to represent exactly.
            closes = _END_OF_DAY
        else:
            closes = to_clock_time(end)

        if closes <= opens:
            # Genuinely inverted — two Rami Levi branches publish a Friday as
            # 13:30-06:30, from and to swapped at the source. Skip the day and
            # say so, rather than raising: one unusable day must not cost the
            # branch its other six.
            log.warning(
                "%s: closing time %s is not after opening time %s; skipping that day",
                day_name, end, start,
            )
            continue

        intervals.append((iso_weekday(day_name), 0, opens, closes))

    return intervals
