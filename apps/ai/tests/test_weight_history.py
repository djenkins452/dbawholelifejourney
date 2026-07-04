# ==============================================================================
# File: apps/ai/tests/test_weight_history.py
# Description: WI-4 — HISTORICAL WEIGHT RETRIEVAL (Weight Entity Completeness). Treat
#   Weight exactly like Sleep: current + yesterday already worked, specific historical
#   dates failed ("What was my weight on 7/1?"). Now any explicit/relative date reads
#   the canonical weight for THAT day, deterministically — never inferred.
# ==============================================================================
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.chatgpt_cos import weight_history as wh
from apps.health.models import WeightEntry
from apps.health.services.weight_queries import on_date

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"


class WeightHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="wt@test.com", password="x")
        self.user.preferences.timezone = "America/New_York"
        self.user.preferences.save()
        # distinct weights per day so we can assert WHICH day was retrieved
        self._mk(date(2026, 7, 1), Decimal("285.7"))
        self._mk(date(2026, 7, 3), Decimal("284.1"))
        self._mk(date(2026, 7, 4), Decimal("283.6"))

    def _mk(self, d, value):
        WeightEntry.objects.create(
            user=self.user, value=value, unit="lb",
            recorded_at=timezone.make_aware(datetime.combine(d, time(7, 0))))

    def _answer(self, msg):
        with mock.patch(_TODAY, return_value=TODAY):
            return wh.answer(self.user, msg)

    def test_explicit_date_retrieves_that_day(self):
        a = self._answer("What was my weight on 7/1?")
        self.assertEqual(a["lane"], "weight_history")
        self.assertEqual(a["weight_date"], "2026-07-01")
        self.assertIn("285.7", a["answer"])
        self.assertNotIn("283.6", a["answer"])        # not today

    def test_iso_and_yesterday_and_weekday(self):
        self.assertIn("284.1", self._answer("weight on 2026-07-03")["answer"])
        self.assertEqual(self._answer("what did I weigh yesterday")["weight_date"], "2026-07-03")
        # 7/4/2026 is Saturday → "last Wednesday" = 2026-07-01
        self.assertEqual(self._answer("my weight last Wednesday")["weight_date"], "2026-07-01")

    def test_on_date_matches_canonical(self):
        self.assertEqual(on_date(self.user, date(2026, 7, 1))["value_lb"], 285.7)

    def test_missing_day_is_honest(self):
        a = self._answer("what was my weight on 6/15")
        self.assertIn("don't have a weight reading", a["answer"].lower())
        for leak in ("285.7", "284.1", "283.6"):
            self.assertNotIn(leak, a["answer"])

    def test_current_weight_declined_to_existing_path(self):
        # No date reference → declines so the existing current-weight path answers.
        for msg in ("what's my weight", "how much do I weigh", "current weight"):
            self.assertIsNone(self._answer(msg), msg)

    def test_non_weight_question_declined(self):
        self.assertIsNone(self._answer("what did I sleep on 7/1"))
