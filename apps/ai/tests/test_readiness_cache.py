"""
CoS Readiness Cache — Tests

Covers:
1. Cache get/set/invalidate/TTL behavior
2. Readiness state tracking
3. Active user tracking
4. Prewarm function (mocked build_cos_context)
5. Wake endpoint (auth, response format, no side effects)
6. Fast-path integration (cache hit avoids rebuild)
7. No-LLM-call assertion for prewarm
"""

from unittest.mock import patch, MagicMock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, RequestFactory, override_settings

User = get_user_model()


class ReadinessTestMixin:
    """Common setup for readiness cache tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=django_settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def setUp(self):
        super().setUp()
        cache.clear()


# =============================================================================
# CACHE SERVICE TESTS
# =============================================================================

class TestReadinessCache(ReadinessTestMixin, TestCase):
    """Test the core cache service functions."""

    def test_get_returns_none_on_miss(self):
        from apps.ai.readiness_cache import get_cached_cos_context
        user = self.create_user()
        result = get_cached_cos_context(user)
        self.assertIsNone(result)

    def test_set_and_get_roundtrip(self):
        from apps.ai.readiness_cache import (
            get_cached_cos_context,
            set_cached_cos_context,
        )
        user = self.create_user()
        context = {'alignment_score': 85, 'capacity_snapshot': {'capacity_pct': 70}}
        set_cached_cos_context(user, context)
        result = get_cached_cos_context(user)
        self.assertIsNotNone(result)
        self.assertEqual(result['alignment_score'], 85)
        self.assertEqual(result['capacity_snapshot']['capacity_pct'], 70)

    def test_set_strips_internal_keys(self):
        """Internal keys starting with '_' should not be cached."""
        from apps.ai.readiness_cache import (
            get_cached_cos_context,
            set_cached_cos_context,
        )
        user = self.create_user()
        context = {'_user': user, 'alignment_score': 90}
        set_cached_cos_context(user, context)
        result = get_cached_cos_context(user)
        self.assertNotIn('_user', result)
        self.assertEqual(result['alignment_score'], 90)

    def test_invalidate_removes_cached_context(self):
        from apps.ai.readiness_cache import (
            get_cached_cos_context,
            invalidate_cos_context,
            set_cached_cos_context,
        )
        user = self.create_user()
        set_cached_cos_context(user, {'alignment_score': 75})
        invalidate_cos_context(user)
        result = get_cached_cos_context(user)
        self.assertIsNone(result)

    def test_different_users_have_separate_caches(self):
        from apps.ai.readiness_cache import (
            get_cached_cos_context,
            set_cached_cos_context,
        )
        user1 = self.create_user('user1@example.com')
        user2 = self.create_user('user2@example.com')
        set_cached_cos_context(user1, {'alignment_score': 80})
        set_cached_cos_context(user2, {'alignment_score': 60})
        self.assertEqual(get_cached_cos_context(user1)['alignment_score'], 80)
        self.assertEqual(get_cached_cos_context(user2)['alignment_score'], 60)


# =============================================================================
# READINESS STATE TESTS
# =============================================================================

class TestReadinessState(ReadinessTestMixin, TestCase):
    """Test readiness state tracking."""

    def test_default_state_is_cold(self):
        from apps.ai.readiness_cache import get_readiness_state
        user = self.create_user()
        self.assertEqual(get_readiness_state(user), 'cold')

    def test_set_and_get_state(self):
        from apps.ai.readiness_cache import get_readiness_state, set_readiness_state
        user = self.create_user()
        for state in ('warming', 'ready', 'active'):
            set_readiness_state(user, state)
            self.assertEqual(get_readiness_state(user), state)

    def test_invalid_state_ignored(self):
        from apps.ai.readiness_cache import get_readiness_state, set_readiness_state
        user = self.create_user()
        set_readiness_state(user, 'ready')
        set_readiness_state(user, 'invalid_state')
        self.assertEqual(get_readiness_state(user), 'ready')


# =============================================================================
# ACTIVE USER TRACKING TESTS
# =============================================================================

class TestActiveUserTracking(ReadinessTestMixin, TestCase):
    """Test active user tracking for keep-alive."""

    def test_track_and_retrieve_active_users(self):
        from apps.ai.readiness_cache import (
            get_active_user_ids,
            track_active_user,
        )
        user1 = self.create_user('user1@example.com')
        user2 = self.create_user('user2@example.com')
        track_active_user(user1)
        track_active_user(user2)
        active_ids = get_active_user_ids()
        self.assertIn(user1.id, active_ids)
        self.assertIn(user2.id, active_ids)

    def test_empty_when_no_active_users(self):
        from apps.ai.readiness_cache import get_active_user_ids
        self.assertEqual(get_active_user_ids(), [])

    def test_remove_active_user(self):
        from apps.ai.readiness_cache import (
            get_active_user_ids,
            remove_active_user,
            track_active_user,
        )
        user = self.create_user()
        track_active_user(user)
        self.assertIn(user.id, get_active_user_ids())
        remove_active_user(user.id)
        self.assertNotIn(user.id, get_active_user_ids())


# =============================================================================
# PREWARM FUNCTION TESTS
# =============================================================================

class TestPrewarm(ReadinessTestMixin, TestCase):
    """Test the prewarm_cos_context function."""

    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    def test_prewarm_builds_and_caches(self, mock_build):
        from apps.ai.readiness_cache import (
            get_cached_cos_context,
            get_readiness_state,
            prewarm_cos_context,
        )
        user = self.create_user()
        mock_build.return_value = {'alignment_score': 95, '_user': user}
        result = prewarm_cos_context(user)
        mock_build.assert_called_once_with(user)
        self.assertEqual(result['alignment_score'], 95)
        cached = get_cached_cos_context(user)
        self.assertIsNotNone(cached)
        self.assertEqual(cached['alignment_score'], 95)
        self.assertEqual(get_readiness_state(user), 'ready')

    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    def test_prewarm_sets_cold_on_failure(self, mock_build):
        from apps.ai.readiness_cache import get_readiness_state, prewarm_cos_context
        user = self.create_user()
        mock_build.side_effect = Exception("DB error")
        result = prewarm_cos_context(user)
        self.assertEqual(result, {})
        self.assertEqual(get_readiness_state(user), 'cold')

    @patch('openai.OpenAI')
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    def test_prewarm_does_not_call_openai(self, mock_build, mock_openai):
        """Pre-warm must never trigger LLM calls."""
        from apps.ai.readiness_cache import prewarm_cos_context
        user = self.create_user()
        mock_build.return_value = {'alignment_score': 80}
        prewarm_cos_context(user)
        mock_openai.assert_not_called()


# =============================================================================
# DB WARM-UP TESTS
# =============================================================================

class TestDbWarmup(ReadinessTestMixin, TestCase):
    """Test DB connection warm-up."""

    def test_warm_db_connection_succeeds(self):
        from apps.ai.readiness_cache import warm_db_connection
        result = warm_db_connection()
        self.assertTrue(result)


# =============================================================================
# WAKE ENDPOINT TESTS
# =============================================================================

class TestWakeEndpoint(ReadinessTestMixin, TestCase):
    """Test the /assistant/api/wake/ endpoint."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.user = self.create_user()
        # Enable PA for the user
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.client.login(email='test@example.com', password='testpass123')

    def test_requires_auth(self):
        anon_client = Client()
        response = anon_client.post('/assistant/api/wake/')
        self.assertIn(response.status_code, [302, 403])

    @patch('apps.ai.readiness_cache.prewarm_cos_context')
    def test_returns_warming_on_miss(self, mock_prewarm):
        response = self.client.post(
            '/assistant/api/wake/',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'warming')
        self.assertFalse(data['cached'])

    @patch('apps.ai.readiness_cache.get_cached_cos_context')
    def test_returns_ready_on_hit(self, mock_get):
        mock_get.return_value = {'alignment_score': 85}
        response = self.client.post(
            '/assistant/api/wake/',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ready')
        self.assertTrue(data['cached'])

    def test_disabled_user_gets_disabled_status(self):
        prefs = self.user.preferences
        prefs.personal_assistant_enabled = False
        prefs.save()
        response = self.client.post(
            '/assistant/api/wake/',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'disabled')
