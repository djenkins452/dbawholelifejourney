"""
Phase 6 — Degraded-Mode Tests.

Tests:
1. LLM down: safe plain-language fallback, no crash, state preserved.
2. DB down on write: sentinel patterns protect user flow, safe message.
3. Cache/Redis down: scheduler safe (DB token), context assembly completes.
4. No user-facing technical jargon in any degraded message.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.db import OperationalError
from django.test import TestCase, override_settings
from django.utils import timezone


def _create_test_user(email='degraded@example.com'):
    from apps.users.models import User, UserPreferences

    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user,
        defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_conversation(user):
    from apps.ai.models import AssistantConversation

    return AssistantConversation.objects.create(
        user=user,
        title='Test conversation',
        metadata={},
    )


# Forbidden tokens that must NEVER appear in user-facing messages
FORBIDDEN_TOKENS = [
    'CPI', 'density', 'probability', '0.',
    'breach_risk', 'compression_score', 'erosion_score',
    'collision_score', 'pressure_index',
    'select_for_update', 'transaction', 'deadlock',
    'Redis', 'DB token', 'SAME anomaly',
    'OperationalError', 'DatabaseError', 'IntegrityError',
]


# =========================================================================
# 6.7 — LLM DOWN FALLBACK
# =========================================================================


class LLMDownFallbackTests(TestCase):
    """Simulate OpenAI timeout/None/error."""

    def test_llm_timeout_returns_safe_fallback(self):
        """LLM timeout returns plain-language fallback."""
        from apps.core.blueprint.concurrency import safe_llm_call

        def failing_llm():
            raise TimeoutError("OpenAI request timed out")

        result = safe_llm_call(failing_llm)

        self.assertTrue(result['degraded'])
        self.assertIsNotNone(result['response'])
        self.assertIsNotNone(result['message'])
        # Verify plain language — no jargon
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, result['response'])
            self.assertNotIn(token, result['message'])

    def test_llm_returns_none_uses_fallback(self):
        """LLM returning None triggers fallback."""
        from apps.core.blueprint.concurrency import safe_llm_call

        def none_llm():
            return None

        result = safe_llm_call(none_llm)
        self.assertTrue(result['degraded'])
        self.assertIsNotNone(result['response'])

    def test_llm_error_returns_custom_fallback(self):
        """Custom fallback message is used when provided."""
        from apps.core.blueprint.concurrency import safe_llm_call

        def error_llm():
            raise ConnectionError("API unreachable")

        custom_msg = "I'll have better suggestions next time."
        result = safe_llm_call(error_llm, fallback_response=custom_msg)

        self.assertTrue(result['degraded'])
        self.assertEqual(result['response'], custom_msg)

    def test_llm_success_no_degradation(self):
        """Successful LLM call returns normal response."""
        from apps.core.blueprint.concurrency import safe_llm_call

        def good_llm():
            return "Here is a great recommendation."

        result = safe_llm_call(good_llm)
        self.assertFalse(result['degraded'])
        self.assertEqual(result['response'], "Here is a great recommendation.")
        self.assertIsNone(result['message'])

    def test_commitment_state_preserved_on_llm_failure(self):
        """Commitment state is not affected by LLM failure."""
        from apps.core.ai_orchestrator.commitment_contract import (
            CommitmentData,
            create_db_commitment,
        )
        from apps.core.blueprint.models import Commitment

        user = _create_test_user('llm-preserve@example.com')
        conversation = _create_conversation(user)

        # Create commitment
        cd = CommitmentData(
            normalized_text='Survive LLM failure',
            commitment_type='DO',
            time_boundary=timezone.now() + timedelta(hours=2),
            done_definition='Test complete',
        )
        db_commit = create_db_commitment(user, cd, conversation, 'CLEAN')
        self.assertIsNotNone(db_commit)

        # Simulate LLM failure during response generation
        from apps.core.blueprint.concurrency import safe_llm_call

        def failing_llm():
            raise Exception("LLM is down")

        safe_llm_call(failing_llm)

        # Verify commitment is still intact
        db_commit.refresh_from_db()
        self.assertEqual(db_commit.status, 'pending')
        self.assertEqual(db_commit.normalized_text, 'Survive LLM failure')

    def test_degraded_llm_informs_user(self):
        """When response is materially degraded, user sees one-sentence note."""
        from apps.core.blueprint.concurrency import (
            DEGRADED_MSG_LIMITED_MODE,
            safe_llm_call,
        )

        def failing_llm():
            raise Exception("API error")

        result = safe_llm_call(failing_llm)
        self.assertEqual(result['message'], DEGRADED_MSG_LIMITED_MODE)
        # Verify it's plain language
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, result['message'])


# =========================================================================
# 6.8 — DB DOWN ON WRITE
# =========================================================================


class DBDownFallbackTests(TestCase):
    """Simulate DB write failure during commitment and protective log saves."""

    def test_commitment_save_failure_returns_safe_result(self):
        """DB failure on commitment save returns degraded result."""
        from apps.core.blueprint.concurrency import safe_db_write

        def failing_write():
            raise OperationalError("database is locked")

        result = safe_db_write(failing_write)

        self.assertFalse(result['success'])
        self.assertTrue(result['degraded'])
        self.assertIsNotNone(result['message'])
        # Verify plain language
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, result['message'])

    def test_protective_log_failure_does_not_crash(self):
        """Protective action log write failure is swallowed."""
        from apps.core.blueprint.concurrency import safe_db_write

        def failing_log():
            raise OperationalError("connection reset")

        result = safe_db_write(failing_log)

        self.assertFalse(result['success'])
        self.assertTrue(result['degraded'])
        self.assertIsNone(result['result'])

    def test_successful_db_write(self):
        """Successful DB write returns normal result."""
        from apps.core.blueprint.concurrency import safe_db_write

        def good_write():
            return "saved_object"

        result = safe_db_write(good_write)
        self.assertTrue(result['success'])
        self.assertFalse(result['degraded'])
        self.assertEqual(result['result'], 'saved_object')
        self.assertIsNone(result['message'])

    def test_no_partial_corrupt_state_on_db_failure(self):
        """DB failure during commitment create leaves no partial records."""
        from apps.core.blueprint.models import Commitment

        user = _create_test_user('db-fail@example.com')
        initial_count = Commitment.objects.filter(user=user).count()

        # Simulate failure inside create_db_commitment
        with patch(
            'apps.core.blueprint.models.Commitment.objects.create',
            side_effect=OperationalError("connection lost"),
        ):
            from apps.core.ai_orchestrator.commitment_contract import (
                CommitmentData,
                create_db_commitment,
            )
            from apps.ai.models import AssistantConversation

            conversation = _create_conversation(user)
            cd = CommitmentData(
                normalized_text='Should not persist',
                commitment_type='DO',
                time_boundary=timezone.now() + timedelta(hours=2),
                done_definition='',
            )
            result = create_db_commitment(user, cd, conversation, 'CLEAN')

        self.assertIsNone(result)
        # No new commitment records
        final_count = Commitment.objects.filter(user=user).count()
        self.assertEqual(initial_count, final_count)


# =========================================================================
# 6.9 — CACHE/REDIS DOWN
# =========================================================================


class CacheDownFallbackTests(TestCase):
    """Simulate Redis/cache unavailable."""

    def test_cache_read_failure_returns_fallback(self):
        """Cache read failure returns fallback value."""
        from apps.core.blueprint.concurrency import safe_cache_read

        def failing_cache():
            raise ConnectionError("Redis unavailable")

        result = safe_cache_read(failing_cache, fallback={'default': 'data'})

        self.assertTrue(result['degraded'])
        self.assertEqual(result['value'], {'default': 'data'})

    def test_cache_read_success(self):
        """Successful cache read returns cached value."""
        from apps.core.blueprint.concurrency import safe_cache_read

        def good_cache():
            return {'cached': 'value'}

        result = safe_cache_read(good_cache)
        self.assertFalse(result['degraded'])
        self.assertEqual(result['value'], {'cached': 'value'})

    def test_cache_returns_none_uses_fallback(self):
        """Cache returning None uses fallback."""
        from apps.core.blueprint.concurrency import safe_cache_read

        def empty_cache():
            return None

        result = safe_cache_read(empty_cache, fallback='default')
        self.assertFalse(result['degraded'])
        self.assertEqual(result['value'], 'default')

    def test_scheduler_safe_with_db_token_when_cache_down(self):
        """With cache down, DB token still prevents double-run."""
        from apps.core.ai_scheduler.scheduler_models import EngineRunToken

        # Simulate cache-down scenario: DB token is the only protection
        window = '2026-02-23T15:00'

        # First acquire succeeds
        token1 = EngineRunToken.acquire('sweep_engine', window)
        self.assertIsNotNone(token1)

        # Second acquire blocked by DB constraint
        token2 = EngineRunToken.acquire('sweep_engine', window)
        self.assertIsNone(token2)

    def test_cache_down_does_not_expose_technical_info(self):
        """Cache failure message (if any) has no technical jargon."""
        from apps.core.blueprint.concurrency import safe_cache_read

        def failing_cache():
            raise ConnectionError("Redis connection refused at 127.0.0.1:6379")

        result = safe_cache_read(failing_cache, fallback=None)

        # message is None by default (only notify if material impact)
        # When message IS present, verify no jargon
        if result['message']:
            for token in FORBIDDEN_TOKENS:
                self.assertNotIn(token, result['message'])


# =========================================================================
# USER-FACING LANGUAGE COMPLIANCE
# =========================================================================


class UserFacingLanguageTests(TestCase):
    """Verify all degraded-mode messages are plain language."""

    def test_all_degraded_messages_are_plain_language(self):
        """Every constant message uses human-readable language."""
        from apps.core.blueprint.concurrency import (
            DEGRADED_MSG_LIMITED_MODE,
            DEGRADED_MSG_SAVE_RETRY,
            DEGRADED_MSG_SLOW_RESPONSE,
            DEGRADED_MSG_TEMPORARY_ISSUE,
        )

        messages = [
            DEGRADED_MSG_SAVE_RETRY,
            DEGRADED_MSG_LIMITED_MODE,
            DEGRADED_MSG_TEMPORARY_ISSUE,
            DEGRADED_MSG_SLOW_RESPONSE,
        ]

        for msg in messages:
            self.assertIsInstance(msg, str)
            self.assertGreater(len(msg), 10)
            for token in FORBIDDEN_TOKENS:
                self.assertNotIn(
                    token, msg,
                    f"Found forbidden token '{token}' in message: {msg}",
                )

    def test_safe_llm_fallback_has_no_jargon(self):
        """Default LLM fallback response is human-readable."""
        from apps.core.blueprint.concurrency import safe_llm_call

        def bad_llm():
            raise Exception("500 Internal Server Error from api.openai.com")

        result = safe_llm_call(bad_llm)
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, result['response'])

    def test_safe_db_write_fallback_has_no_jargon(self):
        """DB write fallback message is human-readable."""
        from apps.core.blueprint.concurrency import safe_db_write

        def bad_write():
            raise OperationalError("connection pool exhausted")

        result = safe_db_write(bad_write)
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, result['message'])
