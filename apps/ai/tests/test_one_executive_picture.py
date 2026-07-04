# ==============================================================================
# File: apps/ai/tests/test_one_executive_picture.py
# Description: ONE evolving executive understanding of today. Conversation-reported
#   evidence (subjective state, accomplishments) is MERGED once, in interpret(), into
#   ExecutiveSignals — every consumer (brief, decision support, …) reflects the same
#   evolving picture WITHOUT independently reading caches. Proves the architectural
#   correction: Beth remembered it, not Decision Support.
# ==============================================================================
from datetime import date, datetime, timezone as _tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.chatgpt_cos import decision_support as ds
from apps.ai.chatgpt_cos import executive_evidence as ev
from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief
from apps.ai.chatgpt_cos.executive_interpretation import ExecutiveSignals, interpret

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"
_GDS = "apps.ai.cos_services.get_domain_state"
ACC = "made up 2 missed workouts (Wednesday, Friday)"


def _state(hours):
    def f(user, domain):
        return {"state": {"sleep_last_night_hours": hours}} if domain == "health" \
            else {"state": {}}
    return f


class OneExecutivePictureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="onepic@test.com", password="x")
        cache.clear()

    # interpret() is the single merge point — it carries reported evidence.
    def test_interpret_merges_accomplishments(self):
        with mock.patch(_TODAY, return_value=TODAY), mock.patch(_GDS, side_effect=_state(7.5)):
            ev.record_accomplishment(self.user, ACC)
            sig = interpret(self.user)
        self.assertIn(ACC, sig.accomplishments)
        self.assertTrue(sig.ease_load)          # ahead of plan → recovery latitude

    def test_interpret_merges_subjective_without_a_param(self):
        with mock.patch(_TODAY, return_value=TODAY), mock.patch(_GDS, side_effect=_state(6.4)):
            ev.record_subjective(self.user, "positive")
            sig = interpret(self.user)          # NO subjective param — read from the store
        self.assertEqual(sig.reconciliation, "positive_over_debt")

    # The Morning Brief reflects accomplishments with NO consumer-specific wiring.
    def test_morning_brief_reflects_accomplishments(self):
        with mock.patch(_TODAY, return_value=TODAY), mock.patch(_GDS, side_effect=_state(7.5)):
            ev.record_accomplishment(self.user, ACC)
            brief = compose_executive_brief(self.user).lower()
        self.assertIn("made up 2 missed workouts", brief)
        self.assertIn("ahead of plan", brief)

    # Decision Support presents the SHARED picture — not the cache.
    def test_decision_support_reads_the_picture_not_the_cache(self):
        # Store HAS the accomplishment, but interpret returns a sig WITHOUT it → Decision
        # Support must NOT invent 'ahead of plan'. Proves it reads ExecutiveSignals.
        with mock.patch(_TODAY, return_value=TODAY):
            ev.record_accomplishment(self.user, ACC)
            with mock.patch.object(ds, "_safe_interpret", return_value=ExecutiveSignals()):
                out = ds.respond(self.user, "I won't be doing the bike ride tonight")
        self.assertNotIn("ahead of plan", out["answer"].lower())

    # The exact production sequence — one brain across the day.
    def test_full_production_sequence_one_brain(self):
        from apps.ai.models import AssistantConversation
        from apps.ai.chatgpt_cos.lanes import route_message
        conv = AssistantConversation.objects.create(user=self.user)
        clock = datetime(2026, 7, 4, 18, 0, tzinfo=_tz.utc)
        with mock.patch(_TODAY, return_value=TODAY), \
                mock.patch("apps.core.utils.get_user_now", return_value=clock), \
                mock.patch(_GDS, side_effect=_state(6.4)):
            route_message(self.user, "Good morning", conv)
            route_message(self.user, "I feel refreshed, 6.4 is good for me", conv)     # → subjective
            r3 = route_message(self.user, "I made up my workouts from Wednesday and Friday", conv)
            skip = route_message(self.user, "I won't be doing the bike ride tonight", conv)
            brief = compose_executive_brief(self.user).lower()
        self.assertEqual(r3["lane"], "accomplishment")
        self.assertEqual(skip["lane"], "decision_support")
        # Decision Support recommends recovery BECAUSE the picture knows the workouts.
        self.assertIn("made up 2 missed workouts", skip["answer"])
        self.assertIn("recovery", skip["answer"].lower())
        # A fresh brief reflects the SAME evolved understanding — no re-wiring.
        self.assertIn("made up 2 missed workouts", brief)
