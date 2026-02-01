# ==============================================================================
# File: apps/security/report_generator.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security report generation - executive summary, attack paths, remediation
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Security Report Generator

Generates comprehensive security reports including:
- Executive summary
- Attack path narratives
- Failure mode analysis
- CISO sleep test
- Remediation prompt (copy-paste for Claude)
"""

from typing import List


class ReportGenerator:
    """Generate security assessment reports."""

    def __init__(self, run, test_results: List, findings: List, scores):
        """
        Initialize report generator.

        Args:
            run: SecurityRun instance
            test_results: List of TestResult objects
            findings: List of Finding objects
            scores: ScoreResult from scoring engine
        """
        self.run = run
        self.test_results = test_results
        self.findings = findings
        self.scores = scores

    def generate_executive_summary(self) -> str:
        """Generate executive summary (1 page max)."""
        passed = sum(1 for t in self.test_results if t.result == 'pass')
        sum(1 for t in self.test_results if t.result == 'fail')
        total = len(self.test_results)

        # Determine overall posture
        if self.scores.securityscorecard_grade in ['A', 'B']:
            posture = "GOOD"
            posture_desc = "The application demonstrates strong security practices with well-implemented controls."
        elif self.scores.securityscorecard_grade == 'C':
            posture = "FAIR"
            posture_desc = "The application has adequate security but has areas requiring attention."
        else:
            posture = "NEEDS IMPROVEMENT"
            posture_desc = "The application has significant security gaps that should be addressed promptly."

        # Top risks
        top_risks = sorted(self.findings, key=lambda f: f.cvss_score, reverse=True)[:5]

        # Top actions
        quick_wins = [f for f in self.findings if f.is_quick_win]

        summary = f"""
EXECUTIVE SUMMARY
=================
Assessment Date: {self.run.run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Overall Posture: {posture}

{posture_desc}

KEY METRICS:
- Tests Run: {total}
- Tests Passed: {passed} ({passed*100//total if total else 0}%)
- Security Grade: {self.scores.securityscorecard_grade}
- BitSight Score: {self.scores.bitsight_score}/900
- Risk Score: {self.scores.risk_score_0_100}/100
- Maturity Level: {self.scores.maturity_level}/3

FINDINGS SUMMARY:
- Critical: {self.scores.cvss_critical_count}
- High: {self.scores.cvss_high_count}
- Medium: {self.scores.cvss_medium_count}
- Low: {self.scores.cvss_low_count}

TOP 5 RISKS:
"""
        for i, risk in enumerate(top_risks, 1):
            summary += f"{i}. [{risk.severity.upper()}] {risk.title} (CVSS {risk.cvss_score})\n"

        summary += """
TOP 5 RECOMMENDED ACTIONS:
"""
        actions = quick_wins[:5] if quick_wins else top_risks[:5]
        for i, action in enumerate(actions, 1):
            recs = action.recommendations if hasattr(action, 'recommendations') else []
            rec = recs[0] if recs else "Address this finding"
            summary += f"{i}. {rec}\n"

        summary += f"""
WHAT'S WORKING WELL:
- {passed} of {total} security tests passing
- Encryption at rest implemented for sensitive data
- Rate limiting configured for authentication
- CSP with nonces for XSS protection
- Audit logging for financial operations

UNKNOWNS/ASSUMPTIONS:
- pip-audit not available for dependency vulnerability scan
- WAF/CDN configuration not verifiable from code
- Production DEBUG setting assumed from env configuration
"""
        return summary.strip()

    def generate_attack_paths(self) -> List[dict]:
        """Generate attack path narratives for high-risk areas."""
        paths = []

        # Check for credential-related findings
        cred_findings = [f for f in self.findings if 'credential' in f.title.lower() or 'api key' in f.title.lower() or 'secret' in f.title.lower()]
        if cred_findings:
            paths.append({
                'title': 'Credential Exposure Attack',
                'attacker_goal': 'Gain unauthorized access via exposed credentials',
                'steps': [
                    'Attacker discovers repository (public or via insider access)',
                    'Attacker searches for API keys in documentation/code',
                    'Attacker extracts hardcoded credentials from CLAUDE.md or similar',
                    'Attacker authenticates to admin API using stolen key',
                    'Attacker manipulates task system or extracts sensitive data',
                ],
                'controls_encountered': [
                    'Rate limiting on API endpoints (partial mitigation)',
                    'API key validation (bypassed with valid key)',
                ],
                'outcome': 'Successful unauthorized access to admin functionality',
                'business_impact': 'Task manipulation, potential data exposure, operational disruption',
            })

        # Check for auth-related findings
        auth_findings = [f for f in self.findings if 'mfa' in f.title.lower() or 'auth' in f.title.lower()]
        if auth_findings:
            paths.append({
                'title': 'Account Takeover via Credential Stuffing',
                'attacker_goal': 'Take over user accounts using stolen credentials',
                'steps': [
                    'Attacker obtains credential dumps from data breaches',
                    'Attacker automates login attempts against application',
                    'Rate limiting triggers after 5 failed attempts per IP',
                    'Attacker rotates IPs to bypass rate limiting',
                    'Without MFA enforcement, valid credentials grant full access',
                ],
                'controls_encountered': [
                    'django-axes rate limiting (5 attempts/hour)',
                    'reCAPTCHA v3 (score-based, can be bypassed)',
                    'MFA available but not enforced',
                ],
                'outcome': 'Partial mitigation - rate limiting slows attack but MFA gap allows compromise',
                'business_impact': 'User account compromise, access to health/financial data',
            })

        # Log exposure path
        log_findings = [f for f in self.findings if 'log' in f.title.lower() or 'pii' in f.title.lower()]
        if log_findings:
            paths.append({
                'title': 'PII Exposure via Log Access',
                'attacker_goal': 'Extract user PII from application logs',
                'steps': [
                    'Attacker gains access to log aggregation system (Sentry, etc.)',
                    'Attacker searches logs for email addresses and identifiers',
                    'Email addresses logged in plain text are extracted',
                    'Attacker builds user list for targeted phishing',
                ],
                'controls_encountered': [
                    'Log access requires authentication',
                    'PII is logged without hashing',
                ],
                'outcome': 'User email exposure enabling secondary attacks',
                'business_impact': 'Privacy violation, phishing risk, potential regulatory issues',
            })

        return paths

    def generate_failure_modes(self) -> List[dict]:
        """Generate failure mode analysis for critical/high findings."""
        modes = []

        for finding in self.findings:
            if finding.severity in ['critical', 'high']:
                modes.append({
                    'finding_id': finding.finding_id,
                    'title': finding.title,
                    'primary_failure': finding.description,
                    'secondary_risks': self._get_secondary_risks(finding),
                    'blast_radius': self._get_blast_radius(finding),
                    'operational_impact': self._get_operational_impact(finding),
                    'regulatory_exposure': self._get_regulatory_exposure(finding),
                })

        return modes

    def _get_secondary_risks(self, finding) -> List[str]:
        """Determine secondary cascade risks."""
        risks = []
        title_lower = finding.title.lower()

        if 'credential' in title_lower or 'key' in title_lower:
            risks.append("Lateral movement to connected systems")
            risks.append("Data exfiltration via compromised access")
        if 'mfa' in title_lower or 'auth' in title_lower:
            risks.append("Mass account compromise")
            risks.append("Privilege escalation")
        if 'log' in title_lower or 'pii' in title_lower:
            risks.append("Identity theft enablement")
            risks.append("Targeted social engineering")

        return risks or ["Direct exploitation risk"]

    def _get_blast_radius(self, finding) -> str:
        """Determine blast radius of finding."""
        components = finding.affected_components or []
        if any('admin' in str(c).lower() for c in components):
            return "HIGH - Admin access affects all users and data"
        if any('auth' in str(c).lower() or 'user' in str(c).lower() for c in components):
            return "HIGH - Authentication affects all users"
        if any('finance' in str(c).lower() or 'billing' in str(c).lower() for c in components):
            return "HIGH - Financial data exposure"
        return "MEDIUM - Scoped to specific functionality"

    def _get_operational_impact(self, finding) -> str:
        """Determine operational impact."""
        if finding.severity == 'critical':
            return "SEVERE - Requires immediate incident response"
        if finding.severity == 'high':
            return "SIGNIFICANT - Requires urgent remediation"
        return "MODERATE - Should be addressed in normal sprint"

    def _get_regulatory_exposure(self, finding) -> str:
        """Determine regulatory/compliance exposure."""
        title_lower = finding.title.lower()
        if 'pii' in title_lower or 'log' in title_lower:
            return "GDPR/CCPA - Personal data handling violation"
        if 'credential' in title_lower or 'key' in title_lower:
            return "SOC 2 - Access control deficiency"
        if 'health' in title_lower:
            return "HIPAA-like - Health data exposure risk"
        return "General security best practice"

    def generate_ciso_sleep_test(self) -> str:
        """Generate CISO sleep test - top 3 things that would keep a CISO up at night."""
        concerns = []

        # Check for critical findings
        critical = [f for f in self.findings if f.severity == 'critical']
        if critical:
            for finding in critical[:1]:
                concerns.append({
                    'concern': finding.title,
                    'why_matters': f"CVSS {finding.cvss_score} - {finding.risk_reasoning}",
                    'disaster_trigger': "Repository access by unauthorized party reveals credentials",
                    'fix_first': finding.recommendations[0] if finding.recommendations else "Rotate affected credentials immediately",
                })

        # Check for MFA gap
        mfa_findings = [f for f in self.findings if 'mfa' in f.title.lower()]
        if mfa_findings:
            concerns.append({
                'concern': "No MFA Enforcement for Privileged Access",
                'why_matters': "Credential compromise = full account takeover without second factor",
                'disaster_trigger': "Admin credentials phished or leaked from another breach",
                'fix_first': "Require MFA for all staff/admin accounts",
            })

        # Check for PII logging
        pii_findings = [f for f in self.findings if 'pii' in f.title.lower() or 'log' in f.title.lower()]
        if pii_findings:
            concerns.append({
                'concern': "PII Exposure in Logs",
                'why_matters': "Email addresses logged without hashing - privacy violation risk",
                'disaster_trigger': "Log aggregation breach exposes user contact information",
                'fix_first': "Hash all PII before logging using hash_pii() utility",
            })

        # Fill remaining slots if needed
        high = [f for f in self.findings if f.severity == 'high']
        for finding in high:
            if len(concerns) >= 3:
                break
            if not any(c['concern'] == finding.title for c in concerns):
                concerns.append({
                    'concern': finding.title,
                    'why_matters': finding.risk_reasoning,
                    'disaster_trigger': "Exploitation by motivated attacker",
                    'fix_first': finding.recommendations[0] if finding.recommendations else "Address immediately",
                })

        # Format output
        output = """
CISO SLEEP TEST
===============
"If I were accountable for this in production, the top 3 things that would keep me up at night are..."

"""
        for i, concern in enumerate(concerns[:3], 1):
            output += f"""
{i}. {concern['concern']}
   WHY IT MATTERS: {concern['why_matters']}
   DISASTER TRIGGER: {concern['disaster_trigger']}
   FIX FIRST: {concern['fix_first']}
"""

        return output.strip()

    def generate_remediation_prompt(self) -> str:
        """
        Generate a copy-paste prompt for Claude to fix all findings.

        This prompt can be given to a fresh Claude session to systematically
        address all security findings.
        """
        # Filter to only actionable findings (code changes that can be made)
        # Exclude findings that:
        # - Are environment-config only (DEBUG mode issues that pass in production)
        # - Have no actionable code changes
        actionable_findings = self._get_actionable_findings()

        if not actionable_findings:
            return self._generate_no_findings_prompt()

        prompt = f"""# Security Remediation Task

You are tasked with fixing the security findings from the assessment run on {self.run.run_timestamp.strftime('%Y-%m-%d')}.

## Assessment Summary
- Total Findings: {len(actionable_findings)}
- Critical: {sum(1 for f in actionable_findings if f.severity == 'critical')}
- High: {sum(1 for f in actionable_findings if f.severity == 'high')}
- Medium: {sum(1 for f in actionable_findings if f.severity == 'medium')}
- Low: {sum(1 for f in actionable_findings if f.severity == 'low')}
- Current Grade: {self.scores.securityscorecard_grade}
- Target Grade: A

## Instructions
Fix each finding in priority order (Critical → High → Medium → Low).
For each finding:
1. Read the affected files
2. Implement the recommended fix
3. Verify the fix works
4. Move to the next finding

## Findings to Fix (Priority Order)

"""
        # Sort by severity then CVSS score
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'info': 4}
        sorted_findings = sorted(
            actionable_findings,
            key=lambda f: (severity_order.get(f.severity, 5), -float(f.cvss_score))
        )

        for i, finding in enumerate(sorted_findings, 1):
            prompt += f"""
### {i}. {finding.finding_id}: {finding.title}
**Severity:** {finding.severity.upper()} (CVSS {finding.cvss_score})
**Quick Win:** {'Yes' if finding.is_quick_win else 'No'}

**Description:**
{finding.description}

**Affected Components:**
{', '.join(str(c) for c in (finding.affected_components or [])) or 'See evidence'}

**Recommendations:**
"""
            for rec in (finding.recommendations or []):
                prompt += f"- {rec}\n"

            prompt += f"""
**Validation:**
{finding.validation_steps}

---
"""

        prompt += """
## After Completing All Fixes

1. Run the security assessment again:
   ```
   python manage.py run_security_assessment --report
   ```

2. Verify the grade has improved

3. Commit all changes with message:
   ```
   Security remediation: Fix {N} findings from assessment {DATE}

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

4. Update the changelog in docs/wlj_claude_changelog.md
"""

        return prompt.strip()

    def _get_actionable_findings(self) -> List:
        """
        Filter findings to only those that require code changes.

        Excludes:
        - Findings that are purely environment configuration (e.g., missing env vars)
        - Findings that are expected in DEBUG mode but pass in production
        - Findings that have already been acknowledged/resolved
        """
        actionable = []

        # Finding keys that are environment-config only (not code fixes)
        env_config_only_keys = {
            # These are expected to fail in dev but configured correctly for prod
            'phi_transmission_insecure',  # SSL settings - handled by Railway proxy
            'no_captcha_protection',  # CAPTCHA keys set in production env
            'https_not_enforced',  # SSL handled by Railway
        }

        for finding in self.findings:
            # Skip findings that are purely environment config
            if hasattr(finding, 'finding_key') and finding.finding_key in env_config_only_keys:
                continue

            # Check evidence for DEBUG mode indicators - if the finding shows
            # DEBUG=True in evidence and the finding is about prod-only settings,
            # it's likely not actionable
            evidence = finding.evidence if hasattr(finding, 'evidence') else {}
            if isinstance(evidence, dict) and evidence.get('debug', False):
                # Finding was detected in debug mode - check if it's prod-only
                title_lower = finding.title.lower()
                if any(term in title_lower for term in ['https', 'ssl', 'hsts', 'captcha', 'phi transmission']):
                    continue

            actionable.append(finding)

        return actionable

    def _generate_no_findings_prompt(self) -> str:
        """Generate a prompt when there are no actionable findings."""
        return f"""# Security Assessment Complete

Assessment run on {self.run.run_timestamp.strftime('%Y-%m-%d')} found **no actionable security findings** requiring code changes.

## Assessment Summary
- Current Grade: {self.scores.securityscorecard_grade}
- Tests Passed: {sum(1 for t in self.test_results if t.result == 'pass')}/{len(self.test_results)}

## What This Means
All findings from this assessment are either:
1. **Environment-specific** - Settings that are correctly configured in production (e.g., HTTPS, CAPTCHA)
2. **Already resolved** - Previously fixed issues
3. **Not applicable** - Issues that don't affect this codebase

## Next Steps
- No code changes required
- Continue monitoring with regular security assessments
- Review the full assessment report for informational findings
"""
