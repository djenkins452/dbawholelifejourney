# ==============================================================================
# File: apps/faith/tests/test_biblical_calendar.py
# Description: Tests for biblical calendar date resolver
# Created: 2026-03-29
# ==============================================================================
"""
Tests for the biblical calendar raw data layer.

Validates:
- Easter computation (Anonymous Gregorian algorithm)
- Fixed-date matching (Christmas)
- Easter-relative matching (Palm Sunday, Good Friday, Easter)
- Return structure
- Non-significant days return None
"""

import datetime
from django.test import TestCase

from apps.faith.biblical_calendar import (
    compute_easter,
    get_biblical_day,
)


class ComputeEasterTests(TestCase):
    """Test the Anonymous Gregorian Easter algorithm."""

    def test_known_easter_dates(self):
        """Verify against known Easter dates 2026-2035."""
        known = {
            2026: datetime.date(2026, 4, 5),
            2027: datetime.date(2027, 3, 28),
            2028: datetime.date(2028, 4, 16),
            2029: datetime.date(2029, 4, 1),
            2030: datetime.date(2030, 4, 21),
            2031: datetime.date(2031, 4, 13),
            2032: datetime.date(2032, 3, 28),
            2033: datetime.date(2033, 4, 17),
            2034: datetime.date(2034, 4, 9),
            2035: datetime.date(2035, 3, 25),
        }
        for year, expected in known.items():
            with self.subTest(year=year):
                self.assertEqual(compute_easter(year), expected)

    def test_easter_2040(self):
        """Verify Easter 2040."""
        self.assertEqual(compute_easter(2040), datetime.date(2040, 4, 1))


class GetBiblicalDayTests(TestCase):
    """Test the biblical day resolver."""

    # ── Easter-relative days (2026: Easter = April 5) ──

    def test_easter_sunday_2026(self):
        result = get_biblical_day(datetime.date(2026, 4, 5))
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Easter Sunday')
        self.assertEqual(result['level'], 'defining')
        self.assertEqual(result['theme'], 'resurrection and conviction')
        self.assertEqual(result['scripture_reference'], 'Matthew 28:6')

    def test_good_friday_2026(self):
        result = get_biblical_day(datetime.date(2026, 4, 3))
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Good Friday')
        self.assertEqual(result['level'], 'defining')
        self.assertEqual(result['theme'], 'sacrifice and surrender')

    def test_palm_sunday_2026(self):
        result = get_biblical_day(datetime.date(2026, 3, 29))
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Palm Sunday')
        self.assertEqual(result['level'], 'highlighted')
        self.assertEqual(result['theme'], 'praise without alignment')

    # ── Fixed dates ──

    def test_christmas(self):
        result = get_biblical_day(datetime.date(2026, 12, 25))
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Christmas')
        self.assertEqual(result['level'], 'highlighted')
        self.assertEqual(result['theme'], 'incarnation and purpose')

    def test_christmas_different_year(self):
        result = get_biblical_day(datetime.date(2030, 12, 25))
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Christmas')

    # ── Non-significant days ──

    def test_ordinary_day_returns_none(self):
        self.assertIsNone(get_biblical_day(datetime.date(2026, 6, 15)))

    def test_day_before_easter_not_good_friday(self):
        """Easter Saturday (April 4, 2026) is NOT a significant day."""
        self.assertIsNone(get_biblical_day(datetime.date(2026, 4, 4)))

    def test_day_after_christmas_returns_none(self):
        self.assertIsNone(get_biblical_day(datetime.date(2026, 12, 26)))

    # ── Return structure ──

    def test_return_structure_contains_signal_ontology(self):
        result = get_biblical_day(datetime.date(2026, 4, 5))  # Easter
        self.assertIn('signal_ontology', result)
        self.assertEqual(result['signal_ontology']['event'], 'biblical_day_detected')
        self.assertEqual(result['signal_ontology']['influence'], 'faith_theme_active')

    def test_return_structure_keys(self):
        result = get_biblical_day(datetime.date(2026, 4, 5))  # Easter
        expected_keys = {'name', 'level', 'theme', 'scripture_reference', 'signal_ontology'}
        self.assertEqual(set(result.keys()), expected_keys)

    # ── Cross-year verification ──

    def test_easter_relative_days_track_year(self):
        """Palm Sunday should be 7 days before Easter regardless of year."""
        for year in (2027, 2028, 2029, 2030):
            easter = compute_easter(year)
            palm_sunday = easter - datetime.timedelta(days=7)
            with self.subTest(year=year):
                result = get_biblical_day(palm_sunday)
                self.assertIsNotNone(result, f"Palm Sunday not detected for {year}")
                self.assertEqual(result['name'], 'Palm Sunday')
