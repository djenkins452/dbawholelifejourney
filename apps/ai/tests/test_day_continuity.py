# ==============================================================================
# File: apps/ai/tests/test_day_continuity.py
# Description: DAY CONTINUITY (Phase 2). Beth works alongside the executive all day — she
#   does not wake up fresh on every chat. Production failure: "Good morning" at 7am, 11am,
#   3pm, 5:30pm each replayed "You got about 6 hours of sleep...". Here: the first
#   conversation orients (as before); a later unprompted opener CONTINUES the day — a light
#   "welcome back" when nothing material changed, or a CONCISE delta when the executive
#   picture changed — driven by material change, not the clock. The opening check-in→brief
#   exchange is never collapsed. Explicit "brief me" is unaffected (not tested here — it
#   never routes through the gated openers).
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import day_continuity as dc

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_NOW = "apps.core.utils.get_user_now"
_MORNING = datetime.datetime(2026, 7, 3, 9, 0, tzinfo=datetime.timezone.utc)


class _FakeSig:
    def __init__(self, **kw):
        d = dict(priority_action=None, biggest_risk="", today_count=0, overdue_count=0,
                 accomplishments=[], foundation=[], health_critical=[], mission={})
        d.update(kw)
        for k, v in d.items():
            setattr(self, k, v)


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class FingerprintTests(SimpleTestCase):
    def test_material_change_detected(self):
        prev = dc.compute_fingerprint(_FakeSig(accomplishments=[]))
        cur = dc.compute_fingerprint(_FakeSig(accomplishments=["a walk", "a call"]))
        ch = dc.material_changes(prev, cur)
        self.assertTrue(any("knocked out 2 more" in c for c in ch), ch)

    def test_no_change_is_empty(self):
        fp = dc.compute_fingerprint(_FakeSig(today_count=3))
        self.assertEqual(dc.material_changes(fp, dict(fp)), [])

    def test_new_health_critical_is_material(self):
        prev = dc.compute_fingerprint(_FakeSig(health_critical=[]))
        cur = dc.compute_fingerprint(_FakeSig(health_critical=[{"text": "overdue dose"}]))
        self.assertTrue(any("health-critical" in c for c in dc.material_changes(prev, cur)))


class ContinuationVoiceTests(SimpleTestCase):
    def test_continue_mode_is_light_no_orientation(self):
        d = dc.Decision("continue", [], {}, _FakeSig())
        out = dc.compose_continuation(None, d.sig, d).lower()
        self.assertIn("progress", out)
        self.assertTrue(out.rstrip().endswith("?"))
        self.assertNotIn("sleep", out)
        self.assertNotIn("hours", out)

    def test_delta_mode_surfaces_the_change(self):
        d = dc.Decision("reorient_delta", ["you've knocked out 2 more things since we "
                                           "last talked"], {},
                        _FakeSig(priority_action={"text": "call the plumber"}))
        out = dc.compose_continuation(None, d.sig, d).lower()
        self.assertIn("knocked out 2 more", out)
        self.assertIn("call the plumber", out)


class AssessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.u = _mkuser("assess@example.com")

    def test_first_today_is_orient_full(self):
        with mock.patch(_NOW, return_value=_MORNING):
            self.assertTrue(dc.is_first_today(self.u))
            self.assertEqual(dc.assess(self.u, sig=_FakeSig()).mode, "orient_full")

    def test_returning_unchanged_is_continue(self):
        with mock.patch(_NOW, return_value=_MORNING):
            dc.mark_established(self.u, dc.compute_fingerprint(_FakeSig()))
            self.assertFalse(dc.is_first_today(self.u))
            self.assertEqual(dc.assess(self.u, sig=_FakeSig()).mode, "continue")

    def test_returning_changed_is_reorient_delta(self):
        with mock.patch(_NOW, return_value=_MORNING):
            dc.mark_established(self.u, dc.compute_fingerprint(_FakeSig(accomplishments=[])))
            d = dc.assess(self.u, sig=_FakeSig(accomplishments=["a walk"]))
            self.assertEqual(d.mode, "reorient_delta")
            self.assertTrue(d.changes)


class DayContinuityRoutingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.u = _mkuser("continuity@example.com")

    def _route(self, msg, conv):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("no llm")), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")), \
             mock.patch(_NOW, return_value=_MORNING):
            res = route_message(self.u, msg, conv)
        if res and res.get("answer"):
            AssistantMessage.objects.create(conversation=conv, role="assistant",
                                            content=res["answer"])
        return res

    def _conv(self):
        from apps.ai.models import AssistantConversation
        return AssistantConversation.objects.create(user=self.u, is_active=True)

    def test_second_greeting_continues_instead_of_reorienting(self):
        c = self._conv()
        r1 = self._route("Good morning", c)
        self.assertNotEqual(r1["lane"], "day_continuity")     # first → real check-in
        # A later greeting continues the day — no fresh orientation, no sleep recap.
        r2 = self._route("Good morning", c)
        self.assertEqual(r2["lane"], "day_continuity")
        low = r2["answer"].lower()
        self.assertNotIn("hours of sleep", low)
        self.assertNotIn("you got about", low)

    def test_opening_checkin_to_brief_is_not_collapsed(self):
        # The first exchange (greeting → feeling → brief) must complete fully — the brief
        # is part of the FIRST orientation, never a day-continuity continuation.
        c = self._conv()
        self._route("Good morning", c)
        r = self._route("I feel good and rested today", c)
        self.assertNotEqual((r or {}).get("lane"), "day_continuity")
