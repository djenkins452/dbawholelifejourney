# ==============================================================================
# File: apps/ai/tests/test_current_context_baseline.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context baseline (Pillar 4) — the FAST tier ("what's happening now").
# ==============================================================================
"""
Tests for apps/ai/cos_services/current_context.py.

Current Context is the FAST tier: clock, current screen (structured page), capability
index. It does NOT own deterministic understanding (priority/patterns/etc. moved to the
Understanding tier). Structured page context is exposed; a missing page is a benign
'none', never "I can't see the screen".
"""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.current_context import (
    CURRENT_CONTEXT_SCHEMA_VERSION,
    get_current_context_baseline,
)

User = get_user_model()


class CurrentContextBaselineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cc@example.com", password="x")

    def setUp(self):
        cache.clear()  # the priority-2 fallback is cache-backed; isolate each test

    def test_shape_is_fast_tier_only(self):
        ctx = get_current_context_baseline(self.user)
        self.assertEqual(ctx["schema_version"], CURRENT_CONTEXT_SCHEMA_VERSION)
        self.assertEqual(set(ctx.keys()),
                         {"schema_version", "clock", "current_screen", "capabilities"})
        # No deterministic understanding leaks into Current Context.
        for banned in ("priority", "day_continuity", "patterns", "biggest_risk"):
            self.assertNotIn(banned, ctx)

    def test_clock_and_capabilities_present(self):
        ctx = get_current_context_baseline(self.user)
        self.assertIn("local_time", ctx["clock"])
        self.assertIn("part_of_day", ctx["clock"])
        self.assertIn("answerable_domains", ctx["capabilities"])

    def test_location_is_exposed_without_a_declared_focus(self):
        # WHERE the user is (navigation facts) is always safe to pass; with no declared
        # reference there is simply no focused object.
        page = {"url": "/faith/journey/today/", "module": "Faith",
                "page_title": "Today's Reading"}
        ctx = get_current_context_baseline(self.user, page_context=page)
        screen = ctx["current_screen"]
        self.assertEqual(screen["status"], "present")
        self.assertEqual(screen["location"]["url"], "/faith/journey/today/")
        self.assertEqual(screen["location"]["module"], "Faith")
        self.assertIsNone(screen["focus"])

    def test_declared_reference_resolves_to_canonical_truth(self):
        # The CONTRACT: page sends a reference; WLJ resolves the deterministic truth
        # server-side from the canonical model. Scraped DOM is never trusted.
        from apps.purpose.models import LifeGoal
        goal = LifeGoal.objects.create(
            user=self.user, title="Run a half marathon",
            description="Build to 13.1 miles by fall.",
            why_it_matters="Prove I can commit to something hard.",
        )
        page = {"url": f"/goals/{goal.pk}/", "module": "Goals",
                "focus_ref": f"purpose.lifegoal:{goal.pk}",
                # A scraped-content blob that must NOT be trusted as truth:
                "page_content": {"description": "SCRAPED-JUNK-SHOULD-BE-IGNORED"}}
        ctx = get_current_context_baseline(self.user, page_context=page)
        focus = ctx["current_screen"]["focus"]
        self.assertIsNotNone(focus)
        self.assertEqual(focus["source"], "canonical")
        self.assertEqual(focus["ref"], f"purpose.lifegoal:{goal.pk}")
        self.assertIn("Run a half marathon", focus["title"])
        self.assertIn("Prove I can commit", focus["content"])
        # Scraped junk never enters the truth WLJ hands the model.
        self.assertNotIn("SCRAPED-JUNK", json.dumps(ctx))

    def test_unowned_reference_is_reported_not_denied(self):
        # A declared reference to another user's object must not leak, and must not read
        # as "this does not exist" — it is a sync/ownership condition.
        from apps.purpose.models import LifeGoal
        other = User.objects.create_user(email="other@example.com", password="x")
        goal = LifeGoal.objects.create(user=other, title="Not my goal")
        page = {"url": f"/goals/{goal.pk}/", "module": "Goals",
                "focus_ref": f"purpose.lifegoal:{goal.pk}"}
        ctx = get_current_context_baseline(self.user, page_context=page)
        screen = ctx["current_screen"]
        self.assertIsNone(screen["focus"])
        self.assertIn("did not resolve", screen["note"])
        self.assertNotIn("Not my goal", json.dumps(ctx))

    def test_missing_page_is_benign_none_not_denial(self):
        ctx = get_current_context_baseline(self.user)  # no page_context
        self.assertEqual(ctx["current_screen"]["status"], "none")
        # never phrased as "cannot see"
        self.assertNotIn("cannot", json.dumps(ctx).lower())


class CurrentContextOwnershipModelTests(TestCase):
    """The safety-net ownership model: current request ALWAYS wins; the conversation store
    only fills a gap; no stale truth ever becomes authoritative."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="own@example.com", password="x")

    def setUp(self):
        cache.clear()
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _goal(self, title):
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.create(user=self.user, title=title,
                                       description=f"About {title}.")

    def _screen(self, page_context=None, now=None):
        return get_current_context_baseline(
            self.user, page_context=page_context, conversation=self.conv, now=now,
        )["current_screen"]

    def test_current_request_focus_wins_over_remembered(self):
        # Message 1: looking at Goal A (remembered). Message 2: navigated to Goal B and the
        # client DID declare it — Goal B must win; no stale Goal A.
        a, b = self._goal("Goal A"), self._goal("Goal B")
        self._screen({"focus_ref": f"purpose.lifegoal:{a.pk}"})  # remembers A
        screen = self._screen({"focus_ref": f"purpose.lifegoal:{b.pk}"})
        focus = screen["focus"]
        self.assertEqual(focus["authority"], "current_request")
        self.assertEqual(focus["ref"], f"purpose.lifegoal:{b.pk}")
        self.assertIn("Goal B", focus["title"])
        self.assertNotIn("Goal A", json.dumps(screen))

    def test_fallback_fills_gap_when_client_omits_focus(self):
        # Message 1 declared Goal A; message 2 arrives with NO focus_ref (client hiccup) →
        # the safety net serves Goal A, clearly marked as a stale-able fallback.
        a = self._goal("Goal A")
        now = timezone.now()
        self._screen({"focus_ref": f"purpose.lifegoal:{a.pk}"}, now=now)  # remembers A @ now
        screen = self._screen({"url": "/dashboard/"}, now=now + timedelta(seconds=30))
        focus = screen["focus"]
        self.assertIsNotNone(focus)
        self.assertEqual(focus["source"], "fallback")
        self.assertEqual(focus["authority"], "conversation_fallback")
        self.assertIn("Goal A", focus["title"])
        self.assertEqual(focus["freshness"], "current")   # 30s old
        self.assertEqual(focus["age_seconds"], 30)
        self.assertIn("as_of", focus)

    def test_fallback_marked_stale_when_old(self):
        a = self._goal("Goal A")
        now = timezone.now()
        self._screen({"focus_ref": f"purpose.lifegoal:{a.pk}"}, now=now)
        screen = self._screen({"url": "/dashboard/"}, now=now + timedelta(minutes=20))
        self.assertEqual(screen["focus"]["freshness"], "stale")
        self.assertEqual(screen["focus"]["age_seconds"], 1200)

    def test_fallback_does_not_refresh_its_own_age(self):
        # A fallback turn must NOT reset the remembered timestamp — age keeps growing from
        # the last AUTHORITATIVE sighting, so staleness is honest across many gap turns.
        a = self._goal("Goal A")
        now = timezone.now()
        self._screen({"focus_ref": f"purpose.lifegoal:{a.pk}"}, now=now)   # authoritative @ now
        self._screen({"url": "/x/"}, now=now + timedelta(minutes=5))       # fallback (no remember)
        screen = self._screen({"url": "/y/"}, now=now + timedelta(minutes=20))
        self.assertEqual(screen["focus"]["age_seconds"], 1200)             # from t0, not t+5

    def test_declared_but_unresolved_never_falls_back(self):
        # A ref the client DID send but that failed (unowned) is a sync signal — it must be
        # reported, never masked by the remembered object.
        a = self._goal("Goal A")
        other = User.objects.create_user(email="other2@example.com", password="x")
        from apps.purpose.models import LifeGoal
        foreign = LifeGoal.objects.create(user=other, title="Foreign")
        self._screen({"focus_ref": f"purpose.lifegoal:{a.pk}"})  # remembers A
        screen = self._screen({"focus_ref": f"purpose.lifegoal:{foreign.pk}"})
        self.assertIsNone(screen["focus"])
        self.assertIn("did not resolve", screen["note"])
        self.assertNotIn("Goal A", json.dumps(screen))  # NOT masked by the fallback

    def test_no_fallback_without_a_conversation(self):
        # Request-scoped only: omit conversation and there is simply no safety net.
        a = self._goal("Goal A")
        get_current_context_baseline(
            self.user, page_context={"focus_ref": f"purpose.lifegoal:{a.pk}"},
            conversation=self.conv,
        )  # remembers on THIS conversation
        screen = get_current_context_baseline(
            self.user, page_context={"url": "/dashboard/"},  # no conversation passed
        )["current_screen"]
        self.assertIsNone(screen["focus"])

    def test_output_is_json_safe(self):
        json.dumps(get_current_context_baseline(
            self.user, page_context={"page": "dashboard"}))
