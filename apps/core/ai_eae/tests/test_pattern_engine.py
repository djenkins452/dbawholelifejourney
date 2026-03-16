# ==============================================================================
# File: apps/core/ai_eae/tests/test_pattern_engine.py
# Description: Phase 5 — Cross-Domain Pattern Engine Tests
#
# Validates:
#   - Pattern taxonomy governance (no collisions, domains registered)
#   - Each pattern rule fires/no-fires correctly
#   - Missing data produces no patterns
#   - Pattern snapshots use derived_pattern signal_class
#   - Pattern domains resolve to real registry domains
#   - Patterns appear in CoS context query
# ==============================================================================

from datetime import date, timedelta

from django.test import TestCase

from apps.core.ai_eae.models import SignalSnapshot
from apps.core.ai_eae.pattern_engine import (
    PatternEngine,
    _get_trend_from_history,
)
from apps.core.ai_eae.pattern_taxonomy import (
    BASE_SIGNAL_TYPES,
    PATTERN_CONFIDENCE_DISCOUNT,
    PATTERN_TYPE_CATALOG,
    PATTERN_TYPES,
)


class PatternTaxonomyGovernanceTest(TestCase):
    """Test pattern taxonomy doesn't collide with base signals and resolves to registry."""

    def test_no_collision_with_base_signals(self):
        """Pattern types must not share names with base signal types."""
        for pt in PATTERN_TYPES:
            self.assertNotIn(
                pt, BASE_SIGNAL_TYPES,
                f"Pattern type '{pt}' collides with base signal type",
            )

    def test_all_pattern_types_fit_field_length(self):
        """All pattern type names must fit in signal_type CharField (max 30)."""
        for pt in PATTERN_TYPES:
            self.assertLessEqual(
                len(pt), 30,
                f"Pattern type '{pt}' exceeds 30-char signal_type limit",
            )

    def test_catalog_matches_pattern_types(self):
        """PATTERN_TYPE_CATALOG keys must match PATTERN_TYPES set."""
        self.assertEqual(set(PATTERN_TYPE_CATALOG.keys()), PATTERN_TYPES)

    def test_pattern_types_in_signal_taxonomy(self):
        """All pattern types must be registered in SIGNAL_TYPE_DOMAIN."""
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
        for pt in PATTERN_TYPES:
            self.assertIn(
                pt, SIGNAL_TYPE_DOMAIN,
                f"Pattern type '{pt}' not registered in SIGNAL_TYPE_DOMAIN",
            )

    def test_pattern_domains_resolve_to_registry(self):
        """Pattern type domains must exist in the Domain Registry."""
        from apps.core.ai_eae.signal_aggregation import SIGNAL_TYPE_DOMAIN
        from apps.core.domain_registry.registry import registry

        for pt in PATTERN_TYPES:
            domain = SIGNAL_TYPE_DOMAIN[pt]
            self.assertTrue(
                registry.is_registered(domain),
                f"Pattern type '{pt}' maps to domain '{domain}' "
                f"which is not registered. Registered: {registry.get_names()}",
            )

    def test_confidence_discount_is_less_than_one(self):
        """Derived patterns must have discounted confidence."""
        self.assertLess(PATTERN_CONFIDENCE_DISCOUNT, 1.0)
        self.assertGreater(PATTERN_CONFIDENCE_DISCOUNT, 0.0)

    def test_validation_passes(self):
        """Full pattern taxonomy validation should pass."""
        from apps.core.domain_registry.validation import validate_pattern_taxonomy
        result = validate_pattern_taxonomy()
        self.assertEqual(len(result['collisions']), 0,
                         f"Collisions: {result['collisions']}")
        self.assertEqual(len(result['oversized']), 0,
                         f"Oversized: {result['oversized']}")
        self.assertEqual(len(result['unregistered_domains']), 0,
                         f"Unregistered: {result['unregistered_domains']}")
        self.assertEqual(len(result['valid']), len(PATTERN_TYPES))

    def test_pattern_health_summary_healthy(self):
        """Pattern health summary should report healthy."""
        from apps.core.domain_registry.validation import get_pattern_health_summary
        summary = get_pattern_health_summary()
        self.assertEqual(summary['status'], 'healthy',
                         f"Pattern health drift: {summary}")
        self.assertEqual(summary['catalog_types'], len(PATTERN_TYPES))


class PatternEngineBaseTest(TestCase):
    """Base test with helper to create signal snapshots."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            email='pattern_test@test.com', password='test',
        )
        self.today = date.today()

    def _create_signal(self, signal_type, domain, score,
                       confidence=1.0, signal_class='verified_action',
                       offset_days=0):
        """Create a base signal snapshot."""
        return SignalSnapshot.objects.create(
            user=self.user,
            date=self.today - timedelta(days=offset_days),
            signal_type=signal_type,
            domain=domain,
            signal_class=signal_class,
            score=score,
            confidence=confidence,
            source_signals={'test': True},
        )

    def _create_declining_history(self, signal_type, domain,
                                  start_score=0.9, drop_per_day=0.1,
                                  signal_class='verified_action', days=7):
        """Create a 7-day declining history for a signal type."""
        for day in range(days):
            score = max(0.0, start_score - (day * drop_per_day))
            SignalSnapshot.objects.create(
                user=self.user,
                date=self.today - timedelta(days=(days - 1) - day),
                signal_type=signal_type,
                domain=domain,
                signal_class=signal_class,
                score=score,
                confidence=1.0,
                source_signals={'test': True},
            )


class RecoveryRiskPatternTest(PatternEngineBaseTest):
    """Test recovery_risk pattern: activity HIGH + biometrics LOW."""

    def test_fires_when_activity_high_biometrics_low(self):
        self._create_signal('health_activity', 'health', 0.9)
        self._create_signal('health_biometrics', 'health', 0.2)
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'recovery_risk'), None)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.signal_class, 'derived_pattern')
        self.assertEqual(pattern.domain, 'health')
        self.assertGreater(pattern.score, 0.0)
        self.assertLessEqual(pattern.score, 1.0)
        self.assertLess(pattern.confidence, 1.0)  # discounted

    def test_no_fire_when_biometrics_adequate(self):
        self._create_signal('health_activity', 'health', 0.9)
        self._create_signal('health_biometrics', 'health', 0.6)
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'recovery_risk'), None)
        self.assertIsNone(pattern)

    def test_no_fire_when_activity_low(self):
        self._create_signal('health_activity', 'health', 0.3)
        self._create_signal('health_biometrics', 'health', 0.2)
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'recovery_risk'), None)
        self.assertIsNone(pattern)

    def test_no_fire_when_missing_signals(self):
        self._create_signal('health_activity', 'health', 0.9)
        # No biometrics signal
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'recovery_risk'), None)
        self.assertIsNone(pattern)


class HolisticMomentumPatternTest(PatternEngineBaseTest):
    """Test holistic_momentum pattern: 3+ signals >= 0.7 across 2+ domains."""

    def test_fires_with_3_signals_2_domains(self):
        self._create_signal('health_activity', 'health', 0.8)
        self._create_signal('faith_practice', 'faith', 0.9)
        self._create_signal('mental_reflection', 'journal', 0.7)
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'holistic_momentum'), None)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.domain, 'purpose')
        self.assertGreaterEqual(pattern.score, 0.7)

    def test_no_fire_with_only_2_qualifying(self):
        self._create_signal('health_activity', 'health', 0.8)
        self._create_signal('faith_practice', 'faith', 0.9)
        self._create_signal('mental_reflection', 'journal', 0.3)  # below threshold
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'holistic_momentum'), None)
        self.assertIsNone(pattern)

    def test_no_fire_with_single_domain(self):
        self._create_signal('health_activity', 'health', 0.8)
        self._create_signal('health_biometrics', 'health', 0.9)
        self._create_signal('medication_adherence', 'health', 0.7)
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'holistic_momentum'), None)
        self.assertIsNone(pattern)


class DomainNeglectPatternTest(PatternEngineBaseTest):
    """Test domain_neglect pattern: 2+ signals in same domain ALL declining."""

    def test_fires_when_domain_all_declining(self):
        # Create 7-day declining history for 2 health signals
        self._create_declining_history(
            'health_activity', 'health', start_score=0.9, drop_per_day=0.1,
        )
        self._create_declining_history(
            'health_biometrics', 'health', start_score=0.8, drop_per_day=0.08,
            signal_class='verified_measurement',
        )
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'domain_neglect'), None)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.domain, 'life')  # domain_neglect → life
        self.assertEqual(pattern.source_signals['neglected_domain'], 'health')

    def test_no_fire_when_mixed_trends(self):
        # One improving, one declining
        for day in range(7):
            score = 0.3 + (day * 0.1)  # improving
            SignalSnapshot.objects.create(
                user=self.user,
                date=self.today - timedelta(days=(6 - day)),
                signal_type='health_activity',
                domain='health',
                signal_class='verified_action',
                score=score,
                confidence=1.0,
                source_signals={'test': True},
            )
        self._create_declining_history(
            'health_biometrics', 'health', start_score=0.8, drop_per_day=0.08,
            signal_class='verified_measurement',
        )
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'domain_neglect'), None)
        self.assertIsNone(pattern)


class ComplianceDriftPatternTest(PatternEngineBaseTest):
    """Test compliance_drift pattern: med_adherence + biometrics both declining."""

    def test_fires_when_both_declining(self):
        self._create_declining_history(
            'medication_adherence', 'health', start_score=0.9, drop_per_day=0.1,
        )
        self._create_declining_history(
            'health_biometrics', 'health', start_score=0.8, drop_per_day=0.08,
            signal_class='verified_measurement',
        )
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'compliance_drift'), None)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.domain, 'health')

    def test_no_fire_when_adherence_stable(self):
        # Stable adherence
        for day in range(7):
            SignalSnapshot.objects.create(
                user=self.user,
                date=self.today - timedelta(days=(6 - day)),
                signal_type='medication_adherence',
                domain='health',
                signal_class='verified_action',
                score=0.9,  # stable
                confidence=1.0,
                source_signals={'test': True},
            )
        self._create_declining_history(
            'health_biometrics', 'health', start_score=0.8, drop_per_day=0.08,
            signal_class='verified_measurement',
        )
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'compliance_drift'), None)
        self.assertIsNone(pattern)


class WellbeingConvergencePatternTest(PatternEngineBaseTest):
    """Test wellbeing_convergence pattern: 3 inner-life signals all >= 0.6."""

    def test_fires_when_all_three_above_threshold(self):
        self._create_signal('mental_reflection', 'journal', 0.8)
        self._create_signal('relational_engagement', 'relationships', 0.7)
        self._create_signal('faith_practice', 'faith', 0.6)
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'wellbeing_convergence'), None)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.domain, 'journal')

    def test_no_fire_when_one_below_threshold(self):
        self._create_signal('mental_reflection', 'journal', 0.8)
        self._create_signal('relational_engagement', 'relationships', 0.7)
        self._create_signal('faith_practice', 'faith', 0.3)  # below 0.6
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'wellbeing_convergence'), None)
        self.assertIsNone(pattern)

    def test_no_fire_when_signal_missing(self):
        self._create_signal('mental_reflection', 'journal', 0.8)
        self._create_signal('relational_engagement', 'relationships', 0.7)
        # No faith_practice
        results = PatternEngine.compute_patterns(self.user, self.today)
        pattern = next((r for r in results if r.signal_type == 'wellbeing_convergence'), None)
        self.assertIsNone(pattern)


class NoDataReturnsEmptyTest(PatternEngineBaseTest):
    """Test that no base signals produces no patterns."""

    def test_no_signals_returns_empty_list(self):
        results = PatternEngine.compute_patterns(self.user, self.today)
        self.assertEqual(results, [])


class PatternFlowsIntoCoSTest(PatternEngineBaseTest):
    """Verify pattern snapshots are queryable by the CoS signal builder."""

    def test_derived_patterns_appear_in_all_snapshots_query(self):
        """CoS queries ALL snapshots — patterns must be included."""
        self._create_signal('health_activity', 'health', 0.9)
        self._create_signal('health_biometrics', 'health', 0.2)
        PatternEngine.compute_patterns(self.user, self.today)

        # This mirrors the query in _build_signal_aware_context()
        all_snapshots = SignalSnapshot.objects.filter(
            user=self.user, date=self.today,
        )
        types = set(s.signal_type for s in all_snapshots)
        # Should include base signals AND recovery_risk pattern
        self.assertIn('health_activity', types)
        self.assertIn('health_biometrics', types)
        self.assertIn('recovery_risk', types)

    def test_pattern_excluded_from_base_signal_query(self):
        """Pattern engine must exclude derived_pattern when reading base signals."""
        self._create_signal('health_activity', 'health', 0.9)
        self._create_signal('health_biometrics', 'health', 0.2)
        PatternEngine.compute_patterns(self.user, self.today)

        # Running again should not cause patterns to feed back into patterns
        results2 = PatternEngine.compute_patterns(self.user, self.today)
        # Should still produce same pattern (update_or_create), no recursion
        pattern_types = [r.signal_type for r in results2]
        self.assertIn('recovery_risk', pattern_types)

        # Total derived patterns should be 1, not compounding
        derived_count = SignalSnapshot.objects.filter(
            user=self.user, date=self.today, signal_class='derived_pattern',
        ).count()
        self.assertEqual(derived_count, 1)


class PatternSignalClassTest(PatternEngineBaseTest):
    """Verify all patterns use the correct signal_class."""

    def test_all_patterns_use_derived_pattern_class(self):
        """Every pattern snapshot must have signal_class='derived_pattern'."""
        self._create_signal('health_activity', 'health', 0.9)
        self._create_signal('health_biometrics', 'health', 0.2)
        self._create_signal('faith_practice', 'faith', 0.8)
        self._create_signal('mental_reflection', 'journal', 0.8)
        self._create_signal('relational_engagement', 'relationships', 0.7)
        results = PatternEngine.compute_patterns(self.user, self.today)
        for pattern in results:
            self.assertEqual(
                pattern.signal_class, 'derived_pattern',
                f"Pattern {pattern.signal_type} has signal_class={pattern.signal_class}",
            )


class TrendHelperTest(TestCase):
    """Test the _get_trend_from_history helper."""

    def test_declining_trend(self):
        history = {
            'test_signal': [
                {'date': date.today() - timedelta(days=6), 'score': 0.9},
                {'date': date.today() - timedelta(days=5), 'score': 0.85},
                {'date': date.today() - timedelta(days=4), 'score': 0.7},
                {'date': date.today() - timedelta(days=3), 'score': 0.6},
                {'date': date.today() - timedelta(days=2), 'score': 0.5},
                {'date': date.today() - timedelta(days=1), 'score': 0.4},
                {'date': date.today(), 'score': 0.3},
            ],
        }
        self.assertEqual(_get_trend_from_history(history, 'test_signal'), 'declining')

    def test_improving_trend(self):
        history = {
            'test_signal': [
                {'date': date.today() - timedelta(days=3), 'score': 0.3},
                {'date': date.today() - timedelta(days=2), 'score': 0.5},
                {'date': date.today() - timedelta(days=1), 'score': 0.7},
                {'date': date.today(), 'score': 0.9},
            ],
        }
        self.assertEqual(_get_trend_from_history(history, 'test_signal'), 'improving')

    def test_stable_trend(self):
        history = {
            'test_signal': [
                {'date': date.today() - timedelta(days=1), 'score': 0.7},
                {'date': date.today(), 'score': 0.72},
            ],
        }
        self.assertEqual(_get_trend_from_history(history, 'test_signal'), 'stable')

    def test_missing_signal_returns_stable(self):
        self.assertEqual(_get_trend_from_history({}, 'nonexistent'), 'stable')

    def test_single_data_point_returns_stable(self):
        history = {
            'test_signal': [
                {'date': date.today(), 'score': 0.5},
            ],
        }
        self.assertEqual(_get_trend_from_history(history, 'test_signal'), 'stable')
