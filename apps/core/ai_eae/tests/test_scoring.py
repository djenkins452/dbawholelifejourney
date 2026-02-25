"""
EAE — Scoring & Normalization tests (Phase 8.2).
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_eae.constants import (
    CONFIDENCE_HIGH_BOOST,
    CONFIDENCE_LOW_PENALTY,
    WEIGHT_DRIFT_ANCHOR,
    WEIGHT_GOVERNANCE,
    WEIGHT_LOCAL_SCORE,
    WEIGHT_RECENCY,
    apply_intensity,
)
from apps.core.ai_eae.scorer import (
    ScoredSignal,
    _compute_drift_anchor,
    _compute_recency,
    score_signal,
)
from apps.core.ai_eae.signal_collector import RawSignal


def _make_signal(**kwargs):
    """Create a RawSignal with defaults."""
    defaults = {
        'engine': 'PIE',
        'signal_type': 'test_signal',
        'module': 'health',
        'title': 'Test Signal',
        'message': 'Test message',
        'local_score': 50.0,
        'confidence': 0.7,
        'severity': 'warning',
        'object_type': 'Insight',
        'object_id': 1,
        'created_at': timezone.now(),
    }
    defaults.update(kwargs)
    return RawSignal(**defaults)


class RecencyTests(TestCase):
    """Tests for recency decay calculation."""

    def test_brand_new_signal(self):
        """Signal created now has recency 1.0."""
        now = timezone.now()
        self.assertAlmostEqual(_compute_recency(now, now), 1.0, places=2)

    def test_signal_at_decay_limit(self):
        """Signal at 7 days old has recency ~0.0."""
        now = timezone.now()
        old = now - timedelta(hours=168)
        self.assertAlmostEqual(_compute_recency(old, now), 0.0, places=2)

    def test_signal_halfway(self):
        """Signal at 3.5 days old has recency ~0.5."""
        now = timezone.now()
        half = now - timedelta(hours=84)
        self.assertAlmostEqual(_compute_recency(half, now), 0.5, places=1)

    def test_none_created_at(self):
        """Unknown creation time defaults to 0.5."""
        self.assertAlmostEqual(_compute_recency(None), 0.5, places=2)

    def test_future_signal(self):
        """Future creation time clamps to 1.0."""
        now = timezone.now()
        future = now + timedelta(hours=1)
        self.assertAlmostEqual(_compute_recency(future, now), 1.0, places=2)


class DriftAnchorTests(TestCase):
    """Tests for drift anchor weight calculation."""

    def test_no_drift_no_anchor(self):
        """Zero drift produces zero anchor weight."""
        signal = _make_signal(module='health')
        result = _compute_drift_anchor(signal, 0.0, {}, {})
        self.assertEqual(result, 0.0)

    def test_module_drift_contributes(self):
        """Per-module drift score produces non-zero anchor."""
        signal = _make_signal(module='health')
        result = _compute_drift_anchor(
            signal, 0.0,
            module_drift_scores={'health': 60.0},
            governance_weights={'health': 2.0},
        )
        self.assertGreater(result, 0.0)

    def test_governance_weight_scales_anchor(self):
        """Higher governance weight produces higher anchor."""
        signal = _make_signal(module='health')
        anchor_high = _compute_drift_anchor(
            signal, 50.0, {}, {'health': 2.0},
        )
        anchor_low = _compute_drift_anchor(
            signal, 50.0, {}, {'health': 0.3},
        )
        self.assertGreater(anchor_high, anchor_low)

    def test_no_module_no_anchor(self):
        """Signal with no module gets zero anchor."""
        signal = _make_signal(module='')
        result = _compute_drift_anchor(signal, 80.0, {}, {'health': 2.0})
        self.assertEqual(result, 0.0)


class ScoreSignalTests(TestCase):
    """Tests for the full scoring formula."""

    def test_baseline_scoring(self):
        """Signal with baseline values produces reasonable score."""
        signal = _make_signal(local_score=50.0, confidence=0.7)
        scored = score_signal(
            signal, drift_risk_severity=0.0,
            module_drift_scores={},
            governance_weights={},
        )
        self.assertGreater(scored.normalized_score, 0)
        self.assertLessEqual(scored.normalized_score, 100)

    def test_high_confidence_boost(self):
        """Confidence >= 0.85 gets a score boost."""
        signal_high = _make_signal(local_score=50.0, confidence=0.90)
        signal_low = _make_signal(local_score=50.0, confidence=0.70)

        scored_high = score_signal(signal_high, 0.0, {}, {})
        scored_low = score_signal(signal_low, 0.0, {}, {})

        self.assertGreater(scored_high.normalized_score, scored_low.normalized_score)
        self.assertGreater(scored_high.confidence_modifier, 0)

    def test_low_confidence_penalty(self):
        """Confidence <= 0.50 gets a score penalty."""
        signal = _make_signal(local_score=50.0, confidence=0.40)
        scored = score_signal(signal, 0.0, {}, {})
        self.assertLess(scored.confidence_modifier, 0)

    def test_score_clamped_to_0_100(self):
        """Score is always within 0-100 range."""
        # Very high inputs
        signal_high = _make_signal(local_score=100.0, confidence=0.95)
        scored = score_signal(
            signal_high, 100.0,
            {'health': 100.0},
            {'health': 2.0},
        )
        self.assertLessEqual(scored.normalized_score, 100.0)

        # Very low inputs
        signal_low = _make_signal(local_score=0.0, confidence=0.1)
        scored = score_signal(signal_low, 0.0, {}, {})
        self.assertGreaterEqual(scored.normalized_score, 0.0)

    def test_drift_boosts_drifting_module(self):
        """A drifting module's signals get higher scores."""
        signal = _make_signal(module='health', local_score=50.0)
        scored_drifting = score_signal(
            signal, 80.0,
            {'health': 80.0},
            {'health': 2.0},
        )
        scored_stable = score_signal(signal, 0.0, {}, {})
        self.assertGreater(scored_drifting.normalized_score, scored_stable.normalized_score)

    def test_intensity_amplifies_drift_anchor(self):
        """Higher intensity increases drift anchor contribution."""
        signal = _make_signal(module='health')
        scored_normal = score_signal(
            signal, 60.0,
            {'health': 60.0}, {'health': 2.0},
            intensity=1.0,
        )
        scored_intense = score_signal(
            signal, 60.0,
            {'health': 60.0}, {'health': 2.0},
            intensity=1.5,
        )
        self.assertGreater(scored_intense.component_drift, scored_normal.component_drift)

    def test_scoring_breakdown_sums_correctly(self):
        """Component scores sum approximately to normalized_score (before confidence mod)."""
        signal = _make_signal(local_score=50.0, confidence=0.7)
        scored = score_signal(signal, 30.0, {}, {'health': 1.0})

        component_sum = (
            scored.component_local
            + scored.component_drift
            + scored.component_governance
            + scored.component_recency
            + scored.confidence_modifier
        )
        # Should be close to normalized (clamping may cause small diffs)
        self.assertAlmostEqual(scored.normalized_score, component_sum, delta=1.0)


class IntensityTests(TestCase):
    """Tests for intensity multiplier function."""

    def test_intensity_1_0_no_change(self):
        """Intensity 1.0 returns value unchanged."""
        self.assertEqual(apply_intensity(50, 1.0), 50)

    def test_intensity_above_1_multiplies(self):
        """Intensity > 1.0 increases value."""
        self.assertGreater(apply_intensity(50, 1.5), 50)

    def test_intensity_below_1_reduces(self):
        """Intensity < 1.0 decreases value."""
        self.assertLess(apply_intensity(50, 0.7), 50)

    def test_inverse_mode(self):
        """Inverse mode divides instead of multiplies."""
        # Higher intensity + inverse = lower value (more sensitive thresholds)
        self.assertLess(apply_intensity(50, 1.5, inverse=True), 50)

    def test_intensity_clamped(self):
        """Intensity is clamped to [0.5, 2.0]."""
        # Extreme values should be clamped
        result_low = apply_intensity(100, 0.1)  # Clamped to 0.5
        self.assertEqual(result_low, 50)  # 100 * 0.5

        result_high = apply_intensity(100, 5.0)  # Clamped to 2.0
        self.assertEqual(result_high, 200)  # 100 * 2.0
