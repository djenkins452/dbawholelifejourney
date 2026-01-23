# ==============================================================================
# File: apps/security/scoring.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security scoring engine - CVSS, grades, BitSight, risk, maturity
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Security Scoring Engine

Computes security scores from assessment findings:
- CVSS v3.1 statistics (average, severity counts)
- SecurityScorecard grade (A-F)
- BitSight-style score (250-900)
- Risk score (0-100)
- AppSec maturity level (0-3)

All formulas are documented and reproducible.
"""

from decimal import Decimal
from typing import NamedTuple


class ScoreResult(NamedTuple):
    """Security score calculation result."""
    cvss_avg: Decimal
    cvss_critical_count: int
    cvss_high_count: int
    cvss_medium_count: int
    cvss_low_count: int
    cvss_none_count: int
    securityscorecard_grade: str
    bitsight_score: int
    risk_score_0_100: int
    maturity_level: int
    methodology: dict


class ScoringEngine:
    """
    Security Scoring Engine.

    Computes multiple security scores from findings data.
    All formulas are documented and reproducible.
    """

    # CVSS severity thresholds (CVSS v3.1)
    CVSS_CRITICAL_MIN = Decimal('9.0')
    CVSS_HIGH_MIN = Decimal('7.0')
    CVSS_MEDIUM_MIN = Decimal('4.0')
    CVSS_LOW_MIN = Decimal('0.1')

    # SecurityScorecard grade thresholds
    GRADE_THRESHOLDS = {
        'A': {'max_cvss_avg': Decimal('2.0'), 'max_critical': 0, 'max_high': 0},
        'B': {'max_cvss_avg': Decimal('4.0'), 'max_critical': 0, 'max_high': 2},
        'C': {'max_cvss_avg': Decimal('6.0'), 'max_critical': 1, 'max_high': 5},
        'D': {'max_cvss_avg': Decimal('8.0'), 'max_critical': 2, 'max_high': 10},
        'F': {'max_cvss_avg': Decimal('10.0'), 'max_critical': 999, 'max_high': 999},
    }

    # BitSight score formula weights
    BITSIGHT_BASE = 900
    BITSIGHT_CRITICAL_PENALTY = 100
    BITSIGHT_HIGH_PENALTY = 50
    BITSIGHT_MEDIUM_PENALTY = 25
    BITSIGHT_LOW_PENALTY = 10
    BITSIGHT_MIN = 250

    # Risk score weights
    RISK_CRITICAL_WEIGHT = 25
    RISK_HIGH_WEIGHT = 15
    RISK_MEDIUM_WEIGHT = 8
    RISK_LOW_WEIGHT = 3

    # Maturity indicators
    MATURITY_INDICATORS = {
        'encryption_at_rest': 10,
        'rate_limiting': 10,
        'security_logging': 10,
        'csp_with_nonce': 10,
        'csrf_protection': 10,
        'audit_logging': 10,
        'mfa_available': 10,
        'waf_enabled': 10,
        'pii_redaction': 10,
        'soft_delete': 10,
    }

    def calculate_scores(
        self,
        findings: list,
        test_results: list,
    ) -> ScoreResult:
        """
        Calculate all security scores from findings and test results.

        Args:
            findings: List of Finding objects with cvss_score
            test_results: List of TestResult objects

        Returns:
            ScoreResult with all computed scores
        """
        # Calculate CVSS statistics
        cvss_stats = self._calculate_cvss_stats(findings)

        # Calculate SecurityScorecard grade
        grade = self._calculate_grade(
            cvss_stats['avg'],
            cvss_stats['critical'],
            cvss_stats['high'],
        )

        # Calculate BitSight score
        bitsight = self._calculate_bitsight(
            cvss_stats['critical'],
            cvss_stats['high'],
            cvss_stats['medium'],
            cvss_stats['low'],
            test_results,
        )

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            cvss_stats['critical'],
            cvss_stats['high'],
            cvss_stats['medium'],
            cvss_stats['low'],
            findings,
        )

        # Calculate maturity level
        maturity = self._calculate_maturity(test_results)

        # Build methodology documentation
        methodology = self._build_methodology(
            cvss_stats, grade, bitsight, risk_score, maturity
        )

        return ScoreResult(
            cvss_avg=cvss_stats['avg'],
            cvss_critical_count=cvss_stats['critical'],
            cvss_high_count=cvss_stats['high'],
            cvss_medium_count=cvss_stats['medium'],
            cvss_low_count=cvss_stats['low'],
            cvss_none_count=cvss_stats['none'],
            securityscorecard_grade=grade,
            bitsight_score=bitsight,
            risk_score_0_100=risk_score,
            maturity_level=maturity,
            methodology=methodology,
        )

    def _calculate_cvss_stats(self, findings: list) -> dict:
        """Calculate CVSS statistics from findings."""
        if not findings:
            return {
                'avg': Decimal('0.0'),
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0,
                'none': 0,
            }

        scores = [f.cvss_score for f in findings if f.cvss_score]
        if not scores:
            return {
                'avg': Decimal('0.0'),
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0,
                'none': 0,
            }

        # Calculate average
        avg = sum(scores) / len(scores)
        avg = Decimal(str(round(float(avg), 2)))

        # Count by severity
        critical = sum(1 for s in scores if s >= self.CVSS_CRITICAL_MIN)
        high = sum(1 for s in scores if self.CVSS_HIGH_MIN <= s < self.CVSS_CRITICAL_MIN)
        medium = sum(1 for s in scores if self.CVSS_MEDIUM_MIN <= s < self.CVSS_HIGH_MIN)
        low = sum(1 for s in scores if self.CVSS_LOW_MIN <= s < self.CVSS_MEDIUM_MIN)
        none = sum(1 for s in scores if s < self.CVSS_LOW_MIN)

        return {
            'avg': avg,
            'critical': critical,
            'high': high,
            'medium': medium,
            'low': low,
            'none': none,
        }

    def _calculate_grade(
        self,
        cvss_avg: Decimal,
        critical_count: int,
        high_count: int,
    ) -> str:
        """
        Calculate SecurityScorecard-style grade (A-F).

        Rubric:
        - A: CVSS avg < 2.0, no Critical, no High
        - B: CVSS avg < 4.0, no Critical, <= 2 High
        - C: CVSS avg < 6.0, <= 1 Critical, <= 5 High
        - D: CVSS avg < 8.0, <= 2 Critical, <= 10 High
        - F: Anything worse
        """
        for grade in ['A', 'B', 'C', 'D', 'F']:
            thresholds = self.GRADE_THRESHOLDS[grade]
            if (cvss_avg < thresholds['max_cvss_avg'] and
                critical_count <= thresholds['max_critical'] and
                high_count <= thresholds['max_high']):
                return grade

        return 'F'

    def _calculate_bitsight(
        self,
        critical: int,
        high: int,
        medium: int,
        low: int,
        test_results: list,
    ) -> int:
        """
        Calculate BitSight-style score (250-900).

        Formula:
        base (900) - penalties for findings + bonuses for controls

        Penalties:
        - Critical: -100 each
        - High: -50 each
        - Medium: -25 each
        - Low: -10 each

        Bonuses (up to +50):
        - +5 for each passed critical security test
        """
        # Calculate penalties
        penalty = (
            critical * self.BITSIGHT_CRITICAL_PENALTY +
            high * self.BITSIGHT_HIGH_PENALTY +
            medium * self.BITSIGHT_MEDIUM_PENALTY +
            low * self.BITSIGHT_LOW_PENALTY
        )

        # Calculate bonus for passed tests
        passed_tests = sum(1 for t in test_results if t.result == 'pass')
        total_tests = len([t for t in test_results if t.result != 'skipped'])
        if total_tests > 0:
            pass_rate = passed_tests / total_tests
            bonus = int(pass_rate * 50)  # Up to 50 points
        else:
            bonus = 0

        score = self.BITSIGHT_BASE - penalty + bonus

        # Clamp to valid range
        return max(self.BITSIGHT_MIN, min(900, score))

    def _calculate_risk_score(
        self,
        critical: int,
        high: int,
        medium: int,
        low: int,
        findings: list,
    ) -> int:
        """
        Calculate risk score (0-100).

        Formula:
        (critical * 25 + high * 15 + medium * 8 + low * 3) × exposure_factor

        Exposure factor (0.5-1.0):
        - 1.0 if findings affect crown jewels (auth, finance, health)
        - 0.8 if findings affect user data
        - 0.5 if findings are infrastructure-only
        """
        raw_score = (
            critical * self.RISK_CRITICAL_WEIGHT +
            high * self.RISK_HIGH_WEIGHT +
            medium * self.RISK_MEDIUM_WEIGHT +
            low * self.RISK_LOW_WEIGHT
        )

        # Determine exposure factor based on affected components
        exposure_factor = 0.5  # Default: infrastructure only

        for finding in findings:
            components = getattr(finding, 'affected_components', []) or []
            components_str = ' '.join(str(c).lower() for c in components)

            if any(kw in components_str for kw in ['auth', 'finance', 'billing', 'health', 'password', 'token']):
                exposure_factor = 1.0
                break
            elif any(kw in components_str for kw in ['user', 'journal', 'personal', 'pii']):
                exposure_factor = max(exposure_factor, 0.8)

        risk_score = int(raw_score * exposure_factor)

        # Clamp to 0-100
        return min(100, max(0, risk_score))

    def _calculate_maturity(self, test_results: list) -> int:
        """
        Calculate AppSec maturity level (0-3).

        Levels:
        - 0 (Ad Hoc): < 40% of security controls implemented
        - 1 (Basic): 40-60% of security controls implemented
        - 2 (Managed): 60-80% of security controls implemented
        - 3 (Mature): > 80% of security controls implemented

        Key indicators (from test results):
        - Encryption at rest
        - Rate limiting
        - Security logging
        - CSP with nonce
        - CSRF protection
        - Audit logging
        - MFA available
        - WAF/CDN (would be unknown/fail if not present)
        - PII redaction in logs
        - Soft delete/retention
        """
        indicator_tests = {
            'encryption_at_rest': ['SEC-T025'],
            'rate_limiting': ['SEC-T011'],
            'security_logging': ['SEC-T030'],
            'csp_with_nonce': ['SEC-T035'],
            'csrf_protection': ['SEC-T023'],
            'audit_logging': ['SEC-T031'],
            'mfa_available': ['SEC-T012'],
            'pii_redaction': ['SEC-T028'],
            'soft_delete': ['SEC-T029'],
            'password_hashing': ['SEC-T027'],
        }

        # Build test results lookup
        test_lookup = {t.test_id: t.result for t in test_results}

        # Count passed indicators
        passed_indicators = 0
        total_indicators = len(indicator_tests)

        for indicator, test_ids in indicator_tests.items():
            for test_id in test_ids:
                if test_lookup.get(test_id) == 'pass':
                    passed_indicators += 1
                    break

        # Calculate percentage
        if total_indicators == 0:
            percentage = 0
        else:
            percentage = (passed_indicators / total_indicators) * 100

        # Determine maturity level
        if percentage >= 80:
            return 3  # Mature
        elif percentage >= 60:
            return 2  # Managed
        elif percentage >= 40:
            return 1  # Basic
        else:
            return 0  # Ad Hoc

    def _build_methodology(
        self,
        cvss_stats: dict,
        grade: str,
        bitsight: int,
        risk_score: int,
        maturity: int,
    ) -> dict:
        """Build methodology documentation."""
        return {
            'cvss': {
                'version': '3.1',
                'formula': 'Average of all finding CVSS scores',
                'severity_thresholds': {
                    'critical': '9.0-10.0',
                    'high': '7.0-8.9',
                    'medium': '4.0-6.9',
                    'low': '0.1-3.9',
                },
            },
            'grade': {
                'scale': 'A-F (SecurityScorecard-style)',
                'rubric': {
                    'A': 'CVSS avg < 2.0, no Critical, no High',
                    'B': 'CVSS avg < 4.0, no Critical, ≤2 High',
                    'C': 'CVSS avg < 6.0, ≤1 Critical, ≤5 High',
                    'D': 'CVSS avg < 8.0, ≤2 Critical, ≤10 High',
                    'F': 'Anything worse',
                },
                'computed_grade': grade,
            },
            'bitsight': {
                'scale': '250-900',
                'formula': 'base(900) - penalties + bonus(pass_rate × 50)',
                'penalties': {
                    'critical': f'-{self.BITSIGHT_CRITICAL_PENALTY} each',
                    'high': f'-{self.BITSIGHT_HIGH_PENALTY} each',
                    'medium': f'-{self.BITSIGHT_MEDIUM_PENALTY} each',
                    'low': f'-{self.BITSIGHT_LOW_PENALTY} each',
                },
                'computed_score': bitsight,
            },
            'risk': {
                'scale': '0-100',
                'formula': '(critical×25 + high×15 + medium×8 + low×3) × exposure_factor',
                'exposure_factors': {
                    '1.0': 'Crown jewels affected (auth, finance, health)',
                    '0.8': 'User data affected',
                    '0.5': 'Infrastructure only',
                },
                'computed_score': risk_score,
            },
            'maturity': {
                'scale': '0-3',
                'levels': {
                    0: 'Ad Hoc (< 40% controls)',
                    1: 'Basic (40-60% controls)',
                    2: 'Managed (60-80% controls)',
                    3: 'Mature (> 80% controls)',
                },
                'computed_level': maturity,
            },
        }
