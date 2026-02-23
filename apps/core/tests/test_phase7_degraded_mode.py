"""
Phase 7 — Degraded Mode Tests.

Covers:
    1. LLM timeout → safe fallback
    2. DB write failure during commitment save
    3. Redis/cache unavailable
    4. Validator crash path verified

These tests verify that the system degrades gracefully when external
dependencies fail, never breaking user flow.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_degraded_mode.py
"""

import datetime as dt
from unittest.mock import patch, MagicMock

from django.db import OperationalError, DatabaseError
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='degraded-p7@example.com'):
    """Create a test user with preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


# =========================================================================
# 1) LLM TIMEOUT → SAFE FALLBACK
# =========================================================================


class LLMTimeoutFallbackTests(TestCase):
    """Test safe_llm_call handles LLM failures gracefully."""

    def setUp(self):
        self.user = _create_test_user('llm-timeout@example.com')

    def test_llm_timeout_returns_fallback(self):
        """LLM call that raises returns default fallback."""
        from apps.core.blueprint.concurrency import (
            DEGRADED_MSG_LIMITED_MODE,
            safe_llm_call,
        )

        def failing_llm():
            raise TimeoutError('LLM timed out')

        result = safe_llm_call(failing_llm)
        self.assertTrue(result['degraded'])
        self.assertIsNotNone(result['response'])
        self.assertEqual(result['message'], DEGRADED_MSG_LIMITED_MODE)

    def test_llm_returns_none_treated_as_degraded(self):
        """LLM returning None is treated as degraded."""
        from apps.core.blueprint.concurrency import safe_llm_call

        result = safe_llm_call(lambda: None)
        self.assertTrue(result['degraded'])
        self.assertIsNotNone(result['response'])

    def test_llm_success_returns_response(self):
        """Successful LLM call returns the response."""
        from apps.core.blueprint.concurrency import safe_llm_call

        result = safe_llm_call(lambda: 'Good response')
        self.assertFalse(result['degraded'])
        self.assertEqual(result['response'], 'Good response')
        self.assertIsNone(result['message'])

    def test_custom_fallback_response_used(self):
        """Custom fallback is used when LLM fails."""
        from apps.core.blueprint.concurrency import safe_llm_call

        custom = 'Custom fallback text'
        result = safe_llm_call(
            lambda: (_ for _ in ()).throw(Exception('fail')),
            fallback_response=custom,
        )
        self.assertTrue(result['degraded'])
        self.assertEqual(result['response'], custom)

    def test_llm_exception_types_all_caught(self):
        """Various exception types are all caught gracefully."""
        from apps.core.blueprint.concurrency import safe_llm_call

        exceptions = [
            TimeoutError('timeout'),
            ConnectionError('connection refused'),
            RuntimeError('runtime error'),
            ValueError('value error'),
            Exception('generic'),
        ]

        for exc in exceptions:
            result = safe_llm_call(
                MagicMock(side_effect=exc),
            )
            self.assertTrue(result['degraded'],
                            f"Failed for {type(exc).__name__}")

    def test_llm_with_args_passes_through(self):
        """Arguments are passed to the LLM function."""
        from apps.core.blueprint.concurrency import safe_llm_call

        def llm_fn(prompt, temperature=0.7):
            return f'Response to: {prompt} at {temperature}'

        result = safe_llm_call(llm_fn, 'Hello', temperature=0.5)
        self.assertFalse(result['degraded'])
        self.assertEqual(result['response'], 'Response to: Hello at 0.5')


# =========================================================================
# 2) DB WRITE FAILURE DURING COMMITMENT SAVE
# =========================================================================


class DBWriteFailureTests(TestCase):
    """Test safe_db_write handles DB failures gracefully."""

    def setUp(self):
        self.user = _create_test_user('db-fail@example.com')

    def test_db_write_operational_error_degrades(self):
        """OperationalError during write enters degraded mode."""
        from apps.core.blueprint.concurrency import (
            DEGRADED_MSG_TEMPORARY_ISSUE,
            safe_db_write,
        )

        def failing_write():
            raise OperationalError('DB connection lost')

        result = safe_db_write(failing_write)
        self.assertFalse(result['success'])
        self.assertTrue(result['degraded'])
        self.assertEqual(result['message'], DEGRADED_MSG_TEMPORARY_ISSUE)
        self.assertIsNone(result['result'])

    def test_db_write_database_error_degrades(self):
        """DatabaseError during write enters degraded mode."""
        from apps.core.blueprint.concurrency import safe_db_write

        def failing_write():
            raise DatabaseError('constraint violation')

        result = safe_db_write(failing_write)
        self.assertFalse(result['success'])
        self.assertTrue(result['degraded'])

    def test_db_write_unexpected_error_degrades(self):
        """Unexpected exceptions also degrade gracefully."""
        from apps.core.blueprint.concurrency import safe_db_write

        def failing_write():
            raise RuntimeError('unexpected error')

        result = safe_db_write(failing_write)
        self.assertFalse(result['success'])
        self.assertTrue(result['degraded'])

    def test_db_write_success(self):
        """Successful DB write returns result."""
        from apps.core.blueprint.concurrency import safe_db_write

        def success_write():
            return {'id': 42, 'saved': True}

        result = safe_db_write(success_write)
        self.assertTrue(result['success'])
        self.assertFalse(result['degraded'])
        self.assertIsNone(result['message'])
        self.assertEqual(result['result'], {'id': 42, 'saved': True})

    def test_commitment_save_failure_handled(self):
        """Commitment DB write failure handled through safe_db_write."""
        from apps.core.blueprint.concurrency import safe_db_write

        def create_commitment():
            raise OperationalError('Disk full')

        result = safe_db_write(create_commitment)
        self.assertFalse(result['success'])
        self.assertTrue(result['degraded'])


# =========================================================================
# 3) REDIS/CACHE UNAVAILABLE
# =========================================================================


class CacheUnavailableTests(TestCase):
    """Test safe_cache_read handles cache failures gracefully."""

    def setUp(self):
        self.user = _create_test_user('cache-fail@example.com')

    def test_cache_unavailable_returns_fallback(self):
        """Cache read failure returns the fallback value."""
        from apps.core.blueprint.concurrency import safe_cache_read

        def failing_cache():
            raise ConnectionError('Redis unavailable')

        result = safe_cache_read(failing_cache, fallback={'default': True})
        self.assertTrue(result['degraded'])
        self.assertEqual(result['value'], {'default': True})

    def test_cache_returns_none_uses_fallback(self):
        """Cache returning None uses fallback (not degraded)."""
        from apps.core.blueprint.concurrency import safe_cache_read

        result = safe_cache_read(lambda: None, fallback='default_value')
        self.assertFalse(result['degraded'])
        self.assertEqual(result['value'], 'default_value')

    def test_cache_success_returns_value(self):
        """Successful cache read returns the cached value."""
        from apps.core.blueprint.concurrency import safe_cache_read

        result = safe_cache_read(lambda: {'cached': 'data'})
        self.assertFalse(result['degraded'])
        self.assertEqual(result['value'], {'cached': 'data'})
        self.assertIsNone(result['message'])

    def test_cache_failure_no_material_impact_message(self):
        """Cache failure doesn't notify user (no material impact by default)."""
        from apps.core.blueprint.concurrency import safe_cache_read

        result = safe_cache_read(
            MagicMock(side_effect=Exception('cache down')),
            fallback=None,
        )
        self.assertTrue(result['degraded'])
        self.assertIsNone(result['message'])  # No notification

    def test_cache_various_exceptions_handled(self):
        """Various cache exception types all handled."""
        from apps.core.blueprint.concurrency import safe_cache_read

        exceptions = [
            ConnectionError('refused'),
            TimeoutError('timeout'),
            OSError('IO error'),
            Exception('generic'),
        ]

        for exc in exceptions:
            result = safe_cache_read(
                MagicMock(side_effect=exc),
                fallback='safe',
            )
            self.assertTrue(result['degraded'],
                            f"Failed for {type(exc).__name__}")
            self.assertEqual(result['value'], 'safe')


# =========================================================================
# 4) VALIDATOR CRASH PATH VERIFIED
# =========================================================================


class ValidatorCrashPathTests(TestCase):
    """Test the full validator crash degraded-mode path."""

    def setUp(self):
        self.user = _create_test_user('validator-crash@example.com')

    def test_validator_crash_returns_safe_not_original(self):
        """Validator crash NEVER returns the original response."""
        from apps.core.ai_governance.validator_gate import (
            VALIDATOR_CRASH_RESPONSE,
            validate_response,
        )

        original = "This is a potentially problematic response with tier 1."

        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=Exception('crash'),
        ):
            result = validate_response(original, user=self.user)

        self.assertNotEqual(result['response'], original)
        self.assertEqual(result['response'], VALIDATOR_CRASH_RESPONSE)

    def test_validator_crash_never_silently_bypasses(self):
        """Validator crash is always detected — never silent bypass."""
        from apps.core.ai_governance.validator_gate import validate_response

        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=Exception('crash'),
        ):
            result = validate_response('test', user=self.user)

        self.assertTrue(result['blocked'])
        self.assertTrue(
            any('VALIDATOR_CRASH' in v for v in result['violations']),
        )

    def test_validator_crash_logs_self_error(self):
        """Validator crash logs a Level 3 SelfError."""
        from apps.core.ai_governance.validator_gate import validate_response

        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=Exception('test crash'),
        ), patch(
            'apps.core.ai_governance.validator_gate._handle_validator_crash',
        ) as mock_handler:
            validate_response('test', user=self.user)
            mock_handler.assert_called_once()

    def test_degraded_messages_are_plain_language(self):
        """All degraded-mode messages use plain language (no jargon)."""
        from apps.core.blueprint.concurrency import (
            DEGRADED_MSG_LIMITED_MODE,
            DEGRADED_MSG_SAVE_RETRY,
            DEGRADED_MSG_SLOW_RESPONSE,
            DEGRADED_MSG_TEMPORARY_ISSUE,
        )

        jargon_terms = [
            'transaction', 'lock', 'mutex', 'deadlock', 'SELECT',
            'query', 'exception', 'traceback', 'stack', 'rollback',
            'OperationalError', 'DatabaseError', 'timeout_ms',
        ]

        for msg in [
            DEGRADED_MSG_SAVE_RETRY,
            DEGRADED_MSG_LIMITED_MODE,
            DEGRADED_MSG_TEMPORARY_ISSUE,
            DEGRADED_MSG_SLOW_RESPONSE,
        ]:
            for term in jargon_terms:
                self.assertNotIn(
                    term.lower(), msg.lower(),
                    f"Jargon '{term}' found in degraded message: {msg}",
                )

    def test_pressure_snapshot_failure_handled(self):
        """update_pressure_snapshot failure returns None, no crash."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        user = _create_test_user('snap-fail@example.com')

        with patch(
            'apps.core.blueprint.pressure_engine.compute_pressure_index',
            side_effect=Exception('computation failed'),
        ):
            snapshot = update_pressure_snapshot(user, horizon_days=7)

        self.assertIsNone(snapshot)
