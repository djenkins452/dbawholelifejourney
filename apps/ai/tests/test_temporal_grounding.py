# ==============================================================================
# File: apps/ai/tests/test_temporal_grounding.py
# Description: Temporal Grounding & Data Freshness Awareness. A CoS making
#   time-relative statements ("last night", "today") must ground them in
#   deterministic temporal truth and, when the data is CHALLENGED, enter
#   trust-verification instead of failing. Regression from the reported failure:
#   Beth said "about 4.8 hours of sleep last night", then couldn't say which
#   night, what date/time it is, or whether the data was stale. Natural
#   multi-turn conversations. No OpenAI (deterministic).
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.utils import get_user_today
from apps.ai.chatgpt_cos import temporal_grounding as tg
from apps.ai.chatgpt_cos.lanes import route_message

User = get_user_model()


class FakeConversation:
    def __init__(self, metadata=None):
        self.metadata = dict(metadata or {})

    def save(self, update_fields=None):
        pass


def _mock_general(system, message, **kw):
    return f"[GENERAL] {message}"


class _TemporalBase(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email="temporal@test.com", password="pw12345!")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.timezone = "America/New_York"     # timezone_iana derives from this
        prefs.save()
        self.today = get_user_today(self.user)


# ── Current date / time / timezone awareness ───────────────────────────────

class CurrentDateTimeTests(_TemporalBase):
    def test_answer_current_date(self):
        r = tg.answer_datetime(self.user, "What date is today?")
        self.assertIsNotNone(r)
        self.assertEqual(r["lane"], "temporal")
        self.assertIn(str(self.today.year), r["answer"])
        self.assertIn(self.today.strftime("%A"), r["answer"])   # weekday named

    def test_answer_current_time_and_timezone(self):
        timer = tg.answer_datetime(self.user, "what time is it?")
        self.assertIsNotNone(timer)
        self.assertEqual(timer["lane"], "temporal")
        self.assertTrue(("AM" in timer["answer"]) or ("PM" in timer["answer"]))
        tzr = tg.answer_datetime(self.user, "what's my timezone?")
        self.assertIn("New_York", tzr["answer"])

    def test_non_datetime_declines(self):
        self.assertIsNone(tg.answer_datetime(self.user, "how did I sleep?"))


# ── Never mislabel a window (the core grounding rule) ──────────────────────

class SleepGroundingTests(_TemporalBase):
    def test_genuine_last_night_is_grounded(self):
        y = (self.today - timedelta(days=1)).isoformat()
        s, strong, fact = tg.sleep_last_night_grounded(
            self.user, {"sleep_last_night_hours": 4.8, "last_sleep_entry": y})
        self.assertIn("last night", s.lower())
        self.assertTrue(strong)                              # 4.8 < 6.5
        self.assertEqual(fact["window"], "last night")
        self.assertEqual(fact["freshness"], "current")
        self.assertEqual(fact["for_date"], y)

    def test_seven_day_average_is_NOT_labelled_last_night(self):
        # THE reported failure: an average presented as "last night".
        s, strong, fact = tg.sleep_last_night_grounded(
            self.user, {"sleep_avg_hours_7d": 4.8, "sleep_entries_7d": 6,
                        "last_sleep_entry": (self.today - timedelta(days=1)).isoformat()})
        # Never CLAIMS the average as last night's number (the disclaimer may
        # honestly say it does NOT have last night).
        self.assertNotIn("hours of sleep last night", s.lower())
        self.assertIn("average", s.lower())
        self.assertTrue(fact["aggregate"])

    def test_stale_record_is_not_called_last_night(self):
        old = (self.today - timedelta(days=5)).isoformat()
        s, strong, fact = tg.sleep_last_night_grounded(
            self.user, {"sleep_last_night_hours": 4.8, "last_sleep_entry": old})
        self.assertIn("most recent recorded night", s.lower())
        self.assertNotIn("got about 4.8 hours of sleep last night", s.lower())
        self.assertEqual(fact["freshness"], "stale")

    def test_no_sleep_data_yields_nothing(self):
        s, strong, fact = tg.sleep_last_night_grounded(self.user, {})
        self.assertIsNone(s)
        self.assertIsNone(fact)


# ── Trust-Verification mode ────────────────────────────────────────────────

class TrustVerificationTests(_TemporalBase):
    def _avg_last(self):
        return {"lane": "conversation_checkin", "fact_key": "sleep_last_night",
                "fact": {"key": "sleep_last_night", "value": 4.8, "unit": "hours",
                         "aggregate": True, "window": "7-night average",
                         "for_date": (self.today - timedelta(days=1)).isoformat(),
                         "freshness": "current"}}

    def test_challenge_detection(self):
        for m in ("What date are you calling last night?", "I think your data is stale.",
                  "How old is the data you're using?", "When was this synchronized?",
                  "Are you sure you're looking at today's information?",
                  "Which sleep record are you referring to?"):
            self.assertTrue(tg.is_temporal_trust_challenge(m), m)
        self.assertFalse(tg.is_temporal_trust_challenge("how did I sleep?"))

    def test_verify_average_clarifies_it_is_not_last_night(self):
        r = tg.verify_temporal_trust(
            self.user, self._avg_last(), "What date are you calling last night?")
        self.assertIsNotNone(r)
        self.assertEqual(r["lane"], "temporal")
        self.assertIn("average", r["answer"].lower())
        self.assertIn("not last night", r["answer"].lower())

    def test_verify_stale_challenge_preserves_trust(self):
        r = tg.verify_temporal_trust(self.user, self._avg_last(),
                                     "I think your data is stale.")
        self.assertIsNotNone(r)
        self.assertTrue(len(r["answer"]) > 0)

    def test_verify_declines_when_no_temporal_fact(self):
        # A non-time-relative last answer → nothing to verify (route on).
        last = {"lane": "general_conversation", "answer": "Jezebel was a queen."}
        self.assertIsNone(tg.verify_temporal_trust(self.user, last, "is that stale?"))


# ── End-to-end — natural multi-turn conversations through the router ───────

class TemporalGroundingE2ETests(_TemporalBase):
    def setUp(self):
        super().setUp()
        self.conv = FakeConversation()

    def _route(self, msg):
        return route_message(self.user, msg, self.conv)

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_what_date_and_time_route_to_temporal(self, _m):
        self.assertEqual(self._route("What date is today?")["lane"], "temporal")
        self.assertEqual(self._route("What time is it?")["lane"], "temporal")

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_freshness_challenge_after_checkin_enters_trust_verification(self, _m):
        # Simulate the check-in having grounded an (aggregate) sleep statement.
        self.conv.metadata["last_answer"] = {
            "lane": "conversation_checkin", "fact_key": "sleep_last_night",
            "fact": {"key": "sleep_last_night", "value": 4.8, "aggregate": True,
                     "window": "7-night average",
                     "for_date": (self.today - timedelta(days=1)).isoformat(),
                     "freshness": "current"}}
        # The conversation has shifted to TRUST — Beth must verify, not fail.
        r1 = self._route("What date are you calling last night?")
        self.assertEqual(r1["lane"], "temporal")
        self.assertIn("not last night", r1["answer"].lower())
        r2 = self._route("I think your data is stale.")
        self.assertEqual(r2["lane"], "temporal")

    @mock.patch("apps.ai.services.ai_service._call_api", side_effect=_mock_general)
    def test_time_question_during_checkin_is_not_briefed(self, _m):
        # A clock question mid-check-in is answered deterministically, not
        # hijacked into personal coaching.
        self._route("Good morning")
        r = self._route("What time is it?")
        self.assertEqual(r["lane"], "temporal")
