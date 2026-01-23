# ==============================================================================
# File: apps/security/management/commands/run_security_assessment.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to run comprehensive security assessment
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Run Security Assessment Command

Executes a full security assessment and stores results in the database.

Usage:
    python manage.py run_security_assessment
    python manage.py run_security_assessment --type=quick
    python manage.py run_security_assessment --report

Options:
    --type: Assessment type (full, quick, targeted). Default: full
    --report: Generate and print executive report
    --json: Output results as JSON
"""

import json
import time
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.security.models import (
    SecurityRun,
    SecurityScore,
    SecurityTest,
    SecurityFinding,
)
from apps.security.scanner import SecurityScanner
from apps.security.scoring import ScoringEngine
from apps.security.report_generator import ReportGenerator


class Command(BaseCommand):
    help = 'Run comprehensive security assessment and store results'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            default='full',
            choices=['full', 'quick', 'targeted'],
            help='Assessment type: full (all tests), quick (critical only), targeted (specific category)',
        )
        parser.add_argument(
            '--report',
            action='store_true',
            help='Generate and display executive report',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output results as JSON',
        )
        parser.add_argument(
            '--triggered-by',
            type=str,
            default='manual',
            help='Who/what triggered this run (manual, scheduled, ci)',
        )

    def handle(self, *args, **options):
        start_time = time.time()
        run_type = options['type']
        triggered_by = options['triggered_by']

        self.stdout.write(self.style.NOTICE(f'\n{"="*60}'))
        self.stdout.write(self.style.NOTICE('SECURITY ASSESSMENT'))
        self.stdout.write(self.style.NOTICE(f'{"="*60}'))
        self.stdout.write(f'Started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Type: {run_type}')
        self.stdout.write(f'Triggered by: {triggered_by}')
        self.stdout.write('')

        # Create the run record
        run = SecurityRun.objects.create(
            run_type=run_type,
            triggered_by=triggered_by,
            status=SecurityRun.STATUS_RUNNING,
        )

        try:
            # Run the scanner
            self.stdout.write('Running security tests...')
            scanner = SecurityScanner()
            test_results, findings = scanner.run_all_tests()

            # Calculate scores
            self.stdout.write('Calculating security scores...')
            engine = ScoringEngine()
            scores = engine.calculate_scores(findings, test_results)

            # Save test results
            self.stdout.write('Saving test results...')
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
            self.stdout.write('Saving findings...')
            for finding in findings:
                # Find the associated test
                test = SecurityTest.objects.filter(run=run).first()  # Simplified

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
                    finding_key=getattr(finding, 'finding_key', '') or '',
                    is_acknowledged=getattr(finding, 'is_acknowledged', False),
                    acknowledgment_justification=getattr(finding, 'acknowledgment_justification', ''),
                )

            # Save scores
            self.stdout.write('Saving scores...')
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
            self.stdout.write('Generating reports...')
            report_gen = ReportGenerator(run, test_results, findings, scores)

            run.executive_summary = report_gen.generate_executive_summary()
            run.attack_paths = report_gen.generate_attack_paths()
            run.failure_modes = report_gen.generate_failure_modes()
            run.ciso_sleep_test = report_gen.generate_ciso_sleep_test()
            run.remediation_prompt = report_gen.generate_remediation_prompt()

            run.save()

            # Output results
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'{"="*60}'))
            self.stdout.write(self.style.SUCCESS('ASSESSMENT COMPLETE'))
            self.stdout.write(self.style.SUCCESS(f'{"="*60}'))
            self.stdout.write('')

            # Snapshot
            self.stdout.write('SECURITY ASSESSMENT SNAPSHOT')
            self.stdout.write(f'Run ID: {run.id}')
            self.stdout.write(f'Timestamp: {run.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")}')
            self.stdout.write('')
            self.stdout.write(f'Tests Run: {run.total_tests} (100%)')
            self.stdout.write(f'Tests Passed: {run.passed_tests} ({run.passed_tests*100//run.total_tests if run.total_tests else 0}%)')
            self.stdout.write('')
            self.stdout.write(f'Critical Findings: {run.critical_findings}')
            self.stdout.write(f'High Findings: {run.high_findings}')
            self.stdout.write(f'Medium Findings: {run.medium_findings}')
            self.stdout.write(f'Low Findings: {run.low_findings}')
            self.stdout.write('')
            self.stdout.write('SCORES:')
            self.stdout.write(f'  CVSS Average: {scores.cvss_avg}')
            self.stdout.write(f'  Grade: {scores.securityscorecard_grade}')
            self.stdout.write(f'  BitSight Score: {scores.bitsight_score}/900')
            self.stdout.write(f'  Risk Score: {scores.risk_score_0_100}/100')
            self.stdout.write(f'  Maturity Level: {scores.maturity_level}/3')
            self.stdout.write('')
            self.stdout.write(f'Duration: {duration:.2f}s')

            if options['report']:
                self.stdout.write('')
                self.stdout.write(self.style.NOTICE('EXECUTIVE SUMMARY:'))
                self.stdout.write(run.executive_summary)

            if options['json']:
                output = {
                    'run_id': str(run.id),
                    'timestamp': run.run_timestamp.isoformat(),
                    'tests': {
                        'total': run.total_tests,
                        'passed': run.passed_tests,
                        'failed': run.failed_tests,
                    },
                    'findings': {
                        'total': run.total_findings,
                        'critical': run.critical_findings,
                        'high': run.high_findings,
                        'medium': run.medium_findings,
                        'low': run.low_findings,
                    },
                    'scores': {
                        'cvss_avg': float(scores.cvss_avg),
                        'grade': scores.securityscorecard_grade,
                        'bitsight': scores.bitsight_score,
                        'risk': scores.risk_score_0_100,
                        'maturity': scores.maturity_level,
                    },
                }
                self.stdout.write('')
                self.stdout.write(json.dumps(output, indent=2))

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                f'View dashboard at: /security/dashboard/'
            ))

        except Exception as e:
            run.status = SecurityRun.STATUS_FAILED
            run.save()
            self.stdout.write(self.style.ERROR(f'Assessment failed: {e}'))
            raise
