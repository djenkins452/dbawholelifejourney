"""
Tests for apps/ai/cos_mode_router.py — deterministic keyword resolver.

The router MUST NOT use any LLM. It is a pure regex matcher that maps a
raw user message to one of three CoS decision modes, or None when the
message does not match a known mode.
"""

from django.test import SimpleTestCase

from apps.ai.cos_mode_router import (
    VALID_MODES,
    normalize_mode,
    resolve_cos_mode,
)


class ResolveCosModeTests(SimpleTestCase):

    def test_execution_phrasings(self):
        for q in [
            "what should I do",
            "What should I do right now?",
            "what's next?",
            "WHAT IS NEXT",
            "what now?",
            "next action please",
            "next step",
        ]:
            self.assertEqual(
                resolve_cos_mode(q), "execution",
                f"Expected execution for: {q!r}",
            )

    def test_risk_phrasings(self):
        for q in [
            "what's my biggest risk?",
            "What is wrong",
            "what's wrong right now",
            "I'm at risk of what?",
            "what should I worry about",
            "biggest concern",
            "biggest problem",
            "top risk",
        ]:
            self.assertEqual(
                resolve_cos_mode(q), "risk",
                f"Expected risk for: {q!r}",
            )

    def test_fix_phrasings(self):
        for q in [
            "what should I fix",
            "what should I fix first",
            "I need to clean up",
            "cleanup time",
            "I'm behind on stuff",
            "falling behind",
            "fix backlog",
            "catch up",
        ]:
            self.assertEqual(
                resolve_cos_mode(q), "fix",
                f"Expected fix for: {q!r}",
            )

    def test_no_match_returns_none(self):
        for q in [
            "log my weight",
            "how was my workout",
            "tell me about my goals",
            "",
            None,
            "   ",
            "schedule a meeting tomorrow",
        ]:
            self.assertIsNone(
                resolve_cos_mode(q),
                f"Expected None for: {q!r}",
            )

    def test_word_boundary_avoids_false_positives(self):
        """'Affix' / 'prefix' must NOT trigger fix mode."""
        self.assertIsNone(resolve_cos_mode("Tell me about the prefix"))
        self.assertIsNone(resolve_cos_mode("Affix this to my journal"))

    def test_fix_takes_precedence_over_risk(self):
        """Per CoS Strict Mode Isolation: FIX > RISK > EXECUTION.
        'biggest risk and what to fix' — fix wins."""
        result = resolve_cos_mode(
            "what's my biggest risk and what to fix",
        )
        self.assertEqual(result, "fix")

    def test_fix_takes_precedence_over_execution(self):
        """'what should I fix' includes 'what should I' — fix wins over
        the broader 'what should I do' phrasing."""
        result = resolve_cos_mode("what should I fix first today")
        self.assertEqual(result, "fix")

    def test_risk_takes_precedence_over_execution(self):
        """When fix doesn't match but risk does, risk wins over execution."""
        result = resolve_cos_mode("what's my biggest risk right now")
        self.assertEqual(result, "risk")

    def test_status_queries_default_to_execution(self):
        """Per spec: generic status queries default to Execution mode
        so the LLM never gets to compose a blended response."""
        for q in [
            "How am I doing?",
            "Where am I at?",
            "Status",
            "What's going on",
            "Update me",
            "Give me a status",
            "Walk me through my day",
            "What's my situation",
            "Brief me",
            "Where do I stand",
        ]:
            self.assertEqual(
                resolve_cos_mode(q), "execution",
                f"Status query must default to execution: {q!r}",
            )


class NormalizeModeTests(SimpleTestCase):

    def test_known_modes_pass_through(self):
        for m in VALID_MODES:
            self.assertEqual(normalize_mode(m), m)
            self.assertEqual(normalize_mode(m.upper()), m)
            self.assertEqual(normalize_mode(f"  {m}  "), m)

    def test_unknown_defaults_to_execution(self):
        self.assertEqual(normalize_mode("mystery"), "execution")
        self.assertEqual(normalize_mode(""), "execution")
        self.assertEqual(normalize_mode(None), "execution")
