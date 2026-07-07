# ==============================================================================
# File: apps/ai/tests/test_morning_correction_trust.py
# Description: MORNING CHECK-IN TRUST-REPAIR & DETERMINISTIC DAY-TRUTH GROUNDING.
#   Regression for the production trust failure: Beth recommended "strength training"
#   on a Cardio day (inferred a workout type from a health goal instead of reading the
#   schedule), gave "focus on protein" with no options, ignored completed prayer/Bible,
#   and — when corrected — replied "Tell me what you're moving to…" as if the user were
#   rescheduling. Acceptance tests 1-5 encoded here.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import correction as C
from apps.ai.chatgpt_cos import decision_support as D
from apps.ai.chatgpt_cos import accomplishment as A
from apps.ai.chatgpt_cos.reasoning import stages

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_PLANNED = "apps.ai.chatgpt_cos.day_truth.todays_planned_workout"
CARDIO = {"title": "Workout: Cardio", "type": "cardio", "time": "6:00 PM", "completed": False}


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


# ── Acceptance 1: cardio scheduled, no strength → never recommend strength ──────
class WorkoutGroundingTests(SimpleTestCase):
    def test_movement_action_uses_the_scheduled_workout_not_a_goal(self):
        out = stages._movement_action(CARDIO).lower()
        self.assertIn("cardio", out)
        self.assertNotIn("strength", out)

    def test_concrete_action_for_muscle_concern_defers_to_schedule(self):
        # A muscle-loss concern must NOT emit "strength" when today is Cardio.
        out = stages._concrete_today_action(
            "you may be losing some muscle", "morning", planned=CARDIO).lower()
        self.assertIn("cardio", out)
        self.assertNotIn("strength", out)

    def test_ranked_concern_muscle_action_never_prescribes_strength_on_cardio_day(self):
        buckets = {"active_risks": {"muscle_loss_risk_level": "moderate"},
                   "todays_planned_workout": CARDIO}
        ranked = stages._rank_health_concerns(buckets)
        muscle = [c for c in ranked if "muscle" in c["concern"]][0]
        self.assertNotIn("strength", muscle["action"].lower())

    def test_health_focus_fallback_grounds_in_cardio(self):
        wm = {"facts": {
            "ranked_concerns": [{"concern": "you may be losing some muscle",
                                 "action": "x", "evidence": "y", "why": "z"}],
            "todays_planned_workout": CARDIO,
            "nutrition_context": {"day_phase": "morning"}}}
        out = stages._health_focus_today_fallback(wm).lower()
        self.assertIn("cardio", out)
        self.assertNotIn("strength", out)

    def test_no_planned_workout_never_invents_a_modality(self):
        out = stages._movement_action(None).lower()
        for modality in ("strength", "cardio", "bike", "pickleball"):
            self.assertNotIn(modality, out)
        self.assertIn("walk", out)


# ── Acceptance 4: protein advice is actionable ─────────────────────────────────
class ProteinActionableTests(SimpleTestCase):
    def test_protein_action_includes_concrete_options(self):
        out = stages._concrete_today_action(
            "your protein is running low", "morning",
            protein="eggs, Greek yogurt, or a protein shake").lower()
        self.assertIn("30g", out)
        self.assertTrue(any(food in out for food in ("eggs", "yogurt", "shake")))


# ── Acceptance 3: completed prayer/Bible is acknowledged, not ignored ──────────
class FoundationAcknowledgmentTests(SimpleTestCase):
    def test_detects_completed_prayer_and_bible(self):
        a = A.detect("I feel rested — and I already did my prayer and Bible reading")
        self.assertIsNotNone(a)
        self.assertEqual(a.kind, "foundation")
        self.assertIn("prayer", a.label)
        self.assertIn("Bible reading", a.label)

    def test_does_not_fire_on_a_plain_feeling(self):
        self.assertIsNone(A.detect("I'm feeling pretty good this morning"))

    def test_a_question_about_prayer_is_not_an_accomplishment(self):
        self.assertIsNone(A.detect("did I pray today?"))


# ── Acceptance 5 + detector: correction is trust-repair, not a plan-change ─────
class CorrectionDetectorTests(SimpleTestCase):
    def test_recognizes_factual_corrections(self):
        for m in ("today is not strength training, it's cardio",
                  "it's cardio instead of strength today",
                  "today is cardio rather than strength",
                  "why didn't you know that?",
                  "you should have checked my schedule"):
            self.assertTrue(C.is_factual_correction(m), m)

    def test_does_not_fire_on_a_real_change_of_mind_or_feeling(self):
        for m in ("I'm going to do cardio instead of strength today",
                  "I changed my mind, doing cardio instead",
                  "I'm not great but hanging in",
                  "I feel rested, already did prayer and Bible reading",
                  "what should I do today?"):
            self.assertFalse(C.is_factual_correction(m), m)

    def test_decision_support_declines_a_correction(self):
        # The false-positive path: "instead of" must NOT read as change_mind here.
        self.assertIsNone(D.detect_decision("it's cardio instead of strength today"))
        # …but a genuine change-of-mind is still detected.
        self.assertIsNotNone(D.detect_decision("I changed my mind, doing cardio instead"))


class CorrectionRecoveryComposeTests(TestCase):
    def setUp(self):
        self.u = _mkuser("corr_compose@example.com")

    def test_recovery_names_miss_source_and_corrected_plan(self):
        with mock.patch(_PLANNED, return_value=CARDIO):
            res = C.respond(self.u, "today is not strength, it's cardio. why didn't "
                                    "you offer protein options?")
        ans = res["answer"].lower()
        self.assertEqual(res["lane"], "correction_recovery")
        self.assertIn("cardio", ans)                       # corrected truth
        self.assertNotIn("strength training", ans)
        self.assertIn("schedule", ans)                     # names the source to check
        self.assertNotIn("moving to", ans)                 # NEVER the reschedule reply
        # protein complaint answered with concrete options
        self.assertTrue(any(f in ans for f in ("eggs", "yogurt", "shake", "chicken")))


class CorrectionRoutingTests(TestCase):
    """End-to-end: a workout correction after a prior Beth turn reaches the correction
    lane, never decision_support's 'what are you moving to' reply."""
    def setUp(self):
        from apps.ai.models import AssistantConversation, AssistantMessage
        self.u = _mkuser("corr_route@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant",
            content="A good focus today is strength training to protect muscle.")

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")), \
             mock.patch(_PLANNED, return_value=CARDIO):
            return route_message(self.u, msg, self.conv)

    def test_workout_correction_routes_to_correction_recovery(self):
        res = self._route("today is not strength training, it's cardio at 6pm "
                          "instead of strength")
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "correction_recovery")
        ans = res["answer"].lower()
        self.assertNotIn("moving to", ans)
        self.assertNotIn("sanity-check", ans)
        self.assertIn("cardio", ans)
