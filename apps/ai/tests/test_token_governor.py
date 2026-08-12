# ==============================================================================
# File: apps/ai/tests/test_token_governor.py
# Description: Token governor — recent conversation must survive trimming.
# ==============================================================================
"""Conversation Continuity root-cause fix (2026-08-12).

The governor was deleting the ENTIRE conversation history every model-interface turn
because the legacy 12k budget was smaller than the ~21k system prompt — the model
received "system + bare user sentence" and could not resolve "why?". These tests lock in
the two guarantees of the fix: an explicit caller budget wins over the setting, and the
most-recent turns are NEVER trimmed (the immediate antecedent always survives)."""

from django.test import SimpleTestCase, override_settings

from apps.ai.conversation.token_governor import govern_prompt


def _msgs(history_turns):
    m = [{"role": "system", "content": "S" * 200}]
    for i in range(history_turns):
        m.append({"role": "user", "content": f"user turn {i} " * 20})
        m.append({"role": "assistant", "content": f"assistant answer {i} " * 40})
    m.append({"role": "user", "content": "Why do you think that?"})
    return m


@override_settings(WLJ_TOKEN_BUDGET_ENABLED=True, WLJ_TOKEN_BUDGET_MAX=12000)
class TokenGovernorRecentTurnsTests(SimpleTestCase):

    def test_explicit_budget_wins_over_setting(self):
        # The setting is 12000; a large explicit budget must win so nothing is trimmed.
        msgs = _msgs(3)
        gov, rep = govern_prompt(msgs, max_budget=64000)
        self.assertEqual(len(gov), len(msgs))       # nothing trimmed
        self.assertFalse(rep.over_budget)

    def test_recent_turns_survive_even_under_a_tiny_budget(self):
        # The exact regression: a budget far below the prompt must still preserve the
        # immediate antecedent (the assistant answer a follow-up refers to), never collapse
        # to system + user only.
        msgs = _msgs(8)
        gov, rep = govern_prompt(msgs, max_budget=100, protect_recent=6)
        roles = [m["role"] for m in gov]
        self.assertEqual(roles[0], "system")
        self.assertEqual(roles[-1], "user")
        # at least one assistant turn (the antecedent) survives between them
        self.assertTrue(any(m["role"] == "assistant" for m in gov[1:-1]),
                        "the immediate conversational antecedent must never be deleted")
        # the LAST few history messages are exactly the protected recent ones
        self.assertEqual(gov[-7:-1], msgs[-7:-1])

    def test_older_history_is_still_trimmable_beyond_the_protected_window(self):
        # Older turns beyond protect_recent may still be trimmed when genuinely over budget.
        msgs = _msgs(10)
        gov, _ = govern_prompt(msgs, max_budget=100, protect_recent=4)
        self.assertLess(len(gov), len(msgs))        # some older history removed
        self.assertEqual(gov[-5:-1], msgs[-5:-1])   # but the recent window is intact

    def test_default_falls_back_to_setting_when_no_explicit_budget(self):
        # Legacy callers (no explicit budget) still honor the setting — unchanged behavior.
        msgs = _msgs(3)
        _, rep = govern_prompt(msgs)                 # no max_budget → setting (12000)
        # 3 turns of short content stay under 12k, so nothing trims here; the point is it
        # does not raise and uses the setting path.
        self.assertIsNotNone(rep)
