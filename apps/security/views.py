# ==============================================================================
# File: apps/security/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security dashboard views - requires SecurityAdmin/SecurityViewer role
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Security Dashboard Views

Provides:
- Dashboard with latest scores and trend graphs
- Run detail view with tests and findings
- Finding detail popup (AJAX)
- Test detail popup (AJAX)
- Remediation prompt export

Access Control (Tier-0):
- All views require staff status
- All access is logged to SecurityAuditLog
"""

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .models import (
    SecurityAuditLog,
    SecurityFinding,
    SecurityRun,
    SecurityScore,
    SecurityTest,
)


class SecurityAccessMixin:
    """
    Mixin to enforce security access controls.

    - Requires staff status
    - Logs all access to audit log
    """

    @method_decorator(staff_member_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def log_access(self, request, action, resource_type='', resource_id=''):
        """Log access to security data."""
        SecurityAuditLog.log(
            request=request,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )


class SecurityDashboardView(SecurityAccessMixin, TemplateView):
    """
    Security dashboard with latest scores and trend graphs.

    Shows:
    - Latest run scores at top
    - Trend graphs for all metrics
    - Summary table of recent runs
    """

    template_name = 'security/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Log access
        self.log_access(self.request, SecurityAuditLog.ACTION_VIEW_DASHBOARD)

        # Get latest run
        latest_run = SecurityRun.objects.filter(
            status=SecurityRun.STATUS_COMPLETED
        ).first()

        context['latest_run'] = latest_run

        if latest_run:
            context['latest_score'] = getattr(latest_run, 'score', None)
            context['latest_tests'] = latest_run.tests.all()[:10]
            context['latest_findings'] = latest_run.findings.all().order_by('-cvss_score')[:10]

        # Get historical scores for trends (last 30 runs)
        scores = SecurityScore.objects.all()[:30]
        context['scores'] = scores

        # Prepare chart data
        chart_data = {
            'labels': [],
            'cvss_avg': [],
            'bitsight': [],
            'risk': [],
            'maturity': [],
        }

        for score in reversed(list(scores)):
            chart_data['labels'].append(score.run_timestamp.strftime('%m/%d'))
            chart_data['cvss_avg'].append(float(score.cvss_avg))
            chart_data['bitsight'].append(score.bitsight_score)
            chart_data['risk'].append(score.risk_score_0_100)
            chart_data['maturity'].append(score.maturity_level)

        context['chart_data'] = json.dumps(chart_data)

        # Get all completed runs for table
        context['runs'] = SecurityRun.objects.filter(
            status=SecurityRun.STATUS_COMPLETED
        )[:20]

        return context


class SecurityRunDetailView(SecurityAccessMixin, DetailView):
    """
    Detailed view of a security run.

    Shows:
    - Run metadata and scores
    - All tests with results
    - All findings with details
    - Executive summary
    - Remediation prompt (copyable)
    """

    model = SecurityRun
    template_name = 'security/run_detail.html'
    context_object_name = 'run'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        run = self.object

        # Log access
        self.log_access(
            self.request,
            SecurityAuditLog.ACTION_VIEW_RUN,
            resource_type='run',
            resource_id=run.id,
        )

        context['score'] = getattr(run, 'score', None)
        context['tests'] = run.tests.all().order_by('test_id')
        context['findings'] = run.findings.all().order_by('-cvss_score')

        # Group tests by category
        tests_by_category = {}
        for test in context['tests']:
            category = test.get_category_display()
            if category not in tests_by_category:
                tests_by_category[category] = []
            tests_by_category[category].append(test)
        context['tests_by_category'] = tests_by_category

        return context


class TestDetailAPIView(SecurityAccessMixin, View):
    """
    AJAX endpoint for test detail popup.

    Returns JSON with test criteria, evidence, and result.
    """

    def get(self, request, pk):
        test = get_object_or_404(SecurityTest, pk=pk)

        # Log access
        self.log_access(
            request,
            SecurityAuditLog.ACTION_VIEW_FINDING,
            resource_type='test',
            resource_id=test.id,
        )

        # Get related findings
        findings = [
            {
                'id': str(f.id),
                'finding_id': f.finding_id,
                'title': f.title,
                'severity': f.severity,
                'cvss_score': float(f.cvss_score),
            }
            for f in test.findings.all()
        ]

        data = {
            'test_id': test.test_id,
            'title': test.title,
            'category': test.get_category_display(),
            'description': test.description,
            'criteria': test.criteria,
            'result': test.result,
            'result_details': test.result_details,
            'evidence': test.evidence,
            'duration_ms': test.duration_ms,
            'findings': findings,
        }

        return JsonResponse(data)


class FindingDetailAPIView(SecurityAccessMixin, View):
    """
    AJAX endpoint for finding detail popup.

    Returns JSON with full finding details including encrypted fields.
    """

    def get(self, request, pk):
        finding = get_object_or_404(SecurityFinding, pk=pk)

        # Log access
        self.log_access(
            request,
            SecurityAuditLog.ACTION_VIEW_FINDING,
            resource_type='finding',
            resource_id=finding.id,
        )

        data = {
            'finding_id': finding.finding_id,
            'title': finding.title,
            'severity': finding.severity,
            'likelihood': finding.likelihood,
            'impact': finding.impact,
            'cvss_vector': finding.cvss_vector,
            'cvss_score': float(finding.cvss_score),
            'description': finding.description,
            'risk_reasoning': finding.risk_reasoning,
            'evidence': finding.evidence,
            'affected_components': finding.affected_components,
            'recommendations': finding.recommendations,
            'validation_steps': finding.validation_steps,
            'is_quick_win': finding.is_quick_win,
            'remediation_effort': finding.remediation_effort,
        }

        return JsonResponse(data)


class RemediationPromptView(SecurityAccessMixin, View):
    """
    View to get the remediation prompt for a run.

    Returns plain text prompt that can be copied and pasted.
    """

    def get(self, request, pk):
        run = get_object_or_404(SecurityRun, pk=pk)

        # Log access
        self.log_access(
            request,
            SecurityAuditLog.ACTION_EXPORT,
            resource_type='remediation_prompt',
            resource_id=run.id,
        )

        return JsonResponse({
            'prompt': run.remediation_prompt,
            'run_id': str(run.id),
            'timestamp': run.run_timestamp.isoformat(),
        })


class TrendDataAPIView(SecurityAccessMixin, View):
    """
    AJAX endpoint for trend chart data.

    Returns time series data for all metrics.
    """

    def get(self, request):
        # Get historical scores (last 50 runs)
        scores = SecurityScore.objects.all()[:50]

        data = {
            'labels': [],
            'cvss_avg': [],
            'bitsight': [],
            'risk': [],
            'maturity': [],
            'grade': [],
        }

        for score in reversed(list(scores)):
            data['labels'].append(score.run_timestamp.strftime('%Y-%m-%d %H:%M'))
            data['cvss_avg'].append(float(score.cvss_avg))
            data['bitsight'].append(score.bitsight_score)
            data['risk'].append(score.risk_score_0_100)
            data['maturity'].append(score.maturity_level)
            data['grade'].append(score.securityscorecard_grade)

        return JsonResponse(data)
