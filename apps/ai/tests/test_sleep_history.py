# ==============================================================================
# File: apps/ai/tests/test_sleep_history.py
# Description: WI-3 — HISTORICAL SLEEP RETRIEVAL (Sleep Entity Completeness). Sleep
#   must be queryable by point in time, deterministically. Origin: "What did I sleep
#   on 7/1?" and "the night before?" both returned last night. Retrieval now resolves
#   the requested night (explicit date, yesterday, night before last, last Monday, N
#   nights ago, arbitrary dates) and reads the canonical record for THAT night — never
#   inferring or substituting another night.
# ==============================================================================
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.chatgpt_cos import sleep_history as sh
from apps.health.models import SleepEntry
from apps.health.services.sleep_queries import on_date

User = get_user_model()
TODAY = date(2026, 7, 4)          # a Saturday
_TZ = "apps.core.utils.get_user_today"


class SleepHistoryRetrievalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sleephist@test.com", password="x")
        # One night per day, asleep minutes distinct per date so we can assert WHICH
        # night was retrieved: 7/1→288(4.8h) … 7/4→378(6.3h), plus 6/29 (last Monday).
        self._mk(date(2026, 6, 29), 300)      # Monday
        for i, d in enumerate([date(2026, 7, 1), date(2026, 7, 2),
                               date(2026, 7, 3), date(2026, 7, 4)]):
            self._mk(d, 288 + i * 30)

    def _mk(self, d, asleep):
        SleepEntry.objects.create(
            user=self.user, sleep_date=d, source="apple_health",
            sync_id=f"sleep-{d.isoformat()}", total_duration_minutes=asleep + 20,
            asleep_duration_minutes=asleep, quality_score=85,
            bedtime=timezone.make_aware(datetime.combine(d, time(22, 0)) - timedelta(days=1)),
            wake_time=timezone.make_aware(datetime.combine(d, time(6, 0))))

    def _resolve(self, msg):
        with mock.patch(_TZ, return_value=TODAY):
            return sh.resolve_night_date(self.user, msg)

    def _answer(self, msg):
        with mock.patch(_TZ, return_value=TODAY):
            return sh.answer(self.user, msg)

    # ── Date resolution (deterministic, by point in time) ──────────────────────
    def test_explicit_and_relative_resolution(self):
        cases = {
            "What did I sleep on 7/1?": date(2026, 7, 1),
            "How much did I sleep 2026-07-02?": date(2026, 7, 2),
            "What was my sleep on July 1?": date(2026, 7, 1),
            "How did I sleep yesterday?": date(2026, 7, 3),
            "What was my sleep the night before?": date(2026, 7, 3),
            "sleep night before last?": date(2026, 7, 3),
            "how much sleep two nights ago?": date(2026, 7, 2),
            "my sleep 3 nights ago": date(2026, 7, 1),
            "what did I sleep last Monday?": date(2026, 6, 29),
        }
        for msg, expected in cases.items():
            self.assertEqual(self._resolve(msg), expected, msg)

    def test_last_night_and_current_are_declined(self):
        # "last night" / no historical marker → None, so the existing current path answers.
        for msg in ("How did I sleep last night?", "How's my sleep?",
                    "What's my sleep been like?", "How did I sleep?"):
            self.assertIsNone(self._resolve(msg), msg)

    # ── Retrieval reads the canonical record for THAT night ────────────────────
    def test_retrieves_the_requested_night_not_last_night(self):
        a = self._answer("What did I sleep on 7/1?")
        self.assertEqual(a["lane"], "sleep_history")
        self.assertEqual(a["sleep_date"], "2026-07-01")
        self.assertIn("4.8 hours", a["answer"])       # 7/1 asleep 288m, NOT last night
        self.assertNotIn("6.3", a["answer"])          # last night (7/4) value must not leak

    def test_on_date_matches_canonical_truth(self):
        self.assertEqual(on_date(self.user, date(2026, 7, 1))["asleep_minutes"], 288)
        self.assertEqual(on_date(self.user, date(2026, 7, 3))["asleep_minutes"], 348)

    def test_missing_night_is_honest_never_inferred(self):
        a = self._answer("What did I sleep on 6/15?")   # no record that night
        self.assertEqual(a["lane"], "sleep_history")
        self.assertIn("don't have a sleep record", a["answer"].lower())
        # never substitutes another night's number
        for leak in ("4.8", "6.3", "5.8"):
            self.assertNotIn(leak, a["answer"])

    def test_non_sleep_question_declined(self):
        self.assertIsNone(self._answer("What did I weigh on 7/1?"))


class SleepHistoryRoutingTests(TestCase):
    """The production conversation, routed end-to-end."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="sleephistroute@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)
        for i, d in enumerate([date(2026, 7, 1), date(2026, 7, 3), date(2026, 7, 4)]):
            SleepEntry.objects.create(
                user=self.user, sleep_date=d, source="apple_health",
                sync_id=f"sleep-{d.isoformat()}", total_duration_minutes=300 + i * 40,
                asleep_duration_minutes=288 + i * 40, quality_score=85,
                bedtime=timezone.make_aware(datetime.combine(d, time(22, 0)) - timedelta(days=1)),
                wake_time=timezone.make_aware(datetime.combine(d, time(6, 0))))

    def test_historical_question_routes_to_sleep_history(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        with mock.patch(_TZ, return_value=TODAY), \
                mock.patch("apps.core.utils.get_user_now",
                           return_value=datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc)):
            out = route_message(self.user, "What did I sleep on 7/1?", self.conv)
        self.assertEqual(out["lane"], "sleep_history")
        self.assertEqual(out["sleep_date"], "2026-07-01")
