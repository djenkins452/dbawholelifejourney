# ==============================================================================
# File: apps/health/tests/test_daily_health_freshness.py
# Description: Batch 3 (Layer 1) — Freshness. Every per-day Current Truth carries a
#   READ verdict (current/stale/pending/partial/missing); phrasing honors it (Law 1).
#   Beth never infers freshness — she reads it. No OpenAI.
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, SleepEntry
from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
from apps.ai.cos_services.health_facts import get_foundational_health_facts

User = get_user_model()


def _sleep(user, night_date, hours):
    mins = int(hours * 60)
    bed = timezone.now()
    SleepEntry.objects.create(
        user=user, sleep_date=night_date, bedtime=bed,
        wake_time=bed + timedelta(minutes=mins),
        total_duration_minutes=mins, asleep_duration_minutes=mins)


class FreshnessVerdictTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="fresh@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)

    def _fact(self, key):
        return get_foundational_health_facts(self.user, [key])[key]

    def test_current_cites_the_value(self):
        _sleep(self.user, self.yest, 7.2)
        f = self._fact("sleep_last_night")
        self.assertEqual(f["freshness"], "current")
        self.assertIn("7.2", format_fact_sentence("sleep_last_night", f))

    def test_stale_says_from_an_older_date(self):
        _sleep(self.user, self.today - timedelta(days=4), 6.5)   # nothing for last night
        f = self._fact("sleep_last_night")
        self.assertEqual(f["freshness"], "stale")
        s = format_fact_sentence("sleep_last_night", f).lower()
        self.assertTrue(any(m in s for m in ("from", "as of", "older", "don't have")))

    def test_missing_is_honest_absence(self):
        f = self._fact("sleep_last_night")                      # no sleep at all
        self.assertEqual(f.get("freshness"), "missing")
        self.assertIn("don't have", format_fact_sentence("sleep_last_night", f).lower())

    def test_partial_says_so_far_for_today(self):
        StepsEntry.objects.create(user=self.user, count=3100, logged_date=self.today)
        f = self._fact("steps_today")
        self.assertEqual(f["freshness"], "partial")
        self.assertIn("so far", format_fact_sentence("steps_today", f).lower())

    def test_pending_is_honest_absence_for_today(self):
        f = self._fact("steps_today")                           # nothing logged yet today
        self.assertEqual(f.get("freshness"), "pending")
        self.assertIn("don't have", format_fact_sentence("steps_today", f).lower())

    def test_yesterday_complete_day_is_current(self):
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        f = self._fact("steps_yesterday")
        self.assertEqual(f["freshness"], "current")
