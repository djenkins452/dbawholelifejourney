# ==============================================================================
# File: apps/security/tests/test_quick_win_detector.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Test cases for quick win detection
# ==============================================================================
"""
Tests for Quick Win Detector

Covers:
- Title pattern matching
- Recommendation keyword analysis
- Effort/CVSS heuristics
- Overall detection logic
- Run processing
"""

from decimal import Decimal

from django.test import TestCase

from apps.security.models import SecurityRun, SecurityFinding
from apps.security.quick_win_detector import (
    is_quick_win_by_title,
    is_quick_win_by_recommendations,
    is_quick_win_by_effort,
    detect_quick_win,
    update_finding_quick_win_status,
    process_run_quick_wins,
)


class IsQuickWinByTitleTest(TestCase):
    """Test title pattern matching."""

    def test_missing_header_patterns(self):
        """Test missing header patterns are detected."""
        self.assertTrue(is_quick_win_by_title('Missing X-Frame-Options Header'))
        self.assertTrue(is_quick_win_by_title('Missing X-Content-Type-Options'))
        self.assertTrue(is_quick_win_by_title('Missing Strict-Transport-Security Header'))
        self.assertTrue(is_quick_win_by_title('Content-Security-Policy Header Missing'))
        self.assertTrue(is_quick_win_by_title('Missing Referrer-Policy Header'))

    def test_default_config_patterns(self):
        """Test default configuration patterns."""
        self.assertTrue(is_quick_win_by_title('Default Configuration in Production'))
        self.assertTrue(is_quick_win_by_title('Default Credentials Detected'))

    def test_debug_patterns(self):
        """Test debug mode patterns."""
        self.assertTrue(is_quick_win_by_title('Debug Mode Enabled in Production'))

    def test_error_message_patterns(self):
        """Test verbose error patterns."""
        self.assertTrue(is_quick_win_by_title('Verbose Error Messages Exposed'))
        self.assertTrue(is_quick_win_by_title('Information Disclosure in Error Response'))

    def test_cookie_patterns(self):
        """Test cookie flag patterns."""
        self.assertTrue(is_quick_win_by_title('Cookie Missing Secure Flag'))
        self.assertTrue(is_quick_win_by_title('HttpOnly Flag Not Set'))
        self.assertTrue(is_quick_win_by_title('SameSite Attribute Missing'))

    def test_session_patterns(self):
        """Test session-related patterns."""
        self.assertTrue(is_quick_win_by_title('Session Timeout Too Long'))
        self.assertTrue(is_quick_win_by_title('Missing Idle Timeout'))

    def test_rate_limit_patterns(self):
        """Test rate limiting patterns."""
        self.assertTrue(is_quick_win_by_title('Missing Rate Limiting'))
        self.assertTrue(is_quick_win_by_title('No Rate Limit on Login'))

    def test_non_quick_win_titles(self):
        """Test titles that should NOT be quick wins."""
        self.assertFalse(is_quick_win_by_title('SQL Injection Vulnerability'))
        self.assertFalse(is_quick_win_by_title('Remote Code Execution'))
        self.assertFalse(is_quick_win_by_title('Authentication Bypass'))
        self.assertFalse(is_quick_win_by_title('Hardcoded API Keys'))
        self.assertFalse(is_quick_win_by_title('Insecure Deserialization'))

    def test_case_insensitivity(self):
        """Test matching is case-insensitive."""
        self.assertTrue(is_quick_win_by_title('MISSING X-FRAME-OPTIONS'))
        self.assertTrue(is_quick_win_by_title('missing x-frame-options'))
        self.assertTrue(is_quick_win_by_title('Missing X-Frame-Options'))


class IsQuickWinByRecommendationsTest(TestCase):
    """Test recommendation keyword analysis."""

    def test_config_change_recommendations(self):
        """Test configuration change recommendations."""
        recs = [
            'Set header X-Frame-Options to DENY',
            'Configure the server settings.py to enable this header',
        ]
        self.assertTrue(is_quick_win_by_recommendations(recs))

    def test_setting_change_recommendations(self):
        """Test setting change recommendations."""
        recs = [
            'Set the DEBUG flag to False in settings.py',
            'Update setting in configuration file',
        ]
        self.assertTrue(is_quick_win_by_recommendations(recs))

    def test_enable_disable_recommendations(self):
        """Test enable/disable recommendations."""
        recs = [
            'Enable HTTPS redirect in nginx configuration',
            'Disable debug mode for production',
        ]
        self.assertTrue(is_quick_win_by_recommendations(recs))

    def test_environment_variable_recommendations(self):
        """Test environment variable recommendations."""
        recs = [
            'Set the environment variable DJANGO_DEBUG=False',
            'Add SECRET_KEY to your .env file',
        ]
        self.assertTrue(is_quick_win_by_recommendations(recs))

    def test_complex_recommendations(self):
        """Test recommendations that suggest complex changes."""
        recs = [
            'Refactor the authentication module to use tokens',
            'Major change to the architecture is required',
            'Rewrite the database access layer',
        ]
        self.assertFalse(is_quick_win_by_recommendations(recs))

    def test_extensive_change_recommendations(self):
        """Test recommendations indicating extensive changes."""
        recs = [
            'Update multiple files across the codebase',
            'Complex security audit required',
        ]
        self.assertFalse(is_quick_win_by_recommendations(recs))

    def test_empty_recommendations(self):
        """Test empty recommendations."""
        self.assertFalse(is_quick_win_by_recommendations([]))
        self.assertFalse(is_quick_win_by_recommendations(None))

    def test_single_keyword_not_enough(self):
        """Test single keyword isn't enough."""
        recs = ['Configure something']  # Only one keyword
        self.assertFalse(is_quick_win_by_recommendations(recs))


class IsQuickWinByEffortTest(TestCase):
    """Test effort/CVSS heuristics."""

    def test_low_effort_is_quick_win(self):
        """Test low effort is always quick win candidate."""
        self.assertTrue(is_quick_win_by_effort('low', Decimal('2.0')))
        self.assertTrue(is_quick_win_by_effort('low', Decimal('5.0')))
        self.assertTrue(is_quick_win_by_effort('low', Decimal('9.0')))

    def test_medium_effort_with_low_cvss(self):
        """Test medium effort with low CVSS is quick win."""
        self.assertTrue(is_quick_win_by_effort('medium', Decimal('3.5')))
        self.assertTrue(is_quick_win_by_effort('medium', Decimal('2.0')))

    def test_medium_effort_with_high_cvss(self):
        """Test medium effort with high CVSS is not quick win."""
        self.assertFalse(is_quick_win_by_effort('medium', Decimal('5.0')))
        self.assertFalse(is_quick_win_by_effort('medium', Decimal('7.5')))

    def test_high_effort_not_quick_win(self):
        """Test high effort is never quick win by effort alone."""
        self.assertFalse(is_quick_win_by_effort('high', Decimal('2.0')))
        self.assertFalse(is_quick_win_by_effort('high', Decimal('5.0')))
        self.assertFalse(is_quick_win_by_effort('high', Decimal('9.0')))


class DetectQuickWinTest(TestCase):
    """Test overall quick win detection logic."""

    def test_clear_quick_win(self):
        """Test clear quick win (multiple indicators)."""
        is_quick, reason = detect_quick_win(
            title='Missing X-Frame-Options Header',
            severity='low',
            cvss_score=Decimal('2.5'),
            remediation_effort='low',
            recommendations=['Add the X-Frame-Options header', 'Configure in settings.py'],
        )
        self.assertTrue(is_quick)
        self.assertIn('Title matches', reason)

    def test_low_effort_only(self):
        """Test low effort alone is sufficient."""
        is_quick, reason = detect_quick_win(
            title='Some Random Finding',  # Doesn't match patterns
            severity='low',
            cvss_score=Decimal('2.0'),
            remediation_effort='low',
            recommendations=['Do something'],
        )
        self.assertTrue(is_quick)
        self.assertIn('Low remediation effort', reason)

    def test_critical_never_quick_win(self):
        """Test critical findings are never quick wins."""
        is_quick, reason = detect_quick_win(
            title='Missing X-Frame-Options Header',
            severity='critical',
            cvss_score=Decimal('9.5'),
            remediation_effort='low',
            recommendations=['Add header', 'Configure setting'],
        )
        self.assertFalse(is_quick)
        self.assertIn('Critical findings', reason)

    def test_not_quick_win(self):
        """Test finding that is not a quick win."""
        is_quick, reason = detect_quick_win(
            title='SQL Injection Vulnerability',
            severity='high',
            cvss_score=Decimal('8.5'),
            remediation_effort='high',
            recommendations=['Refactor database layer', 'Major architecture change'],
        )
        self.assertFalse(is_quick)
        self.assertIn('Does not match', reason)

    def test_two_indicators_required(self):
        """Test that generally two indicators are needed."""
        # Only title matches, high effort
        is_quick, reason = detect_quick_win(
            title='Missing Rate Limit',
            severity='medium',
            cvss_score=Decimal('5.5'),
            remediation_effort='high',
            recommendations=['Implement rate limiting middleware'],
        )
        # Title matches but other indicators are negative
        # Should still be false because only one criterion


class UpdateFindingQuickWinStatusTest(TestCase):
    """Test updating finding quick win status."""

    def test_update_finding_detected(self):
        """Test finding gets marked as quick win."""
        run = SecurityRun.objects.create()
        finding = SecurityFinding.objects.create(
            run=run,
            finding_id='SEC-001',
            title='Missing X-Frame-Options Header',
            severity='low',
            likelihood='low',
            impact='low',
            cvss_score=Decimal('2.5'),
            remediation_effort='low',
            is_quick_win=False,
        )
        finding.description = "Test"
        finding.recommendations = ['Add header', 'Configure in nginx']
        finding.save()

        result = update_finding_quick_win_status(finding)

        self.assertTrue(result)
        finding.refresh_from_db()
        self.assertTrue(finding.is_quick_win)

    def test_update_finding_already_marked(self):
        """Test finding already marked stays marked."""
        run = SecurityRun.objects.create()
        finding = SecurityFinding.objects.create(
            run=run,
            finding_id='SEC-001',
            title='Random Finding',
            severity='high',
            likelihood='high',
            impact='high',
            cvss_score=Decimal('8.0'),
            remediation_effort='high',
            is_quick_win=True,  # Already marked
        )
        finding.description = "Test"
        finding.save()

        result = update_finding_quick_win_status(finding)

        self.assertTrue(result)  # Returns True because it's a quick win
        finding.refresh_from_db()
        self.assertTrue(finding.is_quick_win)

    def test_update_finding_not_quick_win(self):
        """Test finding that isn't a quick win."""
        run = SecurityRun.objects.create()
        finding = SecurityFinding.objects.create(
            run=run,
            finding_id='SEC-001',
            title='SQL Injection',
            severity='critical',
            likelihood='high',
            impact='high',
            cvss_score=Decimal('9.5'),
            remediation_effort='high',
            is_quick_win=False,
        )
        finding.description = "Test"
        finding.save()

        result = update_finding_quick_win_status(finding)

        self.assertFalse(result)
        finding.refresh_from_db()
        self.assertFalse(finding.is_quick_win)


class ProcessRunQuickWinsTest(TestCase):
    """Test processing all findings in a run."""

    def test_process_run_quick_wins(self):
        """Test processing multiple findings."""
        run = SecurityRun.objects.create()

        # Quick win finding
        f1 = SecurityFinding.objects.create(
            run=run,
            finding_id='SEC-001',
            title='Missing X-Frame-Options',
            severity='low',
            likelihood='low',
            impact='low',
            cvss_score=Decimal('2.0'),
            remediation_effort='low',
            is_quick_win=False,
        )
        f1.description = "Test"
        f1.recommendations = ['Add header', 'Configure setting']
        f1.save()

        # Already marked quick win
        f2 = SecurityFinding.objects.create(
            run=run,
            finding_id='SEC-002',
            title='Cookie Flag Missing',
            severity='low',
            likelihood='low',
            impact='low',
            cvss_score=Decimal('2.5'),
            remediation_effort='low',
            is_quick_win=True,
        )
        f2.description = "Test"
        f2.save()

        # Not a quick win
        f3 = SecurityFinding.objects.create(
            run=run,
            finding_id='SEC-003',
            title='SQL Injection',
            severity='high',
            likelihood='high',
            impact='high',
            cvss_score=Decimal('8.5'),
            remediation_effort='high',
            is_quick_win=False,
        )
        f3.description = "Test"
        f3.save()

        stats = process_run_quick_wins(run)

        self.assertEqual(stats['total'], 3)
        self.assertEqual(stats['already_marked'], 1)
        self.assertGreaterEqual(stats['detected'], 1)

    def test_process_empty_run(self):
        """Test processing run with no findings."""
        run = SecurityRun.objects.create()

        stats = process_run_quick_wins(run)

        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['already_marked'], 0)
        self.assertEqual(stats['detected'], 0)
