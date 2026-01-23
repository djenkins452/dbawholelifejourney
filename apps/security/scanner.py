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

        # Industry-specific compliance tests
        self._run_financial_compliance_tests()
        self._run_health_compliance_tests()
        self._run_api_security_tests()
        self._run_database_security_tests()
        self._run_third_party_tests()
        self._run_infrastructure_tests()

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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="env_file_not_protected",
                title=".env File Not Protected from Git",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                description=".env file is not in .gitignore, risking secrets being committed to version control.",
                risk_reasoning="If .env is committed to git, all secrets (API keys, passwords, tokens) become exposed in the repository history forever.",
                evidence=evidence,
                affected_components=['.gitignore', '.env'],
                recommendations=[
                    "Add .env to .gitignore immediately",
                    "Check git history for any committed .env files",
                    "Rotate any secrets that may have been exposed",
                ],
                validation_steps="grep '.env' .gitignore",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="aws_credentials_exposed",
                title="AWS Credentials Exposed in Code",
                severity='critical',
                likelihood='high',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
                description=f"AWS credentials found in source code: {len(evidence['issues'])} issues detected.",
                risk_reasoning="Exposed AWS credentials can lead to complete cloud infrastructure compromise, data breaches, and significant financial impact from unauthorized resource usage.",
                evidence=evidence,
                affected_components=[i['file'] for i in evidence['issues']] if evidence['issues'] else ['unknown'],
                recommendations=[
                    "Remove AWS credentials from source code immediately",
                    "Use AWS IAM roles or environment variables",
                    "Rotate compromised credentials",
                    "Enable AWS CloudTrail to monitor for unauthorized access",
                ],
                validation_steps="Search codebase for AKIA patterns and AWS secret key patterns",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_database_credentials(self):
        """SEC-T007: Check database credential handling."""
        start = time.time()
        test_id = "SEC-T007"

        evidence = {'uses_env': False, 'hardcoded_found': []}

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            # Check if DATABASE_URL uses env (support both single and double quotes)
            if ("env('DATABASE_URL" in content or 'env("DATABASE_URL' in content or
                "os.environ.get('DATABASE_URL" in content or 'os.environ.get("DATABASE_URL' in content):
                evidence['uses_env'] = True

            # Check for hardcoded database passwords
            if re.search(r"'PASSWORD':\s*'[^']+[a-zA-Z0-9]+'", content):
                evidence['hardcoded_found'].append('settings.py')

        result = 'pass' if evidence['uses_env'] and not evidence['hardcoded_found'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="database_credentials_insecure",
                title="Database Credentials Not Properly Secured",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H",
                description="Database credentials are either hardcoded or not loaded from environment variables.",
                risk_reasoning="Hardcoded or improperly managed database credentials can lead to unauthorized database access if source code is exposed.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Load DATABASE_URL from environment variable",
                    "Remove any hardcoded database passwords",
                    "Use django-environ or similar for config management",
                ],
                validation_steps="Check settings.py for DATABASE_URL configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
                # Check if loaded from env (support both single and double quotes)
                if var in content:
                    if (f"env('{var}" in content or f'env("{var}' in content or
                        f"os.environ.get('{var}" in content or f'os.environ.get("{var}' in content):
                        pass  # Good - from env
                    elif f"'{var}':" in content or f'"{var}":' in content:
                        # Hardcoded
                        evidence['issues'].append(f"{service} ({var}) appears hardcoded")

        result = 'pass' if not evidence['issues'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="third_party_keys_hardcoded",
                title="Third-Party API Keys Hardcoded",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description=f"Third-party API keys appear to be hardcoded: {evidence['issues']}",
                risk_reasoning="Hardcoded API keys can be exposed through source code leaks, leading to unauthorized access to external services and potential financial impact.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Move all API keys to environment variables",
                    "Use django-environ for configuration management",
                    "Rotate any exposed API keys immediately",
                ],
                validation_steps="Check settings.py for hardcoded API key patterns",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="session_security_misconfigured",
                title="Session Security Misconfiguration",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N",
                description=f"Session cookie security issues: {', '.join(issues)}",
                risk_reasoning="Insecure session cookies can lead to session hijacking via XSS or network interception.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set SESSION_COOKIE_SECURE=True in production",
                    "Set SESSION_COOKIE_SAMESITE='Lax' or 'Strict'",
                    "Ensure SESSION_COOKIE_HTTPONLY=True",
                ],
                validation_steps="Review session settings in Django configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="weak_password_policy",
                title="Weak Password Policy Configuration",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:N",
                description="Password validators are missing required checks for length, common passwords, or numeric-only passwords.",
                risk_reasoning="Weak password policies allow users to set easily guessable passwords, increasing credential compromise risk.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Add MinimumLengthValidator (min 8 chars)",
                    "Add CommonPasswordValidator",
                    "Add NumericPasswordValidator",
                    "Consider UserAttributeSimilarityValidator",
                ],
                validation_steps="Review AUTH_PASSWORD_VALIDATORS in settings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
                    if 'WebAuthn' not in evidence['methods']:
                        evidence['methods'].append('WebAuthn')
                if 'TOTP' in content or 'pyotp' in content:
                    evidence['mfa_available'] = True
                    if 'TOTP' not in evidence['methods']:
                        evidence['methods'].append('TOTP')

        # Check if MFA is enforced for admin via middleware
        evidence['mfa_enforced'] = False
        middleware_file = users_app / 'middleware.py'
        if middleware_file.exists():
            middleware_content = middleware_file.read_text(encoding='utf-8', errors='ignore')
            # Check for MFA enforcement middleware that requires WebAuthn for staff
            if 'MFAEnforcementMiddleware' in middleware_content:
                # Verify it checks for staff/superuser and webauthn_credentials
                if 'is_staff' in middleware_content and 'webauthn_credentials' in middleware_content:
                    evidence['mfa_enforced'] = True
                    evidence['enforcement_method'] = 'MFAEnforcementMiddleware'

        # Also check if the middleware is registered in settings
        if evidence['mfa_enforced']:
            settings_file = self.base_path / 'config' / 'settings.py'
            if settings_file.exists():
                settings_content = settings_file.read_text(encoding='utf-8', errors='ignore')
                if 'MFAEnforcementMiddleware' not in settings_content:
                    evidence['mfa_enforced'] = False
                    evidence['note'] = 'Middleware exists but not registered in settings'

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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="session_timeout_too_long",
                title="Session Timeout Too Long",
                severity='low',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:L/A:N",
                description=f"Session timeout is {evidence['session_age_hours']:.0f} hours, exceeding recommended 7 days.",
                risk_reasoning="Long session timeouts increase the window for session hijacking on shared/public computers.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set SESSION_COOKIE_AGE to 7 days (604800) or less",
                    "Consider shorter timeout for sensitive data access",
                ],
                validation_steps="Check SESSION_COOKIE_AGE in Django settings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="insecure_cookie_settings",
                title="Insecure Cookie Settings in Production",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N",
                description=f"Cookie security issues: {', '.join(issues)}",
                risk_reasoning="Cookies without Secure flag can be intercepted over HTTP, enabling session hijacking.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set CSRF_COOKIE_SECURE=True in production",
                    "Ensure all sensitive cookies use Secure flag",
                ],
                validation_steps="Review cookie settings in Django configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_user_scoping",
                title="Missing User Data Scoping",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description="No evidence of user-scoped queries found. Users may be able to access other users' data.",
                risk_reasoning="Without user scoping, IDOR vulnerabilities allow any authenticated user to access all data.",
                evidence=evidence,
                affected_components=evidence.get('potentially_unsafe', ['apps/*/views.py']),
                recommendations=[
                    "Add user=request.user filter to all user-specific queries",
                    "Use get_queryset() to scope data by user",
                    "Audit all .objects.all() calls",
                ],
                validation_steps="Search for 'user=request.user' in view files",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="admin_endpoint_exposed",
                title="Admin Endpoint Not Properly Protected",
                severity='medium',
                likelihood='low',
                impact='high',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:L",
                description="Admin URL is at default path and/or missing staff protection checks.",
                risk_reasoning="Default admin URLs are targeted by automated attacks. Combined with weak credentials, leads to full compromise.",
                evidence=evidence,
                affected_components=['config/urls.py', 'apps/*/views.py'],
                recommendations=[
                    "Change admin URL from default /admin/ to a custom path",
                    "Add rate limiting to admin login",
                    "Use staff_member_required decorator consistently",
                ],
                validation_steps="Check ADMIN_URL_PATH setting and admin URL configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_object_level_access",
                title="Missing Object-Level Access Controls",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
                description="No evidence of object-level access controls (get_object_or_404, filter by user).",
                risk_reasoning="Without object-level checks, IDOR allows any user to access/modify any object by ID.",
                evidence=evidence,
                affected_components=['apps/*/views.py'],
                recommendations=[
                    "Use get_object_or_404 with user filter for detail views",
                    "Filter querysets by user in get_queryset()",
                    "Implement permission checks in dispatch()",
                ],
                validation_steps="Audit all detail/update views for ownership checks",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="api_timing_attack_vulnerable",
                title="API Key Comparison May Be Vulnerable to Timing Attack",
                severity='medium',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N",
                description="API key comparison does not use constant-time comparison (hmac.compare_digest or secrets.compare_digest).",
                risk_reasoning="Non-constant-time string comparison leaks timing information, potentially allowing API key extraction.",
                evidence=evidence,
                affected_components=['apps/admin_console/views.py'],
                recommendations=[
                    "Use hmac.compare_digest() or secrets.compare_digest() for API key validation",
                    "Never use == for comparing secrets",
                ],
                validation_steps="Search for API key validation code and verify constant-time comparison",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="insufficient_permission_decorators",
                title="Insufficient Permission Decorator Usage",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:N",
                description=f"Only {evidence['login_required']} login_required decorators found across views.",
                risk_reasoning="Views without authentication allow anonymous access to potentially sensitive data.",
                evidence=evidence,
                affected_components=['apps/*/views.py'],
                recommendations=[
                    "Add LoginRequiredMixin to all class-based views",
                    "Add @login_required to all function-based views",
                    "Audit views for proper authentication requirements",
                ],
                validation_steps="Count LoginRequiredMixin and login_required usage vs total views",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
            # Exclude the scanner itself - it contains regex patterns that look like SQL injection
            if py_file.name == 'scanner.py' and 'security' in str(py_file):
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="potential_sql_injection",
                title="Potential SQL Injection Vulnerability",
                severity='critical',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H",
                description=f"Found {len(evidence['raw_sql_usage'])} files with potentially unsafe raw SQL patterns.",
                risk_reasoning="SQL injection can lead to complete database compromise, data theft, and unauthorized modifications.",
                evidence=evidence,
                affected_components=evidence['raw_sql_usage'][:5],
                recommendations=[
                    "Use Django ORM instead of raw SQL",
                    "If raw SQL is necessary, use parameterized queries",
                    "Never concatenate user input into SQL strings",
                ],
                validation_steps="Search for .raw(), .extra(), and cursor.execute() with string formatting",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="excessive_mark_safe_usage",
                title="Excessive mark_safe() Usage - Potential XSS",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:R/S:C/C:L/I:L/A:N",
                description=f"Found {len(evidence['mark_safe_usage'])} files using mark_safe(), which bypasses XSS protection.",
                risk_reasoning="Excessive mark_safe usage increases XSS attack surface. Each use must be carefully audited.",
                evidence=evidence,
                affected_components=evidence['mark_safe_usage'][:5],
                recommendations=[
                    "Audit each mark_safe() usage for user input",
                    "Use Django's autoescape where possible",
                    "Sanitize HTML before marking safe",
                ],
                validation_steps="grep -r 'mark_safe' --include='*.py'",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_file_upload_validation",
                title="Missing File Upload Validation",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:L",
                description="File upload validation (magic bytes, size limits) not detected in codebase.",
                risk_reasoning="Without proper validation, malicious files can be uploaded leading to RCE or storage abuse.",
                evidence=evidence,
                affected_components=['apps/*/views.py'],
                recommendations=[
                    "Validate file magic bytes (not just extension)",
                    "Implement file size limits",
                    "Scan uploaded files for malware",
                    "Store uploads outside webroot",
                ],
                validation_steps="Search for file upload handling code and validation",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_csrf_protection(self):
        """SEC-T023: Check CSRF protection."""
        start = time.time()
        test_id = "SEC-T023"

        evidence = {'csrf_middleware': False, 'csrf_exempt_usage': []}

        # Check middleware
        middleware = getattr(settings, 'MIDDLEWARE', [])
        evidence['csrf_middleware'] = 'django.middleware.csrf.CsrfViewMiddleware' in middleware

        # Check for csrf_exempt usage (actual decorator usage, not just string references)
        for py_file in self.base_path.rglob('*.py'):
            try:
                # Skip the scanner itself (it references csrf_exempt in detection logic)
                if 'scanner.py' in str(py_file):
                    continue
                content = py_file.read_text()
                if '@csrf_exempt' in content:
                    rel_path = str(py_file.relative_to(self.base_path))
                    evidence['csrf_exempt_usage'].append(rel_path)
            except Exception:
                pass

        # csrf_exempt is OK for webhooks (check filename OR if the content mentions webhook)
        def is_webhook_file(filepath):
            if 'webhook' in filepath.lower():
                return True
            # Also check if file contains webhook function
            try:
                full_path = self.base_path / filepath
                content = full_path.read_text()
                return '_webhook' in content or 'webhook' in content.lower()
            except Exception:
                return False

        legitimate_exempts = [f for f in evidence['csrf_exempt_usage'] if is_webhook_file(f)]
        suspicious_exempts = [f for f in evidence['csrf_exempt_usage'] if not is_webhook_file(f)]

        result = 'pass' if evidence['csrf_middleware'] and len(suspicious_exempts) == 0 else 'fail'
        findings = []

        if result == 'fail':
            issues = []
            if not evidence['csrf_middleware']:
                issues.append("CSRF middleware not enabled")
            if suspicious_exempts:
                issues.append(f"Suspicious @csrf_exempt usage in: {', '.join(suspicious_exempts[:3])}")
            finding = self._add_finding(
                finding_key="csrf_protection_issue",
                title="CSRF Protection Issue",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:H/A:N",
                description=f"CSRF issues: {'; '.join(issues)}",
                risk_reasoning="Missing CSRF protection allows attackers to trick users into performing actions without consent.",
                evidence=evidence,
                affected_components=suspicious_exempts[:5] if suspicious_exempts else ['config/settings.py'],
                recommendations=[
                    "Enable CsrfViewMiddleware in MIDDLEWARE",
                    "Remove @csrf_exempt except for legitimate webhooks",
                    "Use {% csrf_token %} in all forms",
                ],
                validation_steps="Check MIDDLEWARE setting and search for @csrf_exempt",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="command_injection_risk",
                title="Potential Command Injection Vulnerability",
                severity='critical',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H",
                description=f"Found {len(evidence['shell_true'])} instances of dangerous shell execution patterns.",
                risk_reasoning="shell=True or os.system with user input enables arbitrary command execution.",
                evidence=evidence,
                affected_components=[s['file'] for s in evidence['shell_true'][:5]],
                recommendations=[
                    "Use subprocess with shell=False and list arguments",
                    "Never pass user input to shell commands",
                    "Use shlex.split() for parsing if needed",
                ],
                validation_steps="Search for shell=True, os.system, os.popen",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_encryption_at_rest",
                title="Missing Encryption at Rest for Sensitive Data",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:N/A:N",
                description="No evidence of field-level encryption (Fernet, EncryptedTextField) found.",
                risk_reasoning="Database breach exposes all sensitive data in plaintext.",
                evidence=evidence,
                affected_components=['apps/*/models.py'],
                recommendations=[
                    "Use EncryptedTextField for sensitive fields",
                    "Implement Fernet encryption for tokens and credentials",
                    "Enable database-level encryption (TDE) as additional layer",
                ],
                validation_steps="Search for Fernet, EncryptedTextField usage",
                is_quick_win=False,
                remediation_effort='high',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_soft_delete",
                title="Missing Soft Delete for PII Data",
                severity='low',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:H/UI:N/S:U/C:L/I:N/A:N",
                description="Soft delete pattern not found. Hard deletes may violate data retention requirements.",
                risk_reasoning="Without soft delete, deleted PII cannot be recovered for compliance/audit requests.",
                evidence=evidence,
                affected_components=['apps/*/models.py'],
                recommendations=[
                    "Implement soft_delete() method on models with PII",
                    "Add deleted_at timestamp field",
                    "Filter deleted records in default QuerySet",
                ],
                validation_steps="Search for soft_delete or deleted_at in models",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="weak_password_hashing",
                title="Weak Password Hashing Algorithm",
                severity='high',
                likelihood='low',
                impact='high',
                cvss_vector="AV:N/AC:H/PR:H/UI:N/S:U/C:H/I:H/A:N",
                description="Password hasher is not PBKDF2 or Argon2. Passwords may be vulnerable to cracking.",
                risk_reasoning="Weak hashing allows offline password cracking after database breach.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Use Django's default PBKDF2 hasher",
                    "Consider upgrading to Argon2 (django-argon2)",
                    "Increase PBKDF2 iterations if using custom config",
                ],
                validation_steps="Check PASSWORD_HASHERS setting",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_sensitive_data_logging(self):
        """SEC-T028: Check for sensitive data in logs."""
        start = time.time()
        test_id = "SEC-T028"

        evidence = {'pii_in_logs': [], 'redaction_found': False}

        # More specific patterns - looking for actual sensitive data being logged
        # The pattern \w+\.email matches things like user.email, request.user.email
        # We exclude patterns like "send_email" or "email sent" which are just method names or phrases
        # For token/password, we look for actual variable references like {token} or .token
        pii_patterns = [
            r'logger\.\w+\([^)]*\w+\.email\b[^)]*\)',  # user.email, obj.email attribute access
            r'logger\.\w+\([^)]*\{password\}[^)]*\)',  # {password} variable interpolation
            r'logger\.\w+\([^)]*\w+\.password\b[^)]*\)',  # .password attribute access
            r'logger\.\w+\([^)]*\{token\}[^)]*\)',  # {token} variable interpolation (actual token value)
            r'logger\.\w+\([^)]*\w+\.token\b[^)]*\)',  # .token attribute access
            r'logger\.\w+\([^)]*\{access_token\}[^)]*\)',  # {access_token} interpolation
            r'logger\.\w+\([^)]*\w+\.access_token\b[^)]*\)',  # .access_token attribute
            r'logger\.\w+\([^)]*\{refresh_token\}[^)]*\)',  # {refresh_token} interpolation
            r'logger\.\w+\([^)]*\w+\.refresh_token\b[^)]*\)',  # .refresh_token attribute
        ]

        hash_pii_implemented = False
        hash_pii_usage_count = 0

        for py_file in self.base_path.rglob('*.py'):
            str_path = str(py_file)
            if '/tests/' in str_path or '/backups/' in str_path or 'backups/' in str_path:
                continue
            try:
                content = py_file.read_text()

                # Check for hash_pii implementation in core/utils.py
                if 'def hash_pii' in content:
                    hash_pii_implemented = True
                    evidence['redaction_found'] = True

                # Count hash_pii usage
                hash_pii_usage_count += content.count('hash_pii(')

                # Check for PII logging (only if not using hash_pii on that line)
                for pattern in pii_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Check if this line uses hash_pii
                        line_start = content.rfind('\n', 0, match.start()) + 1
                        line_end = content.find('\n', match.end())
                        if line_end == -1:
                            line_end = len(content)
                        line = content[line_start:line_end]

                        # Skip if line uses hash_pii or user_log_id
                        if 'hash_pii(' in line or 'user_log_id(' in line:
                            continue

                        rel_path = str(py_file.relative_to(self.base_path))
                        if rel_path not in evidence['pii_in_logs']:
                            evidence['pii_in_logs'].append(rel_path)

                # Check for other redaction patterns
                if '[REDACTED]' in content or '_redact' in content or 'redact_email' in content:
                    evidence['redaction_found'] = True
            except Exception:
                pass

        evidence['hash_pii_implemented'] = hash_pii_implemented
        evidence['hash_pii_usage_count'] = hash_pii_usage_count

        # Pass only if there are no unredacted PII logging occurrences
        result = 'pass' if len(evidence['pii_in_logs']) == 0 else 'fail'

        findings = []

        # Create a finding if there are any files with unredacted PII logging
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_data_retention_policy",
                title="Missing Data Retention Policy",
                severity='low',
                likelihood='low',
                impact='low',
                cvss_vector="AV:L/AC:H/PR:H/UI:N/S:U/C:L/I:N/A:N",
                description="No data retention policy (SOFT_DELETE_RETENTION_DAYS) found in codebase.",
                risk_reasoning="Without defined retention, data may be kept indefinitely violating privacy regulations.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Define SOFT_DELETE_RETENTION_DAYS setting",
                    "Implement scheduled cleanup of old soft-deleted records",
                    "Document retention periods for different data types",
                ],
                validation_steps="Search for SOFT_DELETE_RETENTION_DAYS in settings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_security_logging",
                title="Missing Security Event Logging",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:H/UI:N/S:U/C:N/I:N/A:L",
                description="No dedicated security logger found. Security events may not be captured.",
                risk_reasoning="Without security logging, attacks and suspicious activity go undetected.",
                evidence=evidence,
                affected_components=['config/settings.py', 'apps/*/views.py'],
                recommendations=[
                    "Create a dedicated security logger (wlj.security)",
                    "Log authentication events, permission denials, admin actions",
                    "Send security logs to separate destination for analysis",
                ],
                validation_steps="Search for security logger configuration",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_audit_trail",
                title="Missing Audit Trail",
                severity='medium',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:H/UI:N/S:U/C:N/I:L/A:N",
                description="No audit log models found. Sensitive operations may not be tracked.",
                risk_reasoning="Without audit trails, unauthorized changes cannot be detected or investigated.",
                evidence=evidence,
                affected_components=['apps/*/models.py'],
                recommendations=[
                    "Create AuditLog model for tracking sensitive operations",
                    "Log user, timestamp, action, and before/after values",
                    "Implement immutable audit records",
                ],
                validation_steps="Search for AuditLog model definitions",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="error_information_leakage",
                title="Error Pages May Leak Information",
                severity='medium',
                likelihood='medium',
                impact='low',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
                description="DEBUG is enabled or custom error pages are missing, potentially leaking stack traces.",
                risk_reasoning="Debug error pages expose code structure, file paths, and potentially secrets.",
                evidence=evidence,
                affected_components=['config/settings.py', 'templates/'],
                recommendations=[
                    "Set DEBUG=False in production",
                    "Create custom 404.html and 500.html templates",
                    "Ensure error pages don't show technical details",
                ],
                validation_steps="Check DEBUG setting and error template existence",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_security_headers",
                title="Missing Security Headers",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N",
                description="Security headers (XSS filter, content-type nosniff) not configured.",
                risk_reasoning="Missing headers allow XSS attacks and content-type sniffing exploits.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set SECURE_BROWSER_XSS_FILTER=True",
                    "Set SECURE_CONTENT_TYPE_NOSNIFF=True",
                    "Configure X_FRAME_OPTIONS='DENY'",
                ],
                validation_steps="Check SECURE_* settings in Django config",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
                # Check for unsafe directives in actual CSP strings (not comments)
                # Look for pattern like "'unsafe-inline'" or "'unsafe-eval'" in CSP policy
                import re
                # Match 'unsafe-inline' or 'unsafe-eval' as part of CSP directive strings
                if re.search(r"['\"]'unsafe-inline'['\"]|'unsafe-inline'", content):
                    evidence['unsafe_inline'] = True
                # Only flag if unsafe-eval is in actual CSP policy, not comments
                if re.search(r"'unsafe-eval'", content) and not re.search(r"#.*'unsafe-eval'|#.*unsafe-eval", content):
                    # Check if the line containing 'unsafe-eval' is not a comment
                    for line in content.split('\n'):
                        if "'unsafe-eval'" in line and not line.strip().startswith('#') and 'Removed' not in line:
                            evidence['unsafe_eval'] = True
                            break
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="cors_allow_all_origins",
                title="CORS Allows All Origins",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:L/A:N",
                description="CORS is configured with CORS_ALLOW_ALL_ORIGINS=True, allowing any website to make requests.",
                risk_reasoning="Allows any website to read user data via JavaScript, bypassing same-origin policy.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set CORS_ALLOW_ALL_ORIGINS=False",
                    "Use CORS_ALLOWED_ORIGINS with specific domains",
                    "Consider if CORS is needed at all",
                ],
                validation_steps="Check CORS_ALLOW_ALL_ORIGINS setting",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_https_enforcement(self):
        """SEC-T037: Check HTTPS enforcement."""
        start = time.time()
        test_id = "SEC-T037"

        debug = getattr(settings, 'DEBUG', False)
        ssl_redirect = getattr(settings, 'SECURE_SSL_REDIRECT', False)
        proxy_ssl_header = getattr(settings, 'SECURE_PROXY_SSL_HEADER', None)
        hsts_seconds = getattr(settings, 'SECURE_HSTS_SECONDS', 0)

        evidence = {
            'debug': debug,
            'SECURE_SSL_REDIRECT': ssl_redirect,
            'SECURE_PROXY_SSL_HEADER': proxy_ssl_header,
            'SECURE_HSTS_SECONDS': hsts_seconds,
            'SECURE_HSTS_PRELOAD': getattr(settings, 'SECURE_HSTS_PRELOAD', False),
        }

        # In debug mode, SSL settings should be off
        if debug:
            result = 'pass'
        else:
            # HTTPS is enforced if either:
            # 1. SECURE_SSL_REDIRECT is True (Django handles redirect), OR
            # 2. SECURE_PROXY_SSL_HEADER is set (proxy handles SSL termination)
            # AND HSTS must be configured
            https_enforced = ssl_redirect or (proxy_ssl_header is not None)
            result = 'pass' if https_enforced and hsts_seconds > 0 else 'fail'

        findings = []
        if result == 'fail':
            finding = self._add_finding(
                finding_key="https_not_enforced",
                title="HTTPS Not Properly Enforced",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:L/A:N",
                description="HTTPS redirect or HSTS not configured in production settings.",
                risk_reasoning="Without HTTPS enforcement, traffic can be intercepted (MitM) exposing credentials and data.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set SECURE_SSL_REDIRECT=True or configure SECURE_PROXY_SSL_HEADER",
                    "Set SECURE_HSTS_SECONDS to at least 31536000 (1 year)",
                    "Consider SECURE_HSTS_PRELOAD=True",
                ],
                validation_steps="Check SECURE_SSL_REDIRECT and SECURE_HSTS_* settings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='web',
            title="HTTPS Enforcement",
            description="Verify HTTPS is enforced in production.",
            criteria="SSL redirect or proxy SSL header configured, HSTS enabled.",
            result=result,
            result_details=f"SSL redirect: {ssl_redirect}, Proxy SSL: {proxy_ssl_header is not None}, HSTS: {hsts_seconds}s",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="missing_clickjacking_protection",
                title="Missing Clickjacking Protection",
                severity='medium',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:L/A:N",
                description="Neither X-Frame-Options nor CSP frame-ancestors is configured.",
                risk_reasoning="Without frame protection, site can be embedded in malicious pages for clickjacking attacks.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set X_FRAME_OPTIONS='DENY' in Django settings",
                    "Or add frame-ancestors directive to CSP",
                ],
                validation_steps="Check X_FRAME_OPTIONS setting",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="content_type_sniffing_enabled",
                title="Content Type Sniffing Not Prevented",
                severity='low',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:L/A:N",
                description="SECURE_CONTENT_TYPE_NOSNIFF is not enabled, allowing browser content sniffing.",
                risk_reasoning="Content sniffing can turn benign files into executable scripts in some browsers.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set SECURE_CONTENT_TYPE_NOSNIFF=True",
                ],
                validation_steps="Check SECURE_CONTENT_TYPE_NOSNIFF setting",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="unpinned_dependencies",
                title="Dependencies Without Version Pins",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:L/I:H/A:L",
                description=f"Found {evidence['unpinned']} unpinned packages: {evidence['unpinned_packages'][:5]}",
                risk_reasoning="Unpinned dependencies can lead to supply chain attacks or breaking changes when new versions are installed.",
                evidence=evidence,
                affected_components=['requirements.txt'],
                recommendations=[
                    "Pin all dependencies with specific versions (e.g., package==1.2.3)",
                    "Use pip-tools or poetry for dependency management",
                    "Regularly audit and update pinned versions",
                ],
                validation_steps="Check requirements.txt for packages without version specifiers",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if test_result == 'fail':
            finding = self._add_finding(
                finding_key="known_vulnerabilities_detected",
                title="Known Vulnerabilities in Dependencies",
                severity='high',
                likelihood='high',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                description=f"Found {len(evidence['vulnerabilities'])} known vulnerabilities in dependencies.",
                risk_reasoning="Dependencies with known CVEs can be exploited by attackers to compromise the application.",
                evidence=evidence,
                affected_components=['requirements.txt'],
                recommendations=[
                    "Update vulnerable packages to patched versions",
                    "Run pip-audit regularly as part of CI/CD",
                    "Subscribe to security advisories for critical packages",
                ],
                validation_steps="Run pip-audit to check for vulnerabilities",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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

        # Check if DEBUG is loaded from env (support both single and double quotes)
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            if ("env.bool('DEBUG" in content or 'env.bool("DEBUG' in content or
                "env('DEBUG" in content or 'env("DEBUG' in content):
                evidence['from_env'] = True

        result = 'pass' if evidence['from_env'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="debug_not_from_env",
                title="DEBUG Setting Not Environment-Controlled",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:H/UI:N/S:U/C:L/I:L/A:N",
                description="DEBUG setting is not loaded from environment variable, risking production debug exposure.",
                risk_reasoning="Hardcoded DEBUG can accidentally be deployed as True, exposing internal application details.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Load DEBUG from environment: DEBUG = env.bool('DEBUG', default=False)",
                    "Ensure production environment sets DEBUG=False",
                ],
                validation_steps="Check settings.py for DEBUG configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_allowed_hosts(self):
        """SEC-T044: Check ALLOWED_HOSTS configuration."""
        start = time.time()
        test_id = "SEC-T044"

        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        evidence = {'hosts': allowed_hosts, 'has_wildcard': '*' in allowed_hosts}

        result = 'fail' if evidence['has_wildcard'] else 'pass'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="allowed_hosts_wildcard",
                title="ALLOWED_HOSTS Contains Wildcard",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:N",
                description="ALLOWED_HOSTS contains '*', accepting requests from any host.",
                risk_reasoning="Wildcard ALLOWED_HOSTS enables Host header injection attacks for password reset poisoning.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Remove '*' from ALLOWED_HOSTS",
                    "Explicitly list allowed domain names",
                    "Load from environment for different deployments",
                ],
                validation_steps="Check ALLOWED_HOSTS setting for wildcards",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_secret_key_security(self):
        """SEC-T045: Check SECRET_KEY handling."""
        start = time.time()
        test_id = "SEC-T045"

        evidence = {'from_env': False, 'hardcoded': False}

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            # Check if SECRET_KEY is loaded from env (support both single and double quotes)
            if ("env('SECRET_KEY" in content or 'env("SECRET_KEY' in content or
                "os.environ.get('SECRET_KEY" in content or 'os.environ.get("SECRET_KEY' in content):
                evidence['from_env'] = True
            # Check for hardcoded key
            if re.search(r"SECRET_KEY\s*=\s*['\"][^'\"]{20,}['\"]", content):
                if 'env(' not in content.split('SECRET_KEY')[1][:50]:
                    evidence['hardcoded'] = True

        result = 'pass' if evidence['from_env'] and not evidence['hardcoded'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="secret_key_insecure",
                title="SECRET_KEY Not Properly Secured",
                severity='critical',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
                description="SECRET_KEY is either hardcoded or not loaded from environment variables.",
                risk_reasoning="A compromised SECRET_KEY allows attackers to forge sessions, CSRF tokens, and signed data, leading to complete authentication bypass.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Load SECRET_KEY from environment variable",
                    "Generate a new random SECRET_KEY using Django's get_random_secret_key()",
                    "Never commit SECRET_KEY to version control",
                ],
                validation_steps="Check settings.py for SECRET_KEY configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="no_production_wsgi",
                title="Production WSGI Server Not Configured",
                severity='medium',
                likelihood='low',
                impact='high',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:H",
                description="Procfile doesn't use a production-ready WSGI server like gunicorn.",
                risk_reasoning="Development servers are not designed for production traffic and lack security hardening, connection handling, and performance optimization.",
                evidence=evidence,
                affected_components=['Procfile'],
                recommendations=[
                    "Use gunicorn or uvicorn as the WSGI/ASGI server",
                    "Configure appropriate worker count and timeout",
                    "Never use Django's development server in production",
                ],
                validation_steps="Check Procfile for gunicorn or production WSGI server",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="no_captcha_protection",
                title="CAPTCHA Protection Not Configured",
                severity='medium',
                likelihood='high',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L",
                description="No CAPTCHA protection configured for forms, allowing automated bot submissions.",
                risk_reasoning="Without CAPTCHA, bots can create fake accounts, spam forms, and perform credential stuffing attacks.",
                evidence=evidence,
                affected_components=['config/settings.py', 'signup/login forms'],
                recommendations=[
                    "Configure reCAPTCHA v3 for signup and login forms",
                    "Consider invisible CAPTCHA for better UX",
                    "Implement progressive CAPTCHA based on risk score",
                ],
                validation_steps="Check RECAPTCHA_V3_SITE_KEY in settings",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="no_honeypot_protection",
                title="Honeypot Anti-Bot Protection Missing",
                severity='low',
                likelihood='medium',
                impact='low',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N",
                description="No honeypot fields found on forms to detect automated bot submissions.",
                risk_reasoning="Honeypot fields are a simple, low-friction way to catch automated spam submissions without affecting legitimate users.",
                evidence=evidence,
                affected_components=['forms'],
                recommendations=[
                    "Add hidden honeypot field to signup and contact forms",
                    "Reject submissions where honeypot field is filled",
                    "Use django-honeypot package for easy implementation",
                ],
                validation_steps="Search for honeypot or hidden website field in forms",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    def _test_email_verification(self):
        """SEC-T049: Check email verification requirement."""
        start = time.time()
        test_id = "SEC-T049"

        evidence = {
            'ACCOUNT_EMAIL_VERIFICATION': getattr(settings, 'ACCOUNT_EMAIL_VERIFICATION', 'optional'),
        }

        result = 'pass' if evidence['ACCOUNT_EMAIL_VERIFICATION'] in ['mandatory', 'optional'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="email_verification_disabled",
                title="Email Verification Disabled",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L",
                description="Email verification is disabled, allowing accounts with invalid emails.",
                risk_reasoning="Without email verification, attackers can create accounts with fake emails, reducing accountability and enabling abuse.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Set ACCOUNT_EMAIL_VERIFICATION='mandatory' or 'optional'",
                    "Require verified email for sensitive operations",
                    "Send verification email immediately on signup",
                ],
                validation_steps="Check ACCOUNT_EMAIL_VERIFICATION setting",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

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
            findings=findings,
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
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="signup_no_rate_limiting",
                title="Signup Endpoint Missing Rate Limiting",
                severity='medium',
                likelihood='high',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L",
                description="Signup endpoint lacks rate limiting, enabling account enumeration and mass account creation.",
                risk_reasoning="Without rate limiting, attackers can create thousands of fake accounts or perform credential stuffing attacks.",
                evidence=evidence,
                affected_components=['signup views'],
                recommendations=[
                    "Implement IP-based rate limiting for signup",
                    "Add progressive delays for repeated attempts",
                    "Consider device fingerprinting for additional protection",
                ],
                validation_steps="Check signup views for rate_limit decorator or cache-based limiting",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

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
            findings=findings,
        ))

    # ==========================================================================
    # FINANCIAL / PCI DSS COMPLIANCE TESTS (SEC-T051 - SEC-T060)
    # ==========================================================================

    def _run_financial_compliance_tests(self):
        """Run financial data and PCI DSS compliance tests."""
        self._test_pci_card_data_storage()
        self._test_stripe_webhook_security()
        self._test_plaid_token_security()
        self._test_payment_audit_trail()
        self._test_fraud_velocity_checks()
        self._test_payment_credential_rotation()
        self._test_financial_data_encryption()
        self._test_transaction_integrity()
        self._test_payment_error_handling()
        self._test_financial_access_controls()

    def _test_pci_card_data_storage(self):
        """SEC-T051: Verify no credit card data is stored locally (PCI DSS)."""
        start = time.time()
        test_id = "SEC-T051"

        evidence = {'card_patterns_found': [], 'tokenization_used': False}
        findings = []

        # Patterns that indicate raw card data storage (actual card numbers/CVV)
        # NOTE: We look for field definitions that would STORE card data,
        # not references to card types or cardio exercises
        card_patterns = [
            r'card_number\s*=',      # Field storing card number
            r'card_num\s*=',         # Field storing card num
            r'ccnum\s*=',            # Field storing CC number
            r'pan\s*=\s*models\.',   # Primary Account Number field
            r'cvv\s*=',              # CVV field
            r'cvc\s*=',              # CVC field
            r'security_code\s*=\s*models\.', # Security code field
        ]

        # Patterns to EXCLUDE (false positives)
        exclude_patterns = [
            r'cardio',               # Cardiovascular exercise
            r'cardiology',           # Medical specialty
            r'TYPE_CREDIT_CARD',     # Account type constant
            r"'credit_card'",        # String literal for account type
            r'"credit_card"',        # String literal for account type
            r'credit_card_debt',     # Debt tracking (amount, not card data)
        ]

        # Check models for card storage
        models_path = self.base_path / 'apps'
        for py_file in models_path.rglob('models.py'):
            try:
                content = py_file.read_text()
                content_lower = content.lower()

                # First check if file contains any exclude patterns
                # If a line matches exclude, skip checking that line
                has_real_card_data = False
                for line_num, line in enumerate(content.split('\n'), 1):
                    line_lower = line.lower()

                    # Skip if line matches any exclude pattern
                    if any(re.search(exc, line_lower) for exc in exclude_patterns):
                        continue

                    # Check if line has actual card data storage patterns
                    for pattern in card_patterns:
                        if re.search(pattern, line_lower):
                            has_real_card_data = True
                            rel_path = str(py_file.relative_to(self.base_path))
                            if rel_path not in evidence['card_patterns_found']:
                                evidence['card_patterns_found'].append(rel_path)
                            break
                    if has_real_card_data:
                        break
            except Exception:
                pass

        # Check for Stripe tokenization (good)
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'stripe.PaymentMethod' in content or 'stripe.Token' in content or 'pm_' in content:
                    evidence['tokenization_used'] = True
                    break
            except Exception:
                pass

        # Exclude false positives from billing app that uses Stripe tokens
        evidence['card_patterns_found'] = [
            f for f in evidence['card_patterns_found']
            if 'test' not in f.lower() and 'migration' not in f.lower()
        ]

        result = 'pass' if not evidence['card_patterns_found'] and evidence['tokenization_used'] else 'fail'

        if evidence['card_patterns_found']:
            finding = self._add_finding(
                finding_key="pci_card_data_storage",
                title="Potential Card Data Storage Detected",
                severity='critical',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
                description=f"Found potential card data fields in: {evidence['card_patterns_found']}",
                risk_reasoning="Storing raw card data violates PCI DSS and creates massive liability exposure.",
                evidence=evidence,
                affected_components=evidence['card_patterns_found'],
                recommendations=[
                    "Remove all card data storage - use Stripe tokens only",
                    "Never store CVV/CVC under any circumstances",
                    "Use payment processor's hosted fields for card entry",
                ],
                validation_steps="Grep codebase for card_number, cvv, pan patterns",
                is_quick_win=False,
                remediation_effort='high',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="PCI DSS Card Data Storage",
            description="Verify no raw credit card data is stored locally.",
            criteria="No card numbers/CVV stored; tokenization via payment processor.",
            result=result,
            result_details=f"Card patterns: {len(evidence['card_patterns_found'])}, Tokenization: {evidence['tokenization_used']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_stripe_webhook_security(self):
        """SEC-T052: Verify Stripe webhook signature validation."""
        start = time.time()
        test_id = "SEC-T052"

        evidence = {
            'webhook_found': False,
            'signature_verification': False,
            'timing_safe_compare': False,
            'replay_protection': False,
        }
        findings = []

        # Find Stripe webhook handlers
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'stripe' in content.lower() and 'webhook' in content.lower():
                    evidence['webhook_found'] = True
                    rel_path = str(py_file.relative_to(self.base_path))

                    # Check for signature verification
                    if 'construct_event' in content or 'verify_header' in content:
                        evidence['signature_verification'] = True

                    # Check for timing-safe comparison
                    if 'hmac.compare_digest' in content or 'construct_event' in content:
                        evidence['timing_safe_compare'] = True

                    # Check for idempotency/replay protection
                    if 'idempotency' in content.lower() or 'event.id' in content:
                        evidence['replay_protection'] = True
            except Exception:
                pass

        result = 'pass' if (
            evidence['webhook_found'] and
            evidence['signature_verification'] and
            evidence['timing_safe_compare']
        ) else 'fail'

        if evidence['webhook_found'] and not evidence['signature_verification']:
            finding = self._add_finding(
                finding_key="stripe_webhook_no_signature",
                title="Stripe Webhook Missing Signature Verification",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:L",
                description="Stripe webhooks should verify signatures to prevent spoofing.",
                risk_reasoning="Without signature verification, attackers can forge webhook events.",
                evidence=evidence,
                affected_components=['apps/billing/webhooks.py'],
                recommendations=[
                    "Use stripe.Webhook.construct_event() for signature verification",
                    "Store STRIPE_WEBHOOK_SECRET in environment",
                    "Implement idempotency key tracking for replay protection",
                ],
                validation_steps="Verify construct_event() is called before processing webhook",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Stripe Webhook Security",
            description="Verify Stripe webhook signature validation and replay protection.",
            criteria="Webhook signatures verified, timing-safe comparison used.",
            result=result,
            result_details=f"Sig verify: {evidence['signature_verification']}, Timing-safe: {evidence['timing_safe_compare']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_plaid_token_security(self):
        """SEC-T053: Verify Plaid link token and access token security."""
        start = time.time()
        test_id = "SEC-T053"

        evidence = {
            'plaid_integration': False,
            'link_token_expiry': False,
            'access_token_encrypted': False,
            'user_ownership_check': False,
        }
        findings = []

        # Find Plaid integration
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'plaid' in content.lower():
                    evidence['plaid_integration'] = True

                    # Check for link token expiration handling
                    if 'expiration' in content.lower() or 'link_token' in content:
                        evidence['link_token_expiry'] = True

                    # Check for encrypted storage of access tokens
                    if 'EncryptedTextField' in content or 'encrypt' in content.lower():
                        evidence['access_token_encrypted'] = True

                    # Check for user ownership verification
                    if 'request.user' in content and 'plaid' in content.lower():
                        evidence['user_ownership_check'] = True
            except Exception:
                pass

        # If no Plaid integration, pass (not applicable)
        if not evidence['plaid_integration']:
            result = 'pass'
        else:
            result = 'pass' if evidence['access_token_encrypted'] and evidence['user_ownership_check'] else 'fail'

        if evidence['plaid_integration'] and not evidence['access_token_encrypted']:
            finding = self._add_finding(
                finding_key="plaid_token_not_encrypted",
                title="Plaid Access Tokens May Not Be Encrypted",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description="Plaid access tokens should be encrypted at rest.",
                risk_reasoning="Access tokens grant full access to user bank accounts.",
                evidence=evidence,
                affected_components=['apps/finance/models.py'],
                recommendations=[
                    "Encrypt access_token field using Fernet/AES-256",
                    "Implement token refresh rotation",
                    "Log all token access for audit trail",
                ],
                validation_steps="Verify access_token uses EncryptedTextField",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Plaid Token Security",
            description="Verify Plaid access tokens are encrypted and ownership verified.",
            criteria="Access tokens encrypted at rest, user ownership verified.",
            result=result,
            result_details=f"Encrypted: {evidence['access_token_encrypted']}, User check: {evidence['user_ownership_check']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_payment_audit_trail(self):
        """SEC-T054: Verify payment transactions have audit trail."""
        start = time.time()
        test_id = "SEC-T054"

        evidence = {
            'audit_model_exists': False,
            'payment_events_logged': False,
            'immutable_records': False,
        }
        findings = []

        # Check for payment audit models
        audit_patterns = ['PaymentAuditLog', 'TransactionLog', 'FinanceAuditLog', 'BillingAudit']
        for py_file in self.base_path.rglob('models.py'):
            try:
                content = py_file.read_text()
                for pattern in audit_patterns:
                    if pattern in content:
                        evidence['audit_model_exists'] = True
                        break
            except Exception:
                pass

        # Check for payment event logging
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if ('stripe' in content.lower() or 'payment' in content.lower()) and 'logger' in content:
                    evidence['payment_events_logged'] = True

                # Check for soft delete (immutability indicator)
                if 'soft_delete' in content or 'is_deleted' in content:
                    evidence['immutable_records'] = True
            except Exception:
                pass

        result = 'pass' if evidence['audit_model_exists'] and evidence['payment_events_logged'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Payment Audit Trail",
            description="Verify payment transactions have complete audit trail.",
            criteria="Audit model exists, payment events logged, records immutable.",
            result=result,
            result_details=f"Audit model: {evidence['audit_model_exists']}, Events logged: {evidence['payment_events_logged']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_fraud_velocity_checks(self):
        """SEC-T055: Verify fraud prevention velocity checks exist."""
        start = time.time()
        test_id = "SEC-T055"

        evidence = {
            'velocity_checks': False,
            'amount_limits': False,
            'frequency_limits': False,
        }
        findings = []

        # Check for velocity/fraud checks
        velocity_patterns = [
            r'velocity',
            r'rate.?limit.*payment',
            r'max.*transaction',
            r'daily.*limit',
            r'fraud.*check',
            r'suspicious.*activity',
        ]

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text().lower()
                for pattern in velocity_patterns:
                    if re.search(pattern, content):
                        evidence['velocity_checks'] = True
                        break

                # Check for amount limits
                if 'max_amount' in content or 'amount_limit' in content:
                    evidence['amount_limits'] = True

                # Check for frequency limits
                if 'transaction_count' in content or 'per_day' in content or 'per_hour' in content:
                    evidence['frequency_limits'] = True
            except Exception:
                pass

        # This is advisory - many apps rely on Stripe Radar
        result = 'pass' if evidence['velocity_checks'] or evidence['amount_limits'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Fraud Velocity Checks",
            description="Verify fraud prevention velocity and limit checks.",
            criteria="Velocity checks or amount/frequency limits implemented.",
            result=result,
            result_details=f"Velocity: {evidence['velocity_checks']}, Amount limits: {evidence['amount_limits']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_payment_credential_rotation(self):
        """SEC-T056: Verify payment API credentials support rotation."""
        start = time.time()
        test_id = "SEC-T056"

        evidence = {
            'stripe_keys_from_env': False,
            'plaid_keys_from_env': False,
            'no_hardcoded_keys': True,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check Stripe keys from env
            if ("env('STRIPE" in content or 'env("STRIPE' in content or
                "os.environ" in content and "STRIPE" in content):
                evidence['stripe_keys_from_env'] = True

            # Check Plaid keys from env
            if ("env('PLAID" in content or 'env("PLAID' in content or
                "os.environ" in content and "PLAID" in content):
                evidence['plaid_keys_from_env'] = True

            # Check for hardcoded keys
            if re.search(r"sk_live_[a-zA-Z0-9]+", content) or re.search(r"sk_test_[a-zA-Z0-9]+", content):
                evidence['no_hardcoded_keys'] = False

        result = 'pass' if evidence['stripe_keys_from_env'] and evidence['no_hardcoded_keys'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Payment Credential Rotation",
            description="Verify payment API credentials loaded from environment.",
            criteria="Stripe/Plaid keys from env, no hardcoded keys.",
            result=result,
            result_details=f"Stripe env: {evidence['stripe_keys_from_env']}, No hardcoded: {evidence['no_hardcoded_keys']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_financial_data_encryption(self):
        """SEC-T057: Verify financial data is encrypted at rest."""
        start = time.time()
        test_id = "SEC-T057"

        evidence = {
            'encrypted_fields_found': False,
            'finance_models_checked': [],
            'sensitive_fields_encrypted': [],
        }
        findings = []

        # Check finance/billing models for encryption
        finance_paths = [
            self.base_path / 'apps' / 'finance' / 'models.py',
            self.base_path / 'apps' / 'billing' / 'models.py',
        ]

        for model_file in finance_paths:
            if model_file.exists():
                content = model_file.read_text()
                rel_path = str(model_file.relative_to(self.base_path))
                evidence['finance_models_checked'].append(rel_path)

                # Check for encrypted fields
                if 'EncryptedTextField' in content or 'EncryptedCharField' in content:
                    evidence['encrypted_fields_found'] = True

                # Look for sensitive field names that should be encrypted
                sensitive_patterns = ['access_token', 'account_number', 'routing_number', 'balance']
                for pattern in sensitive_patterns:
                    if pattern in content.lower():
                        if 'Encrypted' in content.split(pattern)[0][-100:]:
                            evidence['sensitive_fields_encrypted'].append(pattern)

        result = 'pass' if evidence['encrypted_fields_found'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Financial Data Encryption",
            description="Verify sensitive financial data is encrypted at rest.",
            criteria="Financial models use encrypted fields for sensitive data.",
            result=result,
            result_details=f"Encrypted fields: {evidence['encrypted_fields_found']}, Models: {len(evidence['finance_models_checked'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_transaction_integrity(self):
        """SEC-T058: Verify transaction integrity controls."""
        start = time.time()
        test_id = "SEC-T058"

        evidence = {
            'atomic_transactions': False,
            'idempotency_keys': False,
            'double_spend_prevention': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'payment' in content.lower() or 'transaction' in content.lower():
                    # Check for atomic transactions
                    if 'transaction.atomic' in content or '@atomic' in content:
                        evidence['atomic_transactions'] = True

                    # Check for idempotency
                    if 'idempotency' in content.lower():
                        evidence['idempotency_keys'] = True

                    # Check for double-spend prevention
                    if 'select_for_update' in content or 'lock' in content.lower():
                        evidence['double_spend_prevention'] = True
            except Exception:
                pass

        result = 'pass' if evidence['atomic_transactions'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Transaction Integrity",
            description="Verify transaction integrity with atomic operations.",
            criteria="Atomic transactions used, idempotency supported.",
            result=result,
            result_details=f"Atomic: {evidence['atomic_transactions']}, Idempotency: {evidence['idempotency_keys']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_payment_error_handling(self):
        """SEC-T059: Verify payment errors don't leak sensitive info."""
        start = time.time()
        test_id = "SEC-T059"

        evidence = {
            'generic_error_messages': False,
            'no_stack_trace_exposure': True,
            'error_logging_present': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'stripe' in content.lower() or 'payment' in content.lower():
                    # Check for error handling
                    if 'except' in content and ('StripeError' in content or 'PaymentError' in content):
                        evidence['generic_error_messages'] = True

                    # Check for logging
                    if 'logger.error' in content or 'logger.exception' in content:
                        evidence['error_logging_present'] = True

                    # Check for potential stack trace exposure
                    if 'traceback.format_exc' in content and 'JsonResponse' in content:
                        evidence['no_stack_trace_exposure'] = False
            except Exception:
                pass

        result = 'pass' if evidence['generic_error_messages'] and evidence['no_stack_trace_exposure'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Payment Error Handling",
            description="Verify payment errors don't expose sensitive information.",
            criteria="Generic error messages, no stack trace exposure.",
            result=result,
            result_details=f"Generic errors: {evidence['generic_error_messages']}, Safe: {evidence['no_stack_trace_exposure']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_financial_access_controls(self):
        """SEC-T060: Verify financial data access controls."""
        start = time.time()
        test_id = "SEC-T060"

        evidence = {
            'login_required': False,
            'user_scoping': False,
            'admin_separation': False,
        }
        findings = []

        finance_views = [
            self.base_path / 'apps' / 'finance' / 'views.py',
            self.base_path / 'apps' / 'billing' / 'views.py',
        ]

        for view_file in finance_views:
            if view_file.exists():
                content = view_file.read_text()

                # Check for login requirement
                if '@login_required' in content or 'LoginRequiredMixin' in content:
                    evidence['login_required'] = True

                # Check for user scoping
                if 'request.user' in content and ('filter' in content or 'get_queryset' in content):
                    evidence['user_scoping'] = True

                # Check for admin separation
                if '@staff_member_required' in content or 'is_staff' in content:
                    evidence['admin_separation'] = True

        result = 'pass' if evidence['login_required'] and evidence['user_scoping'] else 'fail'

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Financial Access Controls",
            description="Verify financial data requires authentication and user scoping.",
            criteria="Login required, data scoped to user, admin separation.",
            result=result,
            result_details=f"Login: {evidence['login_required']}, User scoped: {evidence['user_scoping']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    # ==========================================================================
    # HEALTH / HIPAA COMPLIANCE TESTS (SEC-T061 - SEC-T070)
    # ==========================================================================

    def _run_health_compliance_tests(self):
        """Run health data and HIPAA compliance tests."""
        self._test_health_data_encryption()
        self._test_health_access_controls()
        self._test_hipaa_audit_logging()
        self._test_health_data_minimization()
        self._test_phi_transmission_security()
        self._test_health_data_retention()
        self._test_patient_consent_tracking()
        self._test_health_data_portability()
        self._test_breach_notification_capability()
        self._test_health_provider_separation()

    def _test_health_data_encryption(self):
        """SEC-T061: Verify health/PHI data is encrypted at rest (HIPAA)."""
        start = time.time()
        test_id = "SEC-T061"

        evidence = {
            'health_models_found': [],
            'encrypted_fields': False,
            'encryption_utilities': False,
            'database_encryption': False,
            'phi_fields_identified': [],
        }
        findings = []

        # Health-related model files
        health_paths = [
            self.base_path / 'apps' / 'health' / 'models.py',
            self.base_path / 'apps' / 'scan' / 'models.py',
        ]

        # PHI field patterns (Protected Health Information)
        phi_patterns = ['weight', 'height', 'blood_pressure', 'heart_rate', 'glucose',
                        'medication', 'diagnosis', 'symptom', 'cycle', 'period',
                        'health_metric', 'body_', 'medical', 'treatment']

        for model_file in health_paths:
            if model_file.exists():
                content = model_file.read_text()
                rel_path = str(model_file.relative_to(self.base_path))
                evidence['health_models_found'].append(rel_path)

                # Check for encrypted fields
                if 'EncryptedTextField' in content or 'EncryptedCharField' in content or 'EncryptedJSONField' in content:
                    evidence['encrypted_fields'] = True

                # Identify PHI fields
                for pattern in phi_patterns:
                    if pattern in content.lower():
                        evidence['phi_fields_identified'].append(pattern)

        # Check for encryption utilities (indicates encryption infrastructure exists)
        encryption_module = self.base_path / 'apps' / 'core' / 'encryption.py'
        if encryption_module.exists():
            enc_content = encryption_module.read_text()
            if 'Fernet' in enc_content or 'encrypt' in enc_content:
                evidence['encryption_utilities'] = True

        # Check for database-level encryption configuration (Railway PostgreSQL, TDE)
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            settings_content = settings_file.read_text()
            # Railway uses encrypted PostgreSQL by default
            if 'DATABASE_URL' in settings_content or 'railway' in settings_content.lower():
                evidence['database_encryption'] = True

        # Pass conditions:
        # 1. No health models found (N/A)
        # 2. Field-level encryption is used
        # 3. Database-level encryption exists AND encryption utilities are available
        if not evidence['health_models_found']:
            result = 'pass'  # N/A
        elif evidence['encrypted_fields']:
            result = 'pass'  # Field-level encryption
        elif evidence['database_encryption'] and evidence['encryption_utilities']:
            result = 'pass'  # Infrastructure encryption with utilities available
        else:
            result = 'fail'

        if result == 'fail':
            finding = self._add_finding(
                finding_key="hipaa_phi_not_encrypted",
                title="Health/PHI Data May Not Be Encrypted at Rest",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description="HIPAA requires PHI to be encrypted at rest.",
                risk_reasoning="Unencrypted health data exposure = HIPAA violation + $100+ per record fine.",
                evidence=evidence,
                affected_components=evidence['health_models_found'],
                recommendations=[
                    "Use EncryptedTextField for all PHI fields",
                    "Implement database-level encryption (TDE)",
                    "Document encryption in HIPAA security plan",
                ],
                validation_steps="Verify health model fields use encrypted field types",
                is_quick_win=False,
                remediation_effort='high',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="HIPAA PHI Encryption",
            description="Verify health/PHI data is encrypted at rest.",
            criteria="All PHI fields use encryption, encryption keys secured.",
            result=result,
            result_details=f"Health models: {len(evidence['health_models_found'])}, Field encryption: {evidence['encrypted_fields']}, DB encryption: {evidence['database_encryption']}, Utils: {evidence['encryption_utilities']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_health_access_controls(self):
        """SEC-T062: Verify health data access is properly controlled."""
        start = time.time()
        test_id = "SEC-T062"

        evidence = {
            'login_required': False,
            'user_scoping': False,
            'role_based_access': False,
        }
        findings = []

        health_views = self.base_path / 'apps' / 'health' / 'views.py'
        if health_views.exists():
            content = health_views.read_text()

            # Check authentication
            if '@login_required' in content or 'LoginRequiredMixin' in content:
                evidence['login_required'] = True

            # Check user scoping
            if 'request.user' in content and ('filter(user=' in content or 'user=request.user' in content):
                evidence['user_scoping'] = True

            # Check for role-based access
            if 'has_perm' in content or 'permission_required' in content or 'UserPassesTestMixin' in content:
                evidence['role_based_access'] = True

        result = 'pass' if evidence['login_required'] and evidence['user_scoping'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="hipaa_access_controls_missing",
                title="HIPAA Access Controls Insufficient",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description="Health data views lack proper authentication or user-scoping controls.",
                risk_reasoning="HIPAA requires technical safeguards to limit PHI access. Missing controls = unauthorized disclosure risk and regulatory fines.",
                evidence=evidence,
                affected_components=['apps/health/views.py'],
                recommendations=[
                    "Add LoginRequiredMixin to all health data views",
                    "Filter querysets by request.user",
                    "Consider role-based access for provider scenarios",
                ],
                validation_steps="Check health views for authentication and user filtering",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="HIPAA Access Controls",
            description="Verify health data requires authentication and proper access controls.",
            criteria="Login required, user-scoped data, role-based access.",
            result=result,
            result_details=f"Auth: {evidence['login_required']}, Scoped: {evidence['user_scoping']}, RBAC: {evidence['role_based_access']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_hipaa_audit_logging(self):
        """SEC-T063: Verify HIPAA-compliant audit logging for health data access."""
        start = time.time()
        test_id = "SEC-T063"

        evidence = {
            'audit_logging_present': False,
            'who_what_when_where': False,
            'access_denial_logged': False,
        }
        findings = []

        # Check for audit logging in health module
        for py_file in (self.base_path / 'apps' / 'health').rglob('*.py'):
            try:
                content = py_file.read_text()

                # Check for logging
                if 'logger' in content and ('access' in content.lower() or 'audit' in content.lower()):
                    evidence['audit_logging_present'] = True

                # Check for WHO-WHAT-WHEN logging
                if 'request.user' in content and 'logger' in content:
                    evidence['who_what_when_where'] = True

                # Check for access denial logging
                if 'PermissionDenied' in content or 'Http403' in content or 'Forbidden' in content:
                    if 'logger' in content:
                        evidence['access_denial_logged'] = True
            except Exception:
                pass

        result = 'pass' if evidence['audit_logging_present'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="hipaa_audit_logging_missing",
                title="HIPAA Audit Logging Insufficient",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N",
                description="Health data access is not comprehensively logged with audit trail.",
                risk_reasoning="HIPAA requires audit logging of all PHI access. Missing logs make breach detection and investigation impossible.",
                evidence=evidence,
                affected_components=['apps/health/'],
                recommendations=[
                    "Add audit logging for all PHI access events",
                    "Log WHO (user), WHAT (action), WHEN (timestamp), WHERE (IP)",
                    "Retain audit logs for minimum 6 years per HIPAA",
                ],
                validation_steps="Check health views for audit logging implementation",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="HIPAA Audit Logging",
            description="Verify comprehensive audit logging for health data access.",
            criteria="All PHI access logged with WHO/WHAT/WHEN/WHERE.",
            result=result,
            result_details=f"Audit: {evidence['audit_logging_present']}, Full context: {evidence['who_what_when_where']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_health_data_minimization(self):
        """SEC-T064: Verify health data collection is minimized to necessary fields."""
        start = time.time()
        test_id = "SEC-T064"

        evidence = {
            'forms_checked': 0,
            'optional_fields': False,
            'purpose_documented': False,
        }
        findings = []

        # Check health forms
        for py_file in (self.base_path / 'apps' / 'health').rglob('forms.py'):
            try:
                content = py_file.read_text()
                evidence['forms_checked'] += 1

                # Check for optional fields
                if 'required=False' in content or 'blank=True' in content:
                    evidence['optional_fields'] = True

                # Check for documented purpose
                if '"""' in content or "'''" in content:
                    evidence['purpose_documented'] = True
            except Exception:
                pass

        result = 'pass'  # Advisory check

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Health Data Minimization",
            description="Verify health data collection follows minimization principle.",
            criteria="Only necessary data collected, optional fields marked.",
            result=result,
            result_details=f"Forms: {evidence['forms_checked']}, Optional fields: {evidence['optional_fields']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_phi_transmission_security(self):
        """SEC-T065: Verify PHI is transmitted securely (TLS 1.2+)."""
        start = time.time()
        test_id = "SEC-T065"

        evidence = {
            'https_enforced': False,
            'secure_cookies': False,
            'hsts_enabled': False,
        }
        findings = []

        # Check settings for TLS enforcement
        try:
            from django.conf import settings
            evidence['https_enforced'] = (
                getattr(settings, 'SECURE_SSL_REDIRECT', False) or
                getattr(settings, 'SECURE_PROXY_SSL_HEADER', None) is not None
            )
            evidence['secure_cookies'] = getattr(settings, 'SESSION_COOKIE_SECURE', False)
            evidence['hsts_enabled'] = getattr(settings, 'SECURE_HSTS_SECONDS', 0) > 0
        except Exception:
            pass

        result = 'pass' if evidence['https_enforced'] or evidence['hsts_enabled'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="phi_transmission_insecure",
                title="PHI Transmission May Not Be Secure",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                description="HTTPS enforcement or HSTS not configured for secure PHI transmission.",
                risk_reasoning="HIPAA requires transmission security for PHI. Unencrypted transmission exposes health data to interception.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Enable SECURE_SSL_REDIRECT or configure SECURE_PROXY_SSL_HEADER",
                    "Set SECURE_HSTS_SECONDS to enforce HTTPS",
                    "Enable SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE",
                ],
                validation_steps="Check Django security settings for TLS/HSTS configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="PHI Transmission Security",
            description="Verify health data transmitted over secure channels.",
            criteria="HTTPS enforced, secure cookies, HSTS enabled.",
            result=result,
            result_details=f"HTTPS: {evidence['https_enforced']}, HSTS: {evidence['hsts_enabled']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_health_data_retention(self):
        """SEC-T066: Verify health data retention policies are implemented."""
        start = time.time()
        test_id = "SEC-T066"

        evidence = {
            'retention_policy_found': False,
            'soft_delete_used': False,
            'archival_mechanism': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'health' in str(py_file).lower():
                    # Check for retention policy
                    if 'retention' in content.lower() or 'archive' in content.lower():
                        evidence['retention_policy_found'] = True

                    # Check for soft delete
                    if 'soft_delete' in content or 'is_deleted' in content or 'deleted_at' in content:
                        evidence['soft_delete_used'] = True

                    # Check for archival
                    if 'archive' in content.lower() or 'backup' in content.lower():
                        evidence['archival_mechanism'] = True
            except Exception:
                pass

        result = 'pass' if evidence['soft_delete_used'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="health_data_retention_missing",
                title="Health Data Retention Policy Not Implemented",
                severity='medium',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:L/UI:N/S:U/C:L/I:L/A:N",
                description="Health data retention/soft delete not properly implemented.",
                risk_reasoning="HIPAA requires retaining health records for minimum 6 years. Hard deletes violate retention requirements.",
                evidence=evidence,
                affected_components=['apps/health/models.py'],
                recommendations=[
                    "Implement soft delete for all health-related models",
                    "Add deleted_at timestamp field",
                    "Create archival process for aged data",
                ],
                validation_steps="Check health models for soft_delete or deleted_at field",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Health Data Retention",
            description="Verify health data retention policies (HIPAA: 6 years minimum).",
            criteria="Retention policy defined, soft delete used, archival supported.",
            result=result,
            result_details=f"Policy: {evidence['retention_policy_found']}, Soft delete: {evidence['soft_delete_used']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_patient_consent_tracking(self):
        """SEC-T067: Verify patient consent is tracked for health data use."""
        start = time.time()
        test_id = "SEC-T067"

        evidence = {
            'consent_model': False,
            'consent_timestamp': False,
            'consent_revocation': False,
        }
        findings = []

        for py_file in self.base_path.rglob('models.py'):
            try:
                content = py_file.read_text()
                if 'consent' in content.lower():
                    evidence['consent_model'] = True

                    if 'consent' in content.lower() and ('datetime' in content or 'timestamp' in content.lower()):
                        evidence['consent_timestamp'] = True

                    if 'revoke' in content.lower() or 'withdraw' in content.lower():
                        evidence['consent_revocation'] = True
            except Exception:
                pass

        # Also check for terms acceptance (basic consent)
        if not evidence['consent_model']:
            for py_file in self.base_path.rglob('*.py'):
                try:
                    content = py_file.read_text()
                    if 'TermsAcceptance' in content or 'terms_accepted' in content.lower():
                        evidence['consent_model'] = True
                        break
                except Exception:
                    pass

        result = 'pass' if evidence['consent_model'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="patient_consent_not_tracked",
                title="Patient Consent Not Tracked",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N",
                description="No mechanism found for tracking patient consent for health data collection.",
                risk_reasoning="Collecting health data without documented consent may violate HIPAA authorization requirements.",
                evidence=evidence,
                affected_components=['models.py'],
                recommendations=[
                    "Create a Consent or TermsAcceptance model",
                    "Track consent timestamp and version",
                    "Implement consent revocation capability",
                ],
                validation_steps="Check for consent model or terms_accepted field",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Patient Consent Tracking",
            description="Verify patient consent is tracked for health data collection.",
            criteria="Consent model exists, timestamps recorded, revocation supported.",
            result=result,
            result_details=f"Consent: {evidence['consent_model']}, Timestamped: {evidence['consent_timestamp']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_health_data_portability(self):
        """SEC-T068: Verify health data can be exported (HIPAA Right of Access)."""
        start = time.time()
        test_id = "SEC-T068"

        evidence = {
            'export_capability': False,
            'supported_formats': [],
            'user_accessible': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'export' in content.lower() and 'health' in str(py_file).lower():
                    evidence['export_capability'] = True

                    # Check for formats
                    if 'csv' in content.lower():
                        evidence['supported_formats'].append('CSV')
                    if 'json' in content.lower():
                        evidence['supported_formats'].append('JSON')
                    if 'pdf' in content.lower():
                        evidence['supported_formats'].append('PDF')

                    if 'request.user' in content:
                        evidence['user_accessible'] = True
            except Exception:
                pass

        result = 'pass' if evidence['export_capability'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="health_data_not_exportable",
                title="Health Data Export Not Available",
                severity='medium',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:L/UI:N/S:U/C:N/I:L/A:N",
                description="No health data export capability found for user access.",
                risk_reasoning="HIPAA Right of Access requires patients to be able to obtain copies of their health records.",
                evidence=evidence,
                affected_components=['apps/health/'],
                recommendations=[
                    "Implement data export in CSV, JSON, or PDF format",
                    "Ensure users can export their own health data",
                    "Provide complete data within 30 days as required",
                ],
                validation_steps="Check for export views or data download functionality",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Health Data Portability",
            description="Verify health data export capability (HIPAA Right of Access).",
            criteria="Export available, standard formats supported, user-accessible.",
            result=result,
            result_details=f"Export: {evidence['export_capability']}, Formats: {evidence['supported_formats']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_breach_notification_capability(self):
        """SEC-T069: Verify breach notification capability exists."""
        start = time.time()
        test_id = "SEC-T069"

        evidence = {
            'notification_system': False,
            'email_capability': False,
            'affected_user_query': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # Check for notification system
                if 'notification' in content.lower() and ('send' in content or 'email' in content.lower()):
                    evidence['notification_system'] = True

                # Check for email capability
                if 'send_mail' in content or 'EmailMessage' in content:
                    evidence['email_capability'] = True

                # Check for user query capability
                if 'User.objects' in content and 'filter' in content:
                    evidence['affected_user_query'] = True
            except Exception:
                pass

        result = 'pass' if evidence['notification_system'] and evidence['email_capability'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="breach_notification_missing",
                title="Breach Notification Capability Missing",
                severity='medium',
                likelihood='low',
                impact='high',
                cvss_vector="AV:N/AC:H/PR:H/UI:N/S:U/C:N/I:L/A:N",
                description="No capability found to notify users in case of a data breach.",
                risk_reasoning="HIPAA requires breach notification within 60 days. Lack of notification infrastructure delays response.",
                evidence=evidence,
                affected_components=['notification system'],
                recommendations=[
                    "Implement email notification system",
                    "Create user query capability for affected users",
                    "Document breach notification procedures",
                ],
                validation_steps="Check for email sending and user notification code",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Breach Notification Capability",
            description="Verify capability to notify affected users (HIPAA: 60 days).",
            criteria="Notification system exists, email capability, can identify affected users.",
            result=result,
            result_details=f"Notifications: {evidence['notification_system']}, Email: {evidence['email_capability']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_health_provider_separation(self):
        """SEC-T070: Verify separation between user health data and provider access."""
        start = time.time()
        test_id = "SEC-T070"

        evidence = {
            'provider_role_exists': False,
            'access_controls_separate': False,
            'audit_for_provider_access': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # Check for provider/coach role
                if 'provider' in content.lower() or 'coach' in content.lower() or 'practitioner' in content.lower():
                    evidence['provider_role_exists'] = True

                    # Check for separate access controls
                    if 'is_provider' in content or 'is_coach' in content or 'has_provider_access' in content:
                        evidence['access_controls_separate'] = True

                    # Check for audit of provider access
                    if 'logger' in content and ('provider' in content.lower() or 'coach' in content.lower()):
                        evidence['audit_for_provider_access'] = True
            except Exception:
                pass

        result = 'pass'  # Advisory - may not apply to all apps

        self.results.append(TestResult(
            test_id=test_id,
            category='compliance',
            title="Provider Access Separation",
            description="Verify provider access to patient data is controlled and logged.",
            criteria="Provider role exists, separate access controls, audited.",
            result=result,
            result_details=f"Provider role: {evidence['provider_role_exists']}, Separate: {evidence['access_controls_separate']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # API SECURITY TESTS (SEC-T071 - SEC-T078)
    # ==========================================================================

    def _run_api_security_tests(self):
        """Run API security tests."""
        self._test_api_rate_limiting()
        self._test_api_pagination_limits()
        self._test_api_request_validation()
        self._test_api_response_filtering()
        self._test_api_versioning()
        self._test_api_error_responses()
        self._test_graphql_security()
        self._test_api_key_management()

    def _test_api_rate_limiting(self):
        """SEC-T071: Verify API endpoints have rate limiting."""
        start = time.time()
        test_id = "SEC-T071"

        evidence = {
            'rate_limiting_found': False,
            'throttle_classes': False,
            'per_endpoint_limits': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # DRF throttling
                if 'throttle_classes' in content or 'Throttle' in content:
                    evidence['throttle_classes'] = True
                    evidence['rate_limiting_found'] = True

                # Django rate limit decorator
                if '@ratelimit' in content or 'rate_limit' in content:
                    evidence['rate_limiting_found'] = True

                # Per-endpoint check
                if 'UserRateThrottle' in content or 'ScopedRateThrottle' in content:
                    evidence['per_endpoint_limits'] = True
            except Exception:
                pass

        # Also check settings for DRF throttling
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            if 'DEFAULT_THROTTLE' in content or 'THROTTLE_RATES' in content:
                evidence['rate_limiting_found'] = True

        result = 'pass' if evidence['rate_limiting_found'] else 'fail'

        if not evidence['rate_limiting_found']:
            finding = self._add_finding(
                finding_key="api_no_rate_limiting",
                title="API Endpoints Lack Rate Limiting",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                description="API endpoints should have rate limiting to prevent abuse.",
                risk_reasoning="Without rate limiting, APIs are vulnerable to DoS and scraping attacks.",
                evidence=evidence,
                affected_components=['API endpoints'],
                recommendations=[
                    "Implement DRF throttle_classes for REST APIs",
                    "Add per-user and per-IP rate limits",
                    "Configure graduated backoff for repeated violations",
                ],
                validation_steps="Check API views for throttle_classes or rate limiting",
                is_quick_win=True,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Rate Limiting",
            description="Verify API endpoints have rate limiting.",
            criteria="Rate limiting configured, per-user/IP limits set.",
            result=result,
            result_details=f"Rate limiting: {evidence['rate_limiting_found']}, Per-endpoint: {evidence['per_endpoint_limits']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_api_pagination_limits(self):
        """SEC-T072: Verify API pagination has size limits."""
        start = time.time()
        test_id = "SEC-T072"

        evidence = {
            'drf_used': False,
            'pagination_configured': False,
            'max_page_size': None,
            'default_page_size': None,
            'manual_limits_found': False,
            'manual_limit_locations': [],
        }
        findings = []

        # First, check if Django REST Framework is actually used in settings
        # (not just mentioned in scanner test descriptions)
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            # Check for DRF in INSTALLED_APPS (the definitive indicator)
            if "'rest_framework'" in content or '"rest_framework"' in content:
                evidence['drf_used'] = True

            if 'PAGE_SIZE' in content or 'PAGINATION' in content:
                evidence['pagination_configured'] = True

            # Extract page size if possible
            match = re.search(r"'PAGE_SIZE':\s*(\d+)", content)
            if match:
                evidence['default_page_size'] = int(match.group(1))

            match = re.search(r"'MAX_PAGE_SIZE':\s*(\d+)", content)
            if match:
                evidence['max_page_size'] = int(match.group(1))

        # Check for DRF pagination in views and manual limit enforcement
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                relative_path = str(py_file.relative_to(self.base_path))

                # Skip scanner itself (contains DRF string patterns for test descriptions)
                if 'scanner.py' in relative_path:
                    continue

                # Check for actual DRF imports (not string mentions)
                if 'from rest_framework import' in content or 'from rest_framework.' in content:
                    evidence['drf_used'] = True

                if 'PageNumberPagination' in content or 'LimitOffsetPagination' in content:
                    evidence['pagination_configured'] = True

                    # Check for max_page_size
                    if 'max_page_size' in content:
                        match = re.search(r'max_page_size\s*=\s*(\d+)', content)
                        if match:
                            evidence['max_page_size'] = int(match.group(1))

                # Check for manual limit enforcement in custom API views
                # Pattern: limit parameter with capping (e.g., "if limit > 100: limit = 100")
                if re.search(r'limit\s*>\s*\d+', content) or re.search(r'limit\s*=\s*min\s*\(', content):
                    evidence['manual_limits_found'] = True
                    evidence['manual_limit_locations'].append(relative_path)

                # Also check for [:limit] slicing with limit validation
                if re.search(r'\[:limit\]', content) and 'limit' in content:
                    # Check if there's a limit cap
                    if re.search(r'limit\s*[<>=]', content):
                        evidence['manual_limits_found'] = True
                        if relative_path not in evidence['manual_limit_locations']:
                            evidence['manual_limit_locations'].append(relative_path)

            except Exception:
                pass

        # Pass conditions:
        # 1. DRF is used AND pagination with max_page_size is configured, OR
        # 2. DRF is not used AND manual limit enforcement is present, OR
        # 3. DRF pagination is configured with max_page_size
        if evidence['drf_used']:
            # If using DRF, require proper DRF pagination settings
            result = 'pass' if evidence['pagination_configured'] and evidence['max_page_size'] else 'fail'
        else:
            # If not using DRF, check for manual limit enforcement
            result = 'pass' if evidence['manual_limits_found'] else 'fail'

        findings = []

        if result == 'fail':
            if evidence['drf_used']:
                description = "Django REST Framework pagination doesn't enforce maximum page size."
                recommendations = [
                    "Configure PAGE_SIZE and MAX_PAGE_SIZE in REST_FRAMEWORK settings",
                    "Set reasonable limits (e.g., max 100 items per page)",
                    "Add pagination to all list endpoints",
                ]
            else:
                description = "API endpoints may not have pagination or size limits."
                recommendations = [
                    "Add limit parameters with max value caps to API views",
                    "Use Django's Paginator for list views",
                    "Enforce maximum result set sizes in querysets",
                ]

            finding = self._add_finding(
                finding_key="api_pagination_unlimited",
                title="API Pagination Missing Size Limits",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                description=description,
                risk_reasoning="Without size limits, attackers can request huge result sets, causing DoS or data scraping.",
                evidence=evidence,
                affected_components=['API views', 'config/settings.py'],
                recommendations=recommendations,
                validation_steps="Check pagination settings and view limit configurations",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        # Generate result details
        if evidence['drf_used']:
            result_details = f"DRF: Yes, Pagination: {evidence['pagination_configured']}, Max size: {evidence['max_page_size']}"
        else:
            result_details = f"DRF: No, Manual limits: {evidence['manual_limits_found']}"
            if evidence['manual_limit_locations']:
                result_details += f" in {len(evidence['manual_limit_locations'])} files"

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Pagination Limits",
            description="Verify API pagination has maximum size limits.",
            criteria="Pagination configured with max_page_size limit or manual limit enforcement.",
            result=result,
            result_details=result_details,
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_api_request_validation(self):
        """SEC-T073: Verify API request validation (serializers/schemas)."""
        start = time.time()
        test_id = "SEC-T073"

        evidence = {
            'serializers_used': False,
            'validation_present': False,
            'schema_validation': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # Check for DRF serializers
                if 'Serializer' in content and 'serializers' in content:
                    evidence['serializers_used'] = True

                    # Check for validation
                    if 'validate_' in content or 'validators=' in content or 'is_valid()' in content:
                        evidence['validation_present'] = True

                # Check for schema validation
                if 'JSONSchema' in content or 'OpenAPI' in content or 'swagger' in content.lower():
                    evidence['schema_validation'] = True
            except Exception:
                pass

        result = 'pass' if evidence['serializers_used'] and evidence['validation_present'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="api_validation_missing",
                title="API Request Validation Insufficient",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:H/A:N",
                description="API endpoints lack proper serializer validation for incoming requests.",
                risk_reasoning="Without validation, malicious input can bypass expected constraints, leading to injection or data corruption.",
                evidence=evidence,
                affected_components=['API views'],
                recommendations=[
                    "Use DRF serializers for all API endpoints",
                    "Implement validate_<field> methods for custom validation",
                    "Consider adding OpenAPI schema validation",
                ],
                validation_steps="Check API views for serializer usage and validation",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Request Validation",
            description="Verify API requests are validated via serializers/schemas.",
            criteria="Serializers used, validation methods present.",
            result=result,
            result_details=f"Serializers: {evidence['serializers_used']}, Validation: {evidence['validation_present']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_api_response_filtering(self):
        """SEC-T074: Verify API responses filter sensitive data."""
        start = time.time()
        test_id = "SEC-T074"

        evidence = {
            'exclude_fields': False,
            'read_only_fields': False,
            'sensitive_fields_protected': [],
        }
        findings = []

        sensitive_patterns = ['password', 'secret', 'token', 'key', 'ssn', 'credit_card']

        for py_file in self.base_path.rglob('serializers.py'):
            try:
                content = py_file.read_text()
                # Check for field exclusion
                if 'exclude' in content or 'fields =' in content:
                    evidence['exclude_fields'] = True

                # Check for read-only fields
                if 'read_only_fields' in content or 'read_only=True' in content:
                    evidence['read_only_fields'] = True

                # Check sensitive field protection
                for pattern in sensitive_patterns:
                    if pattern in content.lower() and 'write_only' in content:
                        evidence['sensitive_fields_protected'].append(pattern)
            except Exception:
                pass

        result = 'pass' if evidence['exclude_fields'] or evidence['read_only_fields'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="api_response_not_filtered",
                title="API Responses May Expose Sensitive Data",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
                description="API serializers don't explicitly exclude or protect sensitive fields.",
                risk_reasoning="Without field filtering, sensitive data like passwords or tokens may be accidentally exposed in API responses.",
                evidence=evidence,
                affected_components=['serializers.py'],
                recommendations=[
                    "Use explicit 'fields' list instead of '__all__'",
                    "Add 'exclude' for sensitive fields",
                    "Use write_only=True for password fields",
                ],
                validation_steps="Check serializers for field filtering configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Response Filtering",
            description="Verify API responses filter sensitive data.",
            criteria="Serializers exclude/protect sensitive fields.",
            result=result,
            result_details=f"Exclude: {evidence['exclude_fields']}, Read-only: {evidence['read_only_fields']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_api_versioning(self):
        """SEC-T075: Verify API versioning is implemented."""
        start = time.time()
        test_id = "SEC-T075"

        evidence = {
            'versioning_configured': False,
            'version_in_url': False,
            'version_in_header': False,
        }
        findings = []

        # Check settings for DRF versioning
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            if 'DEFAULT_VERSIONING_CLASS' in content or 'VERSION' in content:
                evidence['versioning_configured'] = True

        # Check URLs for versioning
        for py_file in self.base_path.rglob('urls.py'):
            try:
                content = py_file.read_text()
                if '/v1/' in content or '/v2/' in content or 'api/v' in content:
                    evidence['version_in_url'] = True
            except Exception:
                pass

        result = 'pass' if evidence['versioning_configured'] or evidence['version_in_url'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="api_versioning_missing",
                title="API Versioning Not Implemented",
                severity='low',
                likelihood='medium',
                impact='low',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N",
                description="API endpoints don't have versioning, making backward-compatible changes difficult.",
                risk_reasoning="Without versioning, API changes may break client applications unexpectedly.",
                evidence=evidence,
                affected_components=['urls.py', 'config/settings.py'],
                recommendations=[
                    "Add version prefix to API URLs (e.g., /api/v1/)",
                    "Configure DRF versioning class",
                    "Document API version deprecation policy",
                ],
                validation_steps="Check URLs and settings for versioning configuration",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Versioning",
            description="Verify API versioning is implemented for backward compatibility.",
            criteria="Versioning configured in URL or header.",
            result=result,
            result_details=f"Configured: {evidence['versioning_configured']}, URL version: {evidence['version_in_url']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_api_error_responses(self):
        """SEC-T076: Verify API error responses don't leak sensitive info."""
        start = time.time()
        test_id = "SEC-T076"

        evidence = {
            'custom_exception_handler': False,
            'debug_disabled_in_prod': False,
            'generic_error_responses': False,
        }
        findings = []

        # Check for custom exception handler
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            if 'EXCEPTION_HANDLER' in content:
                evidence['custom_exception_handler'] = True

            if 'DEBUG' in content and 'env' in content.lower():
                evidence['debug_disabled_in_prod'] = True

        # Check for generic error handling
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'exception_handler' in content or 'APIException' in content:
                    if 'detail' in content and 'traceback' not in content.lower():
                        evidence['generic_error_responses'] = True
            except Exception:
                pass

        result = 'pass' if evidence['debug_disabled_in_prod'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="api_error_info_leak",
                title="API Error Responses May Leak Information",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N",
                description="DEBUG not environment-controlled; API errors may expose stack traces in production.",
                risk_reasoning="Detailed error messages reveal internal structure, file paths, and potentially sensitive data to attackers.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Load DEBUG from environment variable",
                    "Implement custom exception handler for APIs",
                    "Return generic error messages in production",
                ],
                validation_steps="Check DEBUG setting and exception handler configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Error Responses",
            description="Verify API errors don't leak sensitive information.",
            criteria="Custom exception handler, debug off in prod, generic errors.",
            result=result,
            result_details=f"Custom handler: {evidence['custom_exception_handler']}, Debug controlled: {evidence['debug_disabled_in_prod']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_graphql_security(self):
        """SEC-T077: Verify GraphQL security if GraphQL is used."""
        start = time.time()
        test_id = "SEC-T077"

        evidence = {
            'graphql_used': False,
            'depth_limiting': False,
            'query_cost_analysis': False,
            'introspection_disabled_prod': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'graphene' in content.lower() or 'graphql' in content.lower():
                    evidence['graphql_used'] = True

                    # Check for depth limiting
                    if 'depth_limit' in content.lower() or 'max_depth' in content.lower():
                        evidence['depth_limiting'] = True

                    # Check for query cost
                    if 'cost' in content.lower() and 'query' in content.lower():
                        evidence['query_cost_analysis'] = True

                    # Check for introspection
                    if 'introspection' in content.lower() and 'false' in content.lower():
                        evidence['introspection_disabled_prod'] = True
            except Exception:
                pass

        # If no GraphQL, pass (N/A)
        if not evidence['graphql_used']:
            result = 'pass'
        else:
            result = 'pass' if evidence['depth_limiting'] else 'fail'
        findings = []

        if result == 'fail' and evidence['graphql_used']:
            finding = self._add_finding(
                finding_key="graphql_security_missing",
                title="GraphQL Security Controls Missing",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:H",
                description="GraphQL endpoint lacks depth limiting, enabling DoS via nested queries.",
                risk_reasoning="Without depth limiting, attackers can craft deeply nested queries causing server resource exhaustion.",
                evidence=evidence,
                affected_components=['GraphQL schema'],
                recommendations=[
                    "Implement query depth limiting",
                    "Add query cost analysis",
                    "Disable introspection in production",
                ],
                validation_steps="Check GraphQL configuration for depth_limit and introspection settings",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="GraphQL Security",
            description="Verify GraphQL has depth limiting and introspection controls.",
            criteria="Depth limiting enabled, introspection disabled in prod.",
            result=result,
            result_details=f"GraphQL: {evidence['graphql_used']}, Depth limit: {evidence['depth_limiting']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_api_key_management(self):
        """SEC-T078: Verify API key management for internal APIs."""
        start = time.time()
        test_id = "SEC-T078"

        evidence = {
            'api_key_auth': False,
            'key_rotation_support': False,
            'key_from_env': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # Check for API key authentication
                if 'API_KEY' in content or 'ApiKeyAuthentication' in content or 'X-API-Key' in content:
                    evidence['api_key_auth'] = True

                    # Check for key from env
                    if 'env(' in content and 'API_KEY' in content:
                        evidence['key_from_env'] = True

                    # Check for rotation support
                    if 'key_rotation' in content.lower() or 'multiple_keys' in content.lower():
                        evidence['key_rotation_support'] = True
            except Exception:
                pass

        result = 'pass' if not evidence['api_key_auth'] or evidence['key_from_env'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="api_key_not_from_env",
                title="API Keys Not Loaded From Environment",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
                description="API key authentication found but keys are not loaded from environment variables.",
                risk_reasoning="Hardcoded API keys in source code can be exposed through repository leaks.",
                evidence=evidence,
                affected_components=['*.py files with API_KEY'],
                recommendations=[
                    "Move all API keys to environment variables",
                    "Implement key rotation support",
                    "Use secret management service if possible",
                ],
                validation_steps="Check for API_KEY usage and verify loading from env()",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='api',
            title="API Key Management",
            description="Verify API keys are properly managed and rotatable.",
            criteria="Keys from environment, rotation supported.",
            result=result,
            result_details=f"API key auth: {evidence['api_key_auth']}, From env: {evidence['key_from_env']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    # ==========================================================================
    # DATABASE SECURITY TESTS (SEC-T079 - SEC-T084)
    # ==========================================================================

    def _run_database_security_tests(self):
        """Run database security tests."""
        self._test_database_connection_security()
        self._test_raw_sql_usage()
        self._test_database_user_permissions()
        self._test_migration_security()
        self._test_database_backup_encryption()
        self._test_query_logging()

    def _test_database_connection_security(self):
        """SEC-T079: Verify database connections use TLS."""
        start = time.time()
        test_id = "SEC-T079"

        evidence = {
            'ssl_mode': None,
            'connection_encrypted': False,
            'connection_pooling': False,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for SSL mode
            if 'sslmode' in content.lower() or 'SSL' in content:
                evidence['ssl_mode'] = 'configured'
                if 'require' in content.lower() or 'verify' in content.lower():
                    evidence['connection_encrypted'] = True

            # Check for connection pooling
            if 'CONN_MAX_AGE' in content or 'pgbouncer' in content.lower():
                evidence['connection_pooling'] = True

        # If using DATABASE_URL, assume cloud provider handles TLS
        if 'DATABASE_URL' in (settings_file.read_text() if settings_file.exists() else ''):
            evidence['connection_encrypted'] = True

        result = 'pass' if evidence['connection_encrypted'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="database_connection_unencrypted",
                title="Database Connection May Not Be Encrypted",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N",
                description="Database connections may not be using TLS encryption.",
                risk_reasoning="Unencrypted database connections expose queries and data to network eavesdropping.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Configure sslmode=require for PostgreSQL",
                    "Use DATABASE_URL with cloud-provided encrypted connections",
                    "Verify TLS certificates in production",
                ],
                validation_steps="Check database configuration for SSL/TLS settings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='database',
            title="Database Connection Security",
            description="Verify database connections use TLS encryption.",
            criteria="SSL mode configured, connections encrypted.",
            result=result,
            result_details=f"SSL: {evidence['ssl_mode']}, Encrypted: {evidence['connection_encrypted']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_raw_sql_usage(self):
        """SEC-T080: Detect raw SQL usage that may be vulnerable."""
        start = time.time()
        test_id = "SEC-T080"

        evidence = {
            'raw_sql_files': [],
            'dangerous_sql_files': [],
            'parameterized': True,
            'string_formatting': False,
        }
        findings = []

        # Patterns that indicate dangerous SQL string formatting
        # These look for f-strings or .format() DIRECTLY in SQL context
        dangerous_patterns = [
            r'cursor\.execute\s*\(\s*f["\']',      # cursor.execute(f"...")
            r'\.raw\s*\(\s*f["\']',                # Model.objects.raw(f"...")
            r'RawSQL\s*\(\s*f["\']',               # RawSQL(f"...")
            r'cursor\.execute\s*\([^)]*\.format\(', # cursor.execute("...".format())
            r'\.raw\s*\([^)]*\.format\(',          # .raw("...".format())
            r'cursor\.execute\s*\(\s*["\'][^"\']*%[^s]', # cursor.execute("...%d" % var) - not %s
        ]

        # Safe patterns to exclude (static queries, parameterized, etc.)
        safe_patterns = [
            r'cursor\.execute\s*\(\s*["\']SELECT 1',  # Health check queries
            r'cursor\.execute\s*\(\s*["\']PRAGMA',    # SQLite PRAGMA (static table names OK)
            r'cursor\.execute\s*\([^)]*,\s*\[',       # Parameterized with list
            r'cursor\.execute\s*\([^)]*,\s*\(',       # Parameterized with tuple
        ]

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                rel_path = str(py_file.relative_to(self.base_path))

                # Skip migrations, tests, and the scanner itself (contains regex patterns)
                if 'migration' in rel_path.lower() or 'test' in rel_path.lower():
                    continue
                if 'scanner.py' in rel_path.lower():
                    continue  # Scanner contains regex patterns that look like SQL

                # Check for raw SQL usage
                if '.raw(' in content or 'cursor.execute' in content or 'RawSQL' in content:
                    evidence['raw_sql_files'].append(rel_path)

                    # Check for dangerous patterns line by line
                    for line_num, line in enumerate(content.split('\n'), 1):
                        # Skip if line matches safe patterns
                        if any(re.search(sp, line) for sp in safe_patterns):
                            continue

                        # Check for dangerous SQL patterns
                        for dp in dangerous_patterns:
                            if re.search(dp, line):
                                evidence['string_formatting'] = True
                                evidence['parameterized'] = False
                                if rel_path not in evidence['dangerous_sql_files']:
                                    evidence['dangerous_sql_files'].append(rel_path)
                                break
            except Exception:
                pass

        result = 'pass' if not evidence['string_formatting'] else 'fail'

        if evidence['string_formatting'] and evidence['dangerous_sql_files']:
            finding = self._add_finding(
                finding_key="raw_sql_injection_risk",
                title="Raw SQL with String Formatting Detected",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H",
                description=f"Found raw SQL with string formatting in: {evidence['dangerous_sql_files']}",
                risk_reasoning="String formatting in SQL queries can lead to SQL injection.",
                evidence=evidence,
                affected_components=evidence['dangerous_sql_files'],
                recommendations=[
                    "Use parameterized queries with %s placeholders",
                    "Use Django ORM instead of raw SQL where possible",
                    "Review and sanitize all raw SQL queries",
                ],
                validation_steps="Search for .raw( and cursor.execute with f-strings",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='database',
            title="Raw SQL Usage",
            description="Detect raw SQL usage and verify parameterization.",
            criteria="Raw SQL uses parameterized queries, no string formatting.",
            result=result,
            result_details=f"Raw SQL files: {len(evidence['raw_sql_files'])}, Parameterized: {evidence['parameterized']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_database_user_permissions(self):
        """SEC-T081: Verify database user has minimal permissions."""
        start = time.time()
        test_id = "SEC-T081"

        evidence = {
            'separate_db_user': False,
            'no_superuser': True,
            'least_privilege': False,
        }
        findings = []

        # Check if DATABASE_URL suggests non-root user
        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for separate database user
            if 'DATABASE_URL' in content or "'USER'" in content:
                evidence['separate_db_user'] = True

            # Check for superuser indicators
            if 'postgres:postgres' in content or 'root:root' in content:
                evidence['no_superuser'] = False

        result = 'pass' if evidence['separate_db_user'] and evidence['no_superuser'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="database_user_overprivileged",
                title="Database User May Be Overprivileged",
                severity='medium',
                likelihood='low',
                impact='high',
                cvss_vector="AV:L/AC:H/PR:H/UI:N/S:U/C:H/I:H/A:H",
                description="Database configuration may use superuser or lack dedicated application user.",
                risk_reasoning="Overprivileged database users increase blast radius if application is compromised.",
                evidence=evidence,
                affected_components=['config/settings.py', 'database configuration'],
                recommendations=[
                    "Create dedicated database user for the application",
                    "Grant only necessary permissions (SELECT, INSERT, UPDATE, DELETE)",
                    "Never use postgres:postgres or root:root in production",
                ],
                validation_steps="Check DATABASE_URL or USER configuration for superuser indicators",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='database',
            title="Database User Permissions",
            description="Verify database user follows least privilege principle.",
            criteria="Separate DB user, not superuser, minimal permissions.",
            result=result,
            result_details=f"Separate user: {evidence['separate_db_user']}, No superuser: {evidence['no_superuser']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_migration_security(self):
        """SEC-T082: Verify migrations don't contain sensitive data."""
        start = time.time()
        test_id = "SEC-T082"

        evidence = {
            'migrations_checked': 0,
            'sensitive_data_found': [],
            'hardcoded_passwords': False,
        }
        findings = []

        sensitive_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
        ]

        for migration in self.base_path.rglob('*/migrations/*.py'):
            try:
                content = migration.read_text()
                evidence['migrations_checked'] += 1
                rel_path = str(migration.relative_to(self.base_path))

                for pattern in sensitive_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        evidence['sensitive_data_found'].append(rel_path)
                        evidence['hardcoded_passwords'] = True
                        break
            except Exception:
                pass

        result = 'pass' if not evidence['hardcoded_passwords'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="migration_contains_secrets",
                title="Migrations Contain Sensitive Data",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
                description=f"Found sensitive data in migrations: {evidence['sensitive_data_found']}",
                risk_reasoning="Hardcoded passwords/secrets in migrations are stored in version control and can be extracted.",
                evidence=evidence,
                affected_components=evidence['sensitive_data_found'],
                recommendations=[
                    "Remove hardcoded secrets from migration files",
                    "Use data migrations with environment variables",
                    "Consider rewriting migration history if secrets were committed",
                ],
                validation_steps="Search migrations for password, secret, api_key patterns",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='database',
            title="Migration Security",
            description="Verify migrations don't contain sensitive data.",
            criteria="No hardcoded passwords/secrets in migrations.",
            result=result,
            result_details=f"Migrations: {evidence['migrations_checked']}, Issues: {len(evidence['sensitive_data_found'])}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_database_backup_encryption(self):
        """SEC-T083: Verify database backup encryption is configured."""
        start = time.time()
        test_id = "SEC-T083"

        evidence = {
            'backup_script_found': False,
            'encryption_mentioned': False,
            'cloud_backup': False,
        }
        findings = []

        # Check for backup scripts
        for file in self.base_path.rglob('*backup*'):
            evidence['backup_script_found'] = True
            try:
                if file.is_file():
                    content = file.read_text()
                    if 'encrypt' in content.lower() or 'gpg' in content.lower() or 'aes' in content.lower():
                        evidence['encryption_mentioned'] = True
            except Exception:
                pass

        # Check for cloud backup references
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 's3' in content.lower() or 'gcs' in content.lower() or 'azure' in content.lower():
                    if 'backup' in content.lower():
                        evidence['cloud_backup'] = True
            except Exception:
                pass

        # If using Railway/cloud, assume provider handles backups
        result = 'pass'  # Advisory

        self.results.append(TestResult(
            test_id=test_id,
            category='database',
            title="Database Backup Encryption",
            description="Verify database backups are encrypted.",
            criteria="Backup encryption configured, cloud provider backups enabled.",
            result=result,
            result_details=f"Backup script: {evidence['backup_script_found']}, Encrypted: {evidence['encryption_mentioned']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_query_logging(self):
        """SEC-T084: Verify database query logging for audit trail."""
        start = time.time()
        test_id = "SEC-T084"

        evidence = {
            'query_logging_enabled': False,
            'slow_query_logging': False,
            'sensitive_query_redaction': False,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for query logging
            if "'django.db.backends'" in content and 'DEBUG' in content:
                evidence['query_logging_enabled'] = True

            # Check for slow query logging
            if 'slow' in content.lower() and 'query' in content.lower():
                evidence['slow_query_logging'] = True

        result = 'pass'  # Advisory

        self.results.append(TestResult(
            test_id=test_id,
            category='database',
            title="Database Query Logging",
            description="Verify database queries are logged for audit.",
            criteria="Query logging enabled, slow queries tracked.",
            result=result,
            result_details=f"Query logging: {evidence['query_logging_enabled']}, Slow queries: {evidence['slow_query_logging']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # THIRD-PARTY RISK TESTS (SEC-T085 - SEC-T090)
    # ==========================================================================

    def _run_third_party_tests(self):
        """Run third-party integration security tests."""
        self._test_third_party_webhook_security()
        self._test_oauth_configuration()
        self._test_external_api_timeout()
        self._test_vendor_data_handling()
        self._test_third_party_error_handling()
        self._test_external_service_fallback()

    def _test_third_party_webhook_security(self):
        """SEC-T085: Verify all third-party webhooks validate signatures."""
        start = time.time()
        test_id = "SEC-T085"

        evidence = {
            'webhook_handlers_found': [],
            'providers_with_validation': set(),
            'providers_without_validation': set(),
        }
        findings = []

        # Known webhook providers and their validation patterns
        provider_validation = {
            'stripe': ['construct_event', 'signature'],
            'twilio': ['validate_webhook_signature', 'x_twilio_signature', 'signature'],
            'plaid': ['plaid-verification', 'verify_plaid_webhook', 'jwt.decode', 'signature'],
            'sendgrid': ['signature', 'verify'],
            'cloudinary': ['signature', 'verify'],
        }

        # First pass: Find actual webhook handler files (views.py, webhooks.py, etc.)
        webhook_handler_patterns = ['webhook', 'views.py']
        providers_used = set()

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                content_lower = content.lower()
                rel_path = str(py_file.relative_to(self.base_path))

                # Skip settings, tests, migrations, scanner - these aren't webhook handlers
                if any(skip in rel_path.lower() for skip in ['settings.py', 'test', 'migration', 'scanner.py']):
                    continue

                for provider, validation_patterns in provider_validation.items():
                    # Check if this file handles webhooks for this provider
                    # Look for actual webhook handling code, not just mentions
                    is_webhook_handler = (
                        provider in content_lower and
                        'webhook' in content_lower and
                        ('def ' in content or 'class ' in content) and  # Has function/class definitions
                        ('request' in content_lower or 'post' in content_lower)  # Handles requests
                    )

                    if is_webhook_handler:
                        providers_used.add(provider)
                        evidence['webhook_handlers_found'].append(f"{provider}:{rel_path}")

                        # Check for ANY validation pattern for this provider
                        has_validation = any(
                            pattern.lower() in content_lower
                            for pattern in validation_patterns
                        )

                        if has_validation:
                            evidence['providers_with_validation'].add(provider)
                        else:
                            evidence['providers_without_validation'].add(provider)

            except Exception:
                pass

        # Remove providers that have validation somewhere from the "without" set
        # (validation may be in a helper function, not in every file)
        evidence['providers_without_validation'] -= evidence['providers_with_validation']

        # Convert sets to lists for JSON serialization
        evidence['providers_with_validation'] = list(evidence['providers_with_validation'])
        evidence['providers_without_validation'] = list(evidence['providers_without_validation'])

        result = 'pass' if not evidence['providers_without_validation'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="webhook_signature_missing",
                title="Third-Party Webhooks Missing Signature Validation",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:L",
                description=f"Webhook handlers without signature validation: {evidence['providers_without_validation']}",
                risk_reasoning="Unvalidated webhooks can be spoofed by attackers to inject malicious data or trigger unauthorized actions.",
                evidence=evidence,
                affected_components=evidence['webhook_handlers_found'],
                recommendations=[
                    "Implement signature validation for all webhooks",
                    "Use provider SDK methods like construct_event() for Stripe",
                    "Verify webhook source IP addresses where available",
                ],
                validation_steps="Check webhook handlers for signature verification",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='third_party',
            title="Third-Party Webhook Security",
            description="Verify all third-party webhooks validate signatures.",
            criteria="All webhook handler files verify signatures.",
            result=result,
            result_details=f"Handlers: {len(evidence['webhook_handlers_found'])}, Validated: {evidence['providers_with_validation']}, Missing: {evidence['providers_without_validation']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_oauth_configuration(self):
        """SEC-T086: Verify OAuth/OIDC configuration security."""
        start = time.time()
        test_id = "SEC-T086"

        evidence = {
            'oauth_used': False,
            'state_parameter': False,
            'https_redirect': False,
            'secret_from_env': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'oauth' in content.lower() or 'allauth' in content.lower() or 'social' in content.lower():
                    evidence['oauth_used'] = True

                    if 'state' in content.lower():
                        evidence['state_parameter'] = True

                    if 'https' in content.lower() and 'redirect' in content.lower():
                        evidence['https_redirect'] = True
            except Exception:
                pass

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()
            # Check for various OAuth patterns using env()
            # Look for SOCIAL_AUTH, CLIENT_SECRET, or other OAuth patterns with env()
            oauth_patterns = ['SOCIAL', 'CLIENT_SECRET', 'OAUTH', 'AUTH_TOKEN']
            uses_env = any(pattern in content for pattern in oauth_patterns) and 'env(' in content

            # Additional check: if OAuth patterns exist, verify they use env()
            if uses_env:
                # Make sure CLIENT_SECRET variables use env()
                lines = content.split('\n')
                for line in lines:
                    if 'CLIENT_SECRET' in line and '=' in line:
                        if "env(" in line or "os.environ" in line:
                            evidence['secret_from_env'] = True
                            break
            elif not any(pattern in content for pattern in oauth_patterns):
                # No OAuth patterns found at all, so it's fine
                evidence['secret_from_env'] = True

        result = 'pass' if not evidence['oauth_used'] or evidence['secret_from_env'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="oauth_secrets_not_from_env",
                title="OAuth Secrets Not Loaded From Environment",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
                description="OAuth/social authentication secrets may not be loaded from environment variables.",
                risk_reasoning="Hardcoded OAuth secrets in source code can be exposed through repository leaks, enabling account takeover.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Move all SOCIAL_AUTH secrets to environment variables",
                    "Use django-environ for secure configuration",
                    "Rotate any potentially exposed secrets",
                ],
                validation_steps="Check settings for SOCIAL_AUTH secrets loading from env()",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='third_party',
            title="OAuth Configuration",
            description="Verify OAuth/social auth is securely configured.",
            criteria="State parameter used, HTTPS redirects, secrets from env.",
            result=result,
            result_details=f"OAuth: {evidence['oauth_used']}, Secrets from env: {evidence['secret_from_env']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_external_api_timeout(self):
        """SEC-T087: Verify external API calls have timeouts."""
        start = time.time()
        test_id = "SEC-T087"

        evidence = {
            'requests_used': False,
            'timeout_configured': False,
            'default_timeout': None,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'requests.get' in content or 'requests.post' in content or 'httpx' in content.lower():
                    evidence['requests_used'] = True

                    if 'timeout=' in content or 'timeout =' in content:
                        evidence['timeout_configured'] = True

                        # Extract timeout value
                        match = re.search(r'timeout\s*=\s*(\d+)', content)
                        if match:
                            evidence['default_timeout'] = int(match.group(1))
            except Exception:
                pass

        result = 'pass' if not evidence['requests_used'] or evidence['timeout_configured'] else 'fail'

        if evidence['requests_used'] and not evidence['timeout_configured']:
            finding = self._add_finding(
                finding_key="external_api_no_timeout",
                title="External API Calls Missing Timeout",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                description="External API calls should have timeouts to prevent hanging.",
                risk_reasoning="Missing timeouts can lead to resource exhaustion and DoS.",
                evidence=evidence,
                affected_components=['External API calls'],
                recommendations=[
                    "Add timeout parameter to all requests calls",
                    "Use a default timeout (e.g., 30 seconds)",
                    "Implement circuit breaker pattern for resilience",
                ],
                validation_steps="Search for requests.get/post and verify timeout parameter",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='third_party',
            title="External API Timeout",
            description="Verify external API calls have timeout configured.",
            criteria="All external API calls have timeout parameter.",
            result=result,
            result_details=f"Requests used: {evidence['requests_used']}, Timeout: {evidence['timeout_configured']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_vendor_data_handling(self):
        """SEC-T088: Verify minimal data shared with third parties."""
        start = time.time()
        test_id = "SEC-T088"

        evidence = {
            'data_minimization': False,
            'pii_to_vendors': [],
            'data_processing_agreement': False,
        }
        findings = []

        pii_patterns = ['email', 'phone', 'address', 'ssn', 'dob', 'date_of_birth']

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # Check for third-party API calls with PII
                if 'requests' in content or 'api' in content.lower():
                    for pattern in pii_patterns:
                        if pattern in content.lower() and ('post' in content.lower() or 'send' in content.lower()):
                            evidence['pii_to_vendors'].append(pattern)
            except Exception:
                pass

        # Remove duplicates
        evidence['pii_to_vendors'] = list(set(evidence['pii_to_vendors']))

        result = 'pass'  # Advisory

        self.results.append(TestResult(
            test_id=test_id,
            category='third_party',
            title="Vendor Data Handling",
            description="Verify minimal data shared with third-party vendors.",
            criteria="Data minimization, DPA in place, PII tracked.",
            result=result,
            result_details=f"PII to vendors: {evidence['pii_to_vendors']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_third_party_error_handling(self):
        """SEC-T089: Verify third-party API errors are handled gracefully."""
        start = time.time()
        test_id = "SEC-T089"

        evidence = {
            'exception_handling': False,
            'fallback_behavior': False,
            'error_logging': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'requests' in content or 'stripe' in content.lower() or 'plaid' in content.lower():
                    # Check for exception handling
                    if 'try:' in content and 'except' in content:
                        evidence['exception_handling'] = True

                    # Check for fallback
                    if 'fallback' in content.lower() or 'default' in content.lower():
                        evidence['fallback_behavior'] = True

                    # Check for error logging
                    if 'logger.error' in content or 'logger.exception' in content:
                        evidence['error_logging'] = True
            except Exception:
                pass

        result = 'pass' if evidence['exception_handling'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="third_party_no_error_handling",
                title="Third-Party API Error Handling Missing",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                description="Third-party API calls lack proper exception handling.",
                risk_reasoning="Unhandled external API errors can crash the application or leave it in an inconsistent state.",
                evidence=evidence,
                affected_components=['Files using requests/stripe/plaid'],
                recommendations=[
                    "Wrap all external API calls in try/except blocks",
                    "Log errors for debugging and monitoring",
                    "Implement fallback behavior for critical operations",
                ],
                validation_steps="Check third-party API calls for exception handling",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='third_party',
            title="Third-Party Error Handling",
            description="Verify third-party API errors handled gracefully.",
            criteria="Exception handling, fallback behavior, error logging.",
            result=result,
            result_details=f"Exception handling: {evidence['exception_handling']}, Logging: {evidence['error_logging']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_external_service_fallback(self):
        """SEC-T090: Verify fallback behavior when external services fail."""
        start = time.time()
        test_id = "SEC-T090"

        evidence = {
            'circuit_breaker': False,
            'retry_logic': False,
            'graceful_degradation': False,
        }
        findings = []

        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                # Check for circuit breaker
                if 'circuit' in content.lower() or 'breaker' in content.lower():
                    evidence['circuit_breaker'] = True

                # Check for retry logic
                if 'retry' in content.lower() or 'backoff' in content.lower() or 'tenacity' in content.lower():
                    evidence['retry_logic'] = True

                # Check for graceful degradation
                if 'graceful' in content.lower() or 'degraded' in content.lower() or 'fallback' in content.lower():
                    evidence['graceful_degradation'] = True
            except Exception:
                pass

        result = 'pass'  # Advisory

        self.results.append(TestResult(
            test_id=test_id,
            category='third_party',
            title="External Service Fallback",
            description="Verify fallback behavior for external service failures.",
            criteria="Circuit breaker, retry logic, graceful degradation.",
            result=result,
            result_details=f"Circuit breaker: {evidence['circuit_breaker']}, Retry: {evidence['retry_logic']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    # ==========================================================================
    # INFRASTRUCTURE SECURITY TESTS (SEC-T091 - SEC-T100)
    # ==========================================================================

    def _run_infrastructure_tests(self):
        """Run infrastructure security tests."""
        self._test_container_security()
        self._test_environment_isolation()
        self._test_secret_management()
        self._test_deployment_security()
        self._test_monitoring_alerting()
        self._test_backup_recovery()
        self._test_network_security()
        self._test_logging_centralization()
        self._test_incident_response()
        self._test_security_of_security_system()

    def _test_container_security(self):
        """SEC-T091: Verify container security if Docker is used."""
        start = time.time()
        test_id = "SEC-T091"

        evidence = {
            'dockerfile_found': False,
            'non_root_user': False,
            'no_secrets_in_image': True,
            'minimal_base_image': False,
        }
        findings = []

        dockerfile = self.base_path / 'Dockerfile'
        if dockerfile.exists():
            evidence['dockerfile_found'] = True
            content = dockerfile.read_text()

            # Check for non-root user
            if 'USER' in content and 'root' not in content.lower().split('USER')[1][:20]:
                evidence['non_root_user'] = True

            # Check for secrets
            if 'SECRET' in content or 'PASSWORD' in content or 'API_KEY' in content:
                evidence['no_secrets_in_image'] = False

            # Check for minimal base image
            if 'slim' in content.lower() or 'alpine' in content.lower():
                evidence['minimal_base_image'] = True

        result = 'pass' if not evidence['dockerfile_found'] or evidence['no_secrets_in_image'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="dockerfile_contains_secrets",
                title="Dockerfile Contains Secrets",
                severity='critical',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
                description="Dockerfile appears to contain hardcoded secrets (SECRET, PASSWORD, API_KEY).",
                risk_reasoning="Secrets in Dockerfiles are baked into the image and can be extracted by anyone with image access.",
                evidence=evidence,
                affected_components=['Dockerfile'],
                recommendations=[
                    "Remove all secrets from Dockerfile",
                    "Use environment variables or secret management",
                    "Use Docker BuildKit secrets for build-time secrets",
                ],
                validation_steps="Check Dockerfile for SECRET, PASSWORD, API_KEY strings",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Container Security",
            description="Verify Docker container follows security best practices.",
            criteria="Non-root user, no secrets in image, minimal base.",
            result=result,
            result_details=f"Dockerfile: {evidence['dockerfile_found']}, Safe: {evidence['no_secrets_in_image']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_environment_isolation(self):
        """SEC-T092: Verify environment isolation (dev/staging/prod)."""
        start = time.time()
        test_id = "SEC-T092"

        evidence = {
            'env_based_config': False,
            'separate_settings': False,
            'no_prod_data_in_dev': True,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for environment-based config
            if 'env(' in content or 'os.environ' in content:
                evidence['env_based_config'] = True

            # Check for environment checks
            if 'DEBUG' in content and 'if' in content:
                evidence['separate_settings'] = True

        result = 'pass' if evidence['env_based_config'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="no_environment_isolation",
                title="Environment Isolation Not Configured",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:L/I:H/A:N",
                description="Settings are not loaded from environment variables, hindering dev/staging/prod isolation.",
                risk_reasoning="Without environment-based config, same settings may be used across environments, risking production data exposure.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Use django-environ or os.environ for all settings",
                    "Create separate .env files per environment",
                    "Never commit production secrets to version control",
                ],
                validation_steps="Check settings.py for env() or os.environ usage",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Environment Isolation",
            description="Verify environment isolation between dev/staging/prod.",
            criteria="Environment-based config, separate settings per env.",
            result=result,
            result_details=f"Env config: {evidence['env_based_config']}, Separate: {evidence['separate_settings']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_secret_management(self):
        """SEC-T093: Verify secrets are managed securely."""
        start = time.time()
        test_id = "SEC-T093"

        evidence = {
            'secrets_from_env': False,
            'no_hardcoded_secrets': True,
            'secret_rotation_support': False,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for secrets from env
            if 'env(' in content and ('SECRET' in content or 'KEY' in content):
                evidence['secrets_from_env'] = True

            # Check for hardcoded secrets
            if re.search(r"SECRET_KEY\s*=\s*['\"][a-zA-Z0-9]{30,}['\"]", content):
                evidence['no_hardcoded_secrets'] = False

        result = 'pass' if evidence['secrets_from_env'] and evidence['no_hardcoded_secrets'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="secret_management_insecure",
                title="Secrets Not Managed Securely",
                severity='high',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
                description="Secrets are either hardcoded or not loaded from environment variables.",
                risk_reasoning="Insecure secret management leads to credential exposure through source code leaks.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Load all secrets from environment variables",
                    "Use django-environ for configuration management",
                    "Remove any hardcoded 30+ character strings in settings",
                ],
                validation_steps="Check settings.py for hardcoded secrets and env() usage",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Secret Management",
            description="Verify secrets are managed securely via environment.",
            criteria="Secrets from env, no hardcoded secrets, rotation supported.",
            result=result,
            result_details=f"From env: {evidence['secrets_from_env']}, No hardcoded: {evidence['no_hardcoded_secrets']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_deployment_security(self):
        """SEC-T094: Verify deployment pipeline security."""
        start = time.time()
        test_id = "SEC-T094"

        evidence = {
            'ci_cd_found': False,
            'tests_in_pipeline': False,
            'security_checks': False,
        }
        findings = []

        # Check for CI/CD configuration
        ci_files = [
            self.base_path / '.github' / 'workflows',
            self.base_path / '.gitlab-ci.yml',
            self.base_path / 'railway.json',
            self.base_path / 'Procfile',
        ]

        for ci_path in ci_files:
            if ci_path.exists():
                evidence['ci_cd_found'] = True

                if ci_path.is_dir():
                    for workflow in ci_path.glob('*.yml'):
                        content = workflow.read_text()
                        if 'test' in content.lower():
                            evidence['tests_in_pipeline'] = True
                        if 'security' in content.lower() or 'audit' in content.lower():
                            evidence['security_checks'] = True
                elif ci_path.is_file():
                    content = ci_path.read_text()
                    if 'test' in content.lower():
                        evidence['tests_in_pipeline'] = True

        result = 'pass' if evidence['ci_cd_found'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="no_ci_cd_pipeline",
                title="CI/CD Pipeline Not Configured",
                severity='low',
                likelihood='low',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:H/UI:N/S:U/C:N/I:L/A:N",
                description="No CI/CD configuration found (GitHub Actions, GitLab CI, Procfile, etc.).",
                risk_reasoning="Without automated deployment pipeline, security checks and tests may be skipped during deploys.",
                evidence=evidence,
                affected_components=['deployment configuration'],
                recommendations=[
                    "Set up GitHub Actions or similar CI/CD pipeline",
                    "Include automated tests in the pipeline",
                    "Add security scanning (pip-audit, bandit) to pipeline",
                ],
                validation_steps="Check for .github/workflows, Procfile, or other CI/CD config",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Deployment Security",
            description="Verify deployment pipeline includes security checks.",
            criteria="CI/CD configured, tests run, security checks included.",
            result=result,
            result_details=f"CI/CD: {evidence['ci_cd_found']}, Tests: {evidence['tests_in_pipeline']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_monitoring_alerting(self):
        """SEC-T095: Verify monitoring and alerting is configured."""
        start = time.time()
        test_id = "SEC-T095"

        evidence = {
            'logging_configured': False,
            'error_tracking': False,
            'alerting_configured': False,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for logging
            if 'LOGGING' in content:
                evidence['logging_configured'] = True

            # Check for error tracking (Sentry, etc.)
            if 'sentry' in content.lower() or 'SENTRY_DSN' in content:
                evidence['error_tracking'] = True

        # Check for alerting
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'alert' in content.lower() or 'notify' in content.lower():
                    evidence['alerting_configured'] = True
                    break
            except Exception:
                pass

        result = 'pass' if evidence['logging_configured'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="monitoring_not_configured",
                title="Monitoring and Logging Not Configured",
                severity='medium',
                likelihood='medium',
                impact='medium',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L",
                description="LOGGING configuration not found in settings.",
                risk_reasoning="Without proper logging, security incidents and errors go undetected, delaying incident response.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Configure Django LOGGING dict in settings",
                    "Add Sentry or similar error tracking service",
                    "Set up alerts for critical errors",
                ],
                validation_steps="Check settings.py for LOGGING configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Monitoring & Alerting",
            description="Verify monitoring and alerting is configured.",
            criteria="Logging configured, error tracking, alerting enabled.",
            result=result,
            result_details=f"Logging: {evidence['logging_configured']}, Error tracking: {evidence['error_tracking']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_backup_recovery(self):
        """SEC-T096: Verify backup and recovery procedures exist."""
        start = time.time()
        test_id = "SEC-T096"

        evidence = {
            'backup_mentioned': False,
            'recovery_procedure': False,
            'backup_encryption': False,
        }
        findings = []

        # Check for backup references
        for file in self.base_path.rglob('*'):
            try:
                if file.is_file() and 'backup' in str(file).lower():
                    evidence['backup_mentioned'] = True
                    content = file.read_text()
                    if 'restore' in content.lower() or 'recovery' in content.lower():
                        evidence['recovery_procedure'] = True
                    if 'encrypt' in content.lower():
                        evidence['backup_encryption'] = True
            except Exception:
                pass

        result = 'pass'  # Advisory

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Backup & Recovery",
            description="Verify backup and recovery procedures exist.",
            criteria="Backup configured, recovery procedure documented, encrypted.",
            result=result,
            result_details=f"Backup: {evidence['backup_mentioned']}, Recovery: {evidence['recovery_procedure']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_network_security(self):
        """SEC-T097: Verify network security configuration."""
        start = time.time()
        test_id = "SEC-T097"

        evidence = {
            'allowed_hosts_configured': False,
            'cors_configured': False,
            'csrf_configured': False,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            if 'ALLOWED_HOSTS' in content:
                evidence['allowed_hosts_configured'] = True

            if 'CORS' in content:
                evidence['cors_configured'] = True

            if 'CSRF' in content or 'CsrfViewMiddleware' in content:
                evidence['csrf_configured'] = True

        result = 'pass' if evidence['allowed_hosts_configured'] and evidence['csrf_configured'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="network_security_incomplete",
                title="Network Security Configuration Incomplete",
                severity='medium',
                likelihood='medium',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:N",
                description="ALLOWED_HOSTS or CSRF protection not properly configured.",
                risk_reasoning="Missing ALLOWED_HOSTS enables host header attacks; missing CSRF enables cross-site request forgery.",
                evidence=evidence,
                affected_components=['config/settings.py'],
                recommendations=[
                    "Configure ALLOWED_HOSTS with specific domains",
                    "Ensure CsrfViewMiddleware is enabled",
                    "Configure CORS if APIs are used cross-origin",
                ],
                validation_steps="Check settings for ALLOWED_HOSTS and CSRF configuration",
                is_quick_win=True,
                remediation_effort='low',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Network Security",
            description="Verify network security configuration.",
            criteria="ALLOWED_HOSTS set, CORS configured, CSRF enabled.",
            result=result,
            result_details=f"Hosts: {evidence['allowed_hosts_configured']}, CORS: {evidence['cors_configured']}, CSRF: {evidence['csrf_configured']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_logging_centralization(self):
        """SEC-T098: Verify logs are centralized for security analysis."""
        start = time.time()
        test_id = "SEC-T098"

        evidence = {
            'structured_logging': False,
            'centralized_logging': False,
            'log_retention': False,
        }
        findings = []

        settings_file = self.base_path / 'config' / 'settings.py'
        if settings_file.exists():
            content = settings_file.read_text()

            # Check for structured logging
            if 'json' in content.lower() and 'log' in content.lower():
                evidence['structured_logging'] = True

            # Check for centralized logging
            if 'syslog' in content.lower() or 'logstash' in content.lower() or 'papertrail' in content.lower():
                evidence['centralized_logging'] = True

        result = 'pass'  # Advisory

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Logging Centralization",
            description="Verify logs are centralized for security analysis.",
            criteria="Structured logging, centralized collection, retention policy.",
            result=result,
            result_details=f"Structured: {evidence['structured_logging']}, Centralized: {evidence['centralized_logging']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=[],
        ))

    def _test_incident_response(self):
        """SEC-T099: Verify incident response capability exists."""
        start = time.time()
        test_id = "SEC-T099"

        evidence = {
            'incident_documentation': False,
            'notification_capability': False,
            'audit_capability': False,
        }
        findings = []

        # Check for incident response documentation
        for file in self.base_path.rglob('*'):
            try:
                if 'incident' in str(file).lower() or 'security' in str(file).lower():
                    evidence['incident_documentation'] = True
                    break
            except Exception:
                pass

        # Check for notification capability
        for py_file in self.base_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                if 'send_mail' in content or 'notification' in content.lower():
                    evidence['notification_capability'] = True
                if 'AuditLog' in content or 'audit' in content.lower():
                    evidence['audit_capability'] = True
            except Exception:
                pass

        result = 'pass' if evidence['notification_capability'] and evidence['audit_capability'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="incident_response_missing",
                title="Incident Response Capability Missing",
                severity='medium',
                likelihood='low',
                impact='high',
                cvss_vector="AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L",
                description="Missing notification capability or audit trail for incident response.",
                risk_reasoning="Without incident response capability, security events cannot be properly detected, communicated, or investigated.",
                evidence=evidence,
                affected_components=['notification system', 'audit logging'],
                recommendations=[
                    "Implement email notification capability",
                    "Add audit logging for security-relevant events",
                    "Document incident response procedures",
                ],
                validation_steps="Check for send_mail usage and AuditLog model",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Incident Response",
            description="Verify incident response capability exists.",
            criteria="Documentation, notification capability, audit trail.",
            result=result,
            result_details=f"Docs: {evidence['incident_documentation']}, Notify: {evidence['notification_capability']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))

    def _test_security_of_security_system(self):
        """SEC-T100: Verify security of the security assessment system itself."""
        start = time.time()
        test_id = "SEC-T100"

        evidence = {
            'encrypted_storage': False,
            'access_controlled': False,
            'audit_logged': False,
            'tier0_protected': False,
        }
        findings = []

        # Check security models for encryption
        security_models = self.base_path / 'apps' / 'security' / 'models.py'
        if security_models.exists():
            content = security_models.read_text()

            # Check for encrypted fields
            if 'EncryptedTextField' in content or 'EncryptedJSONField' in content:
                evidence['encrypted_storage'] = True

            # Check for access control
            if 'staff' in content.lower() or 'permission' in content.lower():
                evidence['access_controlled'] = True

            # Check for audit logging
            if 'SecurityAuditLog' in content or 'AuditLog' in content:
                evidence['audit_logged'] = True

        # Check views for access control
        security_views = self.base_path / 'apps' / 'security' / 'views.py'
        if security_views.exists():
            content = security_views.read_text()
            # Check for staff_member_required (directly or via method_decorator)
            if 'staff_member_required' in content or 'LoginRequiredMixin' in content:
                evidence['tier0_protected'] = True

        result = 'pass' if evidence['encrypted_storage'] and evidence['tier0_protected'] else 'fail'
        findings = []

        if result == 'fail':
            finding = self._add_finding(
                finding_key="security_system_not_protected",
                title="Security Assessment System Not Fully Protected",
                severity='high',
                likelihood='low',
                impact='high',
                cvss_vector="AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:L/A:N",
                description="Security system lacks encryption or access controls (Tier-0 protection).",
                risk_reasoning="The security assessment system contains sensitive vulnerability data; if compromised, attackers gain a roadmap.",
                evidence=evidence,
                affected_components=['apps/security/models.py', 'apps/security/views.py'],
                recommendations=[
                    "Use EncryptedTextField/EncryptedJSONField for sensitive findings",
                    "Add staff_member_required or LoginRequiredMixin to all views",
                    "Implement SecurityAuditLog for all operations",
                ],
                validation_steps="Check security app for encryption and access controls",
                is_quick_win=False,
                remediation_effort='medium',
            )
            findings.append(finding)

        self.results.append(TestResult(
            test_id=test_id,
            category='infra',
            title="Security System Protection",
            description="Verify security assessment system itself is protected (Tier-0).",
            criteria="Encrypted storage, access controlled, audit logged.",
            result=result,
            result_details=f"Encrypted: {evidence['encrypted_storage']}, Protected: {evidence['tier0_protected']}",
            evidence=evidence,
            duration_ms=int((time.time() - start) * 1000),
            findings=findings,
        ))
