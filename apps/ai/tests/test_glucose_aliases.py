# ==============================================================================
# File: apps/ai/tests/test_glucose_aliases.py
# Description: Defect 1 — BG / blood-glucose / sugar vocabulary resolves
#   deterministically to the glucose fact (never "assistant unavailable"). Pure
#   deterministic vocabulary, not an LLM task. Origin: real Beth conversation.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.foundational_facts import classify_foundational_fact


class GlucoseAliasTests(SimpleTestCase):
    def test_bg_and_synonyms_resolve_to_glucose(self):
        for q in ("What is my BG?", "what's my bg?", "my bg today", "BG?",
                  "What is my blood glucose?", "What is my blood sugar?",
                  "how is my sugar", "What is my glucose?"):
            self.assertEqual(classify_foundational_fact(q), "last_glucose_reading", q)

    def test_does_not_false_match_unrelated_bg_substrings(self):
        for q in ("debugging my app", "what is in this subgroup"):
            self.assertNotEqual(classify_foundational_fact(q), "last_glucose_reading", q)
