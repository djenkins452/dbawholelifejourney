"""Stabilization sprint — regression tests for the 5 reported trust breaks.

Pure predicate tests (no DB) for the guard vocabulary, plus a light integration
test of the unsafe-mutation filter. The Health Analyze v0 composer is covered by
a DB-backed test that only asserts the safe/empty contract (no fabrication).
"""

from django.test import SimpleTestCase, TestCase

from apps.ai.cognitive_mode import stabilization as stab


class AnalyzeOverrideTests(SimpleTestCase):
    """Fix 1 — Analyze phrasing must be recognized (and beat Retrieve/Execute)."""

    def test_weight_history_is_analyze(self):
        # Example 1: "What do you think about my weight history?" -> Analyze
        self.assertTrue(stab.is_analyze_request("what do you think about my weight history?"))
        self.assertTrue(stab.is_health_context("what do you think about my weight history?"))

    def test_overall_health_is_analyze(self):
        # Example 3: "How am I doing overall with my health?" -> Analyze
        m = "how am i doing overall with my health?"
        self.assertTrue(stab.is_analyze_request(m))
        self.assertTrue(stab.is_health_context(m))

    def test_change_anything_is_analyze(self):
        # Example 4: coaching language -> Analyze (so it can't mutate)
        self.assertTrue(stab.is_analyze_request("do you think i need to change anything?"))

    def test_plain_retrieve_is_not_analyze(self):
        # Must NOT over-trigger on a clean point lookup.
        self.assertFalse(stab.is_analyze_request("what is my current weight?"))

    def test_protein_today_is_not_analyze(self):
        # "how am I doing on protein today" must stay Retrieve (not analyze).
        self.assertFalse(stab.is_analyze_request("how am i doing on protein today?"))


class HealthContextGuardTests(SimpleTestCase):
    """Fix 2 — health context blocks the execute shortcut unless explicit."""

    def test_health_question_is_health_context(self):
        self.assertTrue(stab.is_health_context("how am i doing overall with my health?"))

    def test_explicit_execute_allowed_in_health_context(self):
        m = "what should i do next for my workout?"
        self.assertTrue(stab.is_health_context(m))
        self.assertTrue(stab.is_explicit_execute_request(m))

    def test_non_health_not_blocked(self):
        self.assertFalse(stab.is_health_context("what should i do next?"))

    def test_generic_temporal_words_are_not_health_context(self):
        # Deliberate: "trend"/"history"/"overall" alone are NOT health context
        # (prevents cross-domain bleed into the health package).
        self.assertFalse(stab.is_health_context("what do you think about my spending trends?"))


class MutationGuardTests(SimpleTestCase):
    """Fix 3 — coaching/question language must never mutate state."""

    def test_coaching_question_blocks_mutation(self):
        # Example 4 root: "Do you think I need to change anything?" -> no mutate
        self.assertTrue(stab.should_block_mutation("mutate_task", "do you think i need to change anything?"))

    def test_explicit_imperative_mutation_allowed(self):
        # "push my 3pm to 4" is imperative + explicit -> NOT blocked
        self.assertFalse(stab.should_block_mutation("mutate_task", "push my 3pm meeting to 4"))

    def test_explicit_complete_allowed(self):
        self.assertFalse(stab.should_block_mutation("complete_task", "mark complete the gym task"))

    def test_change_task_phrase_allowed(self):
        # "change task" is explicit; "change anything" is not.
        self.assertFalse(stab.should_block_mutation("mutate_task", "change task title to gym"))
        self.assertTrue(stab.should_block_mutation("mutate_task", "should i change anything?"))

    def test_non_mutation_intent_never_blocked(self):
        self.assertFalse(stab.should_block_mutation("log_weight", "do you think i should?"))

    def test_filter_suppresses_only_unsafe(self):
        class _IR:
            def __init__(self, t):
                self.intent_type = t
        intents = [_IR("mutate_task"), _IR("log_weight")]
        kept, suppressed = stab.filter_unsafe_mutations(intents, "do you think i need to change anything?")
        self.assertEqual([i.intent_type for i in kept], ["log_weight"])
        self.assertEqual([i.intent_type for i in suppressed], ["mutate_task"])

    def test_filter_keeps_imperative_mutation(self):
        class _IR:
            def __init__(self, t):
                self.intent_type = t
        intents = [_IR("mutate_task")]
        kept, suppressed = stab.filter_unsafe_mutations(intents, "delete the gym task")
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(suppressed), 0)


class HealthAnalyzeV0ContractTests(TestCase):
    """Fix 4 — composer is grounded: returns None on no data, never fabricates."""

    def test_returns_none_for_user_with_no_health_data(self):
        from apps.users.models import User
        u = User.objects.create_user(email="stab_v0@test.com", password="x")
        result = stab.build_health_analyze_v0(u)
        # No health data logged -> must fall through (None), not invent a story.
        self.assertIsNone(result)


class KillSwitchTests(SimpleTestCase):
    def test_enabled_by_default(self):
        self.assertTrue(stab.stabilization_enabled())

    def test_disabled_via_setting(self):
        with self.settings(WLJ_BETH_STABILIZATION_ENABLED=False):
            self.assertFalse(stab.stabilization_enabled())
