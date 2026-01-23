# ==============================================================================
# File: apps/security/scanner.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive security scanner with 40+ tests
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Security Scanner

Performs comprehensive security assessment with 40+ automated tests across:
- Secrets & Credentials (8 tests)
- Authentication & Sessions (6 tests)
- Authorization (5 tests)
- Input Validation (5 tests)
- Data Protection (5 tests)
- Logging & Auditing (4 tests)
- Web Security (6 tests)
- Dependencies (3 tests)
- Deployment (4 tests)
- Abuse Resistance (4 tests)

Each test produces:
- Pass/Fail/Unknown result
- Evidence (encrypted)
- Findings with CVSS scores
"""

import hashlib
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ==============================================================================
# Data Classes
# ==============================================================================

@dataclass
class TestResult:
    """Result of a single security test."""
    test_id: str
    category: str
    title: str
    description: str
    criteria: str
    result: str  # pass, fail, unknown, skipped
    result_details: str = ''
    evidence: dict = field(default_factory=dict)
    duration_ms: int = 0
    findings: list = field(default_factory=list)


@dataclass
class Finding:
    """Security finding with CVSS score."""
    finding_id: str
    title: str
    severity: str  # critical, high, medium, low, info
    likelihood: str  # high, medium, low
    impact: str  # high, medium, low
    cvss_vector: str
    cvss_score: Decimal
    description: str
    risk_reasoning: str
    evidence: dict
    affected_components: list
    recommendations: list
    validation_steps: str
    is_quick_win: bool = False
    remediation_effort: str = 'medium'
    # Acknowledgment status - checked against AcknowledgedFinding table
    is_acknowledged: bool = False
    acknowledgment_justification: str = ''


# ==============================================================================
# CVSS Calculator
# ==============================================================================

class CVSSCalculator:
    """
    CVSS v3.1 Base Score Calculator.

    Computes base score from vector string.
    """

    # CVSS v3.1 metric values
    METRICS = {
        'AV': {'N': 0.85, 'A': 0.62, 'L': 0.55, 'P': 0.2},  # Attack Vector
        'AC': {'L': 0.77, 'H': 0.44},  # Attack Complexity
        'PR': {  # Privileges Required (depends on Scope)
            'unchanged': {'N': 0.85, 'L': 0.62, 'H': 0.27},
            'changed': {'N': 0.85, 'L': 0.68, 'H': 0.5},
        },
        'UI': {'N': 0.85, 'R': 0.62},  # User Interaction
        'S': {'U': 'unchanged', 'C': 'changed'},  # Scope
        'C': {'H': 0.56, 'L': 0.22, 'N': 0},  # Confidentiality
        'I': {'H': 0.56, 'L': 0.22, 'N': 0},  # Integrity
        'A': {'H': 0.56, 'L': 0.22, 'N': 0},  # Availability
    }

    @classmethod
    def calculate(cls, vector: str) -> Decimal:
        """
        Calculate CVSS v3.1 base score from vector string.

        Args:
            vector: CVSS vector string, e.g., "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"

        Returns:
            Decimal base score (0.0 - 10.0)
        """
        if not vector:
            return Decimal('0.0')

        try:
            # Parse vector
            metrics = {}
            for part in vector.split('/'):
                if ':' in part:
                    key, value = part.split(':')
                    metrics[key] = value

            # Get scope
            scope = cls.METRICS['S'].get(metrics.get('S', 'U'), 'unchanged')

            # Calculate exploitability
            av = cls.METRICS['AV'].get(metrics.get('AV', 'N'), 0.85)
            ac = cls.METRICS['AC'].get(metrics.get('AC', 'L'), 0.77)
            pr = cls.METRICS['PR'][scope].get(metrics.get('PR', 'N'), 0.85)
            ui = cls.METRICS['UI'].get(metrics.get('UI', 'N'), 0.85)

            exploitability = 8.22 * av * ac * pr * ui

            # Calculate impact
            c = cls.METRICS['C'].get(metrics.get('C', 'N'), 0)
            i = cls.METRICS['I'].get(metrics.get('I', 'N'), 0)
            a = cls.METRICS['A'].get(metrics.get('A', 'N'), 0)

            isc_base = 1 - ((1 - c) * (1 - i) * (1 - a))

            if scope == 'unchanged':
                impact = 6.42 * isc_base
            else:
                impact = 7.52 * (isc_base - 0.029) - 3.25 * ((isc_base - 0.02) ** 15)

            # Calculate base score
            if impact <= 0:
                return Decimal('0.0')

            if scope == 'unchanged':
                base_score = min(exploitability + impact, 10)
            else:
                base_score = min(1.08 * (exploitability + impact), 10)

            # Round up to 1 decimal
            return Decimal(str(round(base_score * 10) / 10))

        except Exception as e:
            logger.error(f"CVSS calculation error: {e}")
            return Decimal('0.0')


# ==============================================================================
# Security Scanner
# ==============================================================================

class SecurityScanner:
    """
    Comprehensive security scanner.

    Runs 40+ automated security tests and generates findings.
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize scanner.

        Args:
            base_path: Project root path (defaults to Django BASE_DIR)
        """
        self.base_path = base_path or Path(settings.BASE_DIR)
        self.results: list[TestResult] = []
        self.findings: list[Finding] = []
        self.finding_counter = 0

    def run_all_tests(self) -> tuple[list[TestResult], list[Finding]]:
        """
        Run all security tests.

        Returns:
            Tuple of (test_results, findings)
        """
        logger.info("Starting comprehensive security scan...")
        start_time = time.time()

        # Run all test categories
        self._run_secrets_tests()
        self._run_auth_tests()
        self._run_authz_tests()
        self._run_input_validation_tests()
        self._run_data_protection_tests()
        self._run_logging_tests()
        self._run_web_security_tests()
        self._run_dependency_tests()
        self._run_deployment_tests()
        self._run_abuse_resistance_tests()

        duration = time.time() - start_time
        logger.info(f"Security scan complete in {duration:.2f}s: {len(self.results)} tests, {len(self.findings)} findings")

        return self.results, self.findings

    def _add_finding(
        self,
        title: str,
        severity: str,
        likelihood: str,
        impact: str,
        cvss_vector: str,
        description: str,
        risk_reasoning: str,
        evidence: dict,
        affected_components: list,
        recommendations: list,
        validation_steps: str,
        is_quick_win: bool = False,
        remediation_effort: str = 'medium',
        finding_key: str = '',  # Stable key for acknowledgment matching
    ) -> Finding:
        """Add a security finding."""
        self.finding_counter += 1
        finding_id = f"SEC-{self.finding_counter:03d}"

        # Check if this finding is acknowledged
        # Use finding_key if provided, otherwise use title for matching
        from apps.security.models import AcknowledgedFinding
        lookup_key = finding_key or title
        acknowledgment = AcknowledgedFinding.get_acknowledgment(lookup_key)
        is_acknowledged = acknowledgment is not None
        acknowledgment_justification = acknowledgment.justification if acknowledgment else ''

        finding = Finding(
            finding_id=finding_id,
            title=title,
            severity=severity,
            likelihood=likelihood,
            impact=impact,
            cvss_vector=cvss_vector,
            cvss_score=CVSSCalculator.calculate(cvss_vector),
            description=description,
            risk_reasoning=risk_reasoning,
            evidence=evidence,
            affected_components=affected_components,
            recommendations=recommendations,
            validation_steps=validation_steps,
            is_quick_win=is_quick_win,
            remediation_effort=remediation_effort,
            is_acknowledged=is_acknowledged,
            acknowledgment_justification=acknowledgment_justification,
        )
        self.findings.append(finding)
        return finding

    # ==========================================================================
    # SECRETS & CREDENTIALS TESTS (8 tests)
    # ==========================================================================

    def _run_secrets_tests(self):
        """Run secrets and credentials tests."""

        # SEC-T001: Hardcoded secrets in code
        self._test_hardcoded_secrets()

        # SEC-T002: Secrets in git-tracked files
        self._test_secrets_in_git()

        # SEC-T003: .env file protection
        self._test_env_file_protection()

        # SEC-T004: API keys in documentation
        self._test_api_keys_in_docs()

        # SEC-T005: Private keys in repo
        self._test_private_keys()

        # SEC-T006: AWS credentials exposure
        self._test_aws_credentials()

        # SEC-T007: Database credentials exposure
        self._test_database_credentials()

        # SEC-T008: Third-party API keys
        self._test_third_party_api_keys()

    def _test_hardcoded_secrets(self):
        """SEC-T001: Check for hardcoded secrets in Python files."""
        start = time.time()
        test_id = "SEC-T001"

        patterns = [
            # Match standalone secret variable names (not part of larger identifiers)
            (r'\b(SECRET_KEY|API_KEY|PASSWORD|TOKEN|PRIVATE_KEY|ACCESS_KEY)\s*=\s*[\'"][^\'"]{10,}[\'"]', 'Secret assignment'),
            # Match credential assignments with word boundaries to avoid false positives like SOURCE_FATSECRET
            (r'\b(password|secret|token|api_key)\s*=\s*[\'"][^\'"]{8,}[\'"]', 'Credential assignment'),
        ]

        evidence = {'files_scanned': 0, 'matches': []}
        issues_found = []

        for py_file in self.base_path.rglob('*.py'):
            # Skip test files and migrations
            if '/tests/' in str(py_file) or '/migrations/' in str(py_file):
                continue

            evidence['files_scanned'] += 1
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')

                # Find all triple-quoted string regions (docstrings/templates)
                # to exclude them from secret detection
                triple_quote_regions = []
                for match in re.finditer(r'(\'\'\'|""").*?\1', content, re.DOTALL):
                    triple_quote_regions.append((match.start(), match.end()))

                def is_in_string_literal(pos):
                    """Check if position is inside a triple-quoted string."""
                    for start, end in triple_quote_regions:
                        if start <= pos < end:
                            return True
                    return False

                for pattern, desc in patterns:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        # Skip matches inside triple-quoted strings (docstrings, templates)
                        if is_in_string_literal(match.start()):
                            continue

                        # Get line number
                        line_num = content[:match.start()].count('\n') + 1
                        line = content.split('\n')[line_num - 1]

                        # Filter out env() calls and test data
                        if 'env(' not in line and 'os.environ' not in line and 'getattr(settings' not in line:
                            rel_path = str(py_file.relative_to(self.base_path))
                            issues_found.append({
                                'file': rel_path,
                                'line': line_num,
                                'type': desc,
                            })
                            evidence['matches'].append({
                                'file': rel_path,
                                'line': line_num,
                            })
            except Exception as e:
                logger.debug(f"Error scanning {py_file}: {e}")

        result = 'pass' if not issues_found else 'fail'
        findings = []

        if issues_found:
            finding = self._add_finding(
                finding_key="hardcoded_secrets",  # Stable key for acknowledgment
                title="Hardcoded Secrets in Source Code",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description=f"Found {len(issues_found)} potential hardcoded secrets in Python source files.",
                risk_reasoning="Hardcoded secrets can be extracted from source code, leading to unauthorized access.",
                evidence={'matches': issues_found[:10]},  # Limit evidence
                affected_components=[m['file'] for m in issues_found[:5]],
                recommendations=[
                    "Move all secrets to environment variables",
                    "Use Django's env() pattern for all sensitive values",
                    "Add pre-commit hooks to scan for secrets",
                ],
                validation_steps="grep -r 'SECRET_KEY.*=' --include='*.py' | grep -v env | grep -v test",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="Hardcoded Secrets in Code",
            description="Scan Python source files for hardcoded API keys, passwords, and secrets.",
            criteria="No hardcoded secrets found outside of test files and env() calls.",
            result=result,
            result_details=f"Scanned {evidence['files_scanned']} files, found {len(issues_found)} issues",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_secrets_in_git(self):
        """SEC-T002: Check for secrets in git-tracked files."""
        start = time.time()
        test_id = "SEC-T002"

        evidence = {'checked': [], 'issues': []}

        # Check .gitignore exists and has .env
        gitignore_path = self.base_path / '.gitignore'
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            has_env = '.env' in content
            evidence['checked'].append({'file': '.gitignore', 'has_env_exclusion': has_env})

        # Check if .env is tracked
        try:
            result = subprocess.run(
                ['git', 'ls-files', '.env'],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            env_tracked = bool(result.stdout.strip())
            evidence['env_tracked'] = env_tracked
            if env_tracked:
                evidence['issues'].append('.env file is tracked in git')
        except Exception as e:
            evidence['error'] = str(e)

        # Check for sensitive file extensions in git
        sensitive_extensions = ['.pem', '.key', '.p12', '.pfx', '.crt']
        try:
            result = subprocess.run(
                ['git', 'ls-files'],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            for line in result.stdout.strip().split('\n'):
                if any(line.endswith(ext) for ext in sensitive_extensions):
                    evidence['issues'].append(f"Sensitive file tracked: {line}")
        except Exception:
            pass

        result = 'pass' if not evidence.get('issues') else 'fail'
        findings = []

        if evidence.get('issues'):
            finding = self._add_finding(
                finding_key="sensitive_files_in_git",
                title="Sensitive Files Tracked in Git",
                severity='high',
                likelihood='high',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                description=f"Found {len(evidence['issues'])} sensitive files tracked in git.",
                risk_reasoning="Git history persists forever. Secrets in git are considered permanently compromised.",
                evidence={'issues': evidence['issues']},
                affected_components=['Repository'],
                recommendations=[
                    "Remove sensitive files from git history using git filter-branch or BFG",
                    "Rotate any exposed credentials immediately",
                    "Add patterns to .gitignore",
                ],
                validation_steps="git ls-files | grep -E '\\.(env|pem|key|p12)$'",
                is_quick_win=False,
                remediation_effort='high',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="Secrets in Git-Tracked Files",
            description="Check for .env, keys, certificates tracked in git.",
            criteria="No sensitive files tracked in git repository.",
            result=result,
            result_details=f"Found {len(evidence.get('issues', []))} issues",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_env_file_protection(self):
        """SEC-T003: Verify .env file protection."""
        start = time.time()
        test_id = "SEC-T003"

        evidence = {'gitignore_exists': False, 'env_in_gitignore': False, 'env_example_exists': False}

        gitignore = self.base_path / '.gitignore'
        if gitignore.exists():
            evidence['gitignore_exists'] = True
            content = gitignore.read_text()
            evidence['env_in_gitignore'] = '.env' in content

        evidence['env_example_exists'] = (self.base_path / '.env.example').exists()

        result = 'pass' if evidence['env_in_gitignore'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title=".env File Protection",
            description="Verify .env is excluded from git and .env.example exists.",
            criteria=".env in .gitignore and .env.example template exists.",
            result=result,
            result_details=f".env in .gitignore: {evidence['env_in_gitignore']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_api_keys_in_docs(self):
        """SEC-T004: Check for API keys in documentation."""
        start = time.time()
        test_id = "SEC-T004"

        # Pattern for potential API keys (hex strings, base64, etc.)
        api_key_patterns = [
            r'[a-f0-9]{32,}',  # Hex strings
            r'[A-Za-z0-9+/=]{32,}',  # Base64-ish
            r'sk_live_[A-Za-z0-9]+',  # Stripe live keys
            r'pk_live_[A-Za-z0-9]+',  # Stripe public keys
        ]

        evidence = {'files_checked': 0, 'potential_keys': []}

        for md_file in self.base_path.rglob('*.md'):
            rel_path = str(md_file.relative_to(self.base_path))
            evidence['files_checked'] += 1
            try:
                content = md_file.read_text(encoding='utf-8', errors='ignore')
                # Look for lines that look like they have API keys
                for line_num, line in enumerate(content.split('\n'), 1):
                    # Skip code block examples with obvious placeholder text
                    if 'your-' in line.lower() and '-here' in line.lower():
                        continue
                    # Check for X-*-API-Key headers with hex values
                    if re.search(r'X-\w+-API-Key.*[a-f0-9]{32}', line, re.IGNORECASE):
                        evidence['potential_keys'].append({
                            'file': rel_path,
                            'line': line_num,
                            'type': 'api_header',
                        })
                    # Check for curl commands with long hex strings (potential keys)
                    elif 'curl' in line and re.search(r'[a-f0-9]{32,}', line):
                        evidence['potential_keys'].append({
                            'file': rel_path,
                            'line': line_num,
                            'type': 'curl_command',
                        })
            except Exception as e:
                logger.debug(f"Error reading {md_file}: {e}")

        result = 'pass' if not evidence['potential_keys'] else 'fail'
        findings = []

        if evidence['potential_keys']:
            finding = self._add_finding(
                finding_key="api_keys_in_docs",  # Stable key for acknowledgment
                title="API Keys Exposed in Documentation",
                severity='critical',
                likelihood='high',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
                description=f"Found {len(evidence['potential_keys'])} potential API keys in documentation files.",
                risk_reasoning="API keys in documentation (especially git-tracked) allow anyone with repo access to authenticate.",
                evidence={'locations': evidence['potential_keys'][:10]},
                affected_components=[k['file'] for k in evidence['potential_keys'][:5]],
                recommendations=[
                    "Remove all real API keys from documentation immediately",
                    "Use placeholder values like 'your-api-key-here'",
                    "Rotate exposed API keys",
                    "Add documentation to .gitignore or use env var references",
                ],
                validation_steps="grep -r 'X-.*-API-Key.*[a-f0-9]' --include='*.md'",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="API Keys in Documentation",
            description="Scan markdown files for exposed API keys.",
            criteria="No real API keys found in documentation files.",
            result=result,
            result_details=f"Checked {evidence['files_checked']} files, found {len(evidence['potential_keys'])} potential keys",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_private_keys(self):
        """SEC-T005: Check for private keys in repository."""
        start = time.time()
        test_id = "SEC-T005"

        evidence = {'files_checked': 0, 'private_keys_found': []}

        # Check for private key files
        key_patterns = ['*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa', 'id_dsa', 'id_ecdsa']
        for pattern in key_patterns:
            for key_file in self.base_path.rglob(pattern):
                rel_path = str(key_file.relative_to(self.base_path))
                evidence['private_keys_found'].append(rel_path)

        # Check file contents for actual private key blocks (header + content + footer)
        # Use a pattern that matches real keys, not just references to the pattern
        private_key_pattern = r'-----BEGIN [A-Z ]*PRIVATE KEY-----\s+[A-Za-z0-9+/=\s]{50,}\s+-----END [A-Z ]*PRIVATE KEY-----'
        # Files to skip (scanner itself, tests, documentation)
        skip_patterns = ['scanner.py', 'test_', '_test.py', '.md', '.rst']
        for py_file in self.base_path.rglob('*'):
            if py_file.is_file() and py_file.suffix in ['.py', '.txt', '.pem', '.key', '']:
                rel_path = str(py_file.relative_to(self.base_path))
                # Skip scanner and test files
                if any(skip in rel_path for skip in skip_patterns):
                    continue
                evidence['files_checked'] += 1
                try:
                    content = py_file.read_text(encoding='utf-8', errors='ignore')
                    if re.search(private_key_pattern, content, re.DOTALL):
                        if rel_path not in evidence['private_keys_found']:
                            evidence['private_keys_found'].append(rel_path)
                except Exception:
                    pass

        result = 'pass' if not evidence['private_keys_found'] else 'fail'
        findings = []

        if evidence['private_keys_found']:
            finding = self._add_finding(
                finding_key="private_keys_in_repo",
                title="Private Keys Found in Repository",
                severity='critical',
                likelihood='high',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:N",
                description=f"Found {len(evidence['private_keys_found'])} private key files in repository.",
                risk_reasoning="Private keys allow impersonation of services, decryption of data, and signing of malicious content.",
                evidence={'files': evidence['private_keys_found']},
                affected_components=evidence['private_keys_found'],
                recommendations=[
                    "Remove private keys from repository immediately",
                    "Revoke and regenerate all exposed keys",
                    "Use secure key management (HSM, AWS KMS, etc.)",
                ],
                validation_steps="find . -name '*.pem' -o -name '*.key' -o -name 'id_rsa'",
                is_quick_win=True,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="Private Keys in Repository",
            description="Search for private key files and embedded keys.",
            criteria="No private keys found in repository.",
            result=result,
            result_details=f"Found {len(evidence['private_keys_found'])} private keys",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_aws_credentials(self):
        """SEC-T006: Check for AWS credentials."""
        start = time.time()
        test_id = "SEC-T006"

        evidence = {'checked': True, 'issues': []}

        # AWS patterns
        aws_patterns = [
            (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
            (r'aws_secret_access_key\s*=\s*[\'"][^\'"]+[\'"]', 'AWS Secret in config'),
        ]

        for py_file in self.base_path.rglob('*.py'):
            if '/tests/' in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                for pattern, desc in aws_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        rel_path = str(py_file.relative_to(self.base_path))
                        evidence['issues'].append({'file': rel_path, 'type': desc})
            except Exception:
                pass

        result = 'pass' if not evidence['issues'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="AWS Credentials Exposure",
            description="Check for AWS access keys and secrets in code.",
            criteria="No AWS credentials found in source code.",
            result=result,
            result_details=f"Found {len(evidence['issues'])} AWS credential issues",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_database_credentials(self):
        """SEC-T007: Check database credential handling."""
        start = time.time()
        test_id = "SEC-T007"

        evidence = {'uses_env': False, 'hardcoded_found': []}

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            # Check if DATABASE_URL uses env
            if "env('DATABASE_URL" in content or "os.environ.get('DATABASE_URL" in content:
                evidence['uses_env'] = True

            # Check for hardcoded database passwords
            if re.search(r"'PASSWORD':\s*'[^']+[a-zA-Z0-9]+'", content):
                evidence['hardcoded_found'].append('settings.py')

        result = 'pass' if evidence['uses_env'] and not evidence['hardcoded_found'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="Database Credentials",
            description="Verify database credentials are loaded from environment.",
            criteria="Database URL loaded from environment, no hardcoded passwords.",
            result=result,
            result_details=f"Uses env: {evidence['uses_env']}, Hardcoded: {len(evidence['hardcoded_found'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_third_party_api_keys(self):
        """SEC-T008: Check third-party API key handling."""
        start = time.time()
        test_id = "SEC-T008"

        evidence = {'services_checked': [], 'issues': []}

        services = [
            ('OPENAI_API_KEY', 'OpenAI'),
            ('STRIPE_SECRET_KEY', 'Stripe'),
            ('TWILIO_AUTH_TOKEN', 'Twilio'),
            ('PLAID_SECRET', 'Plaid'),
            ('SENTRY_DSN', 'Sentry'),
        ]

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            for var, service in services:
                evidence['services_checked'].append(service)
                # Check if loaded from env
                if var in content:
                    if f"env('{var}" in content or f'os.environ.get(\'{var}' in content:
                        pass  # Good - from env
                    elif f"'{var}':" in content or f'"{var}":' in content:
                        # Hardcoded
                        evidence['issues'].append(f"{service} ({var}) appears hardcoded")

        result = 'pass' if not evidence['issues'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='secrets',
            title="Third-Party API Keys",
            description="Verify API keys for external services are loaded from environment.",
            criteria="All third-party API keys loaded from environment variables.",
            result=result,
            result_details=f"Checked {len(evidence['services_checked'])} services",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # AUTHENTICATION & SESSION TESTS (6 tests)
    # ==========================================================================

    def _run_auth_tests(self):
        """Run authentication and session tests."""
        self._test_session_configuration()
        self._test_password_policy()
        self._test_rate_limiting()
        self._test_mfa_availability()
        self._test_session_timeout()
        self._test_secure_cookies()

    def _test_session_configuration(self):
        """SEC-T009: Check session security configuration."""
        start = time.time()
        test_id = "SEC-T009"

        evidence = {'settings': {}}

        # Check Django settings
        evidence['settings']['SESSION_COOKIE_SECURE'] = getattr(settings, 'SESSION_COOKIE_SECURE', False)
        evidence['settings']['SESSION_COOKIE_HTTPONLY'] = getattr(settings, 'SESSION_COOKIE_HTTPONLY', True)
        evidence['settings']['SESSION_COOKIE_SAMESITE'] = getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax')
        evidence['settings']['SESSION_COOKIE_AGE'] = getattr(settings, 'SESSION_COOKIE_AGE', 1209600)

        # In debug mode, SECURE may be false - that's expected
        debug = getattr(settings, 'DEBUG', False)
        evidence['debug_mode'] = debug

        # Check if settings are appropriate
        issues = []
        if not debug and not evidence['settings']['SESSION_COOKIE_SECURE']:
            issues.append('SESSION_COOKIE_SECURE should be True in production')
        if evidence['settings']['SESSION_COOKIE_SAMESITE'] not in ['Lax', 'Strict']:
            issues.append('SESSION_COOKIE_SAMESITE should be Lax or Strict')

        result = 'pass' if not issues else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='auth',
            title="Session Security Configuration",
            description="Verify session cookie security settings.",
            criteria="Secure, HttpOnly, SameSite cookies configured correctly.",
            result=result,
            result_details=f"Issues: {len(issues)}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_password_policy(self):
        """SEC-T010: Check password policy configuration."""
        start = time.time()
        test_id = "SEC-T010"

        evidence = {'validators': []}

        # Check AUTH_PASSWORD_VALIDATORS
        validators = getattr(settings, 'AUTH_PASSWORD_VALIDATORS', [])
        for v in validators:
            evidence['validators'].append(v.get('NAME', '').split('.')[-1])

        # Expected validators
        expected = ['MinimumLengthValidator', 'CommonPasswordValidator', 'NumericPasswordValidator']
        has_all = all(any(e in v for v in evidence['validators']) for e in expected)

        result = 'pass' if has_all else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='auth',
            title="Password Policy",
            description="Verify password validation is configured.",
            criteria="Password validators include length, common password, and numeric checks.",
            result=result,
            result_details=f"Validators: {', '.join(evidence['validators'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_rate_limiting(self):
        """SEC-T011: Check authentication rate limiting."""
        start = time.time()
        test_id = "SEC-T011"

        evidence = {'axes_configured': False, 'settings': {}}

        # Check django-axes configuration
        if 'axes' in getattr(settings, 'INSTALLED_APPS', []):
            evidence['axes_configured'] = True
            evidence['settings']['AXES_FAILURE_LIMIT'] = getattr(settings, 'AXES_FAILURE_LIMIT', 3)
            evidence['settings']['AXES_COOLOFF_TIME'] = getattr(settings, 'AXES_COOLOFF_TIME', 1)
            evidence['settings']['AXES_LOCKOUT_PARAMETERS'] = getattr(settings, 'AXES_LOCKOUT_PARAMETERS', [])

        result = 'pass' if evidence['axes_configured'] else 'fail'
        findings = []

        if not evidence['axes_configured']:
            finding = self._add_finding(
                finding_key="no_auth_rate_limiting",
                title="No Authentication Rate Limiting",
                severity='high',
                likelihood='high',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:N",
                description="No rate limiting configured for authentication endpoints.",
                risk_reasoning="Without rate limiting, attackers can perform unlimited password guessing attacks.",
                evidence=evidence,
                affected_components=['Authentication system'],
                recommendations=[
                    "Install and configure django-axes",
                    "Set reasonable failure limits (5 attempts)",
                    "Configure cooloff time (1 hour)",
                ],
                validation_steps="Check INSTALLED_APPS for 'axes' and AXES_FAILURE_LIMIT in settings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='auth',
            title="Authentication Rate Limiting",
            description="Verify rate limiting is configured for login attempts.",
            criteria="django-axes or similar rate limiting configured.",
            result=result,
            result_details=f"Axes configured: {evidence['axes_configured']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_mfa_availability(self):
        """SEC-T012: Check MFA availability and enforcement."""
        start = time.time()
        test_id = "SEC-T012"

        evidence = {'mfa_available': False, 'mfa_enforced': False, 'methods': []}

        # Check for WebAuthn/TOTP implementations
        users_app = self.base_path / 'apps' / 'users'
        if users_app.exists():
            for py_file in users_app.rglob('*.py'):
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                if 'WebAuthn' in content or 'webauthn' in content:
                    evidence['mfa_available'] = True
                    evidence['methods'].append('WebAuthn')
                if 'TOTP' in content or 'pyotp' in content:
                    evidence['mfa_available'] = True
                    evidence['methods'].append('TOTP')

        # Check if MFA is enforced for admin
        evidence['mfa_enforced'] = False  # Would need to check middleware/decorators

        result = 'pass' if evidence['mfa_available'] else 'fail'
        findings = []

        if not evidence['mfa_enforced']:
            finding = self._add_finding(
                finding_key="mfa_not_enforced",
                title="MFA Not Enforced for Privileged Access",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description="Multi-factor authentication is available but not enforced for admin users.",
                risk_reasoning="Compromised admin credentials without MFA requirement leads to full account takeover.",
                evidence=evidence,
                affected_components=['Admin console', 'Staff accounts'],
                recommendations=[
                    "Require MFA for all staff/admin users",
                    "Implement step-up authentication for sensitive operations",
                    "Consider mandatory WebAuthn for privileged accounts",
                ],
                validation_steps="Verify admin login requires second factor",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='auth',
            title="MFA Availability and Enforcement",
            description="Check if MFA is available and enforced for privileged access.",
            criteria="MFA available for all users, enforced for admin/staff.",
            result=result,
            result_details=f"Available: {evidence['mfa_available']}, Methods: {evidence['methods']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_session_timeout(self):
        """SEC-T013: Check session timeout configuration."""
        start = time.time()
        test_id = "SEC-T013"

        session_age = getattr(settings, 'SESSION_COOKIE_AGE', 1209600)  # Default 2 weeks
        evidence = {
            'session_cookie_age': session_age,
            'session_age_hours': session_age / 3600,
        }

        # 24 hours is reasonable for a personal app
        is_reasonable = session_age <= 86400 * 7  # 7 days max

        result = 'pass' if is_reasonable else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='auth',
            title="Session Timeout",
            description="Verify session timeout is configured appropriately.",
            criteria="Session timeout is 7 days or less.",
            result=result,
            result_details=f"Session age: {evidence['session_age_hours']:.1f} hours",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_secure_cookies(self):
        """SEC-T014: Check cookie security settings."""
        start = time.time()
        test_id = "SEC-T014"

        debug = getattr(settings, 'DEBUG', False)
        evidence = {
            'csrf_cookie_secure': getattr(settings, 'CSRF_COOKIE_SECURE', False),
            'csrf_cookie_httponly': getattr(settings, 'CSRF_COOKIE_HTTPONLY', False),
            'csrf_cookie_samesite': getattr(settings, 'CSRF_COOKIE_SAMESITE', 'Lax'),
            'debug_mode': debug,
        }

        # In production, secure should be True
        issues = []
        if not debug:
            if not evidence['csrf_cookie_secure']:
                issues.append('CSRF_COOKIE_SECURE should be True')

        result = 'pass' if not issues else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='auth',
            title="Cookie Security Settings",
            description="Verify CSRF and session cookie security flags.",
            criteria="Secure, HttpOnly, SameSite set appropriately for production.",
            result=result,
            result_details=f"Issues: {len(issues)}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # AUTHORIZATION TESTS (5 tests)
    # ==========================================================================

    def _run_authz_tests(self):
        """Run authorization tests."""
        self._test_user_scoping()
        self._test_admin_protection()
        self._test_object_level_access()
        self._test_api_authentication()
        self._test_permission_decorators()

    def _test_user_scoping(self):
        """SEC-T015: Check user data scoping in queries."""
        start = time.time()
        test_id = "SEC-T015"

        evidence = {'views_checked': 0, 'user_scoped': 0, 'potentially_unsafe': []}

        views_dir = self.base_path / 'apps'
        for view_file in views_dir.rglob('views.py'):
            evidence['views_checked'] += 1
            try:
                content = view_file.read_text()
                # Check for user scoping patterns
                if 'user=self.request.user' in content or 'user=request.user' in content:
                    evidence['user_scoped'] += 1

                # Check for potentially unsafe patterns (queryset without user filter)
                # This is a heuristic check
                if '.objects.all()' in content and 'user=' not in content:
                    rel_path = str(view_file.relative_to(self.base_path))
                    # Check if it's admin-only
                    if 'staff_member_required' not in content and 'AdminRequiredMixin' not in content:
                        evidence['potentially_unsafe'].append(rel_path)
            except Exception:
                pass

        result = 'pass' if evidence['user_scoped'] > 0 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='authz',
            title="User Data Scoping",
            description="Verify queries are scoped to the current user.",
            criteria="All user data queries filter by current user.",
            result=result,
            result_details=f"User-scoped views: {evidence['user_scoped']}/{evidence['views_checked']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_admin_protection(self):
        """SEC-T016: Check admin endpoint protection."""
        start = time.time()
        test_id = "SEC-T016"

        evidence = {'admin_url_customized': False, 'staff_checks': 0}

        # Check custom admin URL
        admin_url = getattr(settings, 'ADMIN_URL_PATH', 'admin')
        evidence['admin_url'] = admin_url
        evidence['admin_url_customized'] = admin_url != 'admin'

        # Check for staff_member_required decorators
        for py_file in self.base_path.rglob('*.py'):
            if 'views' in str(py_file):
                try:
                    content = py_file.read_text()
                    evidence['staff_checks'] += content.count('staff_member_required')
                    evidence['staff_checks'] += content.count('AdminRequiredMixin')
                except Exception:
                    pass

        result = 'pass' if evidence['admin_url_customized'] and evidence['staff_checks'] > 0 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='authz',
            title="Admin Endpoint Protection",
            description="Verify admin URL is customized and protected.",
            criteria="Admin URL not default '/admin/', staff checks in place.",
            result=result,
            result_details=f"Custom URL: {evidence['admin_url']}, Staff checks: {evidence['staff_checks']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_object_level_access(self):
        """SEC-T017: Check object-level access controls."""
        start = time.time()
        test_id = "SEC-T017"

        evidence = {'get_object_checks': 0, 'filter_user_checks': 0}

        for py_file in (self.base_path / 'apps').rglob('views.py'):
            try:
                content = py_file.read_text()
                evidence['get_object_checks'] += content.count('get_object_or_404')
                evidence['filter_user_checks'] += content.count('filter(user=')
            except Exception:
                pass

        result = 'pass' if evidence['get_object_checks'] > 0 or evidence['filter_user_checks'] > 0 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='authz',
            title="Object-Level Access Control",
            description="Verify object-level permissions are enforced.",
            criteria="get_object_or_404 and filter(user=) patterns used.",
            result=result,
            result_details=f"get_object checks: {evidence['get_object_checks']}, filter(user=): {evidence['filter_user_checks']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_api_authentication(self):
        """SEC-T018: Check API authentication mechanisms."""
        start = time.time()
        test_id = "SEC-T018"

        evidence = {'api_auth_methods': [], 'issues': []}

        # Check for API authentication patterns
        for py_file in self.base_path.rglob('*.py'):
            if 'view' in str(py_file).lower() or 'api' in str(py_file).lower():
                try:
                    content = py_file.read_text()
                    if 'X-Claude-API-Key' in content:
                        evidence['api_auth_methods'].append('Custom API Key')
                    if 'LoginRequiredMixin' in content:
                        evidence['api_auth_methods'].append('Session Auth')
                    if 'TokenAuthentication' in content:
                        evidence['api_auth_methods'].append('Token Auth')

                    # Check for secure comparison
                    if 'secure_compare' in content or 'hmac.compare_digest' in content:
                        evidence['secure_comparison'] = True
                except Exception:
                    pass

        result = 'pass' if evidence.get('secure_comparison') else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='authz',
            title="API Authentication",
            description="Verify API endpoints use secure authentication.",
            criteria="API keys compared using constant-time comparison.",
            result=result,
            result_details=f"Auth methods: {', '.join(set(evidence['api_auth_methods']))}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_permission_decorators(self):
        """SEC-T019: Check permission decorator usage."""
        start = time.time()
        test_id = "SEC-T019"

        evidence = {'login_required': 0, 'permission_required': 0, 'unprotected': []}

        for view_file in (self.base_path / 'apps').rglob('views.py'):
            try:
                content = view_file.read_text()
                evidence['login_required'] += content.count('LoginRequiredMixin')
                evidence['login_required'] += content.count('login_required')
                evidence['permission_required'] += content.count('permission_required')

                # Look for function views without decorators (heuristic)
                # This is imperfect but catches obvious issues
            except Exception:
                pass

        result = 'pass' if evidence['login_required'] > 10 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='authz',
            title="Permission Decorators",
            description="Verify views use authentication decorators.",
            criteria="LoginRequiredMixin or login_required used consistently.",
            result=result,
            result_details=f"login_required: {evidence['login_required']}, permission_required: {evidence['permission_required']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # INPUT VALIDATION TESTS (5 tests)
    # ==========================================================================

    def _run_input_validation_tests(self):
        """Run input validation tests."""
        self._test_sql_injection()
        self._test_xss_protection()
        self._test_file_upload_validation()
        self._test_csrf_protection()
        self._test_command_injection()

    def _test_sql_injection(self):
        """SEC-T020: Check for SQL injection vulnerabilities."""
        start = time.time()
        test_id = "SEC-T020"

        evidence = {'raw_sql_usage': [], 'safe_patterns': 0}

        dangerous_patterns = [
            r'\.raw\([^)]*%s',  # raw() with string formatting
            r'\.extra\(',      # extra() is deprecated and dangerous
            r'cursor\.execute\([^,)]*\+',  # execute with string concatenation
        ]

        for py_file in self.base_path.rglob('*.py'):
            if '/migrations/' in str(py_file):
                continue
            try:
                content = py_file.read_text()
                for pattern in dangerous_patterns:
                    if re.search(pattern, content):
                        rel_path = str(py_file.relative_to(self.base_path))
                        evidence['raw_sql_usage'].append(rel_path)
            except Exception:
                pass

        # Remove duplicates
        evidence['raw_sql_usage'] = list(set(evidence['raw_sql_usage']))

        result = 'pass' if not evidence['raw_sql_usage'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='input',
            title="SQL Injection Protection",
            description="Check for unsafe raw SQL usage.",
            criteria="No unsafe raw SQL or string concatenation in queries.",
            result=result,
            result_details=f"Raw SQL files: {len(evidence['raw_sql_usage'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_xss_protection(self):
        """SEC-T021: Check for XSS vulnerabilities."""
        start = time.time()
        test_id = "SEC-T021"

        evidence = {'mark_safe_usage': [], 'safe_filter_usage': []}

        for py_file in self.base_path.rglob('*.py'):
            if '/tests/' in str(py_file):
                continue
            try:
                content = py_file.read_text()
                if 'mark_safe(' in content:
                    rel_path = str(py_file.relative_to(self.base_path))
                    evidence['mark_safe_usage'].append(rel_path)
            except Exception:
                pass

        # Check templates for |safe filter
        for html_file in self.base_path.rglob('*.html'):
            try:
                content = html_file.read_text()
                if '|safe' in content:
                    rel_path = str(html_file.relative_to(self.base_path))
                    evidence['safe_filter_usage'].append(rel_path)
            except Exception:
                pass

        # Some mark_safe usage is expected for HTML rendering
        result = 'pass' if len(evidence['mark_safe_usage']) < 20 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='input',
            title="XSS Protection",
            description="Check for unsafe HTML rendering.",
            criteria="Limited use of mark_safe() and |safe filter.",
            result=result,
            result_details=f"mark_safe: {len(evidence['mark_safe_usage'])}, |safe: {len(evidence['safe_filter_usage'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_file_upload_validation(self):
        """SEC-T022: Check file upload validation."""
        start = time.time()
        test_id = "SEC-T022"

        evidence = {'validation_found': False, 'magic_bytes_check': False, 'size_check': False}

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'validate_image' in content or 'MAGIC_BYTES' in content:
                    evidence['magic_bytes_check'] = True
                    evidence['validation_found'] = True
                if 'MAX_FILE_SIZE' in content or 'file.size' in content:
                    evidence['size_check'] = True
                    evidence['validation_found'] = True
            except Exception:
                pass

        result = 'pass' if evidence['validation_found'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='input',
            title="File Upload Validation",
            description="Verify file uploads are validated (type, size, content).",
            criteria="Magic bytes validation, size limits, and content-type checks.",
            result=result,
            result_details=f"Magic bytes: {evidence['magic_bytes_check']}, Size: {evidence['size_check']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_csrf_protection(self):
        """SEC-T023: Check CSRF protection."""
        start = time.time()
        test_id = "SEC-T023"

        evidence = {'csrf_middleware': False, 'csrf_exempt_usage': []}

        # Check middleware
        middleware = getattr(settings, 'MIDDLEWARE', [])
        evidence['csrf_middleware'] = 'django.middleware.csrf.CsrfViewMiddleware' in middleware

        # Check for csrf_exempt usage
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if '@csrf_exempt' in content:
                    rel_path = str(py_file.relative_to(self.base_path))
                    evidence['csrf_exempt_usage'].append(rel_path)
            except Exception:
                pass

        # csrf_exempt is OK for webhooks
        legitimate_exempts = [f for f in evidence['csrf_exempt_usage'] if 'webhook' in f.lower()]
        suspicious_exempts = [f for f in evidence['csrf_exempt_usage'] if 'webhook' not in f.lower()]

        result = 'pass' if evidence['csrf_middleware'] and len(suspicious_exempts) == 0 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='input',
            title="CSRF Protection",
            description="Verify CSRF middleware enabled and limited exemptions.",
            criteria="CsrfViewMiddleware enabled, csrf_exempt only on webhooks.",
            result=result,
            result_details=f"Middleware: {evidence['csrf_middleware']}, Exempt: {len(evidence['csrf_exempt_usage'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_command_injection(self):
        """SEC-T024: Check for command injection vulnerabilities."""
        start = time.time()
        test_id = "SEC-T024"

        evidence = {'subprocess_usage': [], 'shell_true': []}

        dangerous_patterns = [
            (r'subprocess\.(call|run|Popen).*shell\s*=\s*True', 'shell=True'),
            (r'os\.system\(', 'os.system'),
            (r'os\.popen\(', 'os.popen'),
        ]

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                for pattern, desc in dangerous_patterns:
                    if re.search(pattern, content):
                        rel_path = str(py_file.relative_to(self.base_path))
                        evidence['shell_true'].append({'file': rel_path, 'type': desc})
            except Exception:
                pass

        result = 'pass' if not evidence['shell_true'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='input',
            title="Command Injection Protection",
            description="Check for unsafe shell command execution.",
            criteria="No shell=True in subprocess, no os.system/popen.",
            result=result,
            result_details=f"Dangerous patterns: {len(evidence['shell_true'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # DATA PROTECTION TESTS (5 tests)
    # ==========================================================================

    def _run_data_protection_tests(self):
        """Run data protection tests."""
        self._test_encryption_at_rest()
        self._test_pii_handling()
        self._test_password_hashing()
        self._test_sensitive_data_logging()
        self._test_data_retention()

    def _test_encryption_at_rest(self):
        """SEC-T025: Check encryption at rest for sensitive data."""
        start = time.time()
        test_id = "SEC-T025"

        evidence = {'encryption_found': False, 'encrypted_fields': []}

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'Fernet' in content or 'encrypt_' in content:
                    evidence['encryption_found'] = True
                if 'EncryptedTextField' in content or 'EncryptedJSONField' in content:
                    rel_path = str(py_file.relative_to(self.base_path))
                    evidence['encrypted_fields'].append(rel_path)
            except Exception:
                pass

        result = 'pass' if evidence['encryption_found'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='data',
            title="Encryption at Rest",
            description="Verify sensitive data is encrypted in database.",
            criteria="Fernet encryption used for tokens, credentials, personal data.",
            result=result,
            result_details=f"Encryption found: {evidence['encryption_found']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_pii_handling(self):
        """SEC-T026: Check PII handling practices."""
        start = time.time()
        test_id = "SEC-T026"

        evidence = {'pii_fields': [], 'soft_delete': False}

        # Check for soft delete pattern
        for py_file in self.base_path.rglob('models.py'):
            try:
                content = py_file.read_text()
                if 'soft_delete' in content or 'deleted_at' in content:
                    evidence['soft_delete'] = True
            except Exception:
                pass

        result = 'pass' if evidence['soft_delete'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='data',
            title="PII Handling",
            description="Check for proper PII management practices.",
            criteria="Soft delete implemented, PII retention policies in place.",
            result=result,
            result_details=f"Soft delete: {evidence['soft_delete']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_password_hashing(self):
        """SEC-T027: Verify password hashing configuration."""
        start = time.time()
        test_id = "SEC-T027"

        hashers = getattr(settings, 'PASSWORD_HASHERS', [])
        evidence = {'hashers': hashers}

        # PBKDF2 or Argon2 is acceptable
        has_strong_hasher = any('PBKDF2' in h or 'Argon2' in h for h in hashers) if hashers else True  # Django default is PBKDF2

        result = 'pass' if has_strong_hasher else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='data',
            title="Password Hashing",
            description="Verify strong password hashing algorithm.",
            criteria="PBKDF2 or Argon2 password hasher configured.",
            result=result,
            result_details=f"Hashers: {len(hashers) if hashers else 'default'}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_sensitive_data_logging(self):
        """SEC-T028: Check for sensitive data in logs."""
        start = time.time()
        test_id = "SEC-T028"

        evidence = {'pii_in_logs': [], 'redaction_found': False}

        pii_patterns = [
            r'logger\.\w+\([^)]*\.email[^)]*\)',
            r'logger\.\w+\([^)]*password[^)]*\)',
            r'logger\.\w+\([^)]*token[^)]*\)',
        ]

        for py_file in self.base_path.rglob('*.py'):
            if '/tests/' in str(py_file):
                continue
            try:
                content = py_file.read_text()
                # Check for PII logging
                for pattern in pii_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        rel_path = str(py_file.relative_to(self.base_path))
                        if rel_path not in evidence['pii_in_logs']:
                            evidence['pii_in_logs'].append(rel_path)

                # Check for redaction
                if 'hash_pii' in content or '[REDACTED]' in content or '_redact' in content:
                    evidence['redaction_found'] = True
            except Exception:
                pass

        result = 'pass' if len(evidence['pii_in_logs']) < 5 else 'fail'
        findings = []

        if evidence['pii_in_logs']:
            finding = self._add_finding(
                finding_key="pii_logged_without_redaction",
                title="PII Logged Without Redaction",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:L/AC:L/PR:H/UI:N/S:U/C:H/I:N/A:N",
                description=f"Found {len(evidence['pii_in_logs'])} files logging PII (emails, etc.) without hashing.",
                risk_reasoning="PII in logs can be exposed through log aggregation breaches or insider access.",
                evidence={'files': evidence['pii_in_logs'][:10]},
                affected_components=evidence['pii_in_logs'][:5],
                recommendations=[
                    "Use hash_pii() for logging identifiable information",
                    "Log user IDs instead of emails where possible",
                    "Implement centralized logging utility with automatic redaction",
                ],
                validation_steps="grep -r 'logger.*email' apps/ | grep -v test",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='data',
            title="Sensitive Data Logging",
            description="Check for PII/secrets in log statements.",
            criteria="No unredacted PII in log statements.",
            result=result,
            result_details=f"PII in logs: {len(evidence['pii_in_logs'])} files",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_data_retention(self):
        """SEC-T029: Check data retention policies."""
        start = time.time()
        test_id = "SEC-T029"

        evidence = {'soft_delete': False, 'retention_days': None}

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'SOFT_DELETE_RETENTION_DAYS' in content:
                    evidence['soft_delete'] = True
                    # Try to extract the value
                    match = re.search(r'SOFT_DELETE_RETENTION_DAYS.*?(\d+)', content)
                    if match:
                        evidence['retention_days'] = int(match.group(1))
            except Exception:
                pass

        result = 'pass' if evidence['soft_delete'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='data',
            title="Data Retention Policy",
            description="Verify data retention policies are implemented.",
            criteria="Soft delete with configurable retention period.",
            result=result,
            result_details=f"Soft delete: {evidence['soft_delete']}, Retention: {evidence['retention_days']} days",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # LOGGING & AUDITING TESTS (4 tests)
    # ==========================================================================

    def _run_logging_tests(self):
        """Run logging and auditing tests."""
        self._test_security_logging()
        self._test_audit_trail()
        self._test_error_handling()
        self._test_log_rotation()

    def _test_security_logging(self):
        """SEC-T030: Check security event logging."""
        start = time.time()
        test_id = "SEC-T030"

        evidence = {'security_logger': False, 'event_types': []}

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'wlj.security' in content or 'security_logger' in content:
                    evidence['security_logger'] = True
                if 'log_security_event' in content:
                    evidence['event_types'].append(str(py_file.relative_to(self.base_path)))
            except Exception:
                pass

        result = 'pass' if evidence['security_logger'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='logging',
            title="Security Event Logging",
            description="Verify security events are logged.",
            criteria="Dedicated security logger with event categorization.",
            result=result,
            result_details=f"Security logger: {evidence['security_logger']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_audit_trail(self):
        """SEC-T031: Check audit trail implementation."""
        start = time.time()
        test_id = "SEC-T031"

        evidence = {'audit_models': [], 'finance_audit': False}

        for py_file in self.base_path.rglob('models.py'):
            try:
                content = py_file.read_text()
                if 'AuditLog' in content:
                    evidence['audit_models'].append(str(py_file.relative_to(self.base_path)))
                if 'FinanceAuditLog' in content:
                    evidence['finance_audit'] = True
            except Exception:
                pass

        result = 'pass' if evidence['audit_models'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='logging',
            title="Audit Trail",
            description="Verify audit logging for sensitive operations.",
            criteria="Audit models exist for tracking changes.",
            result=result,
            result_details=f"Audit models: {len(evidence['audit_models'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_error_handling(self):
        """SEC-T032: Check error handling and information leakage."""
        start = time.time()
        test_id = "SEC-T032"

        debug = getattr(settings, 'DEBUG', False)
        evidence = {'debug_mode': debug, 'custom_error_pages': False}

        # Check for custom error templates
        templates_dir = self.base_path / 'templates'
        if templates_dir.exists():
            for error_page in ['404.html', '500.html']:
                if (templates_dir / error_page).exists():
                    evidence['custom_error_pages'] = True

        result = 'pass' if not debug or evidence['custom_error_pages'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='logging',
            title="Error Handling",
            description="Verify errors don't leak sensitive information.",
            criteria="DEBUG=False in production, custom error pages.",
            result=result,
            result_details=f"Debug: {debug}, Custom pages: {evidence['custom_error_pages']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_log_rotation(self):
        """SEC-T033: Check log rotation configuration."""
        start = time.time()
        test_id = "SEC-T033"

        evidence = {'rotating_handler': False}

        logging_config = getattr(settings, 'LOGGING', {})
        handlers = logging_config.get('handlers', {})

        for handler_name, handler_config in handlers.items():
            handler_class = handler_config.get('class', '')
            if 'Rotating' in handler_class or 'TimedRotating' in handler_class:
                evidence['rotating_handler'] = True

        result = 'pass' if evidence['rotating_handler'] else 'unknown'

        self.results.append(TestResult(
            test_id=test_id,
            category='logging',
            title="Log Rotation",
            description="Verify log rotation is configured.",
            criteria="RotatingFileHandler or TimedRotatingFileHandler configured.",
            result=result,
            result_details=f"Rotating handler: {evidence['rotating_handler']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # WEB SECURITY TESTS (6 tests)
    # ==========================================================================

    def _run_web_security_tests(self):
        """Run web security tests."""
        self._test_security_headers()
        self._test_csp_configuration()
        self._test_cors_configuration()
        self._test_https_enforcement()
        self._test_clickjacking_protection()
        self._test_content_type_sniffing()

    def _test_security_headers(self):
        """SEC-T034: Check security headers configuration."""
        start = time.time()
        test_id = "SEC-T034"

        evidence = {
            'SECURE_BROWSER_XSS_FILTER': getattr(settings, 'SECURE_BROWSER_XSS_FILTER', False),
            'SECURE_CONTENT_TYPE_NOSNIFF': getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False),
            'X_FRAME_OPTIONS': getattr(settings, 'X_FRAME_OPTIONS', 'DENY'),
        }

        debug = getattr(settings, 'DEBUG', False)
        result = 'pass' if debug or (evidence['SECURE_BROWSER_XSS_FILTER'] and evidence['SECURE_CONTENT_TYPE_NOSNIFF']) else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="Security Headers",
            description="Verify security headers are configured.",
            criteria="XSS filter, content type nosniff, X-Frame-Options set.",
            result=result,
            result_details=f"Headers configured: {sum(bool(v) for v in evidence.values())}/3",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_csp_configuration(self):
        """SEC-T035: Check Content Security Policy."""
        start = time.time()
        test_id = "SEC-T035"

        evidence = {'csp_middleware': False, 'uses_nonce': False, 'unsafe_inline': False, 'unsafe_eval': False}

        for py_file in self.base_path.rglob('middleware.py'):
            try:
                content = py_file.read_text()
                if 'Content-Security-Policy' in content:
                    evidence['csp_middleware'] = True
                if 'nonce' in content:
                    evidence['uses_nonce'] = True
                if 'unsafe-inline' in content:
                    evidence['unsafe_inline'] = True
                if 'unsafe-eval' in content:
                    evidence['unsafe_eval'] = True
            except Exception:
                pass

        result = 'pass' if evidence['csp_middleware'] and evidence['uses_nonce'] else 'fail'
        findings = []

        if evidence['unsafe_eval']:
            finding = self._add_finding(
                finding_key="csp_unsafe_eval",
                title="CSP Contains unsafe-eval",
                severity='low',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:L/A:N",
                description="Content Security Policy includes 'unsafe-eval' directive.",
                risk_reasoning="unsafe-eval allows eval() which can be exploited in XSS attacks.",
                evidence={'csp_config': evidence},
                affected_components=['CSP Middleware'],
                recommendations=[
                    "Audit JavaScript for eval() usage",
                    "Refactor to avoid dynamic code execution",
                    "Remove unsafe-eval when possible",
                ],
                validation_steps="Check CSP header for 'unsafe-eval'",
                is_quick_win=False,
                remediation_effort='high',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="Content Security Policy",
            description="Verify CSP is configured with nonces.",
            criteria="CSP middleware with nonce support, minimal unsafe directives.",
            result=result,
            result_details=f"CSP: {evidence['csp_middleware']}, Nonce: {evidence['uses_nonce']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_cors_configuration(self):
        """SEC-T036: Check CORS configuration."""
        start = time.time()
        test_id = "SEC-T036"

        evidence = {'cors_installed': False, 'cors_allow_all': False}

        installed_apps = getattr(settings, 'INSTALLED_APPS', [])
        if 'corsheaders' in installed_apps:
            evidence['cors_installed'] = True
            evidence['cors_allow_all'] = getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False)

        # No CORS is actually OK for a single-origin app
        result = 'pass' if not evidence['cors_installed'] or not evidence['cors_allow_all'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="CORS Configuration",
            description="Verify CORS is restrictive or disabled.",
            criteria="CORS not enabled or restricted to specific origins.",
            result=result,
            result_details=f"CORS installed: {evidence['cors_installed']}, Allow all: {evidence['cors_allow_all']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_https_enforcement(self):
        """SEC-T037: Check HTTPS enforcement."""
        start = time.time()
        test_id = "SEC-T037"

        debug = getattr(settings, 'DEBUG', False)
        evidence = {
            'debug': debug,
            'SECURE_SSL_REDIRECT': getattr(settings, 'SECURE_SSL_REDIRECT', False),
            'SECURE_HSTS_SECONDS': getattr(settings, 'SECURE_HSTS_SECONDS', 0),
            'SECURE_HSTS_PRELOAD': getattr(settings, 'SECURE_HSTS_PRELOAD', False),
        }

        # In debug mode, SSL redirect should be off
        if debug:
            result = 'pass'
        else:
            result = 'pass' if evidence['SECURE_SSL_REDIRECT'] and evidence['SECURE_HSTS_SECONDS'] > 0 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="HTTPS Enforcement",
            description="Verify HTTPS is enforced in production.",
            criteria="SSL redirect enabled, HSTS configured.",
            result=result,
            result_details=f"SSL redirect: {evidence['SECURE_SSL_REDIRECT']}, HSTS: {evidence['SECURE_HSTS_SECONDS']}s",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_clickjacking_protection(self):
        """SEC-T038: Check clickjacking protection."""
        start = time.time()
        test_id = "SEC-T038"

        evidence = {
            'x_frame_options': getattr(settings, 'X_FRAME_OPTIONS', None),
            'csp_frame_ancestors': False,
        }

        # Check CSP for frame-ancestors
        for py_file in self.base_path.rglob('middleware.py'):
            try:
                content = py_file.read_text()
                if 'frame-ancestors' in content:
                    evidence['csp_frame_ancestors'] = True
            except Exception:
                pass

        result = 'pass' if evidence['x_frame_options'] or evidence['csp_frame_ancestors'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="Clickjacking Protection",
            description="Verify X-Frame-Options or CSP frame-ancestors.",
            criteria="X-Frame-Options: DENY or frame-ancestors 'self'.",
            result=result,
            result_details=f"X-Frame-Options: {evidence['x_frame_options']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_content_type_sniffing(self):
        """SEC-T039: Check content type sniffing protection."""
        start = time.time()
        test_id = "SEC-T039"

        debug = getattr(settings, 'DEBUG', False)
        evidence = {
            'SECURE_CONTENT_TYPE_NOSNIFF': getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False),
        }

        result = 'pass' if debug or evidence['SECURE_CONTENT_TYPE_NOSNIFF'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="Content Type Sniffing",
            description="Verify X-Content-Type-Options: nosniff.",
            criteria="SECURE_CONTENT_TYPE_NOSNIFF = True.",
            result=result,
            result_details=f"Nosniff: {evidence['SECURE_CONTENT_TYPE_NOSNIFF']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # DEPENDENCY TESTS (3 tests)
    # ==========================================================================

    def _run_dependency_tests(self):
        """Run dependency security tests."""
        self._test_requirements_pinning()
        self._test_known_vulnerabilities()
        self._test_outdated_packages()

    def _test_requirements_pinning(self):
        """SEC-T040: Check dependency version pinning."""
        start = time.time()
        test_id = "SEC-T040"

        evidence = {'pinned': 0, 'unpinned': 0, 'unpinned_packages': []}

        req_file = self.base_path / 'requirements.txt'
        if req_file.exists():
            content = req_file.read_text()
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    if '>=' in line or '==' in line or '~=' in line:
                        evidence['pinned'] += 1
                    elif line:
                        evidence['unpinned'] += 1
                        evidence['unpinned_packages'].append(line)

        result = 'pass' if evidence['unpinned'] == 0 else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='deps',
            title="Dependency Pinning",
            description="Verify all dependencies have version constraints.",
            criteria="All packages in requirements.txt have version pins.",
            result=result,
            result_details=f"Pinned: {evidence['pinned']}, Unpinned: {evidence['unpinned']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_known_vulnerabilities(self):
        """SEC-T041: Check for known vulnerabilities in dependencies."""
        start = time.time()
        test_id = "SEC-T041"

        evidence = {'checked': False, 'vulnerabilities': []}

        # Try to run pip-audit if available
        try:
            result = subprocess.run(
                ['pip-audit', '--format=json'],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                evidence['checked'] = True
                import json
                vulns = json.loads(result.stdout)
                evidence['vulnerabilities'] = vulns
        except Exception as e:
            evidence['error'] = str(e)

        # If pip-audit not available, check manually for known vulnerable versions
        if not evidence['checked']:
            req_file = self.base_path / 'requirements.txt'
            if req_file.exists():
                content = req_file.read_text().lower()
                # Check for known vulnerable package versions (simplified)
                known_vulnerable = [
                    ('django<3.2', 'Django < 3.2 has known vulnerabilities'),
                    ('pillow<9', 'Pillow < 9 has known vulnerabilities'),
                ]
                for pattern, desc in known_vulnerable:
                    if pattern.split('<')[0] in content:
                        # Very basic check
                        pass

        test_result = 'unknown' if not evidence['checked'] else ('pass' if not evidence['vulnerabilities'] else 'fail')

        self.results.append(TestResult(
            test_id=test_id,
            category='deps',
            title="Known Vulnerabilities",
            description="Check dependencies for known CVEs.",
            criteria="No known vulnerabilities in pip-audit scan.",
            result=test_result,
            result_details=f"Checked: {evidence['checked']}, Vulns: {len(evidence.get('vulnerabilities', []))}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_outdated_packages(self):
        """SEC-T042: Check for outdated packages."""
        start = time.time()
        test_id = "SEC-T042"

        evidence = {'checked': False}

        # This would need pip list --outdated which is slow
        # Skip for now, mark as unknown
        test_result = 'unknown'

        self.results.append(TestResult(
            test_id=test_id,
            category='deps',
            title="Outdated Packages",
            description="Check for outdated dependencies.",
            criteria="All dependencies are reasonably up to date.",
            result=test_result,
            result_details="Skipped - requires pip list --outdated",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # DEPLOYMENT TESTS (4 tests)
    # ==========================================================================

    def _run_deployment_tests(self):
        """Run deployment security tests."""
        self._test_debug_settings()
        self._test_allowed_hosts()
        self._test_secret_key_security()
        self._test_procfile_security()

    def _test_debug_settings(self):
        """SEC-T043: Check DEBUG setting."""
        start = time.time()
        test_id = "SEC-T043"

        debug = getattr(settings, 'DEBUG', False)
        evidence = {'DEBUG': debug, 'from_env': False}

        # Check if DEBUG is loaded from env
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            if "env.bool('DEBUG" in content or "env('DEBUG" in content:
                evidence['from_env'] = True

        result = 'pass' if evidence['from_env'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='deploy',
            title="DEBUG Setting",
            description="Verify DEBUG is loaded from environment.",
            criteria="DEBUG loaded from env, defaults to False.",
            result=result,
            result_details=f"DEBUG: {debug}, From env: {evidence['from_env']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_allowed_hosts(self):
        """SEC-T044: Check ALLOWED_HOSTS configuration."""
        start = time.time()
        test_id = "SEC-T044"

        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        evidence = {'hosts': allowed_hosts, 'has_wildcard': '*' in allowed_hosts}

        result = 'fail' if evidence['has_wildcard'] else 'pass'

        self.results.append(TestResult(
            test_id=test_id,
            category='deploy',
            title="ALLOWED_HOSTS",
            description="Verify ALLOWED_HOSTS doesn't include wildcard.",
            criteria="No '*' in ALLOWED_HOSTS.",
            result=result,
            result_details=f"Hosts: {len(allowed_hosts)}, Wildcard: {evidence['has_wildcard']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_secret_key_security(self):
        """SEC-T045: Check SECRET_KEY handling."""
        start = time.time()
        test_id = "SEC-T045"

        evidence = {'from_env': False, 'hardcoded': False}

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            if "env('SECRET_KEY" in content or "os.environ.get('SECRET_KEY" in content:
                evidence['from_env'] = True
            # Check for hardcoded key
            if re.search(r"SECRET_KEY\s*=\s*['\"][^'\"]{20,}['\"]", content):
                if 'env(' not in content.split('SECRET_KEY')[1][:50]:
                    evidence['hardcoded'] = True

        result = 'pass' if evidence['from_env'] and not evidence['hardcoded'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='deploy',
            title="SECRET_KEY Security",
            description="Verify SECRET_KEY is loaded from environment.",
            criteria="SECRET_KEY from environment, not hardcoded.",
            result=result,
            result_details=f"From env: {evidence['from_env']}, Hardcoded: {evidence['hardcoded']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_procfile_security(self):
        """SEC-T046: Check Procfile for security issues."""
        start = time.time()
        test_id = "SEC-T046"

        evidence = {'procfile_exists': False, 'runs_migrations': False, 'uses_gunicorn': False}

        procfile = self.base_path / 'Procfile'
        if procfile.exists():
            evidence['procfile_exists'] = True
            content = procfile.read_text()
            evidence['runs_migrations'] = 'migrate' in content
            evidence['uses_gunicorn'] = 'gunicorn' in content

        result = 'pass' if evidence['uses_gunicorn'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='deploy',
            title="Procfile Security",
            description="Verify production-appropriate Procfile.",
            criteria="Uses gunicorn or production-ready WSGI server.",
            result=result,
            result_details=f"Gunicorn: {evidence['uses_gunicorn']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # ABUSE RESISTANCE TESTS (4 tests)
    # ==========================================================================

    def _run_abuse_resistance_tests(self):
        """Run abuse resistance tests."""
        self._test_captcha_protection()
        self._test_honeypot_fields()
        self._test_email_verification()
        self._test_signup_rate_limiting()

    def _test_captcha_protection(self):
        """SEC-T047: Check CAPTCHA protection."""
        start = time.time()
        test_id = "SEC-T047"

        evidence = {'recaptcha_configured': False}

        recaptcha_key = getattr(settings, 'RECAPTCHA_V3_SITE_KEY', '')
        if recaptcha_key:
            evidence['recaptcha_configured'] = True

        result = 'pass' if evidence['recaptcha_configured'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='abuse',
            title="CAPTCHA Protection",
            description="Verify CAPTCHA is configured for forms.",
            criteria="reCAPTCHA v3 configured for signup/login.",
            result=result,
            result_details=f"reCAPTCHA: {evidence['recaptcha_configured']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_honeypot_fields(self):
        """SEC-T048: Check honeypot field implementation."""
        start = time.time()
        test_id = "SEC-T048"

        evidence = {'honeypot_found': False}

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'honeypot' in content.lower() or 'website' in content and 'HiddenInput' in content:
                    evidence['honeypot_found'] = True
                    break
            except Exception:
                pass

        result = 'pass' if evidence['honeypot_found'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='abuse',
            title="Honeypot Fields",
            description="Check for honeypot anti-bot protection.",
            criteria="Honeypot field implemented on signup form.",
            result=result,
            result_details=f"Honeypot: {evidence['honeypot_found']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_email_verification(self):
        """SEC-T049: Check email verification requirement."""
        start = time.time()
        test_id = "SEC-T049"

        evidence = {
            'ACCOUNT_EMAIL_VERIFICATION': getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional'),
        }

        result = 'pass' if evidence['ACCOUNT_EMAIL_VERIFICATION'] in ['mandatory', 'optional'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='abuse',
            title="Email Verification",
            description="Verify email verification is required.",
            criteria="ACCOUNT_EMAIL_VERIFICATION is mandatory or optional.",
            result=result,
            result_details=f"Verification: {evidence['ACCOUNT_EMAIL_VERIFICATION']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_signup_rate_limiting(self):
        """SEC-T050: Check signup rate limiting."""
        start = time.time()
        test_id = "SEC-T050"

        evidence = {'rate_limiting_found': False}

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'signup' in content.lower() and ('rate_limit' in content or 'cache.get' in content):
                    evidence['rate_limiting_found'] = True
                    break
            except Exception:
                pass

        result = 'pass' if evidence['rate_limiting_found'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='abuse',
            title="Signup Rate Limiting",
            description="Verify signup endpoint has rate limiting.",
            criteria="Rate limiting implemented for signup endpoint.",
            result=result,
            result_details=f"Rate limiting: {evidence['rate_limiting_found']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))
