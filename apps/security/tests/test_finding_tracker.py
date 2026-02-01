# ==============================================================================
# File: apps/security/tests/test_finding_tracker.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Test cases for finding tracker utilities
# ==============================================================================
"""
Tests for Finding Tracker

Covers:
- Finding key generation
- Finding status analysis (new, recurring, fixed, regressed)
- Trend data generation
- Improvement metrics calculation
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.security.models import (
    SecurityRun,
    SecurityScore,
    SecurityFinding,
)
from apps.security.finding_tracker import (
    generate_finding_key,
    analyze_finding_status,
    get_finding_trend_data,
    get_improvement_metrics,
)


class GenerateFindingKeyTest(TestCase):
    """Test finding key generation."""

    def test_generate_finding_key_basic(self):
        """Test basic key generation."""
        key = generate_finding_key(
            title='Hardcoded API Key',
            severity='high',
            affected_components=['settings.py'],
        )
        self.assertIsNotNone(key)
        self.assertEqual(len(key), 64)  # SHA-256 truncated

    def test_generate_finding_key_deterministic(self):
        """Test key generation is deterministic."""
        key1 = generate_finding_key('Test Finding', 'high', ['module1'])
        key2 = generate_finding_key('Test Finding', 'high', ['module1'])
        self.assertEqual(key1, key2)

    def test_generate_finding_key_case_insensitive_title(self):
        """Test title is case-insensitive."""
        key1 = generate_finding_key('TEST FINDING', 'high', [])
        key2 = generate_finding_key('test finding', 'high', [])
        self.assertEqual(key1, key2)

    def test_generate_finding_key_different_severity(self):
        """Test different severity produces different key."""
        key1 = generate_finding_key('Test', 'high', [])
        key2 = generate_finding_key('Test', 'low', [])
        self.assertNotEqual(key1, key2)

    def test_generate_finding_key_different_components(self):
        """Test different components produce different key."""
        key1 = generate_finding_key('Test', 'high', ['module1'])
        key2 = generate_finding_key('Test', 'high', ['module2'])
        self.assertNotEqual(key1, key2)

    def test_generate_finding_key_component_order_independent(self):
        """Test component order doesn't affect key."""
        key1 = generate_finding_key('Test', 'high', ['module1', 'module2'])
        key2 = generate_finding_key('Test', 'high', ['module2', 'module1'])
        self.assertEqual(key1, key2)

    def test_generate_finding_key_empty_components(self):
        """Test empty components list works."""
        key = generate_finding_key('Test', 'high', [])
        self.assertIsNotNone(key)

    def test_generate_finding_key_none_components(self):
        """Test None components works."""
        key = generate_finding_key('Test', 'high', None)
        self.assertIsNotNone(key)


class AnalyzeFindingStatusTest(TestCase):
    """Test finding status analysis."""

    def _create_run_with_findings(self, finding_keys, status='completed'):
        """Helper to create a run with findings."""
        run = SecurityRun.objects.create(
            status=status,
            run_type='full',
        )
        for i, key in enumerate(finding_keys):
            finding = SecurityFinding.objects.create(
                run=run,
                finding_id=f'SEC-{i+1:03d}',
                title=f'Finding {i}',
                severity='medium',
                likelihood='medium',
                impact='medium',
                finding_key=key,
            )
            finding.description = "Test"
            finding.save()
        return run

    def test_analyze_first_run_all_new(self):
        """Test first run marks all findings as new."""
        run = self._create_run_with_findings(['key1', 'key2', 'key3'])

        stats = analyze_finding_status(run, previous_run=None)

        self.assertEqual(stats['new'], 3)
        self.assertEqual(stats['recurring'], 0)
        self.assertEqual(stats['fixed'], 0)
        self.assertEqual(stats['regressed'], 0)

        # Verify findings are marked as new
        for finding in run.findings.all():
            self.assertEqual(finding.status, SecurityFinding.STATUS_NEW)
            self.assertEqual(finding.first_seen_run_id, run.id)
            self.assertEqual(finding.occurrence_count, 1)

    def test_analyze_recurring_findings(self):
        """Test recurring findings are detected."""
        run1 = self._create_run_with_findings(['key1', 'key2'])
        analyze_finding_status(run1, previous_run=None)

        # Second run with same findings
        run2 = self._create_run_with_findings(['key1', 'key2'])

        stats = analyze_finding_status(run2, previous_run=run1)

        self.assertEqual(stats['new'], 0)
        self.assertEqual(stats['recurring'], 2)
        self.assertEqual(stats['fixed'], 0)

        # Verify findings are marked as recurring
        for finding in run2.findings.all():
            self.assertEqual(finding.status, SecurityFinding.STATUS_RECURRING)
            self.assertEqual(finding.occurrence_count, 2)

    def test_analyze_fixed_findings(self):
        """Test fixed findings are detected."""
        run1 = self._create_run_with_findings(['key1', 'key2', 'key3'])
        analyze_finding_status(run1, previous_run=None)

        # Second run with fewer findings (key2 and key3 fixed)
        run2 = self._create_run_with_findings(['key1'])

        stats = analyze_finding_status(run2, previous_run=run1)

        self.assertEqual(stats['new'], 0)
        self.assertEqual(stats['recurring'], 1)
        self.assertEqual(stats['fixed'], 2)

    def test_analyze_new_findings_in_second_run(self):
        """Test new findings in subsequent runs."""
        run1 = self._create_run_with_findings(['key1'])
        analyze_finding_status(run1, previous_run=None)

        # Second run with old and new findings
        run2 = self._create_run_with_findings(['key1', 'key2'])

        stats = analyze_finding_status(run2, previous_run=run1)

        self.assertEqual(stats['new'], 1)  # key2
        self.assertEqual(stats['recurring'], 1)  # key1

    def test_analyze_mixed_scenario(self):
        """Test mixed scenario with new, recurring, and fixed."""
        run1 = self._create_run_with_findings(['key1', 'key2', 'key3'])
        analyze_finding_status(run1, previous_run=None)

        # key1: recurring, key2: fixed, key3: fixed, key4: new
        run2 = self._create_run_with_findings(['key1', 'key4'])

        stats = analyze_finding_status(run2, previous_run=run1)

        self.assertEqual(stats['new'], 1)  # key4
        self.assertEqual(stats['recurring'], 1)  # key1
        self.assertEqual(stats['fixed'], 2)  # key2, key3

    def test_analyze_empty_runs(self):
        """Test analysis with empty runs."""
        run1 = self._create_run_with_findings([])
        analyze_finding_status(run1, previous_run=None)

        run2 = self._create_run_with_findings([])
        stats = analyze_finding_status(run2, previous_run=run1)

        self.assertEqual(stats['new'], 0)
        self.assertEqual(stats['recurring'], 0)
        self.assertEqual(stats['fixed'], 0)


class GetFindingTrendDataTest(TestCase):
    """Test finding trend data generation."""

    def _create_completed_run(self, days_ago=0, new=0, recurring=0, fixed=0, regressed=0):
        """Helper to create a completed run."""
        run = SecurityRun.objects.create(
            status=SecurityRun.STATUS_COMPLETED,
            run_timestamp=timezone.now() - timedelta(days=days_ago),
            total_findings=new + recurring,
            new_findings=new,
            recurring_findings=recurring,
            fixed_findings=fixed,
            regressed_findings=regressed,
        )
        return run

    def test_get_trend_data_empty(self):
        """Test trend data with no runs."""
        data = get_finding_trend_data(limit=10)

        self.assertEqual(data['labels'], [])
        self.assertEqual(data['new'], [])
        self.assertEqual(data['recurring'], [])
        self.assertEqual(data['fixed'], [])
        self.assertEqual(data['regressed'], [])

    def test_get_trend_data_single_run(self):
        """Test trend data with single run."""
        self._create_completed_run(days_ago=0, new=5, recurring=3, fixed=2, regressed=1)

        data = get_finding_trend_data(limit=10)

        self.assertEqual(len(data['labels']), 1)
        self.assertEqual(data['new'], [5])
        self.assertEqual(data['recurring'], [3])
        self.assertEqual(data['fixed'], [2])
        self.assertEqual(data['regressed'], [1])

    def test_get_trend_data_multiple_runs(self):
        """Test trend data with multiple runs."""
        self._create_completed_run(days_ago=2, new=3, recurring=1, fixed=0, regressed=0)
        self._create_completed_run(days_ago=1, new=1, recurring=2, fixed=1, regressed=0)
        self._create_completed_run(days_ago=0, new=0, recurring=2, fixed=1, regressed=0)

        data = get_finding_trend_data(limit=10)

        self.assertEqual(len(data['labels']), 3)
        # Data should be in chronological order
        self.assertEqual(data['new'], [3, 1, 0])
        self.assertEqual(data['fixed'], [0, 1, 1])

    def test_get_trend_data_limit(self):
        """Test trend data respects limit."""
        for i in range(10):
            self._create_completed_run(days_ago=i, new=i)

        data = get_finding_trend_data(limit=5)

        self.assertEqual(len(data['labels']), 5)

    def test_get_trend_data_excludes_non_completed(self):
        """Test only completed runs are included."""
        self._create_completed_run(days_ago=0, new=5)
        SecurityRun.objects.create(
            status=SecurityRun.STATUS_RUNNING,
            new_findings=10,
        )
        SecurityRun.objects.create(
            status=SecurityRun.STATUS_FAILED,
            new_findings=15,
        )

        data = get_finding_trend_data(limit=10)

        self.assertEqual(len(data['labels']), 1)
        self.assertEqual(data['new'], [5])


class GetImprovementMetricsTest(TestCase):
    """Test improvement metrics calculation."""

    def _create_run_with_score(self, days_ago=0, bitsight=750, risk=25, findings=5):
        """Helper to create a run with score."""
        run = SecurityRun.objects.create(
            status=SecurityRun.STATUS_COMPLETED,
            run_timestamp=timezone.now() - timedelta(days=days_ago),
            total_findings=findings,
            new_findings=2,
            fixed_findings=1,
            regressed_findings=0,
        )
        SecurityScore.objects.create(
            run=run,
            run_timestamp=run.run_timestamp,
            bitsight_score=bitsight,
            risk_score_0_100=risk,
            securityscorecard_grade='B',
        )
        return run

    def test_improvement_metrics_not_enough_data(self):
        """Test metrics with insufficient data."""
        # No runs
        metrics = get_improvement_metrics(days=30)
        self.assertIsNone(metrics['improvement'])
        self.assertIn('Not enough data', metrics['message'])

        # Single run
        self._create_run_with_score(days_ago=0)
        metrics = get_improvement_metrics(days=30)
        self.assertIsNone(metrics['improvement'])

    def test_improvement_metrics_basic(self):
        """Test basic improvement metrics."""
        # First run (worse)
        self._create_run_with_score(days_ago=20, bitsight=700, risk=40, findings=10)
        # Second run (better)
        self._create_run_with_score(days_ago=0, bitsight=800, risk=20, findings=5)

        metrics = get_improvement_metrics(days=30)

        self.assertIsNotNone(metrics['first_run'])
        self.assertIsNotNone(metrics['latest_run'])
        self.assertEqual(metrics['changes']['bitsight'], 100)  # 800 - 700
        self.assertEqual(metrics['changes']['risk'], 20)  # 40 - 20 (positive = improvement)
        self.assertEqual(metrics['changes']['findings'], 5)  # 10 - 5 (positive = improvement)
        self.assertTrue(metrics['improving'])

    def test_improvement_metrics_declining(self):
        """Test metrics when security is declining."""
        # First run (better)
        self._create_run_with_score(days_ago=20, bitsight=850, risk=10, findings=2)
        # Second run (worse)
        self._create_run_with_score(days_ago=0, bitsight=700, risk=40, findings=10)

        metrics = get_improvement_metrics(days=30)

        self.assertEqual(metrics['changes']['bitsight'], -150)
        self.assertFalse(metrics['improving'])

    def test_improvement_metrics_totals(self):
        """Test total fixed/new/regressed counts."""
        self._create_run_with_score(days_ago=20, bitsight=750, risk=25)
        self._create_run_with_score(days_ago=10, bitsight=775, risk=22)
        self._create_run_with_score(days_ago=0, bitsight=800, risk=20)

        metrics = get_improvement_metrics(days=30)

        # Each run has fixed_findings=1, new_findings=2
        self.assertEqual(metrics['totals']['fixed'], 3)  # 3 runs * 1
        self.assertEqual(metrics['totals']['new'], 6)  # 3 runs * 2

    def test_improvement_metrics_period_filter(self):
        """Test metrics respects the period filter."""
        # Run outside the period
        self._create_run_with_score(days_ago=45, bitsight=600, risk=50)
        # Runs within the period
        self._create_run_with_score(days_ago=15, bitsight=700, risk=35)
        self._create_run_with_score(days_ago=0, bitsight=800, risk=20)

        metrics = get_improvement_metrics(days=30)

        # Should only include the last 2 runs
        self.assertEqual(metrics['runs_count'], 2)
        self.assertEqual(metrics['first_run']['bitsight'], 700)
        self.assertEqual(metrics['latest_run']['bitsight'], 800)
