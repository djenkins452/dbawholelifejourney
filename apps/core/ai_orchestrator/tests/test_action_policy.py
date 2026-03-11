"""
Tests for the centralized Action Policy module.

Covers:
- Policy coverage: every registered intent has a policy entry
- Risk level classification
- Authority level determination
- Confirmation requirements
- Destructive action detection
- Rate limiter behavior
- PASSTHROUGH_INTENTS backward compatibility
"""

from django.test import TestCase, override_settings

from apps.core.ai_orchestrator.action_policy import (
    ACTION_POLICY,
    ActionCategory,
    ActionPolicy,
    ActionRateLimiter,
    AuthorityLevel,
    PASSTHROUGH_INTENTS,
    RiskLevel,
    get_policy,
    get_risk_level,
    is_destructive,
    requires_confirmation,
)


class ActionPolicyCoverageTests(TestCase):
    """Every registered intent in the codebase should have a policy entry."""

    def test_policy_dict_is_not_empty(self):
        self.assertGreater(len(ACTION_POLICY), 0)

    def test_all_policies_are_action_policy_instances(self):
        for intent, policy in ACTION_POLICY.items():
            self.assertIsInstance(
                policy, ActionPolicy,
                f"Policy for '{intent}' is not an ActionPolicy instance",
            )

    def test_all_policies_have_valid_enums(self):
        for intent, policy in ACTION_POLICY.items():
            self.assertIsInstance(policy.category, ActionCategory, intent)
            self.assertIsInstance(policy.risk_level, RiskLevel, intent)
            self.assertIsInstance(policy.authority, AuthorityLevel, intent)

    def test_passthrough_intents_is_frozenset(self):
        self.assertIsInstance(PASSTHROUGH_INTENTS, frozenset)

    def test_passthrough_intents_have_auto_authority(self):
        """All passthrough intents should have AUTO authority."""
        for intent in PASSTHROUGH_INTENTS:
            policy = get_policy(intent)
            self.assertEqual(
                policy.authority, AuthorityLevel.AUTO,
                f"Passthrough intent '{intent}' should have AUTO authority",
            )


class RiskLevelTests(TestCase):
    """Test risk level classification."""

    def test_read_intents_are_none_risk(self):
        read_intents = [
            i for i, p in ACTION_POLICY.items()
            if p.category == ActionCategory.READ
        ]
        for intent in read_intents:
            self.assertEqual(
                get_risk_level(intent), RiskLevel.NONE,
                f"Read intent '{intent}' should have NONE risk",
            )

    def test_destructive_intents_are_high_risk(self):
        destructive_intents = [
            i for i, p in ACTION_POLICY.items()
            if p.category == ActionCategory.DESTRUCTIVE
        ]
        for intent in destructive_intents:
            risk = get_risk_level(intent)
            self.assertIn(
                risk, (RiskLevel.HIGH, RiskLevel.CRITICAL),
                f"Destructive intent '{intent}' should be HIGH or CRITICAL risk",
            )


class RequiresConfirmationTests(TestCase):
    """Test confirmation requirements."""

    def test_read_intents_do_not_require_confirmation(self):
        read_intents = [
            i for i, p in ACTION_POLICY.items()
            if p.category == ActionCategory.READ
        ]
        for intent in read_intents:
            self.assertFalse(
                requires_confirmation(intent),
                f"Read intent '{intent}' should not require confirmation",
            )

    def test_create_intents_require_confirmation(self):
        create_intents = [
            i for i, p in ACTION_POLICY.items()
            if p.category == ActionCategory.CREATE
        ]
        for intent in create_intents:
            self.assertTrue(
                requires_confirmation(intent),
                f"Create intent '{intent}' should require confirmation",
            )

    def test_destructive_intents_require_confirmation(self):
        destructive_intents = [
            i for i, p in ACTION_POLICY.items()
            if p.category == ActionCategory.DESTRUCTIVE
        ]
        for intent in destructive_intents:
            self.assertTrue(
                requires_confirmation(intent),
                f"Destructive intent '{intent}' should require confirmation",
            )

    def test_unknown_intent_requires_confirmation_by_default(self):
        """Unknown intents should default to requiring confirmation."""
        self.assertTrue(requires_confirmation('totally_unknown_intent'))


class IsDestructiveTests(TestCase):
    """Test destructive action detection."""

    def test_delete_task_is_destructive(self):
        self.assertTrue(is_destructive('mutate_task', {'action': 'delete'}))

    def test_update_task_is_not_destructive(self):
        self.assertFalse(is_destructive('mutate_task', {'action': 'update'}))

    def test_mutate_task_no_action_not_destructive(self):
        self.assertFalse(is_destructive('mutate_task', {}))

    def test_delete_event_is_destructive(self):
        self.assertTrue(
            is_destructive('mutate_calendar_event', {'action': 'delete'})
        )

    def test_log_intent_not_destructive(self):
        self.assertFalse(is_destructive('log_heart_rate', {}))

    def test_read_intent_not_destructive(self):
        self.assertFalse(is_destructive('search_tasks', {}))

    def test_unknown_intent_defaults_not_destructive(self):
        self.assertFalse(is_destructive('unknown_thing', {}))


class GetPolicyTests(TestCase):
    """Test policy lookup."""

    def test_known_intent_returns_policy(self):
        policy = get_policy('log_heart_rate')
        self.assertIsInstance(policy, ActionPolicy)
        self.assertEqual(policy.category, ActionCategory.LOG)

    def test_unknown_intent_returns_default(self):
        policy = get_policy('completely_unknown')
        self.assertIsInstance(policy, ActionPolicy)
        # Default should be cautious: CONFIRM authority
        self.assertEqual(policy.authority, AuthorityLevel.CONFIRM)

    def test_get_policy_returns_correct_risk(self):
        policy = get_policy('read_task')
        self.assertEqual(policy.risk_level, RiskLevel.NONE)


class ActionRateLimiterTests(TestCase):
    """Test rate limiter behavior."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            email='ratelimit@test.com', password='test123',
        )

    def test_first_action_is_allowed(self):
        allowed, reason = ActionRateLimiter.check_rate_limit(
            self.user, 'log_heart_rate',
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, '')

    def test_general_rate_limit_blocks_after_threshold(self):
        """After MAX_GENERAL_PER_MINUTE actions, should block."""
        for _ in range(ActionRateLimiter.MAX_GENERAL_PER_MINUTE):
            allowed, _ = ActionRateLimiter.check_rate_limit(
                self.user, 'log_heart_rate',
            )
            self.assertTrue(allowed)

        allowed, reason = ActionRateLimiter.check_rate_limit(
            self.user, 'log_heart_rate',
        )
        self.assertFalse(allowed)
        self.assertIn('lot of actions', reason)

    def test_destructive_rate_limit_is_stricter(self):
        """Destructive actions have a lower per-minute limit."""
        for _ in range(ActionRateLimiter.MAX_DESTRUCTIVE_PER_MINUTE):
            allowed, _ = ActionRateLimiter.check_rate_limit(
                self.user, 'mutate_task', {'action': 'delete'},
            )
            self.assertTrue(allowed)

        allowed, reason = ActionRateLimiter.check_rate_limit(
            self.user, 'mutate_task', {'action': 'delete'},
        )
        self.assertFalse(allowed)
        self.assertIn('changes quickly', reason)
