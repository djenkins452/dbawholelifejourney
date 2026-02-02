# ==============================================================================
# File: apps/security/tests/test_admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Test cases for Django admin interface
# ==============================================================================
"""
Tests for Security Admin Interface

Covers:
- Admin site registration
- List displays and filters
- Readonly fields and permissions
- Custom display methods
- Bulk actions
- Inline admins
"""

from decimal import Decimal
from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.security.admin import (
    SecurityRunAdmin,
    SecurityScoreAdmin,
    SecurityTestAdmin,
    SecurityFindingAdmin,
    AcknowledgedFindingAdmin,
    SecurityAuditLogAdmin,
    SeverityFilter,
    QuickWinFilter,
    AcknowledgedFilter,
    FindingStatusFilter,
    SecurityScoreInline,
    SecurityTestInline,
    SecurityFindingInline,
)
from apps.security.models import (
    SecurityRun,
    SecurityScore,
    SecurityTest,
    SecurityFinding,
    AcknowledgedFinding,
    SecurityAuditLog,
)

User = get_user_model()


class AdminRegistrationTest(TestCase):
    """Test admin site registration."""

    def test_all_models_registered(self):
        """Test all security models are registered with admin."""
        from django.contrib.admin.sites import site

        registered_models = [model.__name__ for model in site._registry.keys()]

        self.assertIn('SecurityRun', registered_models)
        self.assertIn('SecurityScore', registered_models)
        self.assertIn('SecurityTest', registered_models)
        self.assertIn('SecurityFinding', registered_models)
        self.assertIn('AcknowledgedFinding', registered_models)
        self.assertIn('SecurityAuditLog', registered_models)


class SecurityRunAdminTest(TestCase):
    """Test SecurityRun admin configuration."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SecurityRunAdmin(SecurityRun, self.site)
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )
        self.run = SecurityRun.objects.create(
            status=SecurityRun.STATUS_COMPLETED,
            total_findings=5,
            critical_findings=1,
            high_findings=2,
        )
        self.score = SecurityScore.objects.create(
            run=self.run,
            run_timestamp=self.run.run_timestamp,
            securityscorecard_grade='B',
            bitsight_score=750,
            risk_score_0_100=25,
        )

    def test_list_display_fields(self):
        """Test list display includes expected fields."""
        expected = [
            'run_timestamp', 'status', 'get_grade', 'get_bitsight',
            'total_findings', 'critical_findings', 'high_findings',
            'passed_tests', 'failed_tests', 'duration_seconds', 'triggered_by',
        ]
        for field in expected:
            self.assertIn(field, self.admin.list_display)

    def test_list_filter_fields(self):
        """Test list filter includes expected fields."""
        self.assertIn('status', self.admin.list_filter)
        self.assertIn('run_type', self.admin.list_filter)
        self.assertIn('triggered_by', self.admin.list_filter)

    def test_has_no_add_permission(self):
        """Test runs cannot be added via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_no_delete_permission(self):
        """Test runs cannot be deleted via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_delete_permission(request, self.run))

    def test_get_grade_display(self):
        """Test grade display method."""
        result = self.admin.get_grade(self.run)
        self.assertIn('B', result)
        self.assertIn('color', result)

    def test_get_grade_no_score(self):
        """Test grade display when no score exists."""
        run = SecurityRun.objects.create()
        result = self.admin.get_grade(run)
        self.assertEqual(result, '-')

    def test_get_bitsight_display(self):
        """Test BitSight display method."""
        result = self.admin.get_bitsight(self.run)
        self.assertEqual(result, 750)

    def test_get_bitsight_no_score(self):
        """Test BitSight display when no score exists."""
        run = SecurityRun.objects.create()
        result = self.admin.get_bitsight(run)
        self.assertEqual(result, '-')

    def test_executive_summary_display(self):
        """Test executive summary display."""
        self.run.executive_summary = "Test summary content"
        self.run.save()
        result = self.admin.executive_summary_display(self.run)
        self.assertIn('Test summary content', result)

    def test_executive_summary_empty(self):
        """Test executive summary when empty."""
        result = self.admin.executive_summary_display(self.run)
        self.assertEqual(result, '-')

    def test_inlines_configured(self):
        """Test inlines are configured."""
        [inline.__class__ for inline in self.admin.inlines]
        # Check by name since they're class references
        inline_names = [inline.__name__ for inline in self.admin.inlines]
        self.assertIn('SecurityScoreInline', inline_names)
        self.assertIn('SecurityFindingInline', inline_names)


class SecurityScoreAdminTest(TestCase):
    """Test SecurityScore admin configuration."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SecurityScoreAdmin(SecurityScore, self.site)
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )

    def test_list_display_fields(self):
        """Test list display includes expected fields."""
        expected = [
            'run_timestamp', 'securityscorecard_grade', 'bitsight_score',
            'risk_score_0_100', 'maturity_level', 'cvss_avg',
        ]
        for field in expected:
            self.assertIn(field, self.admin.list_display)

    def test_has_no_add_permission(self):
        """Test scores cannot be added via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_no_delete_permission(self):
        """Test scores cannot be deleted via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_delete_permission(request))


class SecurityTestAdminTest(TestCase):
    """Test SecurityTest admin configuration."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SecurityTestAdmin(SecurityTest, self.site)
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )
        self.run = SecurityRun.objects.create()
        self.test = SecurityTest.objects.create(
            run=self.run,
            test_id='SEC-TEST-001',
            category='authentication',
            title='Test Auth',
            result='pass',
        )
        self.test.description = "Test description"
        self.test.save()

    def test_list_display_fields(self):
        """Test list display includes expected fields."""
        expected = ['test_id', 'title', 'category', 'result_display', 'duration_ms', 'run_link']
        for field in expected:
            self.assertIn(field, self.admin.list_display)

    def test_has_no_add_permission(self):
        """Test tests cannot be added via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_no_delete_permission(self):
        """Test tests cannot be deleted via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_result_display_pass(self):
        """Test result display for pass."""
        result = self.admin.result_display(self.test)
        self.assertIn('PASS', result)
        self.assertIn('#16a34a', result)  # Green color

    def test_result_display_fail(self):
        """Test result display for fail."""
        self.test.result = 'fail'
        self.test.save()
        result = self.admin.result_display(self.test)
        self.assertIn('FAIL', result)
        self.assertIn('#dc2626', result)  # Red color

    def test_run_link(self):
        """Test run link display."""
        result = self.admin.run_link(self.test)
        self.assertIn('href', result)
        self.assertIn(str(self.run.id), result)

    def test_evidence_display(self):
        """Test evidence display."""
        self.test.evidence = {'key': 'value', 'nested': {'data': 123}}
        self.test.save()
        result = self.admin.evidence_display(self.test)
        self.assertIn('key', result)
        self.assertIn('value', result)

    def test_evidence_display_empty(self):
        """Test evidence display when empty."""
        result = self.admin.evidence_display(self.test)
        self.assertEqual(result, '-')


class SecurityFindingAdminTest(TestCase):
    """Test SecurityFinding admin configuration."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SecurityFindingAdmin(SecurityFinding, self.site)
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )
        self.run = SecurityRun.objects.create()
        self.finding = SecurityFinding.objects.create(
            run=self.run,
            finding_id='SEC-FIND-001',
            title='Test Finding',
            severity='high',
            likelihood='medium',
            impact='high',
            cvss_score=Decimal('7.5'),
            is_quick_win=True,
            is_acknowledged=False,
            status='new',
        )
        self.finding.description = "Test description"
        self.finding.save()

    def test_list_display_fields(self):
        """Test list display includes expected fields."""
        expected = [
            'finding_id', 'title', 'severity_display', 'cvss_score',
            'status_display', 'is_quick_win_display', 'is_acknowledged_display',
        ]
        for field in expected:
            self.assertIn(field, self.admin.list_display)

    def test_list_filter_classes(self):
        """Test list filter includes custom filter classes."""
        self.assertIn(SeverityFilter, self.admin.list_filter)
        self.assertIn(FindingStatusFilter, self.admin.list_filter)
        self.assertIn(QuickWinFilter, self.admin.list_filter)
        self.assertIn(AcknowledgedFilter, self.admin.list_filter)

    def test_has_no_add_permission(self):
        """Test findings cannot be added via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_no_delete_permission(self):
        """Test findings cannot be deleted via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_severity_display_critical(self):
        """Test severity display for critical."""
        self.finding.severity = 'critical'
        result = self.admin.severity_display(self.finding)
        self.assertIn('CRITICAL', result)
        self.assertIn('#dc2626', result)  # Red color

    def test_severity_display_high(self):
        """Test severity display for high."""
        result = self.admin.severity_display(self.finding)
        self.assertIn('HIGH', result)
        self.assertIn('#ea580c', result)  # Orange color

    def test_severity_display_medium(self):
        """Test severity display for medium."""
        self.finding.severity = 'medium'
        result = self.admin.severity_display(self.finding)
        self.assertIn('MEDIUM', result)
        self.assertIn('#ca8a04', result)  # Yellow color

    def test_severity_display_low(self):
        """Test severity display for low."""
        self.finding.severity = 'low'
        result = self.admin.severity_display(self.finding)
        self.assertIn('LOW', result)
        self.assertIn('#2563eb', result)  # Blue color

    def test_status_display_new(self):
        """Test status display for new."""
        result = self.admin.status_display(self.finding)
        self.assertIn('NEW', result)
        self.assertIn('#2563eb', result)  # Blue color

    def test_status_display_recurring(self):
        """Test status display for recurring."""
        self.finding.status = 'recurring'
        result = self.admin.status_display(self.finding)
        self.assertIn('RECURRING', result)
        self.assertIn('#ca8a04', result)  # Yellow color

    def test_status_display_fixed(self):
        """Test status display for fixed."""
        self.finding.status = 'fixed'
        result = self.admin.status_display(self.finding)
        self.assertIn('FIXED', result)
        self.assertIn('#16a34a', result)  # Green color

    def test_status_display_regressed(self):
        """Test status display for regressed."""
        self.finding.status = 'regressed'
        result = self.admin.status_display(self.finding)
        self.assertIn('REGRESSED', result)
        self.assertIn('#dc2626', result)  # Red color

    def test_is_quick_win_display(self):
        """Test quick win display."""
        self.assertTrue(self.admin.is_quick_win_display(self.finding))
        self.finding.is_quick_win = False
        self.assertFalse(self.admin.is_quick_win_display(self.finding))

    def test_is_acknowledged_display(self):
        """Test acknowledged display."""
        self.assertFalse(self.admin.is_acknowledged_display(self.finding))
        self.finding.is_acknowledged = True
        self.assertTrue(self.admin.is_acknowledged_display(self.finding))

    def test_run_link(self):
        """Test run link display."""
        result = self.admin.run_link(self.finding)
        self.assertIn('href', result)
        self.assertIn(str(self.run.id), result)

    def test_description_display(self):
        """Test description display."""
        result = self.admin.description_display(self.finding)
        self.assertIn('Test description', result)

    def test_description_display_empty(self):
        """Test description display when empty."""
        self.finding.description = ''
        self.finding.save()
        result = self.admin.description_display(self.finding)
        self.assertEqual(result, '-')

    def test_recommendations_display(self):
        """Test recommendations display."""
        self.finding.recommendations = ['Fix this', 'Do that']
        self.finding.save()
        result = self.admin.recommendations_display(self.finding)
        self.assertIn('Fix this', result)
        self.assertIn('Do that', result)
        self.assertIn('<li>', result)

    def test_recommendations_display_empty(self):
        """Test recommendations display when empty."""
        result = self.admin.recommendations_display(self.finding)
        self.assertEqual(result, '-')

    def test_affected_components_display(self):
        """Test affected components display."""
        self.finding.affected_components = ['module1.py', 'module2.py']
        self.finding.save()
        result = self.admin.affected_components_display(self.finding)
        self.assertIn('module1.py', result)
        self.assertIn('module2.py', result)

    def test_affected_components_display_empty(self):
        """Test affected components display when empty."""
        result = self.admin.affected_components_display(self.finding)
        self.assertEqual(result, '-')

    def test_mark_as_quick_win_action(self):
        """Test bulk mark as quick win action."""
        self.finding.is_quick_win = False
        self.finding.save()

        request = self.factory.post('/')
        request.user = self.user
        request._messages = MockMessages()

        queryset = SecurityFinding.objects.filter(id=self.finding.id)
        self.admin.mark_as_quick_win(request, queryset)

        self.finding.refresh_from_db()
        self.assertTrue(self.finding.is_quick_win)

    def test_unmark_as_quick_win_action(self):
        """Test bulk unmark as quick win action."""
        request = self.factory.post('/')
        request.user = self.user
        request._messages = MockMessages()

        queryset = SecurityFinding.objects.filter(id=self.finding.id)
        self.admin.unmark_as_quick_win(request, queryset)

        self.finding.refresh_from_db()
        self.assertFalse(self.finding.is_quick_win)


class AcknowledgedFindingAdminTest(TestCase):
    """Test AcknowledgedFinding admin configuration."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = AcknowledgedFindingAdmin(AcknowledgedFinding, self.site)
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )
        self.ack = AcknowledgedFinding.objects.create(
            finding_id='SEC-001',
            title='Test Acknowledged',
            status='accepted',
            acknowledged_by='CISO',
            justification='Risk accepted due to mitigating controls',
            expires_at=timezone.now() + timedelta(days=30),
        )

    def test_list_display_fields(self):
        """Test list display includes expected fields."""
        expected = [
            'finding_id', 'title', 'status', 'accepted_risk_level',
            'acknowledged_by', 'acknowledged_at', 'is_expired_display',
        ]
        for field in expected:
            self.assertIn(field, self.admin.list_display)

    def test_is_expired_display_not_expired(self):
        """Test is_expired display for non-expired."""
        self.assertFalse(self.admin.is_expired_display(self.ack))

    def test_is_expired_display_expired(self):
        """Test is_expired display for expired."""
        self.ack.expires_at = timezone.now() - timedelta(days=1)
        self.ack.save()
        self.assertTrue(self.admin.is_expired_display(self.ack))


class SecurityAuditLogAdminTest(TestCase):
    """Test SecurityAuditLog admin configuration."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SecurityAuditLogAdmin(SecurityAuditLog, self.site)
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )

    def test_list_display_fields(self):
        """Test list display includes expected fields."""
        expected = [
            'timestamp', 'user_email', 'action', 'resource_type',
            'resource_id', 'ip_address', 'success',
        ]
        for field in expected:
            self.assertIn(field, self.admin.list_display)

    def test_has_no_add_permission(self):
        """Test logs cannot be added via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_no_change_permission(self):
        """Test logs cannot be changed via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_no_delete_permission(self):
        """Test logs cannot be deleted via admin."""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_delete_permission(request))


class FilterTest(TestCase):
    """Test custom filter classes."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SecurityFindingAdmin(SecurityFinding, self.site)
        self.factory = RequestFactory()
        self.run = SecurityRun.objects.create()

        # Create findings with different attributes
        for severity in ['critical', 'high', 'medium', 'low']:
            finding = SecurityFinding.objects.create(
                run=self.run,
                finding_id=f'SEC-{severity}',
                title=f'{severity.title()} Finding',
                severity=severity,
                likelihood='medium',
                impact='medium',
                is_quick_win=(severity == 'low'),
                is_acknowledged=(severity == 'critical'),
                status='new' if severity in ['critical', 'high'] else 'recurring',
            )
            finding.description = "Test"
            finding.save()

    def test_severity_filter_lookups(self):
        """Test severity filter has correct lookups."""
        request = self.factory.get('/')
        severity_filter = SeverityFilter(request, {}, SecurityFinding, self.admin)
        lookups = severity_filter.lookups(request, self.admin)
        lookup_values = [item[0] for item in lookups]
        self.assertIn('critical', lookup_values)
        self.assertIn('high', lookup_values)
        self.assertIn('medium', lookup_values)
        self.assertIn('low', lookup_values)

    def test_severity_filter_queryset(self):
        """Test severity filter filters correctly."""
        request = self.factory.get('/', {'severity': 'high'})
        # Django's SimpleListFilter expects list values (like QueryDict), not plain strings
        severity_filter = SeverityFilter(request, {'severity': ['high']}, SecurityFinding, self.admin)
        # Filter by our run to isolate from other tests
        base_queryset = SecurityFinding.objects.filter(run=self.run)
        queryset = severity_filter.queryset(request, base_queryset)
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().severity, 'high')

    def test_quick_win_filter_lookups(self):
        """Test quick win filter has correct lookups."""
        request = self.factory.get('/')
        qw_filter = QuickWinFilter(request, {}, SecurityFinding, self.admin)
        lookups = qw_filter.lookups(request, self.admin)
        lookup_values = [item[0] for item in lookups]
        self.assertIn('yes', lookup_values)
        self.assertIn('no', lookup_values)

    def test_quick_win_filter_queryset_yes(self):
        """Test quick win filter for yes."""
        request = self.factory.get('/', {'quick_win': 'yes'})
        qw_filter = QuickWinFilter(request, {'quick_win': ['yes']}, SecurityFinding, self.admin)
        base_queryset = SecurityFinding.objects.filter(run=self.run)
        queryset = qw_filter.queryset(request, base_queryset)
        self.assertEqual(queryset.count(), 1)
        self.assertTrue(queryset.first().is_quick_win)

    def test_quick_win_filter_queryset_no(self):
        """Test quick win filter for no."""
        request = self.factory.get('/', {'quick_win': 'no'})
        qw_filter = QuickWinFilter(request, {'quick_win': ['no']}, SecurityFinding, self.admin)
        base_queryset = SecurityFinding.objects.filter(run=self.run)
        queryset = qw_filter.queryset(request, base_queryset)
        self.assertEqual(queryset.count(), 3)
        for finding in queryset:
            self.assertFalse(finding.is_quick_win)

    def test_acknowledged_filter_lookups(self):
        """Test acknowledged filter has correct lookups."""
        request = self.factory.get('/')
        ack_filter = AcknowledgedFilter(request, {}, SecurityFinding, self.admin)
        lookups = ack_filter.lookups(request, self.admin)
        lookup_values = [item[0] for item in lookups]
        self.assertIn('yes', lookup_values)
        self.assertIn('no', lookup_values)

    def test_acknowledged_filter_queryset_yes(self):
        """Test acknowledged filter for yes."""
        request = self.factory.get('/', {'acknowledged': 'yes'})
        ack_filter = AcknowledgedFilter(request, {'acknowledged': ['yes']}, SecurityFinding, self.admin)
        base_queryset = SecurityFinding.objects.filter(run=self.run)
        queryset = ack_filter.queryset(request, base_queryset)
        self.assertEqual(queryset.count(), 1)
        self.assertTrue(queryset.first().is_acknowledged)

    def test_acknowledged_filter_queryset_no(self):
        """Test acknowledged filter for no."""
        request = self.factory.get('/', {'acknowledged': 'no'})
        ack_filter = AcknowledgedFilter(request, {'acknowledged': ['no']}, SecurityFinding, self.admin)
        base_queryset = SecurityFinding.objects.filter(run=self.run)
        queryset = ack_filter.queryset(request, base_queryset)
        self.assertEqual(queryset.count(), 3)
        for finding in queryset:
            self.assertFalse(finding.is_acknowledged)

    def test_finding_status_filter_lookups(self):
        """Test finding status filter has correct lookups."""
        request = self.factory.get('/')
        status_filter = FindingStatusFilter(request, {}, SecurityFinding, self.admin)
        lookups = status_filter.lookups(request, self.admin)
        lookup_values = [item[0] for item in lookups]
        self.assertIn('new', lookup_values)
        self.assertIn('recurring', lookup_values)
        self.assertIn('fixed', lookup_values)
        self.assertIn('regressed', lookup_values)

    def test_finding_status_filter_queryset(self):
        """Test finding status filter filters correctly."""
        request = self.factory.get('/', {'status': 'new'})
        status_filter = FindingStatusFilter(request, {'status': ['new']}, SecurityFinding, self.admin)
        base_queryset = SecurityFinding.objects.filter(run=self.run)
        queryset = status_filter.queryset(request, base_queryset)
        self.assertEqual(queryset.count(), 2)  # critical and high are 'new'
        for finding in queryset:
            self.assertEqual(finding.status, 'new')


class InlineAdminTest(TestCase):
    """Test inline admin configurations."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
        )
        self.run = SecurityRun.objects.create()

    def test_security_score_inline_fields(self):
        """Test SecurityScoreInline has correct configuration."""
        SecurityRunAdmin(SecurityRun, self.site)
        inline = SecurityScoreInline(SecurityRun, self.site)

        self.assertEqual(inline.model, SecurityScore)
        self.assertFalse(inline.can_delete)
        self.assertEqual(inline.extra, 0)

    def test_security_test_inline_fields(self):
        """Test SecurityTestInline has correct configuration."""
        inline = SecurityTestInline(SecurityRun, self.site)

        self.assertEqual(inline.model, SecurityTest)
        self.assertFalse(inline.can_delete)
        self.assertEqual(inline.extra, 0)
        self.assertIn('test_id', inline.fields)
        self.assertIn('result', inline.fields)

    def test_security_test_inline_no_add_permission(self):
        """Test SecurityTestInline has no add permission."""
        inline = SecurityTestInline(SecurityRun, self.site)
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(inline.has_add_permission(request))

    def test_security_finding_inline_fields(self):
        """Test SecurityFindingInline has correct configuration."""
        inline = SecurityFindingInline(SecurityRun, self.site)

        self.assertEqual(inline.model, SecurityFinding)
        self.assertFalse(inline.can_delete)
        self.assertEqual(inline.extra, 0)
        self.assertIn('finding_id', inline.fields)
        self.assertIn('severity', inline.fields)
        self.assertIn('is_quick_win', inline.fields)

    def test_security_finding_inline_no_add_permission(self):
        """Test SecurityFindingInline has no add permission."""
        inline = SecurityFindingInline(SecurityRun, self.site)
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(inline.has_add_permission(request))

    def test_security_finding_inline_ordering(self):
        """Test SecurityFindingInline orders by CVSS score descending."""
        inline = SecurityFindingInline(SecurityRun, self.site)
        self.assertEqual(inline.ordering, ['-cvss_score'])


class MockMessages:
    """Mock messages framework for testing admin actions."""

    def __init__(self):
        self.messages = []

    def add(self, level, message, extra_tags=''):
        self.messages.append({'level': level, 'message': message})
