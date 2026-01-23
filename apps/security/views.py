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
import threading
import time

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
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
from .scanner import SecurityScanner
from .scoring import ScoringEngine
from .report_generator import ReportGenerator
from .finding_tracker import analyze_finding_status, get_finding_trend_data, get_improvement_metrics, generate_finding_key
from .quick_win_detector import process_run_quick_wins


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

        # Add finding trend data
        context['finding_trend_data'] = json.dumps(get_finding_trend_data(30))

        # Add improvement metrics
        context['improvement_metrics'] = get_improvement_metrics(30)

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


class FindingTrendAPIView(SecurityAccessMixin, View):
    """
    AJAX endpoint for finding trend chart data.

    Returns time series data for finding status over time.
    """

    def get(self, request):
        limit = int(request.GET.get('limit', 20))
        data = get_finding_trend_data(limit)
        return JsonResponse(data)


class ImprovementMetricsAPIView(SecurityAccessMixin, View):
    """
    AJAX endpoint for security improvement metrics.

    Returns improvement data over a specified period.
    """

    def get(self, request):
        days = int(request.GET.get('days', 30))
        metrics = get_improvement_metrics(days)

        # Convert datetime objects for JSON
        if metrics.get('first_run'):
            metrics['first_run']['date'] = metrics['first_run']['date'].isoformat()
        if metrics.get('latest_run'):
            metrics['latest_run']['date'] = metrics['latest_run']['date'].isoformat()

        return JsonResponse(metrics)


class RunAssessmentView(SecurityAccessMixin, View):
    """
    Trigger a new security assessment.

    POST: Starts the assessment and redirects to dashboard.
    GET: Returns status of running assessment (for polling).
    """

    def post(self, request):
        """Start a new security assessment."""
        # Check if there's already a running assessment
        running = SecurityRun.objects.filter(status=SecurityRun.STATUS_RUNNING).first()
        if running:
            return JsonResponse({
                'status': 'already_running',
                'run_id': str(running.id),
                'message': 'An assessment is already running',
            })

        # Log the action
        self.log_access(
            request,
            SecurityAuditLog.ACTION_RUN_ASSESSMENT,
            resource_type='assessment',
            resource_id='new',
        )

        # Create the run record
        run = SecurityRun.objects.create(
            run_type='full',
            triggered_by=f'web:{request.user.email}',
            status=SecurityRun.STATUS_RUNNING,
        )

        # Run the assessment in the current thread (synchronous)
        # This ensures the user sees results immediately
        try:
            start_time = time.time()

            # Run the scanner
            scanner = SecurityScanner()
            test_results, findings = scanner.run_all_tests()

            # Calculate scores
            engine = ScoringEngine()
            scores = engine.calculate_scores(findings, test_results)

            # Save test results
            for test_result in test_results:
                SecurityTest.objects.create(
                    run=run,
                    test_id=test_result.test_id,
                    category=test_result.category,
                    title=test_result.title,
                    description=test_result.description,
                    criteria=test_result.criteria,
                    result=test_result.result,
                    result_details=test_result.result_details,
                    evidence=test_result.evidence,
                    duration_ms=test_result.duration_ms,
                )

            # Save findings
            for finding in findings:
                test = SecurityTest.objects.filter(run=run).first()
                # Generate stable finding key if not provided
                finding_key = getattr(finding, 'finding_key', '') or ''
                if not finding_key:
                    finding_key = generate_finding_key(
                        finding.title,
                        finding.severity,
                        finding.affected_components,
                    )
                SecurityFinding.objects.create(
                    run=run,
                    test=test,
                    finding_id=finding.finding_id,
                    title=finding.title,
                    severity=finding.severity,
                    likelihood=finding.likelihood,
                    impact=finding.impact,
                    cvss_vector=finding.cvss_vector,
                    cvss_score=finding.cvss_score,
                    description=finding.description,
                    risk_reasoning=finding.risk_reasoning,
                    evidence=finding.evidence,
                    affected_components=finding.affected_components,
                    recommendations=finding.recommendations,
                    validation_steps=finding.validation_steps,
                    is_quick_win=finding.is_quick_win,
                    remediation_effort=finding.remediation_effort,
                    # Acknowledgment tracking
                    finding_key=finding_key,
                    is_acknowledged=getattr(finding, 'is_acknowledged', False),
                    acknowledgment_justification=getattr(finding, 'acknowledgment_justification', ''),
                )

            # Save scores
            SecurityScore.objects.create(
                run=run,
                run_timestamp=run.run_timestamp,
                cvss_avg=scores.cvss_avg,
                cvss_critical_count=scores.cvss_critical_count,
                cvss_high_count=scores.cvss_high_count,
                cvss_medium_count=scores.cvss_medium_count,
                cvss_low_count=scores.cvss_low_count,
                cvss_none_count=scores.cvss_none_count,
                securityscorecard_grade=scores.securityscorecard_grade,
                bitsight_score=scores.bitsight_score,
                risk_score_0_100=scores.risk_score_0_100,
                maturity_level=scores.maturity_level,
                scoring_methodology=scores.methodology,
            )

            # Update run summary
            duration = time.time() - start_time
            passed_tests = sum(1 for t in test_results if t.result == 'pass')
            failed_tests = sum(1 for t in test_results if t.result == 'fail')

            run.status = SecurityRun.STATUS_COMPLETED
            run.completed_at = timezone.now()
            run.duration_seconds = int(duration)
            run.total_tests = len(test_results)
            run.passed_tests = passed_tests
            run.failed_tests = failed_tests
            run.total_findings = len(findings)
            run.critical_findings = scores.cvss_critical_count
            run.high_findings = scores.cvss_high_count
            run.medium_findings = scores.cvss_medium_count
            run.low_findings = scores.cvss_low_count

            # Generate reports
            report_gen = ReportGenerator(run, test_results, findings, scores)
            run.executive_summary = report_gen.generate_executive_summary()
            run.attack_paths = report_gen.generate_attack_paths()
            run.failure_modes = report_gen.generate_failure_modes()
            run.ciso_sleep_test = report_gen.generate_ciso_sleep_test()
            run.remediation_prompt = report_gen.generate_remediation_prompt()

            run.save()

            # Analyze finding status (compare to previous run)
            previous_run = SecurityRun.objects.filter(
                status=SecurityRun.STATUS_COMPLETED,
                run_timestamp__lt=run.run_timestamp,
            ).first()

            status_stats = analyze_finding_status(run, previous_run)

            # Update run with status counts
            run.new_findings = status_stats['new']
            run.recurring_findings = status_stats['recurring']
            run.fixed_findings = status_stats['fixed']
            run.regressed_findings = status_stats['regressed']
            run.save(update_fields=['new_findings', 'recurring_findings', 'fixed_findings', 'regressed_findings'])

            # Auto-detect quick wins
            process_run_quick_wins(run)

            # Redirect to dashboard to see results
            return redirect('security:dashboard')

        except Exception as e:
            run.status = SecurityRun.STATUS_FAILED
            run.save()
            return JsonResponse({
                'status': 'error',
                'message': str(e),
            }, status=500)

    def get(self, request):
        """Check status of running assessment."""
        running = SecurityRun.objects.filter(status=SecurityRun.STATUS_RUNNING).first()
        if running:
            return JsonResponse({
                'status': 'running',
                'run_id': str(running.id),
                'started_at': running.run_timestamp.isoformat(),
            })

        latest = SecurityRun.objects.filter(status=SecurityRun.STATUS_COMPLETED).first()
        if latest:
            return JsonResponse({
                'status': 'idle',
                'last_run_id': str(latest.id),
                'last_run_at': latest.run_timestamp.isoformat(),
            })

        return JsonResponse({'status': 'no_runs'})


class ExportCSVView(SecurityAccessMixin, View):
    """
    Export security run findings as CSV.

    Includes all findings with their details for spreadsheet analysis.
    """

    def get(self, request, pk):
        import csv
        from django.http import HttpResponse

        run = get_object_or_404(SecurityRun, pk=pk)

        # Log export
        self.log_access(
            request,
            SecurityAuditLog.ACTION_EXPORT,
            resource_type='csv',
            resource_id=run.id,
        )

        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        filename = f"security_findings_{run.run_timestamp.strftime('%Y%m%d_%H%M')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)

        # Header row
        writer.writerow([
            'Finding ID',
            'Title',
            'Severity',
            'CVSS Score',
            'CVSS Vector',
            'Status',
            'Quick Win',
            'Remediation Effort',
            'Likelihood',
            'Impact',
            'Description',
            'Risk Reasoning',
            'Affected Components',
            'Recommendations',
            'Validation Steps',
            'Is Acknowledged',
            'Acknowledgment Justification',
            'Occurrence Count',
        ])

        # Data rows
        for finding in run.findings.all().order_by('-cvss_score'):
            writer.writerow([
                finding.finding_id,
                finding.title,
                finding.severity,
                float(finding.cvss_score),
                finding.cvss_vector,
                finding.status,
                'Yes' if finding.is_quick_win else 'No',
                finding.remediation_effort,
                finding.likelihood,
                finding.impact,
                finding.description,
                finding.risk_reasoning,
                ', '.join(finding.affected_components or []),
                '\n'.join(finding.recommendations or []),
                finding.validation_steps,
                'Yes' if finding.is_acknowledged else 'No',
                finding.acknowledgment_justification,
                finding.occurrence_count,
            ])

        return response


class ExportPDFView(SecurityAccessMixin, View):
    """
    Export security run as PDF report.

    Generates a comprehensive executive report with findings summary.
    """

    def get(self, request, pk):
        from django.http import HttpResponse
        from django.template.loader import render_to_string

        run = get_object_or_404(SecurityRun, pk=pk)

        # Log export
        self.log_access(
            request,
            SecurityAuditLog.ACTION_EXPORT,
            resource_type='pdf',
            resource_id=run.id,
        )

        # Get score
        try:
            score = run.score
        except Exception:
            score = None

        # Calculate executive summary metrics
        total_tests = run.total_tests or 0
        passed_tests = run.passed_tests or 0
        pass_rate = (passed_tests * 100 // total_tests) if total_tests else 0

        # Determine posture
        grade = score.securityscorecard_grade if score else 'N/A'
        if grade in ['A', 'B']:
            posture = 'good'
            posture_label = 'GOOD'
            posture_desc = 'The application demonstrates strong security practices with well-implemented controls.'
        elif grade == 'C':
            posture = 'fair'
            posture_label = 'FAIR'
            posture_desc = 'The application has adequate security but has areas requiring attention.'
        else:
            posture = 'poor'
            posture_label = 'NEEDS IMPROVEMENT'
            posture_desc = 'The application has significant security gaps that should be addressed promptly.'

        # Top risks (sorted by CVSS)
        findings_list = list(run.findings.all().order_by('-cvss_score'))
        top_risks = findings_list[:5]

        # Quick wins for recommended actions
        quick_wins = [f for f in findings_list if f.is_quick_win]
        top_actions = quick_wins[:5] if quick_wins else top_risks[:5]

        # Build structured executive summary
        exec_summary = {
            'posture': posture,
            'posture_label': posture_label,
            'posture_desc': posture_desc,
            'metrics': {
                'tests_run': total_tests,
                'tests_passed': passed_tests,
                'pass_rate': pass_rate,
                'grade': grade,
                'bitsight': score.bitsight_score if score else 0,
                'risk_score': score.risk_score_0_100 if score else 0,
                'maturity': score.maturity_level if score else 0,
            },
            'top_risks': top_risks,
            'top_actions': top_actions,
        }

        # Build structured CISO Sleep Test data
        ciso_concerns = []

        # Check for critical findings
        critical = [f for f in findings_list if f.severity == 'critical']
        if critical:
            f = critical[0]
            ciso_concerns.append({
                'concern': f.title,
                'why_matters': f"CVSS {f.cvss_score} - {f.risk_reasoning or 'Critical security vulnerability'}",
                'disaster_trigger': 'Repository access by unauthorized party reveals vulnerability',
                'fix_first': f.recommendations[0] if f.recommendations else 'Address this critical finding immediately',
            })

        # Check for MFA gap
        mfa_findings = [f for f in findings_list if 'mfa' in f.title.lower()]
        if mfa_findings and len(ciso_concerns) < 3:
            ciso_concerns.append({
                'concern': 'No MFA Enforcement for Privileged Access',
                'why_matters': 'Credential compromise equals full account takeover without second factor',
                'disaster_trigger': 'Admin credentials phished or leaked from another breach',
                'fix_first': 'Require MFA for all staff and admin accounts',
            })

        # Check for PII logging
        pii_findings = [f for f in findings_list if 'pii' in f.title.lower() or 'log' in f.title.lower()]
        if pii_findings and len(ciso_concerns) < 3:
            ciso_concerns.append({
                'concern': 'PII Exposure in Logs',
                'why_matters': 'Email addresses logged without hashing creates privacy violation risk',
                'disaster_trigger': 'Log aggregation breach exposes user contact information',
                'fix_first': 'Hash all PII before logging using hash_pii() utility',
            })

        # Fill remaining slots with high severity findings
        high = [f for f in findings_list if f.severity == 'high']
        for f in high:
            if len(ciso_concerns) >= 3:
                break
            if not any(c['concern'] == f.title for c in ciso_concerns):
                ciso_concerns.append({
                    'concern': f.title,
                    'why_matters': f.risk_reasoning or f.description[:150],
                    'disaster_trigger': 'Exploitation by motivated attacker',
                    'fix_first': f.recommendations[0] if f.recommendations else 'Address immediately',
                })

        # Generate HTML content for PDF
        context = {
            'run': run,
            'score': score,
            'exec_summary': exec_summary,
            'ciso_concerns': ciso_concerns[:3],
            'findings': findings_list,
            'tests': run.tests.all().order_by('test_id'),
            'critical_findings': run.findings.filter(severity='critical'),
            'high_findings': run.findings.filter(severity='high'),
            'medium_findings': run.findings.filter(severity='medium'),
            'low_findings': run.findings.filter(severity='low'),
        }

        html_content = render_to_string('security/export_pdf.html', context, request=request)

        # Return HTML that can be printed to PDF
        # Note: For proper PDF generation, you'd use a library like weasyprint or xhtml2pdf
        # For now, we return HTML with print styles that users can print to PDF
        response = HttpResponse(html_content, content_type='text/html')
        response['Content-Disposition'] = f'inline; filename="security_report_{run.run_timestamp.strftime("%Y%m%d_%H%M")}.html"'

        return response
