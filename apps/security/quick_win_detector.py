# ==============================================================================
# File: apps/security/quick_win_detector.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Auto-detect quick wins based on finding patterns
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-23
# ==============================================================================
"""
Quick Win Detector

Automatically identifies findings that are likely quick wins based on:
- Title patterns (missing headers, default configs, etc.)
- Low remediation effort
- Low CVSS scores with simple fixes
- Keyword analysis in descriptions and recommendations

Quick wins are typically:
- Configuration changes (no code needed)
- Single-line fixes
- Well-documented standard remediations
- Low risk of regression
"""

import logging
import re
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


# Patterns that indicate quick wins (case-insensitive)
QUICK_WIN_TITLE_PATTERNS = [
    r'missing.*header',
    r'x-frame-options',
    r'x-content-type',
    r'x-xss-protection',
    r'strict-transport-security',
    r'content-security-policy.*missing',
    r'referrer-policy',
    r'permissions-policy',
    r'default.*config',
    r'default.*credential',
    r'debug.*enabled',
    r'verbose.*error',
    r'error.*messages',
    r'information.*disclosure',
    r'cookie.*flag',
    r'secure.*flag',
    r'httponly.*flag',
    r'samesite.*attribute',
    r'password.*policy',
    r'session.*timeout',
    r'idle.*timeout',
    r'rate.*limit',
    r'csrf.*token',
    r'clickjack',
    r'autocomplete',
    r'logging.*level',
    r'sensitive.*log',
    r'cors.*configuration',
]

# Keywords in recommendations that indicate quick wins
QUICK_WIN_RECOMMENDATION_KEYWORDS = [
    'add header',
    'set header',
    'configure',
    'enable',
    'disable',
    'set flag',
    'add flag',
    'change setting',
    'update setting',
    'modify configuration',
    'single line',
    'one line',
    'environment variable',
    'env var',
    '.env file',
    'settings.py',
    'configuration file',
]

# Keywords that indicate NOT a quick win
NON_QUICK_WIN_KEYWORDS = [
    'refactor',
    'redesign',
    'rewrite',
    'major change',
    'significant change',
    'architecture',
    'database migration',
    'schema change',
    'breaking change',
    'complex',
    'extensive',
    'multiple files',
    'across the codebase',
    'security audit',
    'penetration test',
]


def is_quick_win_by_title(title: str) -> bool:
    """
    Check if a finding is likely a quick win based on its title.

    Args:
        title: Finding title

    Returns:
        True if title matches quick win patterns
    """
    title_lower = title.lower()
    for pattern in QUICK_WIN_TITLE_PATTERNS:
        if re.search(pattern, title_lower):
            return True
    return False


def is_quick_win_by_recommendations(recommendations: list) -> bool:
    """
    Check if recommendations indicate a quick win.

    Args:
        recommendations: List of recommendation strings

    Returns:
        True if recommendations suggest quick fixes
    """
    if not recommendations:
        return False

    all_text = ' '.join(recommendations).lower()

    # Check for non-quick-win keywords first
    for keyword in NON_QUICK_WIN_KEYWORDS:
        if keyword in all_text:
            return False

    # Check for quick win keywords
    quick_win_matches = sum(1 for kw in QUICK_WIN_RECOMMENDATION_KEYWORDS if kw in all_text)

    # If at least 2 quick win keywords and no blockers, it's likely a quick win
    return quick_win_matches >= 2


def is_quick_win_by_effort(remediation_effort: str, cvss_score: Decimal) -> bool:
    """
    Check if effort and CVSS indicate a quick win.

    Low effort + low/medium CVSS = likely quick win
    Low effort + high/critical CVSS = important but still quick

    Args:
        remediation_effort: 'low', 'medium', or 'high'
        cvss_score: CVSS score decimal

    Returns:
        True if effort level suggests quick win
    """
    # Low effort is always a quick win candidate
    if remediation_effort == 'low':
        return True

    # Medium effort with low CVSS is also a quick win
    if remediation_effort == 'medium' and cvss_score < Decimal('4.0'):
        return True

    return False


def detect_quick_win(
    title: str,
    severity: str,
    cvss_score: Decimal,
    remediation_effort: str,
    recommendations: list = None,
    description: str = '',
) -> tuple[bool, str]:
    """
    Determine if a finding is a quick win and provide reasoning.

    Args:
        title: Finding title
        severity: Finding severity
        cvss_score: CVSS score
        remediation_effort: Effort level
        recommendations: List of recommendations
        description: Finding description

    Returns:
        Tuple of (is_quick_win, reason)
    """
    reasons = []

    # Check title patterns
    if is_quick_win_by_title(title):
        reasons.append('Title matches known quick-fix pattern')

    # Check effort level
    if is_quick_win_by_effort(remediation_effort, cvss_score):
        reasons.append(f'Low remediation effort ({remediation_effort})')

    # Check recommendations
    if is_quick_win_by_recommendations(recommendations):
        reasons.append('Recommendations suggest simple configuration changes')

    # Critical findings are never quick wins (even if easy) - they need proper testing
    if severity == 'critical':
        return False, 'Critical findings require thorough testing'

    # Determine result
    if len(reasons) >= 2:
        return True, '; '.join(reasons)
    elif len(reasons) == 1 and remediation_effort == 'low':
        return True, reasons[0]

    return False, 'Does not match quick win criteria'


def update_finding_quick_win_status(finding) -> bool:
    """
    Update a SecurityFinding's is_quick_win field based on auto-detection.

    Args:
        finding: SecurityFinding instance

    Returns:
        True if the finding was marked as a quick win
    """
    # If already marked as quick win, don't change it
    if finding.is_quick_win:
        return True

    is_quick, reason = detect_quick_win(
        title=finding.title,
        severity=finding.severity,
        cvss_score=finding.cvss_score,
        remediation_effort=finding.remediation_effort,
        recommendations=finding.recommendations or [],
        description=finding.description or '',
    )

    if is_quick:
        finding.is_quick_win = True
        finding.save(update_fields=['is_quick_win'])
        logger.info(f"Auto-marked {finding.finding_id} as quick win: {reason}")
        return True

    return False


def process_run_quick_wins(run) -> dict:
    """
    Process all findings in a run and auto-detect quick wins.

    Args:
        run: SecurityRun instance

    Returns:
        Dict with counts: total, detected, already_marked
    """
    stats = {
        'total': 0,
        'detected': 0,
        'already_marked': 0,
    }

    for finding in run.findings.all():
        stats['total'] += 1

        if finding.is_quick_win:
            stats['already_marked'] += 1
        elif update_finding_quick_win_status(finding):
            stats['detected'] += 1

    logger.info(
        f"Quick win detection for run {run.id}: "
        f"{stats['detected']} newly detected, "
        f"{stats['already_marked']} already marked, "
        f"{stats['total']} total findings"
    )

    return stats
