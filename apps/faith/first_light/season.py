"""Liturgical-season awareness — deterministic calendar facts only.

This never makes a spiritual claim. It reports where the Church calendar sits
relative to a date (Advent, Lent, Holy Week, Eastertide, Christmastide) or that
a season is approaching, so the companion can offer a gentle, honest note.
Pure functions of the date; no I/O.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (Anonymous Gregorian / Meeus algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = ((h + ll - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _advent_start(year: int) -> date:
    """First Sunday of Advent — the fourth Sunday before Christmas Day."""
    xmas = date(year, 12, 25)
    # Sunday on/before Christmas (weekday(): Mon=0 … Sun=6).
    sunday_on_or_before = xmas - timedelta(days=(xmas.weekday() + 1) % 7)
    return sunday_on_or_before - timedelta(days=21)


def season_note(today: date) -> Optional[str]:
    """A quiet, honest note about the Church season, or None in Ordinary Time.

    Examples: "Holy Week", "Lent · day 12", "Advent begins in 6 days",
    "Eastertide", "Christmastide". Always a calendar fact — never a claim about
    what God is doing.
    """
    e = _easter(today.year)
    ash_wednesday = e - timedelta(days=46)
    palm_sunday = e - timedelta(days=7)
    pentecost = e + timedelta(days=49)

    # ── Around Easter ──
    if palm_sunday <= today < e:
        return "Holy Week"
    if today == e:
        return "Easter"
    if e < today < pentecost:
        return "Eastertide"
    if ash_wednesday <= today < palm_sunday:
        return f"Lent · day {(today - ash_wednesday).days + 1}"
    if 0 < (ash_wednesday - today).days <= 14:
        return f"Lent begins in {(ash_wednesday - today).days} days"
    if 0 < (palm_sunday - today).days <= 14:
        return f"Holy Week begins in {(palm_sunday - today).days} days"

    # ── Advent / Christmas ──
    advent = _advent_start(today.year)
    xmas = date(today.year, 12, 25)
    if advent <= today < xmas:
        return "Advent"
    if 0 < (advent - today).days <= 14:
        return f"Advent begins in {(advent - today).days} days"
    # Christmastide spans the year boundary (Dec 25 – Jan 5).
    if (today.month == 12 and today.day >= 25) or (today.month == 1 and today.day <= 5):
        return "Christmastide"

    return None
