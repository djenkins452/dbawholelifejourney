# ==============================================================================
# File: apps/core/tests/test_executive_briefing_engine.py
# Description: Executive Briefing Engine (apps/core/truth/briefing.py). The
#   deterministic cross-domain composer that decides what matters BEFORE Beth speaks:
#   enumerates all truth domains, ranks clinical-safety-first, flags stale. Origin:
#   real Beth conversation (focused on sleep, ignored a dangerous glucose).
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.truth.briefing import (
    build_executive_briefing, narrate_briefing, ACUTE,
)
from apps.core.utils import get_user_today
from apps.health.models import GlucoseEntry, SleepEntry, StepsEntry, WeightEntry

User = get_user_model()


def _sleep(user, night_date, hours):
    mins = int(hours * 60)
    bed = timezone.now()
    SleepEntry.objects.create(user=user, sleep_date=night_date, bedtime=bed,
                              wake_time=bed + timedelta(minutes=mins),
                              total_duration_minutes=mins, asleep_duration_minutes=mins)


class ExecutiveBriefingEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="brief@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)
        # A dangerous glucose yesterday, a STALE sleep (only an old night), normal-ish
        # steps today, a recent weight. Five health facets — like the real conversation.
        GlucoseEntry.objects.create(user=self.user, value=43, unit="mg/dL",
                                    recorded_at=timezone.now() - timedelta(days=1))
        _sleep(self.user, self.today - timedelta(days=5), 6.5)   # stale: nothing for last night
        StepsEntry.objects.create(user=self.user, count=8200, logged_date=self.today)
        WeightEntry.objects.create(user=self.user, value=285, unit="lb",
                                   recorded_at=timezone.now() - timedelta(days=1))

    def test_clinical_danger_ranks_first(self):
        b = build_executive_briefing(self.user)
        head = b.headline()
        self.assertEqual(head.tier, ACUTE)
        self.assertIn("glucose", head.metric)
        self.assertEqual(head.value, 43)
        self.assertIn("dangerously low", head.note.lower())

    def test_enumerates_multiple_domains_not_one(self):
        b = build_executive_briefing(self.user)
        metrics = {i.metric for i in b.items}
        # weight, sleep, steps, glucose all considered — synthesis, not sleep-only.
        self.assertTrue({"glucose_yesterday", "sleep_last_night", "steps_today",
                         "weight_yesterday"} <= metrics)
        self.assertIn("health", b.domains_contributing())

    def test_stale_is_flagged_not_silently_dropped(self):
        b = build_executive_briefing(self.user)
        attention_metrics = {i.metric for i in b.attention()}
        self.assertIn("sleep_last_night", attention_metrics)   # stale sleep surfaced

    def test_narration_reads_like_an_executive_briefing(self):
        text = narrate_briefing(build_executive_briefing(self.user))
        self.assertTrue(text.startswith("Top priority"))   # leads with what matters most
        self.assertIn("⚠", text)
        self.assertIn("43", text)
        self.assertIn("On track:", text)                   # executive structure
        for word in ("good range", "healthy", "in range"):
            self.assertNotIn(word, text.lower())
