# ==============================================================================
# File: apps/core/tests/test_domain_registry_phase3.py
# Description: Phase 3 — Domain Registry Alignment tests
#
# Verifies:
#   - All domains have valid domain_class classification
#   - Module catalog domain_keys resolve to registered domains
#   - Builder domain_keys resolve to registered domains
#   - Capture is classified as influence (not behavioral)
#   - Documents is classified as knowledge (not behavioral)
#   - Relationships is registered in DomainRegistry
#   - Validation utilities detect drift correctly
#   - Registry health summary is accurate
# ==============================================================================

from django.test import TestCase

from apps.core.domain_registry import registry, autodiscover
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass


class DomainClassMetadataTest(TestCase):
    """Verify Phase 3 domain_class metadata is present and valid."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        autodiscover()

    def test_all_domains_have_valid_domain_class(self):
        """Every registered domain must have a valid domain_class."""
        for name, domain in registry.get_all().items():
            self.assertIn(
                domain.domain_class, DomainClass.ALL,
                f"Domain '{name}' has invalid domain_class '{domain.domain_class}'"
            )

    def test_behavioral_domains_exist(self):
        """System must have behavioral (user life) domains."""
        behavioral = registry.get_by_class(DomainClass.BEHAVIORAL)
        self.assertGreater(len(behavioral), 0, "No behavioral domains registered")

        # Known behavioral domains
        behavioral_names = {d.name for d in behavioral}
        for expected in ['health', 'journal', 'faith', 'purpose', 'life',
                         'meals', 'medical', 'finance', 'brain_training',
                         'relationships']:
            self.assertIn(
                expected, behavioral_names,
                f"Expected behavioral domain '{expected}' not found"
            )

    def test_capture_is_influence_not_behavioral(self):
        """Capture must be classified as influence, not behavioral."""
        capture = registry.get('capture')
        self.assertIsNotNone(capture, "Capture domain not registered")
        self.assertEqual(
            capture.domain_class, DomainClass.INFLUENCE,
            f"Capture should be INFLUENCE, got '{capture.domain_class}'"
        )
        self.assertFalse(capture.is_user_life_domain)
        self.assertTrue(capture.is_cross_domain_source)
        self.assertTrue(capture.participates_in_cos)

    def test_documents_is_knowledge_not_behavioral(self):
        """Documents must be classified as knowledge, not behavioral."""
        documents = registry.get('documents')
        self.assertIsNotNone(documents, "Documents domain not registered")
        self.assertEqual(
            documents.domain_class, DomainClass.KNOWLEDGE,
            f"Documents should be KNOWLEDGE, got '{documents.domain_class}'"
        )
        self.assertFalse(documents.is_user_life_domain)
        self.assertFalse(documents.is_cross_domain_source)
        self.assertTrue(documents.participates_in_cos)

    def test_relationships_is_registered(self):
        """Relationships must be registered in the DomainRegistry."""
        relationships = registry.get('relationships')
        self.assertIsNotNone(relationships, "Relationships domain not registered")
        self.assertEqual(relationships.domain_class, DomainClass.BEHAVIORAL)
        self.assertTrue(relationships.is_user_life_domain)
        self.assertIn('Person', relationships.primary_models)

    def test_user_life_domain_property(self):
        """Only behavioral domains should be user life domains."""
        for name, domain in registry.get_all().items():
            if domain.domain_class == DomainClass.BEHAVIORAL:
                self.assertTrue(
                    domain.is_user_life_domain,
                    f"Behavioral domain '{name}' should be a user life domain"
                )
            else:
                self.assertFalse(
                    domain.is_user_life_domain,
                    f"Non-behavioral domain '{name}' ({domain.domain_class}) "
                    f"should NOT be a user life domain"
                )


class ModuleCatalogAlignmentTest(TestCase):
    """Verify Module Catalog domain_keys resolve to registered domains."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        autodiscover()

    def test_all_catalog_domain_keys_are_registered(self):
        """Every mapped_domain_key in ModuleDefinition must be registered."""
        from apps.core.domain_registry.validation import validate_module_domain_mappings

        result = validate_module_domain_mappings()
        if result['invalid']:
            reasons = [r for _, _, r in result['invalid']]
            self.fail(
                f"Module catalog has unregistered domain keys:\n"
                + "\n".join(f"  - {r}" for r in reasons)
            )

    def test_domain_to_module_map_is_complete(self):
        """Every domain builder's domain_key should map to a module."""
        from apps.core.module_catalog import get_domain_to_module_map
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS

        domain_to_module = get_domain_to_module_map()
        for tag, _fn, domain_key in _TAGGED_BUILDERS:
            if domain_key is not None:
                self.assertIn(
                    domain_key, domain_to_module,
                    f"Builder '{tag}' domain_key '{domain_key}' has no module mapping"
                )


class BuilderRegistryAlignmentTest(TestCase):
    """Verify builder domain_keys resolve to registered domains."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        autodiscover()

    def test_all_builder_domain_keys_are_registered(self):
        """Every builder's domain_key must be in the DomainRegistry."""
        from apps.core.domain_registry.validation import validate_builder_domain_keys

        result = validate_builder_domain_keys()
        if result['invalid']:
            reasons = [r for _, _, r in result['invalid']]
            self.fail(
                f"Builder registry has unregistered domain keys:\n"
                + "\n".join(f"  - {r}" for r in reasons)
            )

    def test_capture_builder_is_system_level(self):
        """Capture builder must be system-level (domain_key=None)."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS
        capture_entries = [(t, dk) for t, _, dk in _TAGGED_BUILDERS if t == 'capture']
        self.assertEqual(len(capture_entries), 1)
        self.assertIsNone(
            capture_entries[0][1],
            "Capture builder must have domain_key=None (system-level ingestion)"
        )

    def test_system_builders_are_not_in_domain_registry_as_behavioral(self):
        """System-level builders should not reference behavioral domains."""
        from apps.core.ai_orchestrator.cos_context import _TAGGED_BUILDERS

        for tag, _fn, domain_key in _TAGGED_BUILDERS:
            if domain_key is None:
                # System builder — should NOT be registered as behavioral
                domain = registry.get(tag)
                if domain is not None:
                    self.assertNotEqual(
                        domain.domain_class, DomainClass.BEHAVIORAL,
                        f"System builder '{tag}' maps to a behavioral domain "
                        f"— classification conflict"
                    )


class CaptureClassificationTest(TestCase):
    """Verify capture's cross-domain ingestion classification."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        autodiscover()

    def test_capture_related_domains_are_registered(self):
        """Capture's related domains should exist in the registry."""
        capture = registry.get('capture')
        for related in capture.related_domains:
            self.assertTrue(
                registry.is_registered(related),
                f"Capture's related domain '{related}' is not registered"
            )

    def test_capture_has_no_intents(self):
        """Capture is ingestion-only — no CoS intents."""
        capture = registry.get('capture')
        self.assertEqual(
            capture.intent_types, [],
            "Capture should have no intent types (ingestion only)"
        )

    def test_capture_module_has_no_mapped_domain_keys(self):
        """Capture module in catalog should have empty mapped_domain_keys."""
        from apps.users.models import ModuleDefinition
        try:
            capture_mod = ModuleDefinition.objects.get(slug='capture')
            self.assertEqual(
                capture_mod.mapped_domain_keys, [],
                "Capture module should have empty mapped_domain_keys "
                "(it's system-level, not a standard domain)"
            )
        except ModuleDefinition.DoesNotExist:
            self.fail("Capture module not found in catalog")


class FullAlignmentTest(TestCase):
    """End-to-end governance alignment verification."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        autodiscover()

    def test_full_alignment_is_healthy(self):
        """
        The canonical Phase 3 verification:
        'Every CoS-participating builder and every module-mapped domain
        resolves to a canonical domain governance model, and ingestion
        systems are no longer confused with standard life domains.'
        """
        from apps.core.domain_registry import get_registry_health_summary

        health = get_registry_health_summary()
        if health['status'] != 'healthy':
            self.fail(
                f"Registry alignment is not healthy. Issues:\n"
                + "\n".join(f"  - {i}" for i in health['issues'])
            )

    def test_registry_health_summary_structure(self):
        """Health summary must have expected keys."""
        from apps.core.domain_registry import get_registry_health_summary

        health = get_registry_health_summary()
        self.assertIn('status', health)
        self.assertIn('domain_count', health)
        self.assertIn('by_class', health)
        self.assertIn('issues', health)
        self.assertIn('details', health)
        self.assertGreater(health['domain_count'], 0)

    def test_coverage_summary_includes_domain_class(self):
        """Coverage summary must include Phase 3 domain_class field."""
        summary = registry.get_coverage_summary()
        for entry in summary:
            self.assertIn('domain_class', entry)
            self.assertIn(entry['domain_class'], DomainClass.ALL)
            self.assertIn('is_user_life_domain', entry)
            self.assertIn('participates_in_cos', entry)


class ValidationUtilitiesTest(TestCase):
    """Test the validation utility functions directly."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        autodiscover()

    def test_is_registered_domain_valid(self):
        """Known domains should be registered."""
        from apps.core.domain_registry import is_registered_domain
        self.assertTrue(is_registered_domain('health'))
        self.assertTrue(is_registered_domain('capture'))
        self.assertTrue(is_registered_domain('relationships'))
        self.assertTrue(is_registered_domain('documents'))

    def test_is_registered_domain_invalid(self):
        """Unknown domains should not be registered."""
        from apps.core.domain_registry import is_registered_domain
        self.assertFalse(is_registered_domain('nonexistent'))
        self.assertFalse(is_registered_domain(''))
        self.assertFalse(is_registered_domain('notes'))

    def test_get_domain_definition_returns_capability(self):
        """Getting a valid domain should return a DomainCapability."""
        from apps.core.domain_registry import get_domain_definition
        health = get_domain_definition('health')
        self.assertIsInstance(health, DomainCapability)
        self.assertEqual(health.name, 'health')

    def test_get_domain_definition_returns_none_for_invalid(self):
        """Getting an invalid domain should return None."""
        from apps.core.domain_registry import get_domain_definition
        self.assertIsNone(get_domain_definition('nonexistent'))
