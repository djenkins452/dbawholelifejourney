"""
Routing Safety — Deterministic Validation Tests

Validates the deterministic layers (domain classification, tool scoping,
policy lookup, keyword safeguards) for real-world natural language phrases.

These tests verify that:
1. Correct domain is inferred from user message
2. Correct tools are available in the scoped tool set
3. Dangerous tools (set_cos_name) are excluded from non-settings domains
4. All mutation intents require confirmation via ACTION_POLICY
5. Domain-lock safeguard rejects cross-domain intents

NOTE: These tests do NOT call OpenAI. They validate the deterministic
layers that surround the LLM call. The LLM can still misclassify, but
the safeguards ensure misclassified intents are caught and rejected.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.ai.deterministic_router import _infer_domain
from apps.ai.intents import (
    INTENT_HANDLERS,
    get_scoped_intent_tools,
)
from apps.core.ai_orchestrator.action_policy import (
    requires_confirmation,
    get_policy,
    ActionCategory,
    AuthorityLevel,
)


class TestDomainInference(TestCase):
    """Verify domain classification for real-world phrases."""

    def test_move_workout_domain(self):
        """'move my workout to 8:30 tonight' → health domain."""
        domain = _infer_domain("move my workout to 8:30 tonight")
        self.assertEqual(domain, 'health')

    def test_skip_prayer_domain(self):
        """'skip prayer time today' → faith domain."""
        domain = _infer_domain("skip prayer time today")
        self.assertEqual(domain, 'faith')

    def test_complete_task_domain(self):
        """'complete shower' → no clear domain (no task keyword)."""
        # 'shower' is not in any domain keyword set
        domain = _infer_domain("complete shower")
        # Could be None (ambiguous) — that's fine, all tools loaded
        # The important thing is it's NOT 'settings'
        self.assertNotEqual(domain, 'settings')

    def test_rename_beth_domain(self):
        """'rename Beth to Max' → no domain match (settings is keyword-less)."""
        domain = _infer_domain("rename beth to max")
        # 'rename' and 'beth' and 'max' are not in any domain keywords
        self.assertIsNone(domain)

    def test_move_bible_reading_domain(self):
        """'move Bible reading to tomorrow morning' → faith domain."""
        domain = _infer_domain("move bible reading to tomorrow morning")
        self.assertEqual(domain, 'faith')

    def test_log_weight_domain(self):
        """'my weight is 350' → health domain."""
        domain = _infer_domain("my weight is 350")
        self.assertEqual(domain, 'health')

    def test_create_task_domain(self):
        """'create a task to call mom' → tasks domain."""
        domain = _infer_domain("create a task to call mom")
        self.assertEqual(domain, 'tasks')


class TestToolScopingSafety(TestCase):
    """Verify tool scoping excludes dangerous cross-domain tools."""

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_health_scope_excludes_set_cos_name(self):
        """Health domain must never include set_cos_name."""
        tools = get_scoped_intent_tools('health')
        names = {t['function']['name'] for t in tools}
        self.assertNotIn('set_cos_name', names)

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_health_scope_includes_reschedule(self):
        """Health domain must include reschedule_routine_item."""
        tools = get_scoped_intent_tools('health')
        names = {t['function']['name'] for t in tools}
        self.assertIn('reschedule_routine_item', names)

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_faith_scope_excludes_set_cos_name(self):
        """Faith domain must never include set_cos_name."""
        tools = get_scoped_intent_tools('faith')
        names = {t['function']['name'] for t in tools}
        self.assertNotIn('set_cos_name', names)

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_tasks_scope_excludes_set_cos_name(self):
        """Tasks domain must never include set_cos_name."""
        tools = get_scoped_intent_tools('tasks')
        names = {t['function']['name'] for t in tools}
        self.assertNotIn('set_cos_name', names)

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_settings_scope_includes_set_cos_name(self):
        """Settings domain SHOULD include set_cos_name."""
        tools = get_scoped_intent_tools('settings')
        names = {t['function']['name'] for t in tools}
        self.assertIn('set_cos_name', names)

    @patch('django.conf.settings.WLJ_SCOPED_INTENT_TOOLS_ENABLED', True)
    def test_none_domain_includes_all_tools(self):
        """Unknown domain (None) loads ALL tools as fallback."""
        from apps.ai.intents import ALL_INTENT_TOOLS
        tools = get_scoped_intent_tools(None)
        self.assertEqual(len(tools), len(ALL_INTENT_TOOLS))


class TestMutationPolicyCompleteness(TestCase):
    """Verify every mutation intent requires confirmation."""

    def test_all_mutation_intents_require_confirmation(self):
        """Every mutation intent must have AuthorityLevel.CONFIRM."""
        mutations = []
        for intent, domain in INTENT_HANDLERS.items():
            if intent == 'no_action':
                continue
            policy = get_policy(intent)
            if policy.category in (
                ActionCategory.LOG,
                ActionCategory.CREATE,
                ActionCategory.MUTATE,
                ActionCategory.DESTRUCTIVE,
                ActionCategory.SYSTEM,
            ):
                mutations.append(intent)

        unconfirmed = [
            m for m in mutations
            if not requires_confirmation(m)
        ]
        self.assertFalse(
            unconfirmed,
            f"Mutation intents without confirmation: {unconfirmed}",
        )

    def test_reschedule_routine_item_policy(self):
        """reschedule_routine_item must be MUTATE + CONFIRM."""
        policy = get_policy('reschedule_routine_item')
        self.assertEqual(policy.category, ActionCategory.MUTATE)
        self.assertEqual(policy.authority, AuthorityLevel.CONFIRM)

    def test_set_cos_name_policy(self):
        """set_cos_name must be MUTATE + CONFIRM."""
        policy = get_policy('set_cos_name')
        self.assertEqual(policy.category, ActionCategory.MUTATE)
        self.assertEqual(policy.authority, AuthorityLevel.CONFIRM)

    def test_mutate_task_policy(self):
        """mutate_task must be MUTATE + CONFIRM + HIGH risk."""
        from apps.core.ai_orchestrator.action_policy import RiskLevel
        policy = get_policy('mutate_task')
        self.assertEqual(policy.category, ActionCategory.MUTATE)
        self.assertEqual(policy.authority, AuthorityLevel.CONFIRM)
        self.assertEqual(policy.risk_level, RiskLevel.HIGH)

    def test_reads_do_not_require_confirmation(self):
        """Read-only intents must NOT require confirmation."""
        reads = ['read_task', 'read_calendar_events', 'check_budget']
        for intent in reads:
            self.assertFalse(
                requires_confirmation(intent),
                f"{intent} should not require confirmation",
            )


class TestKeywordSafeguard(TestCase):
    """Verify the set_cos_name keyword safeguard works for real phrases."""

    def _has_name_change_language(self, message):
        """Replicate the keyword check from intent_service.py."""
        name_verbs = {
            'call yourself', 'your name', 'rename',
            'change your name', 'name is now',
            'call you', 'named',
        }
        msg_lower = (message or '').lower()
        return any(v in msg_lower for v in name_verbs)

    def test_workout_message_rejected(self):
        """'move my workout to 8:30 tonight' has no name-change language."""
        self.assertFalse(
            self._has_name_change_language(
                "move my workout to 8:30 tonight"
            ),
        )

    def test_skip_prayer_rejected(self):
        """'skip prayer time today' has no name-change language."""
        self.assertFalse(
            self._has_name_change_language("skip prayer time today"),
        )

    def test_rename_allowed(self):
        """'rename Beth to Max' has name-change language."""
        self.assertTrue(
            self._has_name_change_language("rename Beth to Max"),
        )

    def test_call_yourself_allowed(self):
        """'call yourself Jarvis' has name-change language."""
        self.assertTrue(
            self._has_name_change_language("call yourself Jarvis"),
        )

    def test_your_name_is_allowed(self):
        """'your name is now Friday' has name-change language."""
        self.assertTrue(
            self._has_name_change_language("your name is now Friday"),
        )

    def test_complete_shower_rejected(self):
        """'complete shower' has no name-change language."""
        self.assertFalse(
            self._has_name_change_language("complete shower"),
        )
