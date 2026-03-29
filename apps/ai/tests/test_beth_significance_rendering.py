# ==============================================================================
# File: apps/ai/tests/test_beth_significance_rendering.py
# Description: Tests for biblical day significance tone shaping in Beth renderer
# Created: 2026-03-29
# ==============================================================================
"""
Tests for the day significance rendering layer in beth_checkin_renderer.

Validates:
- defining days override greeting and closing
- highlighted days weave into situation line
- baseline days produce no visible change
- faith_enabled=False suppresses all significance
"""

import datetime
from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.ai.beth_checkin_renderer import (
    _get_day_significance,
    _build_defining_day_opening,
    _build_highlighted_day_situation,
    _build_defining_day_closing,
)


class GetDaySignificanceTests(TestCase):
    """Test the _get_day_significance helper."""

    def _make_user(self, faith_enabled=True):
        user = MagicMock()
        user.preferences.faith_enabled = faith_enabled
        return user

    @patch('apps.faith.biblical_calendar.get_biblical_day')
    @patch('apps.core.utils.get_user_today')
    def test_returns_biblical_day_when_present(self, mock_today, mock_get):
        mock_today.return_value = datetime.date(2026, 4, 5)
        mock_get.return_value = {
            'name': 'Easter Sunday',
            'level': 'defining',
            'theme': 'resurrection and conviction',
            'scripture_reference': 'Matthew 28:6',
        }
        user = self._make_user()
        result = _get_day_significance(user)
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Easter Sunday')

    @patch('apps.faith.biblical_calendar.get_biblical_day')
    @patch('apps.core.utils.get_user_today')
    def test_returns_none_on_ordinary_day(self, mock_today, mock_get):
        mock_today.return_value = datetime.date(2026, 6, 15)
        mock_get.return_value = None
        user = self._make_user()
        self.assertIsNone(_get_day_significance(user))

    @patch('apps.faith.biblical_calendar.get_biblical_day')
    @patch('apps.core.utils.get_user_today')
    def test_returns_none_when_faith_disabled(self, mock_today, mock_get):
        mock_today.return_value = datetime.date(2026, 4, 5)
        mock_get.return_value = {
            'name': 'Easter Sunday',
            'level': 'defining',
            'theme': 'resurrection and conviction',
            'scripture_reference': 'Matthew 28:6',
        }
        user = self._make_user(faith_enabled=False)
        result = _get_day_significance(user)
        self.assertIsNone(result)
        # biblical_calendar should never be called
        mock_get.assert_not_called()

    def test_returns_none_on_exception(self):
        """Graceful failure — no crash if calendar unavailable."""
        user = MagicMock()
        user.preferences = None  # Will cause AttributeError
        result = _get_day_significance(user)
        self.assertIsNone(result)


class DefiningDayOpeningTests(TestCase):
    """Test the defining-day opening builder."""

    def test_easter_opening_with_name(self):
        sig = {'name': 'Easter Sunday', 'level': 'defining', 'theme': 'resurrection and conviction'}
        result = _build_defining_day_opening(sig, 'Danny', 7)
        self.assertIn('He is risen', result)
        self.assertIn('Danny', result)

    def test_easter_opening_without_name(self):
        sig = {'name': 'Easter Sunday', 'level': 'defining', 'theme': 'resurrection and conviction'}
        result = _build_defining_day_opening(sig, '', 7)
        self.assertIn('He is risen', result)
        self.assertNotIn(',', result.split('He is risen')[1][:2])

    def test_good_friday_opening(self):
        sig = {'name': 'Good Friday', 'level': 'defining', 'theme': 'sacrifice and surrender'}
        result = _build_defining_day_opening(sig, 'Danny', 7)
        self.assertIn('Good Friday', result)
        self.assertIn('not a day to rush', result)

    def test_unknown_defining_day_uses_fallback(self):
        sig = {'name': 'Ascension Day', 'level': 'defining', 'theme': 'exaltation'}
        result = _build_defining_day_opening(sig, '', 7)
        self.assertIn('Ascension Day', result)
        self.assertIn('defining day', result)


class HighlightedDaySituationTests(TestCase):
    """Test the highlighted-day situation weave."""

    def test_weaves_day_name_before_situation(self):
        sig = {'name': 'Palm Sunday', 'level': 'highlighted', 'theme': 'praise without alignment'}
        result = _build_highlighted_day_situation(sig, "You're on track.")
        self.assertEqual(result, "Today is Palm Sunday. You're on track.")

    def test_weaves_christmas(self):
        sig = {'name': 'Christmas', 'level': 'highlighted', 'theme': 'incarnation and purpose'}
        result = _build_highlighted_day_situation(sig, "Running a bit late — let's get focused.")
        self.assertTrue(result.startswith("Today is Christmas."))
        self.assertIn("Running a bit late", result)


class DefiningDayClosingTests(TestCase):
    """Test the defining-day closing builder."""

    def test_good_friday_closing(self):
        sig = {'name': 'Good Friday', 'level': 'defining', 'theme': 'sacrifice and surrender'}
        result = _build_defining_day_closing(sig)
        self.assertEqual(result, "Carry today with weight — not haste.")

    def test_easter_closing(self):
        sig = {'name': 'Easter Sunday', 'level': 'defining', 'theme': 'resurrection and conviction'}
        result = _build_defining_day_closing(sig)
        self.assertIn('conviction', result)

    def test_unknown_defining_day_uses_fallback(self):
        sig = {'name': 'Pentecost', 'level': 'defining', 'theme': 'empowerment'}
        result = _build_defining_day_closing(sig)
        self.assertEqual(result, "Let today's meaning shape how you move.")
