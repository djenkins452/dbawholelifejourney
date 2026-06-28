# ==============================================================================
# File: apps/health/tests/test_daily_health_queries.py
# Description: Batch 1 (Layer 1) — per-day Canonical Truth. The DailyHealthQueries
#   contract returns a SPECIFIC DAY's value (never a 7-day average), and the
#   foundational-fact path retrieves it deterministically with honest no-data.
#   Closes the dominant Layer-1 defect class (Architecture Laws 0/1/4).
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, SleepEntry, WeightEntry
from apps.health.services.daily_health_queries import DailyHealthQueries as Q
from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, format_fact_sentence,
)
from apps.ai.cos_services.health_facts import get_foundational_health_facts

User = get_user_model()


def _sleep(user, night_date, hours):
    mins = int(hours * 60)
    bed = timezone.now()
    return SleepEntry.objects.create(
        user=user, sleep_date=night_date, bedtime=bed,
        wake_time=bed + timedelta(minutes=mins),
        total_duration_minutes=mins, asleep_duration_minutes=mins)


class DailyHealthQueriesContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="dhq@test.com", password="x")
        cls.today = get_user_today(cls.user)
        cls.yest = cls.today - timedelta(days=1)
        StepsEntry.objects.create(user=cls.user, count=8123, logged_date=cls.yest)
        StepsEntry.objects.create(user=cls.user, count=4200, logged_date=cls.today)
        _sleep(cls.user, cls.yest, 7.2)
        WeightEntry.objects.create(user=cls.user, value=285, unit="lb",
                                   recorded_at=timezone.now() - timedelta(days=3))

    def test_steps_on_returns_specific_day_not_average(self):
        self.assertEqual(Q.steps_on(self.user, self.yest)["value"], 8123)
        self.assertEqual(Q.steps_on(self.user, self.today)["value"], 4200)  # NOT averaged

    def test_steps_no_data_is_honest(self):
        empty = User.objects.create_user(email="empty@test.com", password="x")
        self.assertEqual(Q.steps_on(empty, self.today)["status"], "no_data")

    def test_latest_sleep_is_actual_night(self):
        s = Q.latest_sleep(self.user)
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["value"], 7.2)              # the real night, not a 7d avg
        self.assertEqual(s["for_date"], self.yest.isoformat())

    def test_weight_on_is_as_of_most_recent(self):
        w = Q.weight_on(self.user, self.today)
        self.assertEqual(w["value"], 285.0)
        self.assertFalse(w["exact"])                   # logged 3 days ago → as-of, not exact


class FoundationalDayFactRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="dayfact@test.com", password="x")
        cls.today = get_user_today(cls.user)
        cls.yest = cls.today - timedelta(days=1)
        StepsEntry.objects.create(user=cls.user, count=8123, logged_date=cls.yest)
        StepsEntry.objects.create(user=cls.user, count=4200, logged_date=cls.today)
        _sleep(cls.user, cls.yest, 7.2)

    def test_classifier_routes_to_per_day_keys(self):
        self.assertEqual(classify_foundational_fact("How many steps did I get yesterday?"), "steps_yesterday")
        self.assertEqual(classify_foundational_fact("How many steps today?"), "steps_today")
        self.assertEqual(classify_foundational_fact("How did I sleep last night?"), "sleep_last_night")

    def test_retrieval_returns_specific_day_value(self):
        facts = get_foundational_health_facts(self.user, ["steps_yesterday", "steps_today", "sleep_last_night"])
        self.assertEqual(facts["steps_yesterday"]["value"], 8123)
        self.assertEqual(facts["steps_today"]["value"], 4200)
        self.assertEqual(facts["sleep_last_night"]["value"], 7.2)
        self.assertEqual(facts["steps_yesterday"]["source"], "DailyHealthQueries")

    def test_format_states_the_specific_day(self):
        facts = get_foundational_health_facts(self.user, ["steps_yesterday", "sleep_last_night"])
        self.assertEqual(format_fact_sentence("steps_yesterday", facts["steps_yesterday"]),
                         "You logged 8123 steps yesterday.")
        self.assertEqual(format_fact_sentence("sleep_last_night", facts["sleep_last_night"]),
                         "You slept 7.2 hours last night.")

    def test_no_data_answers_honestly_not_an_average(self):
        empty = User.objects.create_user(email="empty2@test.com", password="x")
        f = get_foundational_health_facts(empty, ["steps_yesterday"])["steps_yesterday"]
        self.assertEqual(f["status"], "unknown")
        self.assertIn("yesterday", format_fact_sentence("steps_yesterday", f).lower())
