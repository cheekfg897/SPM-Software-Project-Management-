"""Weekly opening-hours arithmetic for the venue module (ADR-0008).

Pure functions, no database or Flask. A period is placed on a one-week
timeline measured in minutes from Monday 00:00. A period that closes the day
after it opens simply extends past midnight; one that runs from Sunday into
Monday extends past the end of the week and wraps back to the start.

Kept separate from the schema so later venue-availability work can reuse the
same timeline instead of re-deriving it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import time
from typing import NamedTuple

MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY


class Period(NamedTuple):
    """An opening period as day numbers (Monday = 0) and clock times."""

    open_day: int
    open_time: time
    close_day: int
    close_time: time


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def period_error(period: Period) -> str | None:
    """Return why ``period`` is not a valid opening period, or ``None`` if it is.

    Rules:

    * ``close_day`` is ``open_day`` or the day after (Sunday → Monday wraps).
    * Same day: the close time must be after the open time.
    * Next day: the close time must be at or before the open time, so a
      period is never longer than 24 hours. Monday 00:00 → Tuesday 00:00 is
      "open all day Monday".
    """
    day_gap = (period.close_day - period.open_day) % 7
    opens, closes = _minutes(period.open_time), _minutes(period.close_time)
    if day_gap == 0:
        if closes <= opens:
            return (
                "Close time must be after open time. For hours past midnight, "
                "set the close day to the next day."
            )
        return None
    if day_gap == 1:
        if closes > opens:
            return "An opening period cannot be longer than 24 hours."
        return None
    return "Close day must be the same day as the open day or the day after."


def week_interval(period: Period) -> tuple[int, int]:
    """``(start, end)`` minutes from Monday 00:00; ``end`` may pass the week's end.

    Assumes ``period`` is valid (see :func:`period_error`).
    """
    day_start = period.open_day * MINUTES_PER_DAY
    day_gap = (period.close_day - period.open_day) % 7
    start = day_start + _minutes(period.open_time)
    end = day_start + day_gap * MINUTES_PER_DAY + _minutes(period.close_time)
    return start, end


def find_overlap(periods: Sequence[Period]) -> tuple[int, int] | None:
    """Return the indexes of two overlapping periods, or ``None`` if none overlap.

    Periods that only touch (one closes at 12:00, the next opens at 12:00)
    do not overlap. Assumes every period is valid.
    """
    pieces: list[tuple[int, int, int]] = []
    for index, period in enumerate(periods):
        start, end = week_interval(period)
        if end > MINUTES_PER_WEEK:  # Sunday into Monday: split at the week boundary
            pieces.append((start, MINUTES_PER_WEEK, index))
            pieces.append((0, end - MINUTES_PER_WEEK, index))
        else:
            pieces.append((start, end, index))

    pieces.sort()
    furthest_end, furthest_index = -1, -1
    for start, end, index in pieces:
        if start < furthest_end:
            return tuple(sorted((furthest_index, index)))  # type: ignore[return-value]
        # Sorted by start, a piece that doesn't overlap starts at or after
        # furthest_end, and every piece has positive length, so it ends later.
        furthest_end, furthest_index = end, index
    return None
