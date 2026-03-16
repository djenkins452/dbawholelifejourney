# ==============================================================================
# File: apps/core/ai_eae/tests/test_signal_governance.py
# Description: Phase 4 — Signal governance alignment tests
#
# Validates:
#   - SIGNAL_TYPE_DOMAIN maps to registered domains
#   - Every taxonomy signal type has a computer or stub
#   - DomainCapability.expected_signal_types match taxonomy
#   - Signal computers produce correct output
#   - Missing data produces no snapshot
# ==============================================================================

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.core.ai_eae.models import SignalSnapshot
from apps.core.ai_eae.signal_aggregation import (
    SIGNAL_TYPE_DOMAIN,
    STUBBED_SIGNAL_TYPES,
    SignalAggregationService,
)


class SignalDomainMappingTest(TestCase):
    """Test that SIGNAL_TYPE_DOMAIN maps to registered Domain Registry domains."""

    def test_all_signal_domains_are_registered(self):
        """Every domain in SIGNAL_TYPE_DOMAIN must exist in the Domain Registry."""
        from apps.core.domain_registry.registry import registry

        for signal_type, domain in SIGNAL_TYPE_DOMAIN.items():
            self.assertTrue(
                registry.is_registered(domain),
                f"Signal type '{signal_type}' maps to domain '{domain}' "
                f"which is not registered. Registered: {registry.get_names()}"
            )

    def test_mental_reflection_maps_to_journal(self):
        """Phase 4: mental_reflection must map to 'journal', not 'mind'."""
        self.assertEqual(SIGNAL_TYPE_DOMAIN['mental_reflection'], 'journal')

    def test_cognitive_fitness_maps_to_brain_training(self):
        """Phase 4: cognitive_fitness must map to 'brain_training', not 'mind'."""
        self.assertEqual(SIGNAL_TYPE_DOMAIN['cognitive_fitness'], 'brain_training')

    def test_productivity_progress_maps_to_life(self):
        """productivity_progress must map to 'life'."""
        self.assertEqual(SIGNAL_TYPE_DOMAIN['productivity_progress'], 'life')

    def test_no_mind_domain_in_mappings(self):
        """Phase 4: 'mind' should no longer appear as a domain value."""
        domains_used = set(SIGNAL_TYPE_DOMAIN.values())
        self.assertNotIn('mind', domains_used,
                         "'mind' is not a registered domain — use 'journal' or 'brain_training'")

    def test_no_work_domain_in_mappings(self):
        """'work' should not appear as a domain value."""
        domains_used = set(SIGNAL_TYPE_DOMAIN.values())
        self.assertNotIn('work', domains_used,
                         "'work' is not a registered domain — use 'life'")


class SignalComputerCoverageTest(TestCase):
    """Test that every taxonomy signal type has a computer or is stubbed."""

    def test_every_taxonomy_type_has_computer_or_stub(self):
        """All 10 taxonomy signal types must have a computer method or stub."""
        computer_methods = {
            'health_activity': '_compute_health_activity',
            'health_biometrics': '_compute_health_biometrics',
            'medication_adherence': '_compute_medication_adherence',
            'nutrition_compliance': '_compute_nutrition_compliance',
            'faith_practice': '_compute_faith_practice',
            'mental_reflection': '_compute_mental_reflection',
            'cognitive_fitness': '_compute_cognitive_fitness',
            'productivity_progress': '_compute_productivity_progress',
            'relational_engagement': '_compute_relational_engagement',
            'financial_health': '_compute_financial_health',
        }

        for signal_type in SIGNAL_TYPE_DOMAIN:
            method_name = computer_methods.get(signal_type)
            self.assertIsNotNone(
                method_name,
                f"Signal type '{signal_type}' has no expected computer method"
            )
            self.assertTrue(
                hasattr(SignalAggregationService, method_name),
                f"SignalAggregationService missing method '{method_name}' "
                f"for signal type '{signal_type}'"
            )

    def test_stubbed_signal_types_documented(self):
        """Stubbed signal types must have a reason in STUBBED_SIGNAL_TYPES."""
        self.assertIn('financial_health', STUBBED_SIGNAL_TYPES)
        self.assertIsInstance(STUBBED_SIGNAL_TYPES['financial_health'], str)
        self.assertTrue(len(STUBBED_SIGNAL_TYPES['financial_health']) > 0)

    def test_financial_health_returns_none(self):
        """Financial health stub must return None (no fake signals)."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(email='test_fin@test.com', password='test')
        result = SignalAggregationService._compute_financial_health(user, date.today())
        self.assertIsNone(result)


class ExpectedSignalTypesTest(TestCase):
    """Test that DomainCapability.expected_signal_types match taxonomy."""

    def test_expected_types_exist_in_taxonomy(self):
        """Every expected_signal_type must exist in SIGNAL_TYPE_DOMAIN."""
        from apps.core.domain_registry.registry import registry

        taxonomy_types = set(SIGNAL_TYPE_DOMAIN.keys())

        for name, domain in registry.get_all().items():
            expected = getattr(domain, 'expected_signal_types', [])
            for st in expected:
                self.assertIn(
                    st, taxonomy_types,
                    f"Domain '{name}' declares expected signal type '{st}' "
                    f"which is not in SIGNAL_TYPE_DOMAIN"
                )

    def test_expected_types_map_to_correct_domain(self):
        """Each expected signal type should map back to its declaring domain."""
        from apps.core.domain_registry.registry import registry

        for name, domain in registry.get_all().items():
            expected = getattr(domain, 'expected_signal_types', [])
            for st in expected:
                mapped_domain = SIGNAL_TYPE_DOMAIN.get(st)
                self.assertEqual(
                    mapped_domain, name,
                    f"Signal type '{st}' is expected by domain '{name}' "
                    f"but SIGNAL_TYPE_DOMAIN maps it to '{mapped_domain}'"
                )

    def test_behavioral_cos_domains_have_expected_signals(self):
        """Behavioral CoS-participating domains should declare expected_signal_types."""
        from apps.core.domain_registry.registry import registry

        for name, domain in registry.get_all().items():
            if domain.is_user_life_domain and domain.participates_in_cos:
                expected = getattr(domain, 'expected_signal_types', [])
                # Some behavioral domains may not have signals yet
                # (e.g., purpose doesn't own taxonomy signals directly)
                # Only check domains that SHOULD have signals based on taxonomy
                domain_signals = [
                    st for st, dm in SIGNAL_TYPE_DOMAIN.items()
                    if dm == name
                ]
                if domain_signals:
                    self.assertTrue(
                        len(expected) > 0,
                        f"Behavioral CoS domain '{name}' has taxonomy signals "
                        f"{domain_signals} but no expected_signal_types declared"
                    )


class NutritionComplianceComputerTest(TestCase):
    """Test the nutrition_compliance signal computer."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            email='test_nutrition@test.com', password='test',
        )
        self.today = date.today()

    def test_no_data_returns_none(self):
        """No nutrition data should produce no snapshot."""
        result = SignalAggregationService._compute_nutrition_compliance(
            self.user, self.today,
        )
        self.assertIsNone(result)

    def _create_food_entry(self, food_name='Test meal', calories=500):
        """Helper to create a FoodEntry with required fields."""
        from apps.health.models import FoodEntry
        return FoodEntry.objects.create(
            user=self.user,
            food_name=food_name,
            logged_date=self.today,
            total_calories=calories,
            serving_size=Decimal('1.0'),
            serving_unit='serving',
        )

    def test_food_entries_produce_signal(self):
        """Food entries should produce a nutrition_compliance signal."""
        self._create_food_entry()
        result = SignalAggregationService._compute_nutrition_compliance(
            self.user, self.today,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.signal_type, 'nutrition_compliance')
        self.assertEqual(result.domain, 'health')
        self.assertEqual(result.signal_class, 'verified_action')
        self.assertGreater(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)

    def test_three_meals_gets_full_food_credit(self):
        """Three food entries should get full food logging credit."""
        for i in range(3):
            self._create_food_entry(food_name=f'Meal {i}', calories=400)
        result = SignalAggregationService._compute_nutrition_compliance(
            self.user, self.today,
        )
        self.assertIsNotNone(result)
        # With only food entries (no water/fasting), score = 1.0 / 1 sub-score
        self.assertEqual(result.score, 1.0)

    def test_water_entries_counted(self):
        """Water entries should contribute to nutrition score."""
        from apps.health.models import WaterEntry
        # 64+ oz = full water credit
        WaterEntry.objects.create(
            user=self.user,
            amount=Decimal('64.0'),
            unit='oz',
            logged_date=self.today,
        )
        result = SignalAggregationService._compute_nutrition_compliance(
            self.user, self.today,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.score, 1.0)
        self.assertIn('water_oz', result.source_signals)


class RelationalEngagementComputerTest(TestCase):
    """Test the relational_engagement signal computer."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            email='test_rel@test.com', password='test',
        )
        self.today = date.today()

    def test_no_data_returns_none(self):
        """No interactions should produce no snapshot."""
        result = SignalAggregationService._compute_relational_engagement(
            self.user, self.today,
        )
        self.assertIsNone(result)

    def test_interaction_produces_signal(self):
        """A relationship interaction should produce a signal."""
        from apps.relationships.models import Person, RelationshipInteraction
        person = Person.objects.create(
            owner=self.user,
            first_name='Test',
            last_name='Person',
        )
        RelationshipInteraction.objects.create(
            person=person,
            user=self.user,
            context_type_label='manual',
            interaction_date=self.today,
        )
        result = SignalAggregationService._compute_relational_engagement(
            self.user, self.today,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.signal_type, 'relational_engagement')
        self.assertEqual(result.domain, 'relationships')
        self.assertEqual(result.signal_class, 'verified_action')

    def test_multiple_people_gets_higher_score(self):
        """Interactions with 2+ people should score higher."""
        from apps.relationships.models import Person, RelationshipInteraction
        for i in range(2):
            person = Person.objects.create(
                owner=self.user,
                first_name=f'Person{i}',
            )
            RelationshipInteraction.objects.create(
                person=person,
                user=self.user,
                context_type_label='manual',
                interaction_date=self.today,
            )
        result = SignalAggregationService._compute_relational_engagement(
            self.user, self.today,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.source_signals['distinct_people'], 2)


class SignalValidationTest(TestCase):
    """Test the Phase 4 validation utilities."""

    def test_signal_domain_mappings_valid(self):
        """All signal domain mappings should pass validation."""
        from apps.core.domain_registry.validation import validate_signal_domain_mappings
        result = validate_signal_domain_mappings()
        self.assertEqual(
            len(result['invalid']), 0,
            f"Invalid signal domain mappings: {result['invalid']}"
        )
        self.assertTrue(len(result['valid']) > 0)

    def test_expected_signal_types_valid(self):
        """All expected signal types should pass validation."""
        from apps.core.domain_registry.validation import validate_expected_signal_types
        result = validate_expected_signal_types()
        self.assertEqual(
            len(result['invalid']), 0,
            f"Invalid expected signal types: {result['invalid']}"
        )

    def test_signal_computer_coverage_complete(self):
        """All taxonomy types should be covered or stubbed."""
        from apps.core.domain_registry.validation import validate_signal_computer_coverage
        result = validate_signal_computer_coverage()
        self.assertEqual(
            len(result['missing']), 0,
            f"Missing signal computers: {result['missing']}"
        )
        # Every type is either covered or stubbed
        total = len(result['covered']) + len(result['stubbed'])
        self.assertEqual(total, len(SIGNAL_TYPE_DOMAIN))

    def test_cos_signal_coverage(self):
        """All behavioral CoS domains must have a CoS contribution path."""
        from apps.core.domain_registry.validation import validate_cos_signal_coverage
        result = validate_cos_signal_coverage()
        self.assertEqual(
            len(result['uncovered']), 0,
            f"Uncovered CoS domains: {result['uncovered']}"
        )
        # Some domains contribute via signals, others via builders
        self.assertTrue(
            len(result['covered_by_signals']) > 0,
            "At least some domains should be covered by direct signal ownership"
        )

    def test_signal_health_summary_healthy(self):
        """Signal health summary should report healthy."""
        from apps.core.domain_registry.validation import get_signal_health_summary
        summary = get_signal_health_summary()
        self.assertEqual(
            summary['status'], 'healthy',
            f"Signal health drift detected: {summary}"
        )
        self.assertEqual(summary['taxonomy_types'], 10)
        self.assertEqual(summary['computers_missing'], 0)

    def test_registry_health_includes_signal_health(self):
        """Combined registry health should include signal health."""
        from apps.core.domain_registry.validation import get_registry_health_summary
        summary = get_registry_health_summary()
        self.assertIn('signal_health', summary)
        self.assertIn('taxonomy_types', summary['signal_health'])


class SignalSnapshotDomainTest(TestCase):
    """Test that signal snapshots use registry-aligned domains."""

    def test_upsert_uses_aligned_domains(self):
        """_upsert_snapshot should use registry-aligned domain values."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(email='test_snap@test.com', password='test')

        snapshot = SignalAggregationService._upsert_snapshot(
            user, date.today(), 'mental_reflection',
            score=0.7, confidence=1.0,
            signal_class='verified_action',
            source_signals={'test': True},
        )
        self.assertEqual(snapshot.domain, 'journal')

        snapshot2 = SignalAggregationService._upsert_snapshot(
            user, date.today(), 'cognitive_fitness',
            score=0.5, confidence=1.0,
            signal_class='verified_action',
            source_signals={'test': True},
        )
        self.assertEqual(snapshot2.domain, 'brain_training')
