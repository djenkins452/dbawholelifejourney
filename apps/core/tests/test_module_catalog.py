# ==============================================================================
# File: apps/core/tests/test_module_catalog.py
# Description: Tests for the canonical module catalog and enablement system
# ==============================================================================
"""
Tests for apps/core/module_catalog.py and the ModuleDefinition catalog model.

Covers:
    - Catalog data integrity
    - is_module_enabled() deterministic behavior
    - always_available enforcement
    - coming_soon exclusion
    - Module permissions generation
    - Domain mapping
"""

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.users.models import (
    ModuleDefinition,
    User,
    UserModulePreference,
)


class ModuleCatalogDataIntegrityTest(TestCase):
    """Verify the catalog fixture data is correct."""

    def test_catalog_has_expected_entries(self):
        """All canonical modules exist in the catalog."""
        expected = {
            'capture', 'documents', 'journal', 'health', 'faith',
            'life', 'purpose', 'meals', 'relationships', 'finance',
            'travel', 'system',
        }
        actual = set(ModuleDefinition.objects.values_list('slug', flat=True))
        self.assertEqual(expected, actual)

    def test_no_notes_module(self):
        """The notes module was removed from the catalog."""
        self.assertFalse(ModuleDefinition.objects.filter(slug='notes').exists())

    def test_system_layers_are_always_available(self):
        """System catalog_type entries must have always_available=True."""
        for m in ModuleDefinition.objects.filter(catalog_type='system'):
            self.assertTrue(
                m.always_available,
                f"System layer '{m.slug}' must be always_available"
            )

    def test_internal_entries_are_invisible(self):
        """Internal entries must not show in nav or preferences."""
        for m in ModuleDefinition.objects.filter(catalog_type='internal'):
            self.assertFalse(m.show_in_navigation, f"'{m.slug}' should not show in nav")
            self.assertFalse(m.show_in_preferences, f"'{m.slug}' should not show in prefs")
            self.assertTrue(m.always_available, f"'{m.slug}' should be always_available")

    def test_coming_soon_not_default_enabled(self):
        """Coming soon modules must not be default_enabled."""
        for m in ModuleDefinition.objects.filter(status='coming_soon'):
            self.assertFalse(
                m.default_enabled,
                f"Coming soon '{m.slug}' must not be default_enabled"
            )

    def test_capture_is_layer_1(self):
        """Capture is Layer 1 (ingestion) with no domain ownership."""
        m = ModuleDefinition.objects.get(slug='capture')
        self.assertEqual(m.layer, 1)
        self.assertEqual(m.catalog_type, 'system')
        self.assertTrue(m.always_available)
        self.assertEqual(m.mapped_domain_keys, [])

    def test_documents_is_layer_2(self):
        """Documents is Layer 2 (knowledge) with its own domain."""
        m = ModuleDefinition.objects.get(slug='documents')
        self.assertEqual(m.layer, 2)
        self.assertEqual(m.catalog_type, 'system')
        self.assertTrue(m.always_available)
        self.assertEqual(m.mapped_domain_keys, ['documents'])

    def test_life_is_always_available_module(self):
        """Life (Organize) is a module but always_available."""
        m = ModuleDefinition.objects.get(slug='life')
        self.assertEqual(m.catalog_type, 'module')
        self.assertTrue(m.always_available)

    def test_health_owns_three_domains(self):
        """Health module owns health, medical, and brain_training domains."""
        m = ModuleDefinition.objects.get(slug='health')
        self.assertEqual(sorted(m.mapped_domain_keys), ['brain_training', 'health', 'medical'])

    def test_display_name_fallback(self):
        """get_display_name() returns display_name or falls back to name."""
        m = ModuleDefinition.objects.get(slug='health')
        self.assertEqual(m.get_display_name(), 'Health & Vitals')

        # Test fallback when display_name is empty
        m.display_name = ''
        self.assertEqual(m.get_display_name(), 'Health')


class IsModuleEnabledTest(TestCase):
    """Test the canonical is_module_enabled() function."""

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email='test@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        cache.clear()

    def test_always_available_returns_true_regardless(self):
        """always_available modules return True even when user pref is False."""
        from apps.core.module_catalog import is_module_enabled

        # Life is always_available
        self.assertTrue(is_module_enabled(self.user, 'life'))

        # Even if user has a UserModulePreference set to False
        life_mod = ModuleDefinition.objects.get(slug='life')
        UserModulePreference.objects.update_or_create(
            user=self.user, module=life_mod,
            defaults={'is_enabled': False}
        )
        cache.clear()
        self.assertTrue(is_module_enabled(self.user, 'life'))

    def test_capture_always_available(self):
        """Capture (system layer) is always available."""
        from apps.core.module_catalog import is_module_enabled
        self.assertTrue(is_module_enabled(self.user, 'capture'))

    def test_documents_always_available(self):
        """Documents (system layer) is always available."""
        from apps.core.module_catalog import is_module_enabled
        self.assertTrue(is_module_enabled(self.user, 'documents'))

    def test_coming_soon_returns_false(self):
        """Coming soon modules return False regardless of user prefs."""
        from apps.core.module_catalog import is_module_enabled
        self.assertFalse(is_module_enabled(self.user, 'finance'))
        self.assertFalse(is_module_enabled(self.user, 'travel'))

    def test_admin_kill_switch(self):
        """is_active=False overrides everything."""
        from apps.core.module_catalog import is_module_enabled

        journal = ModuleDefinition.objects.get(slug='journal')
        journal.is_active = False
        journal.save()
        cache.clear()

        self.assertFalse(is_module_enabled(self.user, 'journal'))

        # Restore
        journal.is_active = True
        journal.save()
        cache.clear()

    def test_user_preference_respected(self):
        """User can disable a toggleable module."""
        from apps.core.module_catalog import is_module_enabled

        # Default should be enabled
        self.assertTrue(is_module_enabled(self.user, 'journal'))

        # User disables it
        journal_mod = ModuleDefinition.objects.get(slug='journal')
        UserModulePreference.objects.update_or_create(
            user=self.user, module=journal_mod,
            defaults={'is_enabled': False}
        )
        cache.clear()
        self.assertFalse(is_module_enabled(self.user, 'journal'))

    def test_unknown_slug_returns_false(self):
        """Unknown module slugs fail closed (return False)."""
        from apps.core.module_catalog import is_module_enabled
        self.assertFalse(is_module_enabled(self.user, 'nonexistent'))

    def test_default_enabled_fallback(self):
        """Without user preference, falls back to default_enabled."""
        from apps.core.module_catalog import is_module_enabled

        # Faith defaults to True in catalog
        faith = ModuleDefinition.objects.get(slug='faith')
        self.assertTrue(faith.default_enabled)
        # No UserModulePreference exists
        UserModulePreference.objects.filter(user=self.user, module=faith).delete()
        cache.clear()
        self.assertTrue(is_module_enabled(self.user, 'faith'))


class ModulePermissionsTest(TestCase):
    """Test get_module_permissions() for CoS context."""

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email='test2@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        cache.clear()

    def test_permissions_include_cos_participating_modules(self):
        """Only modules with cos_participation=True appear in permissions."""
        from apps.core.module_catalog import get_module_permissions
        perms = get_module_permissions(self.user)

        # System (internal) should NOT appear
        self.assertNotIn('system', perms)

        # Finance (coming_soon, cos=False) should NOT appear
        self.assertNotIn('finance', perms)

        # Health (active, cos=True) should appear
        self.assertIn('health', perms)
        self.assertTrue(perms['health'])

    def test_always_available_always_true_in_permissions(self):
        """System layers with cos_participation are always True."""
        from apps.core.module_catalog import get_module_permissions
        perms = get_module_permissions(self.user)
        self.assertTrue(perms.get('capture', False))
        self.assertTrue(perms.get('documents', False))
        self.assertTrue(perms.get('life', False))


class DomainMappingTest(TestCase):
    """Test domain-to-module mapping."""

    def test_domain_to_module_map(self):
        """Each domain maps to exactly one module."""
        from apps.core.module_catalog import get_domain_to_module_map
        dmap = get_domain_to_module_map()

        self.assertEqual(dmap.get('health'), 'health')
        self.assertEqual(dmap.get('medical'), 'health')
        self.assertEqual(dmap.get('brain_training'), 'health')
        self.assertEqual(dmap.get('journal'), 'journal')
        self.assertEqual(dmap.get('faith'), 'faith')
        self.assertEqual(dmap.get('life'), 'life')
        self.assertEqual(dmap.get('purpose'), 'purpose')
        self.assertEqual(dmap.get('meals'), 'meals')
        self.assertEqual(dmap.get('documents'), 'documents')
        self.assertEqual(dmap.get('finance'), 'finance')
        self.assertEqual(dmap.get('relationships'), 'relationships')

        # Capture has no domain mapping (Layer 1)
        self.assertNotIn('capture', dmap)

    def test_no_duplicate_domain_ownership(self):
        """No domain is claimed by multiple modules."""
        from apps.core.module_catalog import get_domain_to_module_map
        catalog = {m.slug: m for m in ModuleDefinition.objects.all()}

        seen = {}
        for slug, m in catalog.items():
            for dk in (m.mapped_domain_keys or []):
                self.assertNotIn(
                    dk, seen,
                    f"Domain '{dk}' claimed by both '{seen.get(dk)}' and '{slug}'"
                )
                seen[dk] = slug
