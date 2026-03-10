"""
Personal Operating Context — Tests.

Tests:
- UserOperatingProfile model creation and properties
- Profile computation service (productive windows, deferral, momentum)
- CoS context builder injection
- Safe behavior when profile is missing
- Prompt injection formatting and token limits
- Batch recomputation
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User


def _create_test_user(email="opprofile@example.com"):
    """Create a test user with required onboarding setup."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(
        email=email, password="testpass123", date_of_birth=date(1990, 1, 1)
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.save()
    return user


# =========================================================================
# Model Tests
# =========================================================================


class TestUserOperatingProfileModel(TestCase):
    """Test the UserOperatingProfile model."""

    def setUp(self):
        self.user = _create_test_user()

    def test_create_profile(self):
        from apps.core.ai_state.models import UserOperatingProfile

        profile = UserOperatingProfile.objects.create(
            user=self.user,
            profile_data={'productive_windows': {'peak_hours': [8, 9, 10]}},
            sample_days=20,
            last_computed=timezone.now(),
        )
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.sample_days, 20)
        self.assertEqual(profile.version, UserOperatingProfile.SCHEMA_VERSION)
        self.assertIn('productive_windows', profile.profile_data)

    def test_one_to_one_constraint(self):
        from django.db import IntegrityError

        from apps.core.ai_state.models import UserOperatingProfile

        UserOperatingProfile.objects.create(user=self.user, profile_data={})
        with self.assertRaises(IntegrityError):
            UserOperatingProfile.objects.create(user=self.user, profile_data={})

    def test_is_reliable_true_when_enough_days(self):
        from apps.core.ai_state.models import UserOperatingProfile

        profile = UserOperatingProfile.objects.create(
            user=self.user,
            profile_data={},
            sample_days=14,
        )
        self.assertTrue(profile.is_reliable)

    def test_is_reliable_false_when_insufficient_days(self):
        from apps.core.ai_state.models import UserOperatingProfile

        profile = UserOperatingProfile.objects.create(
            user=self.user,
            profile_data={},
            sample_days=10,
        )
        self.assertFalse(profile.is_reliable)

    def test_get_dimension(self):
        from apps.core.ai_state.models import UserOperatingProfile

        profile = UserOperatingProfile.objects.create(
            user=self.user,
            profile_data={
                'productive_windows': {'peak_hours': [9, 10]},
                'momentum_phase': {'current_phase': 'building'},
            },
        )
        pw = profile.get_dimension('productive_windows')
        self.assertEqual(pw['peak_hours'], [9, 10])

        # Missing dimension returns default
        missing = profile.get_dimension('nonexistent')
        self.assertEqual(missing, {})

    def test_str_representation(self):
        from apps.core.ai_state.models import UserOperatingProfile

        profile = UserOperatingProfile.objects.create(
            user=self.user,
            profile_data={
                'momentum_phase': {'current_phase': 'sustaining'},
            },
            sample_days=20,
        )
        s = str(profile)
        self.assertIn('sample_days=20', s)
        self.assertIn('sustaining', s)

    def test_default_values(self):
        from apps.core.ai_state.models import UserOperatingProfile

        profile = UserOperatingProfile.objects.create(user=self.user)
        self.assertEqual(profile.profile_data, {})
        self.assertEqual(profile.sample_days, 0)
        self.assertIsNone(profile.last_computed)
        self.assertEqual(profile.version, 1)


# =========================================================================
# Computation Service Tests
# =========================================================================


class TestProductiveWindowsComputation(TestCase):
    """Test the productive windows dimension computation."""

    def setUp(self):
        self.user = _create_test_user("pw@example.com")
        self.now = timezone.now()
        self.window_start = self.now - timedelta(days=30)

    def test_no_data_returns_zero_confidence(self):
        from apps.core.ai_state.operating_profile import _compute_productive_windows

        result = _compute_productive_windows(self.user, self.window_start, self.now)
        self.assertEqual(result['confidence'], 0.0)
        self.assertEqual(result['peak_hours'], [])

    def test_with_task_completions(self):
        from apps.life.models import Task

        # Create tasks completed at specific hours
        for i in range(10):
            task = Task.objects.create(
                user=self.user,
                title=f"Task {i}",
                completion_status='completed',
                completed_at=self.now - timedelta(days=i, hours=-(9 - self.now.hour)),
            )
            # Force completed_at to be at 9 AM local
            local_9am = timezone.localtime(self.now).replace(
                hour=9, minute=0, second=0
            ) - timedelta(days=i)
            task.completed_at = local_9am
            task.save()

        from apps.core.ai_state.operating_profile import _compute_productive_windows

        result = _compute_productive_windows(self.user, self.window_start, self.now)
        self.assertGreater(result['confidence'], 0.0)
        self.assertGreater(result['total_events'], 0)
        # 9 AM should be among peak hours
        self.assertIn(9, result['peak_hours'])

    def test_sample_days_counts_distinct_dates(self):
        from apps.life.models import Task

        # Create tasks on 5 different days
        for i in range(5):
            Task.objects.create(
                user=self.user,
                title=f"Task {i}",
                completion_status='completed',
                completed_at=self.now - timedelta(days=i),
            )

        from apps.core.ai_state.operating_profile import _compute_productive_windows

        result = _compute_productive_windows(self.user, self.window_start, self.now)
        self.assertGreaterEqual(result['sample_days'], 5)


class TestDeferralPatternsComputation(TestCase):
    """Test the deferral patterns dimension computation."""

    def setUp(self):
        self.user = _create_test_user("dp@example.com")
        self.now = timezone.now()
        self.window_start = self.now - timedelta(days=30)

    def test_no_data_returns_zero(self):
        from apps.core.ai_state.operating_profile import _compute_deferral_patterns

        result = _compute_deferral_patterns(self.user, self.window_start, self.now)
        self.assertEqual(result['overall_deferral_rate'], 0.0)
        self.assertEqual(result['confidence'], 0.0)

    def test_deferral_rate_calculation(self):
        from apps.life.models import Task

        # 7 completed, 3 skipped = 30% deferral rate
        for i in range(7):
            Task.objects.create(
                user=self.user,
                title=f"Completed {i}",
                completion_status='completed',
                completed_at=self.now - timedelta(days=i),
            )
        for i in range(3):
            Task.objects.create(
                user=self.user,
                title=f"Skipped {i}",
                completion_status='skipped',
            )

        from apps.core.ai_state.operating_profile import _compute_deferral_patterns

        result = _compute_deferral_patterns(self.user, self.window_start, self.now)
        self.assertAlmostEqual(result['overall_deferral_rate'], 0.30, places=2)
        self.assertEqual(result['total_tasks_resolved'], 10)
        self.assertEqual(result['completed_count'], 7)
        self.assertEqual(result['skipped_count'], 3)

    def test_prone_modules_identified(self):
        from apps.life.models import Task

        # Health module: 1 completed, 4 skipped (80% deferral)
        for i in range(4):
            Task.objects.create(
                user=self.user,
                title=f"Health Skipped {i}",
                module='health',
                completion_status='skipped',
            )
        Task.objects.create(
            user=self.user,
            title="Health Done",
            module='health',
            completion_status='completed',
            completed_at=self.now,
        )

        # Life module: 5 completed, 0 skipped
        for i in range(5):
            Task.objects.create(
                user=self.user,
                title=f"Life Done {i}",
                module='life',
                completion_status='completed',
                completed_at=self.now - timedelta(days=i),
            )

        from apps.core.ai_state.operating_profile import _compute_deferral_patterns

        result = _compute_deferral_patterns(self.user, self.window_start, self.now)
        prone = result['prone_modules']
        self.assertTrue(len(prone) > 0)
        # Health should be identified as deferral-prone
        health_entry = next((m for m in prone if m['module'] == 'health'), None)
        self.assertIsNotNone(health_entry)
        self.assertGreaterEqual(health_entry['deferral_rate'], 0.3)


class TestMomentumPhaseComputation(TestCase):
    """Test the momentum phase dimension computation."""

    def setUp(self):
        self.user = _create_test_user("mp@example.com")
        self.now = timezone.now()
        self.window_start = self.now - timedelta(days=30)

    def test_insufficient_data_phase(self):
        from apps.core.ai_state.operating_profile import _compute_momentum_phase

        result = _compute_momentum_phase(self.user, self.window_start, self.now)
        self.assertEqual(result['current_phase'], 'insufficient_data')
        self.assertEqual(result['confidence'], 0.0)

    def test_building_phase_when_recent_exceeds_baseline(self):
        from apps.life.models import Task

        # Sparse activity in first 23 days (3 tasks)
        for i in range(3):
            Task.objects.create(
                user=self.user,
                title=f"Old task {i}",
                completion_status='completed',
                completed_at=self.now - timedelta(days=20 + i),
            )

        # Heavy activity in last 7 days (6 tasks on different days)
        for i in range(6):
            Task.objects.create(
                user=self.user,
                title=f"Recent task {i}",
                completion_status='completed',
                completed_at=self.now - timedelta(days=i),
            )

        from apps.core.ai_state.operating_profile import _compute_momentum_phase

        result = _compute_momentum_phase(self.user, self.window_start, self.now)
        # With sparse baseline and active recent, should be building
        self.assertIn(result['current_phase'], ['building', 'sustaining'])
        self.assertGreater(result['recent_active_days'], 0)

    def test_declining_phase_when_recent_below_baseline(self):
        from apps.life.models import Task

        # Heavy activity in first 23 days (15 tasks)
        for i in range(15):
            Task.objects.create(
                user=self.user,
                title=f"Old task {i}",
                completion_status='completed',
                completed_at=self.now - timedelta(days=8 + i),
            )

        # Minimal activity in last 7 days (1 task)
        Task.objects.create(
            user=self.user,
            title="Lone recent task",
            completion_status='completed',
            completed_at=self.now - timedelta(days=1),
        )

        from apps.core.ai_state.operating_profile import _compute_momentum_phase

        result = _compute_momentum_phase(self.user, self.window_start, self.now)
        self.assertIn(result['current_phase'], ['declining', 'recovering'])

    def test_active_domain_count(self):
        from apps.core.ai_state.operating_profile import _count_active_domains

        from apps.life.models import Task

        seven_days_ago = self.now - timedelta(days=7)

        # Create task (tasks domain)
        Task.objects.create(
            user=self.user,
            title="Test",
            completion_status='completed',
            completed_at=self.now - timedelta(days=1),
        )

        count = _count_active_domains(self.user, seven_days_ago, self.now)
        self.assertGreaterEqual(count, 1)


# =========================================================================
# Full Profile Computation Tests
# =========================================================================


class TestComputeUserOperatingProfile(TestCase):
    """Test the full profile computation end-to-end."""

    def setUp(self):
        self.user = _create_test_user("full@example.com")

    def test_compute_creates_profile(self):
        from apps.core.ai_state.models import UserOperatingProfile
        from apps.core.ai_state.operating_profile import compute_user_operating_profile

        profile = compute_user_operating_profile(self.user)
        self.assertIsNotNone(profile)
        self.assertIsInstance(profile, UserOperatingProfile)
        self.assertEqual(profile.user, self.user)
        self.assertIsNotNone(profile.last_computed)
        self.assertEqual(profile.version, UserOperatingProfile.SCHEMA_VERSION)

    def test_compute_updates_existing_profile(self):
        from apps.core.ai_state.models import UserOperatingProfile
        from apps.core.ai_state.operating_profile import compute_user_operating_profile

        # First computation
        profile1 = compute_user_operating_profile(self.user)
        first_computed = profile1.last_computed

        # Second computation should update, not create new
        profile2 = compute_user_operating_profile(self.user)
        self.assertEqual(UserOperatingProfile.objects.filter(user=self.user).count(), 1)
        profile2.refresh_from_db()
        self.assertGreaterEqual(profile2.last_computed, first_computed)

    def test_profile_data_structure(self):
        from apps.core.ai_state.operating_profile import compute_user_operating_profile

        profile = compute_user_operating_profile(self.user)
        data = profile.profile_data

        # All three Phase 1 dimensions should be present
        # (even if empty due to no data)
        self.assertIn('productive_windows', data)
        self.assertIn('deferral_patterns', data)
        self.assertIn('momentum_phase', data)

    def test_graceful_degradation_on_missing_data(self):
        """Profile should compute even when some data sources are unavailable."""
        from apps.core.ai_state.operating_profile import compute_user_operating_profile

        profile = compute_user_operating_profile(self.user)
        self.assertIsNotNone(profile)
        # Low confidence is expected with no data
        for dim in ['productive_windows', 'deferral_patterns', 'momentum_phase']:
            dim_data = profile.profile_data.get(dim, {})
            # Should not crash, should have confidence field
            if dim_data:
                self.assertIn('confidence', dim_data)


# =========================================================================
# CoS Context Builder Tests
# =========================================================================


class TestOperatingProfileBuilder(TestCase):
    """Test the CoS context builder for operating profile."""

    def setUp(self):
        self.user = _create_test_user("builder@example.com")

    def test_builder_returns_empty_when_no_profile(self):
        from apps.core.ai_orchestrator.cos_context import _build_operating_profile

        result = _build_operating_profile(self.user)
        self.assertEqual(result, {})

    def test_builder_returns_profile_when_exists(self):
        from apps.core.ai_state.models import UserOperatingProfile
        from apps.core.ai_orchestrator.cos_context import _build_operating_profile

        UserOperatingProfile.objects.create(
            user=self.user,
            profile_data={
                'productive_windows': {'peak_hours': [9, 10], 'confidence': 0.8},
                'momentum_phase': {'current_phase': 'building', 'confidence': 0.7},
            },
            sample_days=20,
            last_computed=timezone.now(),
        )

        result = _build_operating_profile(self.user)
        self.assertIn('operating_profile', result)
        profile = result['operating_profile']
        self.assertTrue(profile['is_reliable'])
        self.assertEqual(profile['sample_days'], 20)
        self.assertIn('data', profile)

    def test_builder_handles_exception_gracefully(self):
        from apps.core.ai_orchestrator.cos_context import _build_operating_profile

        with patch(
            'apps.core.ai_state.models.UserOperatingProfile.objects'
        ) as mock_objects:
            mock_objects.filter.side_effect = Exception("DB error")
            result = _build_operating_profile(self.user)
            self.assertEqual(result, {})


# =========================================================================
# Prompt Injection Tests
# =========================================================================


class TestOperatingProfileInjection(TestCase):
    """Test the prompt formatting for operating profile."""

    def test_empty_profile_returns_empty_string(self):
        from apps.core.ai_orchestrator.cos_context import _format_operating_profile_injection

        result = _format_operating_profile_injection({})
        self.assertEqual(result, "")

    def test_low_confidence_dimensions_excluded(self):
        from apps.core.ai_orchestrator.cos_context import _format_operating_profile_injection

        data = {
            'productive_windows': {'peak_hours': [9], 'confidence': 0.1},
            'deferral_patterns': {'confidence': 0.1},
            'momentum_phase': {'confidence': 0.1},
        }
        result = _format_operating_profile_injection(data)
        self.assertEqual(result, "")

    def test_high_confidence_profile_generates_output(self):
        from apps.core.ai_orchestrator.cos_context import _format_operating_profile_injection

        data = {
            'productive_windows': {
                'peak_hours': [9, 10, 14],
                'low_hours': [15, 16],
                'confidence': 0.8,
            },
            'deferral_patterns': {
                'overall_deferral_rate': 0.25,
                'prone_modules': [
                    {'module': 'health', 'deferral_rate': 0.4},
                ],
                'intervention_dismiss_rate': 0.35,
                'confidence': 0.7,
            },
            'momentum_phase': {
                'current_phase': 'building',
                'trend': 'accelerating',
                'recent_active_days': 6,
                'active_domain_count': 4,
                'confidence': 0.8,
            },
        }
        result = _format_operating_profile_injection(data)

        # Should contain the section markers
        self.assertIn('USER OPERATING PROFILE', result)
        self.assertIn('END OPERATING PROFILE', result)

        # Should contain interpreted signals
        self.assertIn('9 AM', result)
        self.assertIn('10 AM', result)
        self.assertIn('25%', result)  # deferral rate
        self.assertIn('health', result)  # prone module
        self.assertIn('Building momentum', result)

        # Should contain the Beth directive
        self.assertIn('Frame timing suggestions', result)

    def test_output_token_limit(self):
        """Injection should stay under ~500 tokens (~2000 chars)."""
        from apps.core.ai_orchestrator.cos_context import _format_operating_profile_injection

        # Maximally populated profile
        data = {
            'productive_windows': {
                'peak_hours': [8, 9, 10],
                'low_hours': [14, 15],
                'confidence': 0.9,
            },
            'deferral_patterns': {
                'overall_deferral_rate': 0.35,
                'prone_modules': [
                    {'module': 'health', 'deferral_rate': 0.5},
                    {'module': 'life', 'deferral_rate': 0.4},
                ],
                'intervention_dismiss_rate': 0.45,
                'confidence': 0.9,
            },
            'momentum_phase': {
                'current_phase': 'declining',
                'trend': 'slowing',
                'recent_active_days': 3,
                'active_domain_count': 2,
                'confidence': 0.85,
            },
        }
        result = _format_operating_profile_injection(data)
        # ~4 chars per token, 500 tokens = 2000 chars
        self.assertLess(len(result), 2000,
                        f"Injection too long: {len(result)} chars")

    def test_hour_label_formatting(self):
        from apps.core.ai_orchestrator.cos_context import _hour_label

        self.assertEqual(_hour_label(0), "12 AM")
        self.assertEqual(_hour_label(6), "6 AM")
        self.assertEqual(_hour_label(12), "12 PM")
        self.assertEqual(_hour_label(14), "2 PM")
        self.assertEqual(_hour_label(23), "11 PM")

    def test_deferral_not_shown_when_rate_low(self):
        """Skip rates below 15% should not be mentioned."""
        from apps.core.ai_orchestrator.cos_context import _format_operating_profile_injection

        data = {
            'deferral_patterns': {
                'overall_deferral_rate': 0.05,
                'confidence': 0.8,
            },
        }
        result = _format_operating_profile_injection(data)
        # Should not mention deferral if rate is low
        self.assertNotIn('skip rate', result)


# =========================================================================
# Integration with format_cos_system_injection
# =========================================================================


class TestCosInjectionWithProfile(TestCase):
    """Test that operating profile integrates correctly into CoS injection."""

    def setUp(self):
        self.user = _create_test_user("injection@example.com")

    def test_injection_excluded_when_unreliable(self):
        """Profile with sample_days < 14 should NOT appear in injection."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            '_user': self.user,
            'user_id': self.user.id,
            'operating_profile': {
                'data': {
                    'productive_windows': {'peak_hours': [9], 'confidence': 0.8},
                },
                'sample_days': 10,
                'is_reliable': False,
                'last_computed': timezone.now().isoformat(),
            },
            'module_permissions': {},
        }
        result = format_cos_system_injection(context)
        self.assertNotIn('OPERATING PROFILE', result)

    def test_injection_included_when_reliable(self):
        """Profile with sample_days >= 14 should appear in injection."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            '_user': self.user,
            'user_id': self.user.id,
            'operating_profile': {
                'data': {
                    'productive_windows': {
                        'peak_hours': [9, 10],
                        'confidence': 0.8,
                    },
                    'momentum_phase': {
                        'current_phase': 'sustaining',
                        'trend': 'steady',
                        'recent_active_days': 5,
                        'active_domain_count': 3,
                        'confidence': 0.7,
                    },
                },
                'sample_days': 20,
                'is_reliable': True,
                'last_computed': timezone.now().isoformat(),
            },
            'module_permissions': {},
        }
        result = format_cos_system_injection(context)
        self.assertIn('USER OPERATING PROFILE', result)
        self.assertIn('9 AM', result)
        self.assertIn('Sustaining', result)

    def test_injection_absent_when_no_profile(self):
        """No profile in context should not crash injection."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            '_user': self.user,
            'user_id': self.user.id,
            'module_permissions': {},
        }
        result = format_cos_system_injection(context)
        self.assertNotIn('OPERATING PROFILE', result)
        # Should still produce valid output
        self.assertIsInstance(result, str)


# =========================================================================
# Batch Recomputation Tests
# =========================================================================


class TestRecomputeAllProfiles(TestCase):
    """Test the batch recomputation for all users."""

    def setUp(self):
        self.user1 = _create_test_user("batch1@example.com")
        self.user2 = _create_test_user("batch2@example.com")
        # user2 has AI disabled
        self.user2.preferences.ai_enabled = False
        self.user2.preferences.save()
        # Set recent login for user1
        self.user1.last_login = timezone.now()
        self.user1.save()

    def test_recompute_returns_stats(self):
        from apps.core.ai_state.operating_profile import recompute_all_profiles

        result = recompute_all_profiles()
        self.assertIn('computed', result)
        self.assertIn('skipped', result)
        self.assertIn('errors', result)

    def test_recompute_skips_ai_disabled_users(self):
        from apps.core.ai_state.models import UserOperatingProfile
        from apps.core.ai_state.operating_profile import recompute_all_profiles

        recompute_all_profiles()
        # user2 (AI disabled) should not have a profile
        self.assertFalse(
            UserOperatingProfile.objects.filter(user=self.user2).exists()
        )

    def test_recompute_creates_profiles_for_active_users(self):
        from apps.core.ai_state.models import UserOperatingProfile
        from apps.core.ai_state.operating_profile import recompute_all_profiles

        recompute_all_profiles()
        # user1 (AI enabled, recent login) should have a profile
        self.assertTrue(
            UserOperatingProfile.objects.filter(user=self.user1).exists()
        )


# =========================================================================
# Celery Task Tests
# =========================================================================


class TestComputeOperatingProfilesTask(TestCase):
    """Test the Celery task wrapper."""

    def test_task_calls_recompute(self):
        with patch(
            'apps.core.ai_state.operating_profile.recompute_all_profiles'
        ) as mock_recompute:
            mock_recompute.return_value = {'computed': 5, 'skipped': 0, 'errors': 0}

            from apps.core.tasks import compute_operating_profiles_task
            # Call as a regular function (not via Celery)
            result = compute_operating_profiles_task.apply()
            self.assertTrue(result.successful())
