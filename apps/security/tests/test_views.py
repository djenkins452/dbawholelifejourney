# ==============================================================================
# File: apps/security/tests/test_views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Test cases for security views and exports
# ==============================================================================
"""
Tests for Security Views

Covers:
- Dashboard view
- Run detail view
- API endpoints (test detail, finding detail, trends)
- Export views (CSV, PDF)
- Run assessment view
- Access control (staff required)
"""

from decimal import Decimal
import base64
import json
import secrets

from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from allauth.account.models import EmailAddress

from apps.security.models import (
    SecurityRun,
    SecurityScore,
    SecurityTest,
    SecurityFinding,
    SecurityAuditLog,
)
from apps.users.models import TermsAcceptance, WebAuthnCredential

User = get_user_model()


class SecurityTestMixin:
    """Mixin for creating properly configured test users."""

    def create_user(self, email='user@example.com', password='testpass123',
                    is_staff=False, is_superuser=False):
        """Create a test user with terms accepted, onboarding completed, and email verified."""
        user = User.objects.create_user(
            email=email,
            password=password,
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        self._accept_terms(user)
        self._complete_onboarding(user)
        self._verify_email(user)
        # Staff users need WebAuthn credential (MFA enforcement middleware)
        if is_staff or is_superuser:
            self._create_webauthn_credential(user)
        return user

    def create_staff_user(self, email='staff@example.com', password='testpass123'):
        """Create a staff user."""
        return self.create_user(
            email=email,
            password=password,
            is_staff=True
        )

    def _accept_terms(self, user):
        current_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=current_version)

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def _verify_email(self, user):
        """Create verified EmailAddress for user."""
        email_addr, created = EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={'verified': True, 'primary': True}
        )
        if not created:
            email_addr.verified = True
            email_addr.primary = True
            email_addr.save()

    def _create_webauthn_credential(self, user, device_name='Test Device'):
        """Create a test WebAuthn credential for MFA enforcement."""
        credential_id = secrets.token_bytes(32)
        credential_id_b64 = base64.urlsafe_b64encode(credential_id).rstrip(b'=').decode()
        public_key = secrets.token_bytes(64)

        return WebAuthnCredential.objects.create(
            user=user,
            credential_id=credential_id,
            credential_id_b64=credential_id_b64,
            public_key=public_key,
            device_name=device_name,
        )


class SecurityViewAccessControlTest(SecurityTestMixin, TestCase):
    """Test access control for security views."""

    def setUp(self):
        self.client = Client()
        self.regular_user = self.create_user(
            email='user@example.com',
            password='testpass123',
        )
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.run = SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)
        SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
        )

    def test_dashboard_requires_staff(self):
        """Test dashboard requires staff status."""
        # Anonymous
        response = self.client.get(reverse('security:dashboard'))
        self.assertNotEqual(response.status_code, 200)

        # Regular user - use force_login to bypass all auth checks
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('security:dashboard'))
        self.assertNotEqual(response.status_code, 200)

        # Staff user - use force_login to bypass all auth checks
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('security:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_run_detail_requires_staff(self):
        """Test run detail requires staff status."""
        url = reverse('security:run_detail', args=[self.run.pk])

        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_export_csv_requires_staff(self):
        """Test CSV export requires staff status."""
        url = reverse('security:export_csv', args=[self.run.pk])

        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_export_pdf_requires_staff(self):
        """Test PDF export requires staff status."""
        url = reverse('security:export_pdf', args=[self.run.pk])

        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class SecurityDashboardViewTest(SecurityTestMixin, TestCase):
    """Test security dashboard view."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

    def test_dashboard_no_runs(self):
        """Test dashboard with no runs."""
        response = self.client.get(reverse('security:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Security Assessments Yet')

    def test_dashboard_with_run(self):
        """Test dashboard with completed run."""
        run = SecurityRun.objects.create(
            status=SecurityRun.STATUS_COMPLETED,
            total_tests=50,
            passed_tests=45,
            failed_tests=5,
            total_findings=3,
        )
        SecurityScore.objects.create(
            run=run,
            run_timestamp=run.run_timestamp,
            securityscorecard_grade='A',
            bitsight_score=900,
        )

        response = self.client.get(reverse('security:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '50')  # Total tests
        self.assertContains(response, '45')  # Passed
        self.assertContains(response, '900')  # BitSight

    def test_dashboard_logs_access(self):
        """Test dashboard access is logged."""
        SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)

        response = self.client.get(reverse('security:dashboard'))

        self.assertEqual(response.status_code, 200)
        log = SecurityAuditLog.objects.filter(
            action=SecurityAuditLog.ACTION_VIEW_DASHBOARD
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user_email, 'staff@example.com')

    def test_dashboard_includes_trend_data(self):
        """Test dashboard includes trend data."""
        run = SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)
        SecurityScore.objects.create(
            run=run,
            run_timestamp=run.run_timestamp,
            bitsight_score=800,
        )

        response = self.client.get(reverse('security:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('chart_data', response.context)
        self.assertIn('finding_trend_data', response.context)


class SecurityRunDetailViewTest(SecurityTestMixin, TestCase):
    """Test security run detail view."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

        self.run = SecurityRun.objects.create(
            status=SecurityRun.STATUS_COMPLETED,
            total_tests=50,
        )
        SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
        )

    def test_run_detail_view(self):
        """Test run detail view loads."""
        url = reverse('security:run_detail', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['run'], self.run)

    def test_run_detail_includes_tests(self):
        """Test run detail includes tests."""
        test = SecurityTest.objects.create(
            run=self.run,
            test_id='SEC-T001',
            category='secrets',
            title='Check Secrets',
            result='pass',
        )
        test.description = "Test"
        test.criteria = "Test criteria"
        test.save()

        url = reverse('security:run_detail', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['tests']), 1)

    def test_run_detail_includes_findings(self):
        """Test run detail includes findings."""
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Test Finding',
            severity='high',
            likelihood='high',
            impact='high',
        )
        finding.description = "Test"
        finding.save()

        url = reverse('security:run_detail', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['findings']), 1)

    def test_run_detail_logs_access(self):
        """Test run detail access is logged."""
        url = reverse('security:run_detail', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        log = SecurityAuditLog.objects.filter(
            action=SecurityAuditLog.ACTION_VIEW_RUN
        ).first()
        self.assertIsNotNone(log)


class FindingDetailAPIViewTest(SecurityTestMixin, TestCase):
    """Test finding detail API endpoint."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

        self.run = SecurityRun.objects.create()
        self.finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Test Finding',
            severity='high',
            likelihood='high',
            impact='high',
            cvss_vector='AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N',
            cvss_score=Decimal('7.5'),
            is_quick_win=True,
            remediation_effort='low',
        )
        self.finding.description = "Test description"
        self.finding.risk_reasoning = "Risk reasoning"
        self.finding.evidence = {'file': 'test.py'}
        self.finding.affected_components = ['module1']
        self.finding.recommendations = ['Fix A']
        self.finding.validation_steps = "Run test"
        self.finding.save()

    def test_finding_detail_api(self):
        """Test finding detail API returns correct data."""
        url = reverse('security:api_finding_detail', args=[self.finding.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data['finding_id'], 'SEC-001')
        self.assertEqual(data['title'], 'Test Finding')
        self.assertEqual(data['severity'], 'high')
        self.assertEqual(data['cvss_score'], 7.5)
        self.assertEqual(data['description'], 'Test description')
        self.assertTrue(data['is_quick_win'])

    def test_finding_detail_logs_access(self):
        """Test finding detail access is logged."""
        url = reverse('security:api_finding_detail', args=[self.finding.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        log = SecurityAuditLog.objects.filter(
            action=SecurityAuditLog.ACTION_VIEW_FINDING,
            resource_type='finding',
        ).first()
        self.assertIsNotNone(log)


class TestDetailAPIViewTest(SecurityTestMixin, TestCase):
    """Test test detail API endpoint."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

        self.run = SecurityRun.objects.create()
        self.test = SecurityTest.objects.create(
            run=self.run,
            test_id='SEC-T001',
            category='secrets',
            title='Check for Hardcoded Secrets',
            result='pass',
            result_details='All clear',
            duration_ms=150,
        )
        self.test.description = 'Scans codebase'
        self.test.criteria = 'No secrets found'
        self.test.evidence = {'files_scanned': 100}
        self.test.save()

    def test_test_detail_api(self):
        """Test test detail API returns correct data."""
        url = reverse('security:api_test_detail', args=[self.test.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data['test_id'], 'SEC-T001')
        self.assertEqual(data['title'], 'Check for Hardcoded Secrets')
        self.assertEqual(data['result'], 'pass')
        self.assertEqual(data['duration_ms'], 150)


class TrendDataAPIViewTest(SecurityTestMixin, TestCase):
    """Test trend data API endpoint."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

    def test_trend_data_api_empty(self):
        """Test trend data API with no runs."""
        url = reverse('security:api_trends')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data['labels'], [])

    def test_trend_data_api_with_data(self):
        """Test trend data API with runs."""
        run = SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)
        SecurityScore.objects.create(
            run=run,
            run_timestamp=run.run_timestamp,
            bitsight_score=800,
            risk_score_0_100=25,
        )

        url = reverse('security:api_trends')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(len(data['labels']), 1)
        self.assertEqual(data['bitsight'], [800])
        self.assertEqual(data['risk'], [25])


class FindingTrendAPIViewTest(SecurityTestMixin, TestCase):
    """Test finding trend API endpoint."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

    def test_finding_trend_api(self):
        """Test finding trend API."""
        SecurityRun.objects.create(
            status=SecurityRun.STATUS_COMPLETED,
            new_findings=5,
            recurring_findings=3,
            fixed_findings=2,
            regressed_findings=1,
        )

        url = reverse('security:api_finding_trends')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(len(data['labels']), 1)
        self.assertEqual(data['new'], [5])
        self.assertEqual(data['recurring'], [3])
        self.assertEqual(data['fixed'], [2])
        self.assertEqual(data['regressed'], [1])


class ImprovementMetricsAPIViewTest(SecurityTestMixin, TestCase):
    """Test improvement metrics API endpoint."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

    def test_improvement_metrics_api(self):
        """Test improvement metrics API."""
        url = reverse('security:api_improvement')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # With no data, should indicate not enough data
        self.assertIn('period_days', data)


class ExportCSVViewTest(SecurityTestMixin, TestCase):
    """Test CSV export view."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

        self.run = SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Test Finding',
            severity='high',
            likelihood='high',
            impact='high',
            cvss_score=Decimal('7.5'),
        )
        finding.description = "Test"
        finding.save()

    def test_export_csv(self):
        """Test CSV export."""
        url = reverse('security:export_csv', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('.csv', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        self.assertIn('Finding ID', content)  # Header
        self.assertIn('SEC-001', content)  # Data

    def test_export_csv_logs_access(self):
        """Test CSV export is logged."""
        url = reverse('security:export_csv', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        log = SecurityAuditLog.objects.filter(
            action=SecurityAuditLog.ACTION_EXPORT,
            resource_type='csv',
        ).first()
        self.assertIsNotNone(log)


class ExportPDFViewTest(SecurityTestMixin, TestCase):
    """Test PDF export view."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

        self.run = SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)
        SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
            securityscorecard_grade='A',
            bitsight_score=900,
        )

    def test_export_pdf(self):
        """Test PDF export (HTML for print)."""
        url = reverse('security:export_pdf', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html')

        content = response.content.decode('utf-8')
        self.assertIn('Security Assessment Report', content)
        self.assertIn('900', content)  # BitSight score

    def test_export_pdf_logs_access(self):
        """Test PDF export is logged."""
        url = reverse('security:export_pdf', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        log = SecurityAuditLog.objects.filter(
            action=SecurityAuditLog.ACTION_EXPORT,
            resource_type='pdf',
        ).first()
        self.assertIsNotNone(log)


class RemediationPromptViewTest(SecurityTestMixin, TestCase):
    """Test remediation prompt view."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user(
            email='staff@example.com',
            password='testpass123',
        )
        self.client.force_login(self.staff_user)

        self.run = SecurityRun.objects.create(status=SecurityRun.STATUS_COMPLETED)
        self.run.remediation_prompt = "Fix the following issues..."
        self.run.save()

    def test_remediation_prompt_api(self):
        """Test remediation prompt API."""
        url = reverse('security:api_remediation', args=[self.run.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data['prompt'], "Fix the following issues...")
        self.assertEqual(data['run_id'], str(self.run.id))
