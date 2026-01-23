# ==============================================================================
# File: apps/security/finding_tracker.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Cross-run finding tracking and trending utilities
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-23
# ==============================================================================
"""
Finding Tracker

Tracks finding status across security assessment runs:
- New: Finding appearing for the first time
- Recurring: Finding that exists in consecutive runs
- Fixed: Finding from previous run that no longer appears
- Regressed: Previously fixed finding that reappeared

Uses finding_key for stable identification across runs.
"""

import hashlib
import logging
from typing import Optional

from django.db.models import Q

logger = logging.getLogger(__name__)


def generate_finding_key(title: str, severity: str, affected_components: list = None) -> str:
    """
    Generate a stable key for a finding based on its characteristics.

    The key is used to track findings across runs even if finding_id changes.

    Args:
        title: Finding title
        severity: Finding severity
        affected_components: List of affected components

    Returns:
        SHA-256 hash truncated to 64 chars
    """
    components_str = ','.join(sorted(affected_components or []))
    data = f"{title.lower().strip()}:{severity}:{components_str}"
    return hashlib.sha256(data.encode()).hexdigest()[:64]


def analyze_finding_status(current_run, previous_run=None) -> dict:
    """
    Analyze finding status by comparing current run to previous run.

    Args:
        current_run: The current SecurityRun
        previous_run: The previous completed SecurityRun (optional)

    Returns:
        Dict with counts: new, recurring, fixed, regressed
    """
    from apps.security.models import SecurityFinding, SecurityRun

    current_findings = list(current_run.findings.all())
    current_keys = {f.finding_key or generate_finding_key(f.title, f.severity): f for f in current_findings}

    stats = {
        'new': 0,
        'recurring': 0,
        'fixed': 0,
        'regressed': 0,
    }

    if not previous_run:
        # First run - all findings are new
        stats['new'] = len(current_findings)
        for finding in current_findings:
            finding.status = SecurityFinding.STATUS_NEW
            finding.first_seen_run_id = current_run.id
            finding.occurrence_count = 1
            finding.save(update_fields=['status', 'first_seen_run_id', 'occurrence_count'])
        return stats

    # Get previous run's findings
    previous_findings = list(previous_run.findings.all())
    previous_keys = {f.finding_key or generate_finding_key(f.title, f.severity): f for f in previous_findings}

    # Also check for historically fixed findings that might regress
    # Look at all findings ever detected
    all_historical_keys = set()
    fixed_keys = set()

    historical_runs = SecurityRun.objects.filter(
        status=SecurityRun.STATUS_COMPLETED,
        run_timestamp__lt=current_run.run_timestamp,
    ).order_by('run_timestamp')

    for run in historical_runs:
        run_keys = set()
        for f in run.findings.all():
            key = f.finding_key or generate_finding_key(f.title, f.severity)
            run_keys.add(key)
            all_historical_keys.add(key)

        # Keys that were in history but not in this run are "fixed"
        # This is simplified - we track the latest state
        if run == previous_run:
            fixed_keys = all_historical_keys - run_keys

    # Analyze each current finding
    for key, finding in current_keys.items():
        if key in previous_keys:
            # Existed in previous run - recurring
            finding.status = SecurityFinding.STATUS_RECURRING
            # Get original first_seen from previous finding
            prev_finding = previous_keys[key]
            finding.first_seen_run_id = prev_finding.first_seen_run_id or previous_run.id
            finding.occurrence_count = prev_finding.occurrence_count + 1
            stats['recurring'] += 1
        elif key in fixed_keys:
            # Was fixed but came back - regressed
            finding.status = SecurityFinding.STATUS_REGRESSED
            finding.occurrence_count = 1  # Reset count for regression
            stats['regressed'] += 1
        else:
            # Never seen before - new
            finding.status = SecurityFinding.STATUS_NEW
            finding.first_seen_run_id = current_run.id
            finding.occurrence_count = 1
            stats['new'] += 1

        finding.save(update_fields=['status', 'first_seen_run_id', 'occurrence_count'])

    # Count fixed findings (were in previous, not in current)
    for key in previous_keys:
        if key not in current_keys:
            stats['fixed'] += 1

    return stats


def get_finding_trend_data(limit: int = 20) -> dict:
    """
    Get trend data for findings across recent runs.

    Args:
        limit: Number of runs to include

    Returns:
        Dict with labels and series data for charting
    """
    from apps.security.models import SecurityRun

    runs = SecurityRun.objects.filter(
        status=SecurityRun.STATUS_COMPLETED
    ).order_by('-run_timestamp')[:limit]

    data = {
        'labels': [],
        'total': [],
        'new': [],
        'recurring': [],
        'fixed': [],
        'regressed': [],
    }

    for run in reversed(list(runs)):
        data['labels'].append(run.run_timestamp.strftime('%m/%d'))
        data['total'].append(run.total_findings)
        data['new'].append(run.new_findings)
        data['recurring'].append(run.recurring_findings)
        data['fixed'].append(run.fixed_findings)
        data['regressed'].append(run.regressed_findings)

    return data


def get_improvement_metrics(days: int = 30) -> dict:
    """
    Calculate security improvement metrics over time.

    Args:
        days: Number of days to analyze

    Returns:
        Dict with improvement metrics
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.security.models import SecurityRun, SecurityScore

    cutoff = timezone.now() - timedelta(days=days)

    # Get first and latest runs in the period
    runs = SecurityRun.objects.filter(
        status=SecurityRun.STATUS_COMPLETED,
        run_timestamp__gte=cutoff,
    ).order_by('run_timestamp')

    if runs.count() < 2:
        return {
            'period_days': days,
            'runs_count': runs.count(),
            'improvement': None,
            'message': 'Not enough data for comparison',
        }

    first_run = runs.first()
    latest_run = runs.last()

    try:
        first_score = first_run.score
        latest_score = latest_run.score
    except Exception:
        return {
            'period_days': days,
            'runs_count': runs.count(),
            'improvement': None,
            'message': 'Score data not available',
        }

    # Calculate improvement metrics
    bitsight_change = latest_score.bitsight_score - first_score.bitsight_score
    risk_change = first_score.risk_score_0_100 - latest_score.risk_score_0_100  # Lower is better
    findings_change = first_run.total_findings - latest_run.total_findings  # Lower is better

    # Count total fixed vs new across all runs
    total_fixed = sum(r.fixed_findings for r in runs)
    total_new = sum(r.new_findings for r in runs)
    total_regressed = sum(r.regressed_findings for r in runs)

    return {
        'period_days': days,
        'runs_count': runs.count(),
        'first_run': {
            'date': first_run.run_timestamp,
            'bitsight': first_score.bitsight_score,
            'risk': first_score.risk_score_0_100,
            'findings': first_run.total_findings,
            'grade': first_score.securityscorecard_grade,
        },
        'latest_run': {
            'date': latest_run.run_timestamp,
            'bitsight': latest_score.bitsight_score,
            'risk': latest_score.risk_score_0_100,
            'findings': latest_run.total_findings,
            'grade': latest_score.securityscorecard_grade,
        },
        'changes': {
            'bitsight': bitsight_change,
            'risk': risk_change,
            'findings': findings_change,
        },
        'totals': {
            'fixed': total_fixed,
            'new': total_new,
            'regressed': total_regressed,
            'net_fixed': total_fixed - total_new - total_regressed,
        },
        'improving': bitsight_change >= 0 and risk_change >= 0,
    }
