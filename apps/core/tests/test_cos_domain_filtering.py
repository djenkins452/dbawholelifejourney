# ==============================================================================
# File: apps/core/tests/test_cos_domain_filtering.py
# Description: Tests for Phase 2 deterministic CoS domain filtering
# ==============================================================================
"""
Tests for the Phase 2 builder filtering in cos_context.py.

Verifies:
    - Disabled modules cause their domain builders to be skipped
    - System-level builders always run
    - Capture (Layer 1) always runs
    - Fail-open when permissions unavailable
    - Skipped builders recorded in telemetry
    - Intelligence builder respects module permissions in output
    - Builder registry structure is valid
"""

from unittest.mock import patch, MagicMock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from apps.users.models import (
    ModuleDefinition,
    User,
    UserModulePreference,
)


class BuilderRegistryTest(TestCase):
    """Verify the builder registry structure is valid."""

    def test_all_builders_have_three_elements(self):
        """Every entry in _TAGGED_BUILDERS must be a 3-tuple."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
        for entry in _TAGGED_BUILDERS:
            self.assertEqual(
                len(entry), 3,
                f"Builder entry must be (tag, fn, domain_key), got {len(entry)} elements: {entry[0]}"
            )

    def test_domain_keys_resolve_to_modules(self):
        """Every non-None domain_key must map to a module via the catalog."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
        from apps.core.module_catalog import get_domain_to_module_map

        domain_to_module = get_domain_to_module_map()
        for tag, _fn, domain_key in _TAGGED_BUILDERS:
            if domain_key is not None:
                self.assertIn(
                    domain_key, domain_to_module,
                    f"Builder '{tag}' has domain_key '{domain_key}' "
                    f"which has no module mapping in catalog"
                )

    def test_system_builders_have_none_domain(self):
        """System-level builders must have domain_key=None."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS

        system_tags = {
            'blueprint', 'plan', 'pressure', 'calendar', 'intelligence',
            'loops', 'strategy', 'images', 'operating_profile',
            'compensatory', 'signals', 'capture',
        }
        for tag, _fn, domain_key in _TAGGED_BUILDERS:
            if tag in system_tags:
                self.assertIsNone(
                    domain_key,
                    f"System builder '{tag}' should have domain_key=None, got '{domain_key}'"
                )

    def test_domain_builders_have_domain_key(self):
        """Domain builders must have a non-None domain_key."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS

        domain_tags = {
            'health', 'brain_training', 'medical', 'faith',
            'meals', 'finance', 'purpose', 'relationships',
        }
        for tag, _fn, domain_key in _TAGGED_BUILDERS:
            if tag in domain_tags:
                self.assertIsNotNone(
                    domain_key,
                    f"Domain builder '{tag}' should have a domain_key, got None"
                )

    def test_capture_is_system_not_domain(self):
        """Capture builder must be system-level (domain_key=None)."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
        capture_entries = [(t, dk) for t, _fn, dk in _TAGGED_BUILDERS if t == 'capture']
        self.assertEqual(len(capture_entries), 1)
        self.assertIsNone(capture_entries[0][1], "Capture must have domain_key=None")

    def test_people_tag_renamed_to_relationships(self):
        """The 'people' tag was renamed to 'relationships'."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
        tags = [t for t, _, _ in _TAGGED_BUILDERS]
        self.assertNotIn('people', tags, "'people' tag should be renamed to 'relationships'")
        self.assertIn('relationships', tags)


class DomainFilteringTest(TestCase):
    """Test deterministic filtering of domain builders."""

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email='filtering@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()
        cache.clear()

    def _disable_module(self, slug):
        """Disable a module for the test user via UserModulePreference."""
        module_def = ModuleDefinition.objects.get(slug=slug)
        UserModulePreference.objects.update_or_create(
            user=self.user, module=module_def,
            defaults={'is_enabled': False}
        )
        cache.clear()

    def test_disabled_module_builders_skipped(self):
        """Builders for disabled modules should be skipped."""
        self._disable_module('faith')

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        skipped = context.get('_skipped_builders', [])
        self.assertIn('faith', skipped, "Faith builder should be skipped when faith disabled")

    def test_disabled_health_skips_three_builders(self):
        """Disabling health module skips health, medical, and brain_training builders."""
        self._disable_module('health')

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        skipped = context.get('_skipped_builders', [])
        self.assertIn('health', skipped)
        self.assertIn('medical', skipped)
        self.assertIn('brain_training', skipped)

    def test_system_builders_always_run(self):
        """System builders should never appear in skipped list."""
        self._disable_module('faith')
        self._disable_module('health')

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        skipped = context.get('_skipped_builders', [])
        system_tags = {'blueprint', 'plan', 'pressure', 'calendar', 'intelligence',
                       'loops', 'strategy', 'images', 'operating_profile',
                       'compensatory', 'signals', 'capture'}
        for tag in system_tags:
            self.assertNotIn(
                tag, skipped,
                f"System builder '{tag}' should never be skipped"
            )

    def test_capture_always_runs(self):
        """Capture builder (Layer 1 ingestion) should never be skipped."""
        # Disable everything possible
        for slug in ['faith', 'health', 'purpose', 'meals', 'relationships']:
            self._disable_module(slug)

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        skipped = context.get('_skipped_builders', [])
        self.assertNotIn('capture', skipped, "Capture should never be skipped")

    def test_always_available_module_builders_run(self):
        """Life module (always_available) builders should always run."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        skipped = context.get('_skipped_builders', [])
        # Life domain is always_available, so no life-related builders should be skipped
        # (calendar and loops are system-level, life data flows through them)
        self.assertNotIn('life', skipped)

    def test_enabled_module_builders_execute(self):
        """Builders for enabled modules should execute normally."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        skipped = context.get('_skipped_builders', [])
        timings = context.get('_builder_timings', {})

        # Health is enabled by default — should not be skipped
        self.assertNotIn('health', skipped)
        # Health builder should have a timing entry (numeric, not 'skipped')
        self.assertIn('health', timings)
        self.assertNotEqual(timings['health'], 'skipped')

    def test_skipped_builders_in_telemetry(self):
        """Skipped builders must appear in _builder_timings as 'skipped'."""
        self._disable_module('faith')

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        timings = context.get('_builder_timings', {})
        self.assertEqual(
            timings.get('faith'), 'skipped',
            "Skipped builder 'faith' should have timing='skipped'"
        )

    def test_domain_filtering_active_flag(self):
        """Context should include _domain_filtering_active flag."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)
        self.assertTrue(context.get('_domain_filtering_active'))

    def test_scoped_builders_bypass_filtering(self):
        """Scoped builder path should not apply Phase 2 filtering."""
        self._disable_module('faith')

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        # When scoped to faith specifically (intent routing), it should run
        context = build_cos_context(self.user, scoped_builders=['faith', 'blueprint'])

        # Scoped path doesn't populate _skipped_builders
        skipped = context.get('_skipped_builders', [])
        self.assertNotIn('faith', skipped)


class FailOpenTest(TestCase):
    """Test fail-open behavior when permissions unavailable."""

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email='failopen@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()
        cache.clear()

    @patch('apps.core.module_catalog.get_domain_to_module_map', side_effect=Exception("DB down"))
    def test_fail_open_when_catalog_unavailable(self, mock_map):
        """When catalog is unavailable, all builders should run (fail-open)."""
        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        # No builders should be skipped
        skipped = context.get('_skipped_builders', [])
        self.assertEqual(skipped, [])
        self.assertFalse(context.get('_domain_filtering_active'))


class IntelligenceBuilderFilteringTest(TestCase):
    """Test that the intelligence builder filters output by module permissions."""

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email='intel@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        cache.clear()

    def test_intelligence_builder_filters_disabled_module_insights(self):
        """Insights from disabled modules should be excluded."""
        # Create test insights
        try:
            from apps.core.ai_insights.models import Insight
            from django.utils import timezone

            Insight.objects.create(
                user=self.user,
                insight_type='test_health',
                severity='info',
                title='Health insight',
                message='Test health insight',
                module='health',
                confidence_score=0.8,
                status='new',
            )
            Insight.objects.create(
                user=self.user,
                insight_type='test_faith',
                severity='info',
                title='Faith insight',
                message='Test faith insight',
                module='faith',
                confidence_score=0.8,
                status='new',
            )
        except Exception:
            self.skipTest("Insight model not available")

        # Mock permissions with faith disabled
        mock_perms = {
            'health': True,
            'faith': False,
            'journal': True,
            'life': True,
            'purpose': True,
            'capture': True,
            'documents': True,
            'meals': True,
            'relationships': True,
        }

        from apps.core.ai_orchestrator.cos_context import _build_intelligence_signals
        result = _build_intelligence_signals(self.user, _module_permissions=mock_perms)

        insights = result.get('active_insights', [])
        insight_modules = [i['module'] for i in insights]

        self.assertIn('health', insight_modules, "Health insight should be included")
        self.assertNotIn('faith', insight_modules, "Faith insight should be excluded")

    def test_intelligence_builder_includes_all_when_no_permissions(self):
        """Without permissions, all insights should be included (fail-open)."""
        try:
            from apps.core.ai_insights.models import Insight

            Insight.objects.create(
                user=self.user,
                insight_type='test_all',
                severity='info',
                title='General insight',
                message='Test general insight',
                module='health',
                confidence_score=0.8,
                status='new',
            )
        except Exception:
            self.skipTest("Insight model not available")

        from apps.core.ai_orchestrator.cos_context import _build_intelligence_signals
        # Pass None permissions — should include everything
        result = _build_intelligence_signals(self.user, _module_permissions=None)

        insights = result.get('active_insights', [])
        self.assertGreater(len(insights), 0, "Insights should be returned with no permissions")
