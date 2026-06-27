# ==============================================================================
# File: apps/ai/tests/test_p29_morning_and_precedence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P29 final hardening — validates ACTUAL rendered responses.
#   DC#1 goal INTENT PRECEDENCE after identity resolution (behind->on_track,
#        threat->failure_modes, "do today for France"->focus, milestone questions
#        not stolen by foundational_facts / next_rhythm).
#   DC#2 real production "Good morning" must produce a deterministic CoS briefing
#        with OpenAI disabled (never the assistant-unavailable message).
#   DC#3 the morning CoS scenario, end-to-end, OpenAI disabled.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.reasoning.plan import named_goal_intent
from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos import acceptance_service as svc

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_TITLES = ["France 2027 Family 18K Mission"]


class GoalIntentPrecedenceTests(SimpleTestCase):
    """Once a request is goal-grounded, goal intent precedence is correct."""
    def _i(self, msg):
        return named_goal_intent(msg, _TITLES, _TITLES[0])[0]

    def test_every_failing_deep_question(self):
        cases = {
            "Am I behind on this goal?": "goal_on_track",
            "What is the biggest threat to this goal?": "goal_failure_modes",
            "What should I do today for France?": "goals_focus_today",
            "What comes next in this mission?": "goal_next_milestone",
            "What's after Goal Weight 284.9?": "goal_next_milestone",
        }
        for q, exp in cases.items():
            self.assertEqual(self._i(q), exp, q)

    def test_semantic_variants(self):
        for q in ("am I falling behind on this mission?", "are we on pace for the mission?"):
            self.assertEqual(self._i(q), "goal_on_track", q)
        for q in ("what threatens this goal?", "what could knock me off track on the mission?"):
            self.assertEqual(self._i(q), "goal_failure_modes", q)
        for q in ("what should I work on for France today?",
                  "what's the next move on the mission?"):
            self.assertEqual(self._i(q), "goals_focus_today", q)


class _LiveDeterministicMixin:
    def setUp(self):
        from apps.users.models import TermsAcceptance
        from apps.purpose.models import LifeGoal
        self.u = User.objects.create_user(email="p29live@x.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()
        LifeGoal.objects.create(user=self.u, title="France 2027 Family 18K Mission",
                                status="active", is_primary_mission=True)

    def _answer(self, q):
        with mock.patch(_C, side_effect=RuntimeError("openai down")), \
             mock.patch(_CT, side_effect=RuntimeError("openai down")):
            return route_message(self.u, q, None)


class MorningGreetingTests(_LiveDeterministicMixin, TestCase):
    """DC#2 — the exact production failure: 'Good morning' must be deterministic."""
    GREETINGS = ["Good morning", "good morning Beth", "morning", "good evening",
                 "start my day", "how is my day looking?", "what needs my attention?"]

    def test_greetings_never_hit_the_tool_loop_or_outage(self):
        for q in self.GREETINGS:
            res = self._answer(q)
            self.assertIsNotNone(res, f"{q!r} fell to the tool loop")
            ans = (res.get("answer") or "").strip()
            self.assertTrue(ans, f"{q!r} empty")
            self.assertFalse(ar.is_failure_message(ans),
                             f"{q!r} returned an assistant-unavailable message: {ans[:80]!r}")

    def test_good_morning_is_a_deterministic_briefing(self):
        res = self._answer("Good morning")
        self.assertEqual(res["lane"], "cos_briefing")
        self.assertNotIn("couldn't pull that together", res["answer"].lower())


class MorningScenarioTests(_LiveDeterministicMixin, TestCase):
    """DC#3 — the full morning CoS scenario, deterministic with OpenAI disabled."""
    SCENARIO = ["Good morning", "How is my day looking?", "What needs my attention?",
                "What could derail me today?",
                "If I only have 30 minutes, what should I do?"]

    def test_scenario_answers_deterministically(self):
        for step in self.SCENARIO:
            res = self._answer(step)
            self.assertIsNotNone(res, f"{step!r} fell to the tool loop")
            ans = (res.get("answer") or "").strip()
            self.assertTrue(ans, f"{step!r} empty")
            self.assertFalse(ar.is_failure_message(ans), f"{step!r}: outage message")
            self.assertEqual(ar.banned_hits(ans), [], f"{step!r}: banned phrase")


class PromptClassificationTests(SimpleTestCase):
    def test_production_path_and_coverage_gap_are_first_class(self):
        self.assertIn("production-path divergence", svc.FAILURE_CLASSIFICATION)
        self.assertIn("acceptance coverage gap", svc.FAILURE_CLASSIFICATION)

    def test_classification_appears_in_generated_prompt(self):
        from types import SimpleNamespace
        rows = [{"key": "x", "suite": "health", "question": "q", "answer": "a",
                 "expected_intent": "", "intent": "overall_progress",
                 "lane": "personal_reasoning", "openai_called": True,
                 "fallback_used": False, "ms": 100, "fails": ["banned_phrase:x"],
                 "passed": False, "spec": {"depth": "deep"}}]
        a = svc.analyze(rows)
        run = SimpleNamespace(environment="p", git_commit="x", suite_name="full",
            depth="deep", completed_at="t", created_at="t", score_percent=90,
            pass_count=9, total_count=10, fail_count=1, grade="RED", critical_count=0,
            warning_count=0, avg_response_ms=100, category_summary={}, analysis=a,
            trustworthy=a["trustworthy"])
        p = svc.build_chatgpt_review_prompt(run, rows)
        self.assertIn("production-path divergence", p)
        self.assertIn("acceptance coverage gap", p)
