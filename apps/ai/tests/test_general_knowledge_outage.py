# ==============================================================================
# File: apps/ai/tests/test_general_knowledge_outage.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: General-knowledge OUTAGE fallback defect class. General knowledge
#   depends on the external LLM (no offline KB by design). When OpenAI is down the
#   outage fallback must (1) NOT leak personal domains, and (2) be accepted by the
#   Acceptance evaluator as a graceful degradation — content tokens (president/
#   Lincoln/1865) are un-satisfiable during an outage. Goals/Health stay strict.
#   Origin: production Smoke RED — `forbidden_concept: your goal` + missing_required.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos.lanes import general_answer

User = get_user_model()
_CALL_API = "apps.ai.services.ai_service._call_api"
_PERSONAL_LEAKS = ("your goal", "your health", "your schedule", "your faith",
                   "your mission", "your weight")


class OutageFallbackTests(TestCase):
    """The rendered outage fallback must never leak personal-domain language."""
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="gk@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def _outage(self, q):
        with mock.patch(_CALL_API, side_effect=RuntimeError("openai down")):
            return general_answer(self.user, q)

    def test_no_personal_domain_leakage_across_questions(self):
        for q in ("Who was Abraham Lincoln?", "Explain photosynthesis.", "What is Delphi?"):
            out = self._outage(q)
            self.assertEqual(out["lane"], "general_conversation")
            self.assertTrue(out["answer"].strip())
            low = out["answer"].lower()
            for leak in _PERSONAL_LEAKS:
                self.assertNotIn(leak, low, f"{q!r} leaked {leak!r}: {out['answer']!r}")

    def test_outage_message_is_graceful_degradation(self):
        out = self._outage("Who was Abraham Lincoln?")
        low = out["answer"].lower()
        self.assertIn("temporarily unavailable", low)
        self.assertIn("try again", low)
        self.assertFalse(ar.banned_hits(out["answer"]))
        # the evaluator recognizes it as a graceful outage degradation
        self.assertTrue(ar.is_failure_message(out["answer"]))


class EvaluatorOutageContractTests(SimpleTestCase):
    """The architecture decision, made permanent: a CLEAN general-knowledge outage
    response PASSES; content gates are skipped (un-satisfiable). Quality still
    enforced. Goals/Health outages stay strict."""
    CLEAN_OUTAGE = ("I normally answer general questions like that directly, but my "
                    "external knowledge service is temporarily unavailable right now. "
                    "Please try again in a minute.")

    def _gen(self, key):
        return next(q for q in ar.QUESTIONS if q["key"] == key)

    def test_clean_outage_passes_for_general_knowledge(self):
        for key in ("gen_lincoln", "gen_photo", "gen_delphi"):
            fails = ar.evaluate(self._gen(key), self.CLEAN_OUTAGE,
                                intent=None, lane="general_conversation")
            self.assertEqual(fails, [], f"{key} clean outage should PASS, got {fails}")

    def test_required_tokens_not_required_during_outage(self):
        # The whole point: president/Lincoln/1865 are NOT demanded during an outage.
        fails = ar.evaluate(self._gen("gen_lincoln"), self.CLEAN_OUTAGE,
                            intent=None, lane="general_conversation")
        self.assertNotIn("missing_required_any:president|lincoln|1865|civil war", fails)

    def test_leaky_outage_still_fails(self):
        leaky = ("I can't reach my knowledge service — try again. Meanwhile I can help "
                 "with your goals and your health.")
        fails = ar.evaluate(self._gen("gen_lincoln"), leaky,
                            intent=None, lane="general_conversation")
        self.assertTrue(any(f.startswith("forbidden_concept") for f in fails), fails)

    def test_banned_phrase_in_outage_still_fails(self):
        banned = "I couldn't reach it — try again. Maintain momentum in the meantime."
        fails = ar.evaluate(self._gen("gen_lincoln"), banned,
                            intent=None, lane="general_conversation")
        self.assertTrue(any(f.startswith("banned_phrase") for f in fails), fails)

    def test_real_answer_when_openai_up_is_fully_gated(self):
        good = ("Abraham Lincoln was the 16th US president; he led the Union through "
                "the Civil War until 1865.")
        bad = "He was a famous American leader."
        self.assertEqual(ar.evaluate(self._gen("gen_lincoln"), good,
                                     intent=None, lane="general_conversation"), [])
        self.assertTrue(ar.evaluate(self._gen("gen_lincoln"), bad,
                                    intent=None, lane="general_conversation"))

    def test_goals_outage_stays_strict_infrastructure_failure(self):
        # WLJ owns goal truth — an outage message there is NOT acceptable (it means
        # the deterministic fallback failed). Must remain an infrastructure failure.
        goalq = next(q for q in ar.QUESTIONS if q["key"] == "bnd_my_milestone")
        fails = ar.evaluate(goalq, self.CLEAN_OUTAGE,
                            intent="goal_next_milestone", lane="personal_reasoning")
        self.assertIn("openai_failure_message", fails)
        self.assertEqual(ar.layer_of("general_failure"), "infrastructure")
