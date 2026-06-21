"""Attention / late / upcoming routes consume the unified event stream first.

"What needs my attention?", "What am I late on?", "What is coming up soon?" now
route to the GuidanceItem event stream (strategic + operational), with execution
state only as a fallback when the stream is empty.
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr
from apps.ai import cos_event_engine as eng

User = get_user_model()


class Matchers(SimpleTestCase):
    def test_matchers(self):
        self.assertTrue(dr._match_attention_now_query("what needs my attention right now"))
        self.assertTrue(dr._match_late_query("what am i late on"))
        self.assertTrue(dr._match_upcoming_query("what is coming up soon"))

    def test_no_cross_match(self):
        self.assertFalse(dr._match_late_query("what is coming up soon"))
        self.assertFalse(dr._match_upcoming_query("what am i late on"))


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _seed(user, category, domain, title):
    return eng.persist_event(user, eng.CoSEvent(
        category, domain, title, f"{title} happened.", "It matters.", "Do it.",
        key=f"op:{domain}:{title.lower().replace(' ', '-')}"
        if category in eng.OPERATIONAL_CATS else None))


class EventStreamFirst(TestCase):
    def setUp(self):
        self.user = _user("evtroute@test.com")

    def test_attention_uses_event_stream(self):
        _seed(self.user, eng.STRATEGIC_RISK, "sleep", "Sleep is trending down")
        _seed(self.user, eng.PAST_DUE, "health", "Wake up")
        res = dr.classify_and_route("what needs my attention right now", self.user)
        self.assertEqual(res.route_name, "attention_now_query")
        self.assertIn("Strategic attention", res.response)
        self.assertIn("Sleep is trending down", res.response)
        self.assertIn("Operational attention", res.response)
        self.assertIn("Wake up", res.response)

    def test_late_uses_event_stream(self):
        _seed(self.user, eng.PAST_DUE, "health", "Metformin")
        res = dr.classify_and_route("what am i late on", self.user)
        self.assertEqual(res.route_name, "late_events_query")
        self.assertIn("Metformin", res.response)

    def test_recurring_marked_in_late(self):
        item, _ = _seed(self.user, eng.PAST_DUE, "health", "Metformin")
        meta = item.metadata
        meta["category"] = eng.RECURRING_PROBLEM
        item.metadata = meta
        item.save(update_fields=["metadata"])
        res = dr.classify_and_route("what am i late on", self.user)
        self.assertIn("recurring", res.response.lower())

    def test_upcoming_uses_event_stream_with_strategic(self):
        _seed(self.user, eng.APPROACHING, "health", "Empty Dishwasher")
        _seed(self.user, eng.STRATEGIC_RISK, "sleep", "Sleep is trending down")
        res = dr.classify_and_route("what is coming up soon", self.user)
        self.assertEqual(res.route_name, "upcoming_events_query")
        self.assertIn("Empty Dishwasher", res.response)
        self.assertIn("sleep", res.response.lower())   # strategic focus appended

    def test_strategic_and_operational_coexist(self):
        _seed(self.user, eng.STRATEGIC_RISK, "sleep", "Sleep is trending down")
        _seed(self.user, eng.DUE_NOW, "health", "Workout")
        res = dr.classify_and_route("what needs my attention", self.user)
        self.assertIn("Sleep is trending down", res.response)
        self.assertIn("Workout", res.response)


class ExecutionFallback(TestCase):
    """When the event stream is empty, fall back to execution state."""

    def setUp(self):
        self.user = _user("evtfb@test.com")

    def test_late_falls_back_to_execution(self):
        with patch.object(dr, "_execution_actions",
                          return_value=(["Trash boxes"], [], [])):
            res = dr.classify_and_route("what am i late on", self.user)
        self.assertEqual(res.route_name, "late_events_query")
        self.assertIn("Trash boxes", res.response)

    def test_upcoming_falls_back_to_execution(self):
        with patch.object(dr, "_execution_actions",
                          return_value=([], [], ["Pool activities"])):
            res = dr.classify_and_route("what is coming up soon", self.user)
        self.assertIn("Pool activities", res.response)

    def test_attention_falls_back_to_execution(self):
        with patch.object(dr, "_execution_actions",
                          return_value=([], ["Cut up boxes"], [])):
            res = dr.classify_and_route("what needs my attention right now", self.user)
        self.assertIn("Cut up boxes", res.response)

    def test_empty_everywhere_is_graceful(self):
        with patch.object(dr, "_execution_actions", return_value=([], [], [])):
            res = dr.classify_and_route("what am i late on", self.user)
        self.assertIn("not late", res.response.lower())
