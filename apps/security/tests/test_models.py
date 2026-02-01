# ==============================================================================
# File: apps/security/tests/test_models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Test cases for security models
# ==============================================================================
"""
Tests for Security Models

Covers:
- SecurityRun model and integrity hash
- SecurityScore model and scoring
- SecurityTest model
- SecurityFinding model with status tracking
- AcknowledgedFinding model
- SecurityAuditLog model
- Encrypted field handling
"""

import uuid
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.security.models import (
    SecurityRun,
    SecurityScore,
    SecurityTest,
    SecurityFinding,
    AcknowledgedFinding,
    SecurityAuditLog,
    encrypt_security_data,
    decrypt_security_data,
)

User = get_user_model()


class EncryptionUtilsTest(TestCase):
    """Test encryption utilities."""

    def test_encrypt_decrypt_round_trip(self):
        """Test that encryption and decryption work correctly."""
        plaintext = "This is sensitive security data"
        encrypted = encrypt_security_data(plaintext)

        # In dev mode without key, should be prefixed with UNENCRYPTED:
        # In prod with key, should be Fernet token starting with gAAAAA
        self.assertIsNotNone(encrypted)

        decrypted = decrypt_security_data(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_empty_string(self):
        """Test encrypting empty string returns empty."""
        result = encrypt_security_data('')
        self.assertEqual(result, '')

    def test_decrypt_empty_string(self):
        """Test decrypting empty string returns empty."""
        result = decrypt_security_data('')
        self.assertEqual(result, '')

    def test_encrypt_none(self):
        """Test encrypting None returns empty."""
        result = encrypt_security_data(None)
        self.assertEqual(result, '')


class SecurityRunModelTest(TestCase):
    """Test SecurityRun model."""

    def test_create_security_run(self):
        """Test creating a basic security run."""
        run = SecurityRun.objects.create(
            run_type='full',
            triggered_by='test',
        )
        self.assertIsNotNone(run.id)
        self.assertEqual(run.status, SecurityRun.STATUS_RUNNING)
        self.assertEqual(run.run_type, 'full')
        self.assertEqual(run.total_tests, 0)

    def test_security_run_hash_computed(self):
        """Test that run hash is computed on save."""
        run = SecurityRun.objects.create(
            run_type='full',
            triggered_by='test',
        )
        self.assertIsNotNone(run.run_hash)
        self.assertEqual(len(run.run_hash), 64)  # SHA-256

    def test_security_run_status_choices(self):
        """Test status choices are valid."""
        run = SecurityRun.objects.create()

        run.status = SecurityRun.STATUS_COMPLETED
        run.save()
        self.assertEqual(run.status, 'completed')

        run.status = SecurityRun.STATUS_FAILED
        run.save()
        self.assertEqual(run.status, 'failed')

    def test_security_run_encrypted_fields(self):
        """Test that encrypted fields work correctly."""
        run = SecurityRun.objects.create()

        # Set encrypted field via property
        run.executive_summary = "Test executive summary"
        run.ciso_sleep_test = "Test CISO sleep test"
        run.remediation_prompt = "Test remediation prompt"
        run.save()

        # Reload from database
        run.refresh_from_db()

        # Read via property should return decrypted value
        self.assertEqual(run.executive_summary, "Test executive summary")
        self.assertEqual(run.ciso_sleep_test, "Test CISO sleep test")

    def test_security_run_finding_counts(self):
        """Test finding count fields."""
        run = SecurityRun.objects.create(
            total_findings=10,
            critical_findings=2,
            high_findings=3,
            medium_findings=4,
            low_findings=1,
            new_findings=5,
            recurring_findings=3,
            fixed_findings=2,
            regressed_findings=0,
        )
        self.assertEqual(run.total_findings, 10)
        self.assertEqual(run.critical_findings, 2)
        self.assertEqual(run.new_findings, 5)
        self.assertEqual(run.fixed_findings, 2)

    def test_security_run_str_representation(self):
        """Test string representation."""
        run = SecurityRun.objects.create()
        str_repr = str(run)
        self.assertIn("Security Run", str_repr)

    def test_security_run_ordering(self):
        """Test runs are ordered by timestamp descending."""
        run1 = SecurityRun.objects.create()
        run2 = SecurityRun.objects.create()

        runs = list(SecurityRun.objects.all())
        # Most recent first
        self.assertEqual(runs[0], run2)
        self.assertEqual(runs[1], run1)


class SecurityScoreModelTest(TestCase):
    """Test SecurityScore model."""

    def setUp(self):
        self.run = SecurityRun.objects.create(
            run_type='full',
            triggered_by='test',
        )

    def test_create_security_score(self):
        """Test creating a security score."""
        score = SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
            cvss_avg=Decimal('5.5'),
            cvss_critical_count=0,
            cvss_high_count=2,
            cvss_medium_count=3,
            securityscorecard_grade='B',
            bitsight_score=750,
            risk_score_0_100=25,
            maturity_level=2,
        )
        self.assertEqual(score.securityscorecard_grade, 'B')
        self.assertEqual(score.bitsight_score, 750)

    def test_security_score_one_to_one(self):
        """Test one-to-one relationship with run."""
        score = SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
        )
        self.assertEqual(self.run.score, score)

    def test_security_score_grade_choices(self):
        """Test valid grade choices."""
        for grade, _ in SecurityScore.GRADE_CHOICES:
            score = SecurityScore(
                run=SecurityRun.objects.create(),
                securityscorecard_grade=grade,
            )
            score.run_timestamp = score.run.run_timestamp
            score.save()
            self.assertEqual(score.securityscorecard_grade, grade)

    def test_security_score_str_representation(self):
        """Test string representation."""
        score = SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
            securityscorecard_grade='A',
            bitsight_score=900,
        )
        str_repr = str(score)
        self.assertIn('Grade A', str_repr)
        self.assertIn('BitSight 900', str_repr)


class SecurityTestModelTest(TestCase):
    """Test SecurityTest model."""

    def setUp(self):
        self.run = SecurityRun.objects.create()

    def test_create_security_test(self):
        """Test creating a security test."""
        test = SecurityTest.objects.create(
            run=self.run,
            test_id='SEC-T001',
            category='secrets',
            title='Check for hardcoded secrets',
            description='Scans codebase for hardcoded credentials',
            criteria='No hardcoded credentials found',
            result=SecurityTest.RESULT_PASS,
        )
        self.assertEqual(test.test_id, 'SEC-T001')
        self.assertEqual(test.result, 'pass')

    def test_security_test_categories(self):
        """Test all category choices are valid."""
        for category, _ in SecurityTest.CATEGORY_CHOICES:
            test = SecurityTest.objects.create(
                run=SecurityRun.objects.create(),
                test_id=f'SEC-T{category}',
                category=category,
                title=f'Test for {category}',
                description='Test description',
                criteria='Test criteria',
                result=SecurityTest.RESULT_PASS,
            )
            self.assertEqual(test.category, category)

    def test_security_test_results(self):
        """Test all result choices."""
        results = [
            SecurityTest.RESULT_PASS,
            SecurityTest.RESULT_FAIL,
            SecurityTest.RESULT_UNKNOWN,
            SecurityTest.RESULT_SKIPPED,
        ]
        for result in results:
            test = SecurityTest.objects.create(
                run=SecurityRun.objects.create(),
                test_id=f'SEC-T{result}',
                category='secrets',
                title='Test',
                description='Test',
                criteria='Test',
                result=result,
            )
            self.assertEqual(test.result, result)

    def test_security_test_evidence_encrypted(self):
        """Test evidence field is encrypted."""
        test = SecurityTest.objects.create(
            run=self.run,
            test_id='SEC-T001',
            category='secrets',
            title='Test',
            description='Test',
            criteria='Test',
            result='pass',
        )
        test.evidence = {'files': ['test.py'], 'lines': [10, 20]}
        test.save()

        test.refresh_from_db()
        self.assertEqual(test.evidence['files'], ['test.py'])

    def test_security_test_unique_together(self):
        """Test run + test_id uniqueness."""
        SecurityTest.objects.create(
            run=self.run,
            test_id='SEC-T001',
            category='secrets',
            title='Test',
            description='Test',
            criteria='Test',
            result='pass',
        )
        with self.assertRaises(Exception):
            SecurityTest.objects.create(
                run=self.run,
                test_id='SEC-T001',  # Same test_id
                category='auth',
                title='Another Test',
                description='Test',
                criteria='Test',
                result='fail',
            )


class SecurityFindingModelTest(TestCase):
    """Test SecurityFinding model."""

    def setUp(self):
        self.run = SecurityRun.objects.create()

    def test_create_security_finding(self):
        """Test creating a security finding."""
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Hardcoded API Key',
            severity=SecurityFinding.SEVERITY_HIGH,
            likelihood='high',
            impact='high',
            cvss_vector='AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N',
            cvss_score=Decimal('7.5'),
        )
        finding.description = "Found hardcoded API key in settings.py"
        finding.save()

        self.assertEqual(finding.finding_id, 'SEC-001')
        self.assertEqual(finding.severity, 'high')
        self.assertEqual(finding.cvss_score, Decimal('7.5'))

    def test_security_finding_status_choices(self):
        """Test status choices for tracking."""
        statuses = [
            SecurityFinding.STATUS_NEW,
            SecurityFinding.STATUS_RECURRING,
            SecurityFinding.STATUS_FIXED,
            SecurityFinding.STATUS_REGRESSED,
        ]
        for status in statuses:
            finding = SecurityFinding.objects.create(
                run=SecurityRun.objects.create(),
                finding_id=f'SEC-{status}',
                title='Test',
                severity='low',
                likelihood='low',
                impact='low',
                status=status,
            )
            finding.description = "Test"
            finding.save()
            self.assertEqual(finding.status, status)

    def test_security_finding_occurrence_tracking(self):
        """Test occurrence count and first_seen tracking."""
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Test Finding',
            severity='medium',
            likelihood='medium',
            impact='medium',
            status=SecurityFinding.STATUS_RECURRING,
            occurrence_count=5,
            first_seen_run_id=uuid.uuid4(),
        )
        finding.description = "Test"
        finding.save()

        self.assertEqual(finding.occurrence_count, 5)
        self.assertIsNotNone(finding.first_seen_run_id)

    def test_security_finding_quick_win(self):
        """Test quick win flag."""
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Missing X-Frame-Options Header',
            severity='low',
            likelihood='low',
            impact='low',
            is_quick_win=True,
            remediation_effort='low',
        )
        finding.description = "Test"
        finding.save()

        self.assertTrue(finding.is_quick_win)
        self.assertEqual(finding.remediation_effort, 'low')

    def test_security_finding_acknowledgment(self):
        """Test acknowledgment tracking."""
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Test Finding',
            severity='medium',
            likelihood='medium',
            impact='medium',
            finding_key='test-finding-key',
            is_acknowledged=True,
            acknowledgment_justification='Accepted risk due to X',
        )
        finding.description = "Test"
        finding.save()

        self.assertTrue(finding.is_acknowledged)
        self.assertEqual(finding.acknowledgment_justification, 'Accepted risk due to X')

    def test_security_finding_encrypted_fields(self):
        """Test encrypted fields."""
        finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Test',
            severity='medium',
            likelihood='medium',
            impact='medium',
        )
        finding.description = "Detailed description"
        finding.risk_reasoning = "Risk reasoning explanation"
        finding.evidence = {'file': 'test.py', 'line': 42}
        finding.affected_components = ['module1', 'module2']
        finding.recommendations = ['Fix A', 'Fix B']
        finding.validation_steps = "Run test X"
        finding.save()

        finding.refresh_from_db()

        self.assertEqual(finding.description, "Detailed description")
        self.assertEqual(finding.risk_reasoning, "Risk reasoning explanation")
        self.assertEqual(finding.evidence['file'], 'test.py')
        self.assertEqual(finding.affected_components, ['module1', 'module2'])
        self.assertEqual(finding.recommendations, ['Fix A', 'Fix B'])

    def test_security_finding_ordering(self):
        """Test findings are ordered by CVSS score descending."""
        finding1 = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-001',
            title='Low',
            severity='low',
            likelihood='low',
            impact='low',
            cvss_score=Decimal('2.0'),
        )
        finding1.description = "Test"
        finding1.save()

        finding2 = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-002',
            title='High',
            severity='high',
            likelihood='high',
            impact='high',
            cvss_score=Decimal('8.0'),
        )
        finding2.description = "Test"
        finding2.save()

        findings = list(self.run.findings.all())
        self.assertEqual(findings[0].finding_id, 'SEC-002')  # Higher CVSS first


class AcknowledgedFindingModelTest(TestCase):
    """Test AcknowledgedFinding model."""

    def test_create_acknowledged_finding(self):
        """Test creating an acknowledged finding."""
        ack = AcknowledgedFinding.objects.create(
            finding_id='SEC-001',
            title='Known Vulnerability',
            status=AcknowledgedFinding.STATUS_ACTIVE,
            justification='Business decision to accept this risk',
            mitigating_controls='Additional monitoring in place',
            accepted_risk_level='low',
            acknowledged_by='Security Team',
        )
        self.assertEqual(ack.finding_id, 'SEC-001')
        self.assertEqual(ack.status, 'active')

    def test_acknowledged_finding_unique_id(self):
        """Test finding_id is unique."""
        AcknowledgedFinding.objects.create(
            finding_id='SEC-001',
            title='Test',
            justification='Test',
            acknowledged_by='Test',
        )
        with self.assertRaises(Exception):
            AcknowledgedFinding.objects.create(
                finding_id='SEC-001',  # Same ID
                title='Another Test',
                justification='Test',
                acknowledged_by='Test',
            )

    def test_acknowledged_finding_expiration(self):
        """Test expiration checking."""
        # Not expired
        ack1 = AcknowledgedFinding.objects.create(
            finding_id='SEC-001',
            title='Test',
            justification='Test',
            acknowledged_by='Test',
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertFalse(ack1.is_expired)

        # Expired
        ack2 = AcknowledgedFinding.objects.create(
            finding_id='SEC-002',
            title='Test',
            justification='Test',
            acknowledged_by='Test',
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertTrue(ack2.is_expired)

        # No expiration (never expires)
        ack3 = AcknowledgedFinding.objects.create(
            finding_id='SEC-003',
            title='Test',
            justification='Test',
            acknowledged_by='Test',
            expires_at=None,
        )
        self.assertFalse(ack3.is_expired)

    def test_is_acknowledged_classmethod(self):
        """Test is_acknowledged class method."""
        AcknowledgedFinding.objects.create(
            finding_id='SEC-001',
            title='Test',
            justification='Test',
            acknowledged_by='Test',
            status=AcknowledgedFinding.STATUS_ACTIVE,
        )
        AcknowledgedFinding.objects.create(
            finding_id='SEC-002',
            title='Test',
            justification='Test',
            acknowledged_by='Test',
            status=AcknowledgedFinding.STATUS_EXPIRED,
        )

        self.assertTrue(AcknowledgedFinding.is_acknowledged('SEC-001'))
        self.assertFalse(AcknowledgedFinding.is_acknowledged('SEC-002'))  # Expired
        self.assertFalse(AcknowledgedFinding.is_acknowledged('SEC-999'))  # Doesn't exist

    def test_get_acknowledgment_classmethod(self):
        """Test get_acknowledgment class method."""
        ack = AcknowledgedFinding.objects.create(
            finding_id='SEC-001',
            title='Test',
            justification='Test justification',
            acknowledged_by='Test',
            status=AcknowledgedFinding.STATUS_ACTIVE,
        )

        result = AcknowledgedFinding.get_acknowledgment('SEC-001')
        self.assertEqual(result, ack)
        self.assertEqual(result.justification, 'Test justification')

        # Non-existent
        result = AcknowledgedFinding.get_acknowledgment('SEC-999')
        self.assertIsNone(result)


class SecurityAuditLogModelTest(TestCase):
    """Test SecurityAuditLog model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )

    def test_create_audit_log(self):
        """Test creating an audit log entry."""
        log = SecurityAuditLog.objects.create(
            user=self.user,
            user_email=self.user.email,
            ip_address='192.168.1.1',
            action=SecurityAuditLog.ACTION_VIEW_DASHBOARD,
            resource_type='dashboard',
            success=True,
        )
        self.assertEqual(log.action, 'view_dashboard')
        self.assertEqual(log.user_email, 'test@example.com')

    def test_audit_log_actions(self):
        """Test all action choices."""
        actions = [
            SecurityAuditLog.ACTION_VIEW_DASHBOARD,
            SecurityAuditLog.ACTION_VIEW_RUN,
            SecurityAuditLog.ACTION_VIEW_FINDING,
            SecurityAuditLog.ACTION_EXPORT,
            SecurityAuditLog.ACTION_RUN_ASSESSMENT,
        ]
        for action in actions:
            log = SecurityAuditLog.objects.create(
                action=action,
                success=True,
            )
            self.assertEqual(log.action, action)

    def test_audit_log_ordering(self):
        """Test logs are ordered by timestamp descending."""
        SecurityAuditLog.objects.create(action='view_dashboard')
        log2 = SecurityAuditLog.objects.create(action='view_run')

        logs = list(SecurityAuditLog.objects.all())
        self.assertEqual(logs[0], log2)  # Most recent first

    def test_audit_log_str_representation(self):
        """Test string representation."""
        log = SecurityAuditLog.objects.create(
            user=self.user,
            user_email=self.user.email,
            action=SecurityAuditLog.ACTION_VIEW_DASHBOARD,
        )
        str_repr = str(log)
        self.assertIn('test@example.com', str_repr)
        self.assertIn('view_dashboard', str_repr)
