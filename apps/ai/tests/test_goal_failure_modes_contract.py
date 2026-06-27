# ==============================================================================
# File: apps/ai/tests/test_goal_failure_modes_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: goal_failure_modes is a SEMANTIC acceptance contract ("clearly
#   communicate failure RISKS"), not a narrow lexical whitelist. A correct failure
#   analysis using "setback / obstacle / stall / burnout / inconsistent / skipped"
#   must PASS; a pure PROGRESS answer (no risk language) must still FAIL; the
#   deterministic floor must pass. Origin: evaluator rejected semantically-correct
#   answers that avoided the 6 hard-coded tokens.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos.reasoning import stages


def _spec():
    return next(q for q in ar.QUESTIONS if q.get("expect_intent") == "goal_failure_modes")


def _ev(text):
    return ar.evaluate(_spec(), text, intent="goal_failure_modes", lane="personal_reasoning")


class SemanticFailureContractTests(SimpleTestCase):
    SEMANTIC_OK = [
        ("setback/inconsistent/burnout/stall",
         "The biggest setbacks would be inconsistent workouts and missed sessions; "
         "burnout could stall progress. Complete today's scheduled workout to guard it."),
        ("obstacle/plateau",
         "The main obstacles are losing workout consistency and a possible plateau. "
         "Log today's session to stay ahead of it."),
        ("skipped/abandoned/derail",
         "Watch for skipped workouts and abandoned habits — those are the likeliest "
         "ways it derails. Do today's workout to guard against it."),
        ("fall behind / off plan",
         "If nutrition drifts off plan and you fall behind on workouts, momentum fades. "
         "The single best guard today is to complete the scheduled workout."),
        # The EXACT production response (commit 6a4b450a) that scored RED under the old
        # narrow contract — must pass now. (Origin: full/full 20/21.)
        ("production 6a4b450a",
         'The "France 2027 Family 18K Mission" could face setbacks from inconsistent '
         'protein intake, hydration lapses, skipped workouts, medication irregularities, '
         'or falling out of routine. These areas are crucial in the current "Momentum '
         'phase" to reach the next milestone of "Goal Weight 279.9". A good next step '
         "would be to schedule and complete today's workout, ensuring it aligns with "
         "your routine. This will help reinforce your commitment to becoming healthier "
         "and more capable of running the 18K in France."),
    ]

    def test_semantic_failure_answers_pass(self):
        for label, ans in self.SEMANTIC_OK:
            self.assertEqual(_ev(ans), [], f"semantically-correct answer failed: {label}")

    def test_pure_progress_answer_still_fails(self):
        # A progress summary with NO failure-risk language must NOT satisfy the
        # failure-modes contract (keeps the intents distinct).
        progress = ("France 2027 is on pace — weight is trending down and workouts are "
                    "steady. Complete today's workout to continue.")
        fails = _ev(progress)
        self.assertTrue(any(f.startswith("missing_required_any") for f in fails), fails)

    def test_deterministic_fallback_passes_the_contract(self):
        france = {"goal": "France 2027 Family 18K Mission",
                  "watch": ["workout frequency is light"],
                  "recommended_action": "complete today's scheduled workout"}
        wm = {"facts": {"goal_evidence": [france]}}
        out = stages._goal_failure_modes_fallback(wm)
        self.assertEqual(_ev(out), [], f"deterministic floor must pass: {out!r}")

    def test_vocab_covers_systems_own_narration_words(self):
        # Every plain-language failure mode the LLM profile + deterministic fallback
        # actually emit must be accepted by the contract.
        for phrase in ("losing workout consistency", "missing scheduled sessions",
                       "nutrition slipping off plan", "momentum fading",
                       "abandoning the daily habits", "inconsistency", "lost momentum"):
            self.assertTrue(any(v in phrase.lower() for v in ar.FAILURE_RISK_VOCAB),
                            f"contract rejects the system's own wording: {phrase!r}")
