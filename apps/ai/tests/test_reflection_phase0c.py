# ==============================================================================
# File: apps/ai/tests/test_reflection_phase0c.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0C — realize + verify (live seams, scheduling, admin).
# ==============================================================================
"""
Phase 0C verification. Unlike the 0B unit tests, these exercise the REAL
production seams end-to-end:
  - ChatGPTCoSService._system_prompt() (the actual CoS prompt assembly)
  - get_gap_awareness_injection() (the actual known-limitations injection)
  - the ISE scheduler runner (off-path scorecard compute)
  - the read-only admin surfaces
proving Phase 4 behaves correctly where it actually runs.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import CorrectionRecord, ExecutiveScorecardSnapshot, ReflectionEvent
from apps.ai.reflection.engine import reflect_on_turn
from apps.core.ai_memory.models import BehaviorDirective
from assistant.models import ImprovementTaskModel

WORKOUT_SRC = "apps.ai.chatgpt_cos.day_truth.todays_planned_workout"


def _user(email="phase0c@test.com"):
    User = get_user_model()
    try:
        return User.objects.create_user(email=email, password="x")
    except TypeError:
        return User.objects.create(email=email)


class LiveVerificationTests(TestCase):
    def setUp(self):
        self.user = _user()

    # Proof 1 + 3: a bounded PREFERENCE correction is learned AND read back into
    # the REAL CoS system prompt.
    def test_preference_learned_and_reaches_real_cos_prompt(self):
        CorrectionRecord.objects.create(
            user=self.user,
            original_response="Okay, Danny.",
            user_correction="actually, please just call me Dan",
            corrected_truth="call you Dan",
            readback_approved=False,
        )
        reflect_on_turn(self.user, "actually, please just call me Dan",
                        "Got it.", None)

        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "learn")
        self.assertEqual(ev.locus, "communication")
        self.assertTrue(BehaviorDirective.objects.filter(user=self.user).exists())
        rec = CorrectionRecord.objects.get(user=self.user)
        self.assertTrue(rec.readback_approved)

        # REAL prompt assembly must now carry the approved learning.
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        prompt = ChatGPTCoSService(self.user)._system_prompt(
            {}, message="what's on my plate today?")
        self.assertIn("LEARNED PREFERENCES", prompt)
        self.assertIn("call you Dan", prompt)

    # Proof 2 + 3(neg): a TRUTH correction creates an EIO, is NOT learned, and
    # never reaches the CoS prompt.
    def test_truth_correction_eio_and_not_in_real_cos_prompt(self):
        CorrectionRecord.objects.create(
            user=self.user,
            original_response="Do strength today.",
            user_correction="that's not right, today is cardio not strength",
            corrected_truth="today is cardio",
            readback_approved=False,
        )
        with mock.patch(WORKOUT_SRC, return_value=None):
            reflect_on_turn(self.user,
                            "that's not right, today is cardio not strength",
                            "strength", None)

        ev = ReflectionEvent.objects.get(user=self.user)
        self.assertEqual(ev.disposition, "eio")
        self.assertEqual(BehaviorDirective.objects.filter(user=self.user).count(), 0)
        self.assertFalse(CorrectionRecord.objects.get(user=self.user).readback_approved)

        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        prompt = ChatGPTCoSService(self.user)._system_prompt(
            {}, message="what's my workout today?")
        self.assertNotIn("LEARNED PREFERENCES", prompt)
        self.assertNotIn("cardio", prompt)

    # Proof 4: open EIOs surface as KNOWN LIMITATIONS via the real injector.
    def test_eio_surfaces_as_known_limitation(self):
        with mock.patch(WORKOUT_SRC, return_value=None):
            reflect_on_turn(self.user,
                            "that's not right, today is cardio not strength",
                            "strength", None)
        self.assertTrue(ImprovementTaskModel.objects.filter(
            source=ImprovementTaskModel.SOURCE_REFLECTION,
            triggered_by_user=self.user).exists())

        from apps.core.blueprint.system_gap_awareness import get_gap_awareness_injection
        injection = get_gap_awareness_injection(self.user)
        self.assertIn("KNOWN SYSTEM LIMITATIONS", injection)
        self.assertIn("workout", injection.lower())


class SchedulingTests(TestCase):
    def setUp(self):
        self.user = _user("sched@test.com")

    # Acceptance 4: the Executive Scorecard computes OFF the request path (the ISE
    # runner), and is a registered scheduled task.
    def test_scorecard_runner_computes_off_path(self):
        reflect_on_turn(self.user, "thanks, that helped!", "ok", None)
        from apps.core.ai_scheduler.scheduler_runner import run_executive_scorecards
        result = run_executive_scorecards()
        self.assertGreaterEqual(result["computed"], 1)
        self.assertTrue(
            ExecutiveScorecardSnapshot.objects.filter(user=self.user).exists())

    def test_scorecard_task_is_registered(self):
        from apps.core.ai_scheduler.scheduler_registry import (
            get_registered_tasks, get_task_function,
        )
        self.assertIn("compute_executive_scorecards", get_registered_tasks())
        self.assertTrue(callable(get_task_function("compute_executive_scorecards")))


class AdminReadOnlyTests(TestCase):
    # Acceptance 5: the operator surfaces are strictly read-only.
    def test_reflection_admin_is_read_only(self):
        from django.contrib import admin
        from apps.ai.models import ExecutiveScorecardSnapshot, ReflectionEvent
        for model in (ReflectionEvent, ExecutiveScorecardSnapshot):
            ma = admin.site._registry[model]
            self.assertFalse(ma.has_add_permission(None))
            self.assertFalse(ma.has_change_permission(None))
            self.assertFalse(ma.has_delete_permission(None))


class ParityTests(TestCase):
    # Acceptance 7: streaming and non-streaming both flow through the ONE canonical
    # post-response writer, which invokes reflection identically.
    def test_single_writer_invokes_reflection(self):
        user = _user("parity@test.com")
        with mock.patch("apps.ai.reflection.engine.reflect_on_turn") as m_reflect, \
                mock.patch("apps.core.ai_learning.learning_extractor.extract_learning"), \
                mock.patch("apps.core.ai_learning.learning_extractor.evolve_profile"), \
                mock.patch("apps.ai.correction_service.detect_correction",
                           return_value=False), \
                mock.patch("apps.ai.pattern_detector.detect_patterns"), \
                mock.patch("apps.core.ai_memory.life_fact_extractor."
                           "extract_life_facts_from_message"):
            from apps.ai.post_response_intelligence import run_post_response_intelligence
            run_post_response_intelligence(user, "hello", "hi there", None)
            m_reflect.assert_called_once_with(user, "hello", "hi there", None)
