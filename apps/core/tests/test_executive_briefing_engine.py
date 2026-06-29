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
    build_executive_briefing, narrate_briefing, ACUTE, ATTENTION, NORMAL,
    BriefingItem, ExecutiveBriefing, _significance,
)
from django.test import SimpleTestCase
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


class SignificancePrioritizationTests(SimpleTestCase):
    """Prioritization is by SIGNIFICANCE, not domain identity. A world-class CoS leads
    with danger, then time-critical, then magnitude — regardless of domain name."""

    def _item(self, domain, metric, value, tier, note=""):
        return BriefingItem(domain, metric, True, value, "", "current", "high", "",
                            tier, note)

    def test_clinical_outranks_alphabetically_earlier_domain(self):
        # faith ('unanswered_prayers') sorts first alphabetically; a HIGH glucose must
        # still lead because clinical significance beats domain name.
        items = [
            self._item("faith", "unanswered_prayers", 3, ATTENTION, "3 need attention"),
            self._item("health", "glucose_yesterday", 210, ATTENTION, "High"),
            self._item("tasks", "overdue_count", 9, ATTENTION, "9 need attention"),
        ]
        ordered = sorted(items, key=lambda i: (-_significance(i), i.domain))
        self.assertEqual(ordered[0].metric, "glucose_yesterday")   # clinical leads
        self.assertEqual(ordered[1].metric, "overdue_count")       # time-critical next
        self.assertEqual(ordered[2].metric, "unanswered_prayers")  # then magnitude

    def test_acute_always_leads_over_any_attention(self):
        acute = self._item("health", "glucose_yesterday", 43, ACUTE, "danger")
        attn = self._item("calendar", "today_event_count", 5, ATTENTION)
        self.assertGreater(_significance(acute), _significance(attn))

    def test_domain_only_breaks_ties_never_decides_priority(self):
        # Two equal-significance NORMAL items: domain is a stable tiebreak only.
        a = self._item("relationships", "birthdays_today", 0, NORMAL)
        b = self._item("calendar", "today_event_count", 2, NORMAL)
        self.assertEqual(_significance(a), _significance(b))
