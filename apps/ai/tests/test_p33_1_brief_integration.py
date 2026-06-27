# ==============================================================================
# File: apps/ai/tests/test_p33_1_brief_integration.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P33.1 Executive Brief INTEGRATION — the composer owns the final story.
#   Regression for the 4 live integration defects: (1) greeting not time-aware,
#   (2) interpreted workload contradicted by a later raw "22 pending tasks",
#   (3) a 6:45 AM item still framed "coming up" at 12:05 PM, (4) a routine task as
#   highest leverage without justification. Uses the EXACT production case.
# ==============================================================================
from datetime import datetime, timezone as _tz
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import executive_brief as eb
from apps.ai.chatgpt_cos import lanes

User = get_user_model()
_HZN = "apps.ai.chatgpt_cos.executive_interpretation._task_horizons"
_ES = "apps.ai.chatgpt_cos.executive_interpretation._exec_summary"
_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_NOW = "apps.core.utils.get_user_now"

# Noon — the production failure time. "Good morning" at 12:05 PM should not echo.
NOON = datetime(2026, 6, 27, 12, 5, tzinfo=_tz.utc)
# Rhythm items: a 6:45 AM item still OPEN (past), and a 2 PM item (future).
RHYTHM_ITEMS = [
    {"title": "Drink Protein Shake", "scheduled_time": "06:45"},   # PAST at noon
    {"title": "Workout", "scheduled_time": "14:00"},               # future
]
# executive_summary that (wrongly) carries a raw task-count attention item.
ES_WITH_RAW = {"needs_attention": [{"title": "22 pending tasks"},
                                   {"title": "review the budget"}],
               "recommendations": ["complete today's scheduled workout"],
               "biggest_risk": None}
PROD_HORIZONS = {"today": 1, "overdue": 0, "soon": 3, "backlog": 18, "total": 22}


class GreetingTimeAwarenessTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p331g@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def test_good_morning_at_noon_is_afternoon(self):
        with mock.patch(_NOW, return_value=NOON):
            # the user TYPED "good morning" but it is 12:05 PM
            self.assertEqual(lanes._greeting_word(self.u, "good morning"), "Good afternoon")

    def test_greeting_tracks_clock(self):
        bands = {6: "Good morning", 13: "Good afternoon", 19: "Good evening"}
        for hour, expected in bands.items():
            with mock.patch(_NOW, return_value=NOON.replace(hour=hour)):
                self.assertEqual(lanes._greeting_word(self.u, "hi"), expected)


class ComposerOwnsFinalStoryTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p331c@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def _brief(self):
        with mock.patch(_HZN, return_value=PROD_HORIZONS), \
             mock.patch(_ES, return_value=ES_WITH_RAW), \
             mock.patch("apps.ai.chatgpt_cos.executive_brief._safe_exec_summary",
                        return_value=ES_WITH_RAW), \
             mock.patch(_RHYTHM, return_value=RHYTHM_ITEMS), \
             mock.patch(_NOW, return_value=NOON):
            return eb.compose_executive_brief(self.u)

    def test_no_raw_workload_contradiction(self):
        # interpretation says "manageable"; the brief must NOT then echo "22 pending"
        brief = self._brief().lower()
        self.assertIn("manageable despite a healthy strategic backlog", brief)
        self.assertNotIn("22 pending tasks", brief)
        self.assertNotIn("pending tasks", brief)

    def test_past_item_not_framed_as_coming_up(self):
        brief = self._brief().lower()
        self.assertNotIn("coming up", brief)
        # the 6:45 AM (past) item is flagged as earlier, NOT upcoming
        self.assertIn("from earlier", brief)
        self.assertIn("still ahead", brief)
        # the future 2 PM item IS still ahead
        self.assertIn("workout", brief)

    def test_routine_task_not_unjustified_highest_leverage(self):
        brief = self._brief().lower()
        # a bare "complete today's scheduled workout" must not be the lever; strategic
        # focus or a justified statement wins.
        if "highest-leverage move:" in brief:
            lev = brief.split("highest-leverage move:")[1][:160]
            self.assertTrue(any(k in lev for k in (
                "leverage is today", "moving", "compounds", "keeps today's momentum")),
                f"unjustified routine leverage: {lev!r}")

    def test_integration_scorer_passes_clean_brief(self):
        j = eb.score_executive_judgment(self._brief())
        self.assertTrue(j["no_raw_workload"])
        self.assertTrue(j["no_past_as_coming_up"])
        self.assertGreaterEqual(j["score"], 0.8)


class IntegrationScorerTests(SimpleTestCase):
    def test_scorer_fails_on_raw_count_and_coming_up(self):
        bad = ("Today's workload is manageable. You're carrying 22 pending tasks. "
               "Coming up today you have Drink Protein Shake at 6:45 AM.")
        j = eb.score_executive_judgment(bad)
        self.assertFalse(j["no_raw_workload"])
        self.assertFalse(j["no_past_as_coming_up"])
