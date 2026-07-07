# ==============================================================================
# File: apps/ai/tests/test_executive_reflection.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0B — Executive Reflection acceptance tests.
# ==============================================================================
"""
The eight acceptance proofs for Executive Reflection (Phase 4). The load-bearing
ones prove the classifier BLOCKS unsafe learning: a correction about deterministic
truth can never become a learned fact, and only classifier-approved
preference/communication learnings are ever read back into the CoS prompt.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import (
    CorrectionRecord,
    ExecutiveScorecardSnapshot,
    ReflectionEvent,
)
from apps.ai.reflection.engine import reflect_on_turn
from apps.ai.reflection.readback import approved_correction_context_block
from apps.ai.reflection import scorecard
from apps.core.ai_memory.models import BehaviorDirective
from assistant.models import ImprovementTaskModel

WORKOUT_SRC = "apps.ai.chatgpt_cos.day_truth.todays_planned_workout"


def _user(email="refl@test.com"):
    User = get_user_model()
    try:
        return User.objects.create_user(email=email, password="x")
    except TypeError:
        return User.objects.create(email=email)


class ReflectionAcceptanceTests(TestCase):
    def setUp(self):
        self.user = _user()

    # 1) Cardio vs strength correction does NOT become a learned fact when the
    #    deterministic truth is missing / stale / wrong.
    def test_truth_correction_missing_source_not_learned(self):
        with mock.patch(WORKOUT_SRC, return_value=None):  # missing state
            reflect_on_turn(
                self.user,
                "no, that's not right — today is cardio, not strength",
                "I recommended strength today.", None)
        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "eio")
        self.assertEqual(ev.locus, "truth_retrieval")
        self.assertEqual(BehaviorDirective.objects.filter(user=self.user).count(), 0)
        self.assertEqual(
            ImprovementTaskModel.objects.filter(
                source=ImprovementTaskModel.SOURCE_REFLECTION).count(), 1)

    def test_truth_correction_stale_source_not_learned(self):
        # Source says strength; user (correctly) says cardio -> stale/wrong truth.
        with mock.patch(WORKOUT_SRC, return_value={"type": "strength", "time": ""}):
            reflect_on_turn(
                self.user,
                "that's not correct, today is cardio not strength",
                "Do strength today.", None)
        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "eio")
        self.assertEqual(ev.locus, "truth_retrieval")
        eio = ImprovementTaskModel.objects.get(
            source=ImprovementTaskModel.SOURCE_REFLECTION)
        self.assertEqual(eio.engineering_category, "serialization")
        self.assertEqual(BehaviorDirective.objects.filter(user=self.user).count(), 0)

    # 2) A preference correction CAN become bounded behavior guidance.
    def test_preference_becomes_bounded_guidance(self):
        reflect_on_turn(
            self.user,
            "Going forward, I prefer you check in with me in the evenings.",
            "Noted.", None)
        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "learn")
        self.assertEqual(ev.locus, "preference")
        d = BehaviorDirective.objects.get(user=self.user)
        self.assertEqual(d.layer, "preference")
        self.assertTrue(d.key.startswith("preference:"))

    # 3) A communication correction CAN become bounded behavior guidance.
    def test_communication_becomes_bounded_guidance(self):
        reflect_on_turn(self.user, "Please stop calling me champ.", "Understood.", None)
        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "learn")
        self.assertEqual(ev.locus, "communication")
        d = BehaviorDirective.objects.get(user=self.user)
        self.assertEqual(d.layer, "communication")

    # 4) Truth/reasoning/execution failures create EIOs instead of learning
    #    (and dedupe by recurrence rather than spawning duplicates).
    def test_reasoning_failure_creates_eio_and_dedupes(self):
        # Source AGREES with the user -> truth was available -> reasoning locus.
        with mock.patch(WORKOUT_SRC, return_value={"type": "cardio", "time": "6pm"}):
            reflect_on_turn(self.user, "that's not right, it's cardio not strength",
                            "Strength today.", None)
            reflect_on_turn(self.user, "that's not right, it's cardio not strength",
                            "Strength again.", None)
        eios = ImprovementTaskModel.objects.filter(
            source=ImprovementTaskModel.SOURCE_REFLECTION)
        self.assertEqual(eios.count(), 1)               # deduped
        eio = eios.first()
        self.assertEqual(eio.functional_locus, "reasoning")
        self.assertEqual(eio.recurrence_count, 2)       # recurrence bumped
        self.assertEqual(BehaviorDirective.objects.filter(user=self.user).count(), 0)

    # 5) A successful recommendation can be reinforced without truth overrides.
    def test_success_reinforced_without_truth_override(self):
        reflect_on_turn(self.user, "Thanks, that was really helpful!",
                        "Here's your plan.", None)
        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "reinforce")
        self.assertEqual(ev.trust_delta, "increased")
        # No truth override, no EIO, no fabricated directive.
        self.assertEqual(CorrectionRecord.objects.filter(user=self.user).count(), 0)
        self.assertEqual(ImprovementTaskModel.objects.count(), 0)
        self.assertEqual(BehaviorDirective.objects.filter(user=self.user).count(), 0)

    # 6) Trust Delta is recorded.
    def test_trust_delta_recorded(self):
        reflect_on_turn(self.user, "that's not helpful at all", "…", None)
        reflect_on_turn(self.user, "perfect, thank you!", "…", None)
        deltas = set(ReflectionEvent.objects.filter(user=self.user)
                     .values_list("trust_delta", flat=True))
        self.assertIn("decreased", deltas)
        self.assertIn("increased", deltas)

    # 7) The Executive Scorecard can summarize reflection outcomes.
    def test_scorecard_summarizes(self):
        reflect_on_turn(self.user, "Please stop calling me champ.", "ok", None)
        reflect_on_turn(self.user, "thanks, that helped!", "ok", None)
        with mock.patch(WORKOUT_SRC, return_value=None):
            reflect_on_turn(self.user, "that's not right, today is cardio not strength",
                            "strength", None)
        data = scorecard.summarize(self.user, days=30)
        self.assertEqual(data["reflection_count"], 3)
        self.assertEqual(data["learning_events"], 1)
        self.assertEqual(data["executive_improvement_opportunities"], 1)
        self.assertEqual(data["reinforcements"], 1)
        self.assertGreaterEqual(data["user_trust"]["increased"], 1)
        snap = scorecard.compute_and_store(self.user, days=30)
        self.assertIsInstance(snap, ExecutiveScorecardSnapshot)
        self.assertEqual(snap.reflection_count, 3)

    # 8) CoS prompt read-back only includes classifier-approved learning.
    def test_readback_only_includes_approved(self):
        CorrectionRecord.objects.create(
            user=self.user, original_response="I'll call you Danny.",
            user_correction="call me Dan", corrected_truth="call you Dan",
            readback_approved=True)
        CorrectionRecord.objects.create(
            user=self.user, original_response="Do strength today.",
            user_correction="today is cardio not strength",
            corrected_truth="today is cardio", readback_approved=False)
        block = approved_correction_context_block(self.user)
        self.assertIn("call you Dan", block)
        self.assertNotIn("cardio", block)

    # 8b) A truth-domain correction is NEVER approved for read-back by reflection.
    def test_truth_correction_never_approved_for_readback(self):
        rec = CorrectionRecord.objects.create(
            user=self.user, original_response="Do strength today.",
            user_correction="that's not right, today is cardio not strength",
            corrected_truth="today is cardio", readback_approved=False)
        with mock.patch(WORKOUT_SRC, return_value=None):
            reflect_on_turn(
                self.user, "that's not right, today is cardio not strength",
                "strength", None)
        rec.refresh_from_db()
        self.assertFalse(rec.readback_approved)
        self.assertEqual(approved_correction_context_block(self.user), "")
