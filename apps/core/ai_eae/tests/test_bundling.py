"""
EAE — Bundling & Budget tests (Phase 8.3).
"""
from datetime import timedelta
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_eae.budget import apply_budget, compute_budget
from apps.core.ai_eae.bundler import CognitiveUnit, bundle_signals
from apps.core.ai_eae.constants import (
    BUDGET_CHAT,
    BUDGET_CHAT_MAX,
    BUDGET_FLOOR,
    BUDGET_GLOBAL_DAILY,
    BUDGET_PUSH,
    BUNDLE_MAX_ITEMS,
    BUNDLE_MIN_ITEMS,
    BUNDLE_SCORE_BONUS,
    CHANNEL_BRIEFING,
    CHANNEL_CHAT,
    CHANNEL_PUSH,
)
from apps.core.ai_eae.scorer import ScoredSignal
from apps.core.ai_eae.signal_collector import RawSignal


def _make_scored(engine='PIE', module='health', signal_type='test',
                 score=50.0, confidence=0.7, severity='warning',
                 bundle_key='', title='Test'):
    """Create a ScoredSignal for testing."""
    raw = RawSignal(
        engine=engine, signal_type=signal_type, module=module,
        title=title, message='msg', local_score=score,
        confidence=confidence, severity=severity,
        object_type='Insight', object_id=1,
        created_at=timezone.now(), bundle_key=bundle_key,
    )
    return ScoredSignal(
        raw=raw, normalized_score=score,
        drift_anchor_weight=0.0, governance_weight=1.0,
        recency_weight=0.8,
    )


class BundlingTests(TestCase):
    """Tests for cognitive unit bundling."""

    def test_no_signals_empty_output(self):
        """Empty input produces empty output."""
        self.assertEqual(bundle_signals([]), [])

    def test_single_signal_becomes_single_unit(self):
        """One signal becomes one single unit."""
        sig = _make_scored(title='Medication reminder')
        units = bundle_signals([sig])
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].unit_type, 'single')
        self.assertEqual(units[0].title, 'Medication reminder')

    def test_two_same_key_bundle(self):
        """Two signals with same bundle_key become one bundle."""
        sig1 = _make_scored(bundle_key='PIE:health:warning', score=60, title='Med A')
        sig2 = _make_scored(bundle_key='PIE:health:warning', score=40, title='Med B')
        units = bundle_signals([sig1, sig2])

        bundles = [u for u in units if u.unit_type == 'bundle']
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0].bundled_count, 2)

    def test_bundle_inherits_highest_severity(self):
        """Bundle severity is the highest among its members."""
        sig1 = _make_scored(bundle_key='test:key', severity='info', score=30)
        sig2 = _make_scored(bundle_key='test:key', severity='critical', score=80)
        units = bundle_signals([sig1, sig2])
        bundles = [u for u in units if u.unit_type == 'bundle']
        self.assertEqual(bundles[0].severity, 'critical')

    def test_bundle_score_includes_bonus(self):
        """Bundle score = max(member_scores) + BUNDLE_SCORE_BONUS."""
        sig1 = _make_scored(bundle_key='test:key', score=60)
        sig2 = _make_scored(bundle_key='test:key', score=40)
        units = bundle_signals([sig1, sig2])
        bundles = [u for u in units if u.unit_type == 'bundle']
        self.assertEqual(bundles[0].normalized_score, 60 + BUNDLE_SCORE_BONUS)

    def test_bundle_max_items_cap(self):
        """Bundles are capped at BUNDLE_MAX_ITEMS."""
        signals = [
            _make_scored(bundle_key='test:cap', score=100 - i, title=f'Sig {i}')
            for i in range(8)
        ]
        units = bundle_signals(signals)
        bundles = [u for u in units if u.unit_type == 'bundle']
        for b in bundles:
            self.assertLessEqual(b.bundled_count, BUNDLE_MAX_ITEMS)

    def test_different_keys_stay_separate(self):
        """Signals with different bundle_keys are not bundled together."""
        sig1 = _make_scored(bundle_key='PIE:health:warning', title='Health A')
        sig2 = _make_scored(bundle_key='PIE:faith:info', title='Faith B')
        units = bundle_signals([sig1, sig2])
        self.assertEqual(len(units), 2)
        for u in units:
            self.assertEqual(u.unit_type, 'single')

    def test_cognitive_unit_to_dict(self):
        """CognitiveUnit serializes to dict correctly."""
        sig = _make_scored(title='Test Unit')
        units = bundle_signals([sig])
        d = units[0].to_dict()
        self.assertIn('unit_id', d)
        self.assertIn('title', d)
        self.assertIn('source_items', d)
        self.assertEqual(d['title'], 'Test Unit')


class BudgetTests(TestCase):
    """Tests for noise budget enforcement."""

    def test_default_chat_budget(self):
        """Chat channel has default budget of 3."""
        budget = compute_budget(CHANNEL_CHAT)
        self.assertEqual(budget, BUDGET_CHAT)

    def test_push_budget_is_1(self):
        """Push channel has budget of 1."""
        budget = compute_budget(CHANNEL_PUSH)
        self.assertEqual(budget, BUDGET_PUSH)

    def test_critical_capacity_reduces_budget(self):
        """Critical capacity reduces budget by 2."""
        budget = compute_budget(CHANNEL_CHAT, capacity_score=0.1)
        self.assertEqual(budget, max(BUDGET_FLOOR, BUDGET_CHAT - 2))

    def test_low_capacity_reduces_budget(self):
        """Low capacity reduces budget by 1."""
        # Use 0.21 — above critical threshold (0.2) but below low threshold
        # (model default 0.25 or code fallback 0.4)
        budget = compute_budget(CHANNEL_CHAT, capacity_score=0.21)
        self.assertEqual(budget, BUDGET_CHAT - 1)

    def test_high_capacity_increases_budget(self):
        """High capacity increases budget by 1."""
        budget = compute_budget(CHANNEL_CHAT, capacity_score=0.8)
        self.assertEqual(budget, BUDGET_CHAT + 1)

    def test_budget_floor_enforced(self):
        """Budget never goes below BUDGET_FLOOR."""
        budget = compute_budget(CHANNEL_PUSH, capacity_score=0.1)
        self.assertGreaterEqual(budget, BUDGET_FLOOR)

    def test_budget_hard_max_enforced(self):
        """Budget never exceeds hard maximum."""
        budget = compute_budget(CHANNEL_CHAT, capacity_score=0.99)
        self.assertLessEqual(budget, BUDGET_CHAT_MAX)

    def test_global_daily_budget(self):
        """Global daily budget caps total across channels."""
        budget = compute_budget(CHANNEL_CHAT, daily_used=BUDGET_GLOBAL_DAILY)
        self.assertEqual(budget, 0)

    def test_apply_budget_ranks_units(self):
        """apply_budget assigns sequential ranks to surfaced units."""
        units = [
            CognitiveUnit(unit_id='a', normalized_score=90, confidence=0.9),
            CognitiveUnit(unit_id='b', normalized_score=70, confidence=0.8),
            CognitiveUnit(unit_id='c', normalized_score=50, confidence=0.7),
        ]
        surfaced, suppressed, _ = apply_budget(units, CHANNEL_CHAT)
        self.assertEqual(surfaced[0].rank, 1)
        self.assertEqual(surfaced[1].rank, 2)
        self.assertEqual(surfaced[2].rank, 3)

    def test_apply_budget_suppresses_extras(self):
        """Extra units beyond budget are suppressed with reason."""
        units = [
            CognitiveUnit(unit_id=str(i), normalized_score=100-i*10, confidence=0.9)
            for i in range(6)
        ]
        surfaced, suppressed, budget = apply_budget(units, CHANNEL_CHAT)
        self.assertEqual(len(surfaced), budget)
        self.assertGreater(len(suppressed), 0)
        self.assertEqual(suppressed[0]['reason'], 'BUDGET_CAP')

    def test_empty_input_empty_output(self):
        """No units produces no output."""
        surfaced, suppressed, budget = apply_budget([], CHANNEL_CHAT)
        self.assertEqual(surfaced, [])
        self.assertEqual(suppressed, [])
