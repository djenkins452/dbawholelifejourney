# ==============================================================================
# File: apps/ai/tests/test_daily_agenda.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Daily Agenda synthesis + CoS no-deflection contract.
# ==============================================================================
"""
build_daily_agenda synthesizes from canonical engines only (P24), deterministic,
no OpenAI, and never deflects ("dashboard"/"area"/"ask me again").
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_REMAINING = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_CURRENT = "apps.core.cos_briefing.rhythm_api.get_current_rhythm_item"
_NEXT_ACTION = "apps.core.execution.selectors.get_next_action"
_EXEC_STATE = "apps.core.execution.execution_state.build_execution_state"
_RHYTHM = "apps.core.cos_briefing.rhythm.build_rhythm_sections"

_ITEMS = [
    {"title": "Prayer Time", "scheduled_time": "05:30", "completed_today": False},
    {"title": "Workout", "scheduled_time": "07:00", "completed_today": False},
]

_DEFLECTION = ("dashboard", "goals area", "faith area", "open your tasks",
               "ask me", "go to", "look at your", "check your", "visit the")


def _patches(overdue=0, at_risk=0):
    return [
        mock.patch(_REMAINING, return_value=_ITEMS),
        mock.patch(_CURRENT, return_value=_ITEMS[0]),
        mock.patch(_EXEC_STATE, return_value={}),
        mock.patch(_NEXT_ACTION, return_value={"primary_action": {"title": "Work on WLJ"}}),
        mock.patch(_RHYTHM, return_value={"totals": {"overdue": overdue, "at_risk": at_risk}}),
    ]


class DailyAgendaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="agenda@example.com", password="x")

    def _agenda(self, **kw):
        from apps.core.cos_briefing.daily_agenda import build_daily_agenda
        ps = _patches(**kw)
        for p in ps:
            p.start()
        try:
            return build_daily_agenda(self.user)
        finally:
            for p in ps:
                p.stop()

    def test_agenda_has_all_four_parts(self):
        with mock.patch(_CALL_API, side_effect=AssertionError("openai")):
            a = self._agenda()
        self.assertIn("Prayer Time", a)               # 1. upcoming
        self.assertIn("5:30 AM", a)                    # time formatted
        self.assertIn("Workout", a)
        self.assertIn("Work on WLJ", a)                # 2. highest priority (Focus Right Now)
        self.assertIn("on track", a.lower())           # 3. risks (none)
        self.assertIn("best next step", a.lower())     # 4. recommended next

    def test_agenda_reports_overdue_and_risk(self):
        a = self._agenda(overdue=2, at_risk=1)
        self.assertIn("2 overdue", a)
        self.assertIn("1 at risk", a)
        self.assertNotIn("on track", a.lower())

    def test_agenda_makes_no_openai_call(self):
        with mock.patch(_CALL_API, side_effect=AssertionError("no openai allowed")):
            a = self._agenda()
        self.assertTrue(a.strip())

    def test_agenda_has_no_deflection_or_implementation_language(self):
        a = self._agenda().lower()
        for phrase in _DEFLECTION:
            self.assertNotIn(phrase, a, f"deflection leaked: {phrase!r}")
        for impl in ("i looked at", "i checked", "your data indicates",
                     "the system says", "according to"):
            self.assertNotIn(impl, a, f"implementation detail leaked: {impl!r}")
