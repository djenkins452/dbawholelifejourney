# ==============================================================================
# File: apps/ai/tests/test_foundational_steps.py
# Description: Regression — "how many steps" is a DETERMINISTIC fact (Law 4), scoped
#   to the steps domain (Law 0), with honest no-data freshness (Law 1). Previously
#   it had no foundational fact and fell into the LLM path. Defect class: incomplete
#   deterministic fast-path. Pure-function tests (no OpenAI).
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, format_fact_sentence,
)
from apps.ai.cos_services.health_facts import SUPPORTED_FACTS


class StepsDeterministicFactTests(SimpleTestCase):
    def test_steps_questions_route_to_deterministic_fact(self):
        for q in ("How many steps did I get yesterday?", "How many steps today?",
                  "what's my step count", "show me my steps"):
            self.assertEqual(classify_foundational_fact(q), "steps_recent", q)

    def test_does_not_capture_next_step_or_coaching(self):
        # "step" (singular) must never hijack reasoning/coaching questions.
        for q in ("what is my next step", "take a step toward my goal",
                  "what should I do next", "what's the next step in my plan"):
            self.assertNotEqual(classify_foundational_fact(q), "steps_recent", q)

    def test_steps_fact_is_supported_and_formats(self):
        self.assertIn("steps_recent", SUPPORTED_FACTS)
        # Deterministic value sentence — honest 7d average, no false day-precision.
        s = format_fact_sentence("steps_recent", {"value": 8200})
        self.assertIn("8200", s)
        self.assertIn("week", s.lower())
        # No-data → honest freshness (Law 1), never a fabricated number.
        none = format_fact_sentence("steps_recent", {"status": "unknown"})
        self.assertIn("don't have", none.lower())
