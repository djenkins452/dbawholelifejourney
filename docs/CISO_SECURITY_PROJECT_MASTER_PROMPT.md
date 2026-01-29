# MASTER PROMPT: Enterprise Security Assessment & Governance System

## Project Overview

Build a comprehensive, enterprise-grade security assessment and governance system for a Django application. This system provides automated security scanning, CVSS-based vulnerability scoring, industry-standard security ratings (SecurityScorecard A-F grades, BitSight 250-900 scores), finding lifecycle management, risk acknowledgment workflows, and AI-assisted remediation.

## Core Requirements

### 1. Security App Structure

Create a Django app called `security` with the following files:
- `models.py` - Core security assessment models with Tier-0 encryption
- `scanner.py` - 40+ automated security tests with CVSS scoring
- `scoring.py` - Security score calculations (Grade, BitSight, Risk, Maturity)
- `finding_tracker.py` - Cross-run finding trend analysis
- `quick_win_detector.py` - Auto-detection of easy-to-fix findings
- `report_generator.py` - Executive summaries, attack paths, CISO sleep test
- `admin.py` - Django admin interface with color-coded severity
- `views.py` - Dashboard, APIs, exports
- `urls.py` - URL routing
- `management/commands/run_security_assessment.py` - CLI for assessments

---

### 2. Security Models (Tier-0 Encrypted)

#### Custom Encrypted Fields

Create custom Django model fields that encrypt data at rest using Fernet (AES-256):

```python
class EncryptedTextField(models.TextField):
    """TextField that encrypts content at rest using Fernet AES-256."""
    # Encrypt on save, decrypt on load
    # Use environment variable for key: SECURITY_DATA_ENCRYPTION_KEY

class EncryptedJSONField(models.JSONField):
    """JSONField that encrypts content at rest using Fernet AES-256."""
    # Serialize to JSON, encrypt, store
    # Decrypt, deserialize on load
```

#### SecurityRun Model
Master record for each security assessment:

**Fields:**
- `id` (UUIDField, primary key)
- `run_timestamp` (DateTimeField, auto_now_add)
- `status` (CharField: running, completed, failed)
- `run_type` (CharField: full, quick, targeted)
- `triggered_by` (CharField: manual, scheduled, ci)
- `duration_seconds` (IntegerField, nullable)
- Test counts: `total_tests`, `passed_tests`, `failed_tests`
- Finding counts: `total_findings`, `critical_findings`, `high_findings`, `medium_findings`, `low_findings`
- Status tracking: `new_findings`, `fixed_findings`, `regressed_findings`, `recurring_findings`
- **Encrypted fields:**
  - `_executive_summary` (EncryptedTextField)
  - `_attack_paths` (EncryptedJSONField)
  - `_failure_modes` (EncryptedJSONField)
  - `_ciso_sleep_test` (EncryptedTextField)
  - `_remediation_prompt` (EncryptedTextField)
- `notes` (TextField, blank) - User annotations
- `notes_updated_at`, `notes_updated_by` - Audit trail
- `run_hash` (CharField) - SHA-256 integrity verification

**Methods:**
- `compute_hash()` - Generate integrity hash from run data
- Property accessors for encrypted fields with automatic decryption

#### SecurityScore Model
Append-only ledger of security scores (never updated after creation):

**Fields:**
- `id` (UUIDField)
- `run` (OneToOneField to SecurityRun)
- `run_timestamp` - Denormalized for easy trending
- **CVSS Statistics:**
  - `cvss_avg` (DecimalField, max_digits=4, decimal_places=2)
  - `cvss_critical_count`, `cvss_high_count`, `cvss_medium_count`, `cvss_low_count`, `cvss_none_count` (IntegerFields)
- **Derived Scores:**
  - `securityscorecard_grade` (CharField: A, B, C, D, F)
  - `bitsight_score` (IntegerField: 250-900)
  - `risk_score_0_100` (IntegerField: 0-100)
  - `maturity_level` (IntegerField: 0-3)
- `_scoring_methodology` (EncryptedJSONField) - Documents calculation formulas

**Grade Calculation (SecurityScorecard style):**
```python
# A: CVSS avg < 2.0, no Critical, no High findings
# B: CVSS avg < 4.0, no Critical, ≤2 High
# C: CVSS avg < 6.0, ≤1 Critical, ≤5 High
# D: CVSS avg < 8.0, ≤2 Critical, ≤10 High
# F: Anything worse
```

**BitSight Formula:**
```python
score = 900 - (critical*100 + high*50 + medium*25 + low*10) + (pass_rate * 50)
# Clamp to 250-900 range
```

**Risk Score Calculation:**
```python
raw = (critical*25 + high*15 + medium*8 + low*3) * exposure_factor
# exposure_factor: 1.0 (auth/finance/health), 0.8 (user data), 0.5 (infrastructure)
# Clamp to 0-100
```

**Maturity Level:**
```python
# Based on security control implementation percentage
# Key indicators: encryption, rate_limiting, logging, CSP, CSRF, audit_logging, MFA, PII_redaction, soft_delete, password_hashing
# 0 (Ad Hoc): <40%, 1 (Basic): 40-60%, 2 (Managed): 60-80%, 3 (Mature): >80%
```

#### SecurityTest Model
Individual test result with evidence:

**Fields:**
- `id` (UUIDField)
- `run` (ForeignKey to SecurityRun)
- `test_id` (CharField, e.g., "SEC-T001")
- `category` (CharField: secrets, auth, authz, input, data, logging, web, deps, deploy, abuse, infra, compliance)
- `title`, `description`, `criteria` (TextFields)
- `result` (CharField: pass, fail, unknown, skipped)
- `result_details` (TextField)
- `_evidence` (EncryptedJSONField) - File paths, code snippets, command outputs
- `executed_at` (DateTimeField)
- `duration_ms` (IntegerField)

**Unique Constraint:** (run, test_id)

#### SecurityFinding Model
Detailed security finding with CVSS v3.1 scoring:

**Fields:**
- `id` (UUIDField)
- `run`, `test` (ForeignKeys)
- `finding_id` (CharField, e.g., "SEC-001")
- `title` (CharField)
- **Severity:**
  - `severity` (CharField: critical, high, medium, low, info)
  - `likelihood` (CharField: high, medium, low)
  - `impact` (CharField: high, medium, low)
- **CVSS v3.1:**
  - `cvss_vector` (CharField, e.g., "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N")
  - `cvss_score` (DecimalField, 0.0-10.0)
- **Encrypted Fields:**
  - `_description` (EncryptedTextField)
  - `_risk_reasoning` (EncryptedTextField)
  - `_evidence` (EncryptedJSONField)
  - `_affected_components` (EncryptedJSONField)
  - `_recommendations` (EncryptedJSONField)
  - `_validation_steps` (EncryptedTextField)
- **Quick Win Metadata:**
  - `is_quick_win` (BooleanField)
  - `remediation_effort` (CharField: low, medium, high)
- **Status Tracking:**
  - `finding_key` - Stable hash for cross-run matching
  - `status` (CharField: new, recurring, fixed, regressed)
  - `first_seen_run_id` (UUIDField, nullable)
  - `occurrence_count` (IntegerField, default=1)
- **Acknowledgment:**
  - `is_acknowledged` (BooleanField)
  - `acknowledgment_justification` (TextField)

**Unique Constraint:** (run, finding_id)

#### AcknowledgedFinding Model
Risk acceptance tracking:

**Fields:**
- `id` (UUIDField)
- `finding_id` (CharField) - Matches SecurityFinding.finding_id pattern
- `title` (CharField)
- `status` (CharField: active, expired, superseded)
- `justification` (TextField) - Why risk is accepted
- `mitigating_controls` (TextField) - Compensating controls
- `accepted_risk_level` (CharField: low, medium, high)
- `acknowledged_by` (CharField)
- `acknowledged_at` (DateTimeField)
- `expires_at` (DateTimeField, nullable)
- `notes` (TextField)
- `created_at`, `updated_at`

**Methods:**
- `is_expired` (property)
- `is_acknowledged(finding_id)` (classmethod)
- `get_acknowledgment(finding_id)` (classmethod)

#### SecurityAuditLog Model
Access logging for compliance:

**Fields:**
- `id` (UUIDField)
- `timestamp` (DateTimeField, indexed)
- `user` (ForeignKey to User, nullable)
- `user_email` (CharField)
- `ip_address` (GenericIPAddressField)
- `user_agent` (TextField)
- `action` (CharField: view_dashboard, view_run, view_finding, export, run_assessment, modify, delete)
- `resource_type`, `resource_id` (CharFields)
- `success` (BooleanField)
- `details` (JSONField)

**Methods:**
- `log(request, action, resource_type, resource_id, success, details)` (classmethod)

---

### 3. Security Scanner (40+ Tests)

Create a comprehensive scanner with tests across 12 categories:

#### CVSS v3.1 Calculator
```python
class CVSSCalculator:
    """Calculate CVSS v3.1 Base Score from vector string."""

    def calculate(self, vector: str) -> Decimal:
        """
        Parse vector like "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"
        Calculate exploitability and impact subscores
        Return base score 0.0-10.0
        """
```

#### Test Categories (implement 3-5 tests per category):

1. **Secrets & Credentials (SEC-T001-T008)**
   - Check for .env files in version control
   - Scan for hardcoded API keys, passwords, secrets in code
   - Verify credentials not in settings.py
   - Check for exposed AWS/GCP/Azure keys

2. **Authentication & Sessions (SEC-T009-T014)**
   - Password policy enforcement (length, complexity)
   - Session timeout configuration
   - MFA availability check
   - Secure cookie flags (HttpOnly, Secure, SameSite)

3. **Authorization (SEC-T015-T019)**
   - Permission checks on views
   - Object-level access controls
   - Admin-only route protection
   - Privilege escalation vectors

4. **Input Validation (SEC-T020-T024)**
   - SQL injection patterns in raw queries
   - XSS vulnerability patterns
   - Command injection in subprocess calls
   - Path traversal in file operations

5. **Data Protection (SEC-T025-T029)**
   - Encryption at rest for sensitive fields
   - PII handling and masking
   - Soft delete implementation
   - Data retention policies

6. **Logging & Auditing (SEC-T030-T033)**
   - Security event logging
   - Sensitive data in logs check
   - Audit trail for admin actions
   - Log injection prevention

7. **Web Security (SEC-T034-T039)**
   - Content-Security-Policy header
   - X-Frame-Options, X-Content-Type-Options
   - CORS configuration
   - HTTPS enforcement

8. **Dependencies (SEC-T040-T042)**
   - Run pip-audit for known vulnerabilities
   - Check for outdated packages
   - License compliance

9. **Deployment (SEC-T043-T046)**
   - DEBUG mode disabled in production
   - Secret key not default
   - ALLOWED_HOSTS configured
   - Static file security

10. **Abuse Resistance (SEC-T047-T050)**
    - Rate limiting on auth endpoints
    - CSRF protection enabled
    - Account lockout after failed attempts
    - Captcha on public forms

11. **Infrastructure**
    - WAF/CDN detection
    - TLS configuration
    - DNS security

12. **Compliance**
    - Data retention policies
    - Privacy controls
    - Terms acceptance tracking

#### Scanner Output
```python
@dataclass
class TestResult:
    test_id: str
    category: str
    title: str
    description: str
    criteria: str
    result: str  # pass, fail, unknown, skipped
    result_details: str
    evidence: dict
    duration_ms: int
    findings: List[Finding]

@dataclass
class Finding:
    finding_id: str
    title: str
    severity: str
    likelihood: str
    impact: str
    cvss_vector: str
    cvss_score: Decimal
    description: str
    risk_reasoning: str
    evidence: dict
    affected_components: list
    recommendations: list
    validation_steps: str
    is_quick_win: bool
    remediation_effort: str
    finding_key: str
```

---

### 4. Finding Tracker & Trending

Track finding status across runs:

```python
def generate_finding_key(title: str, severity: str, affected_components: list) -> str:
    """Create stable hash for finding across runs using SHA-256."""

def analyze_finding_status(current_run, previous_run) -> dict:
    """
    Compare findings between runs.
    Mark each finding as: new, recurring, fixed, regressed
    Return counts: {'new': int, 'recurring': int, 'fixed': int, 'regressed': int}
    """

def get_finding_trend_data(limit=20) -> dict:
    """
    Return time series data for charting:
    {'labels': [...], 'total': [...], 'new': [...], 'recurring': [...], 'fixed': [...], 'regressed': [...]}
    """

def get_improvement_metrics(days=30) -> dict:
    """
    Calculate improvement over time period:
    {'first_run': {...}, 'latest_run': {...}, 'improvement': bool, 'changes': {...}}
    """
```

---

### 5. Quick Win Detection

Auto-identify easy-to-fix findings:

```python
def detect_quick_win(title, severity, cvss_score, remediation_effort, recommendations, description) -> tuple[bool, str]:
    """
    Detect if finding is likely a quick fix.

    Quick win indicators:
    - Title patterns: "Missing header", "Default config", "Debug enabled", "Cookie flags"
    - Recommendation keywords: "Add header", "Configure", "Enable", "Disable", "Environment variable"

    Never quick wins:
    - Critical severity (requires testing)
    - Keywords: "Refactor", "Redesign", "Rewrite", "Database migration", "Breaking change"

    Returns: (is_quick_win: bool, reason: str)
    """

def process_run_quick_wins(run) -> dict:
    """Auto-detect quick wins for all findings in run."""
```

---

### 6. Report Generation

Generate executive-friendly reports:

```python
class ReportGenerator:
    def __init__(self, run, score, findings, tests):
        pass

    def generate_executive_summary(self) -> str:
        """
        1-page max executive summary:
        - Overall posture: GOOD / FAIR / NEEDS IMPROVEMENT
        - Key metrics (grade, score, finding counts)
        - Top 3 risks with business impact
        - Recommended actions (prioritized)
        """

    def generate_attack_paths(self) -> list[dict]:
        """
        Narrative attack scenarios based on findings:
        [{'name': str, 'steps': [str], 'controls': [str], 'business_impact': str}]
        """

    def generate_failure_modes(self) -> list[dict]:
        """Potential failure scenarios."""

    def generate_ciso_sleep_test(self) -> str:
        """
        What keeps the CISO up at night?
        Critical concerns extracted from findings.
        """

    def generate_remediation_prompt(self) -> str:
        """
        Copy-paste prompt for AI remediation:

        'I need help fixing security findings in my Django application.

        ## Current Security Posture
        Grade: {grade}, BitSight: {score}, Risk: {risk}

        ## Findings to Address (prioritized)

        ### 1. {finding_title} (Severity: {severity}, CVSS: {score})
        **Description:** {description}
        **Affected Components:** {components}
        **Recommendations:** {recommendations}
        **Validation Steps:** {validation}

        [repeat for all findings]

        Please provide specific code fixes for each finding, starting with the highest priority items.'
        """
```

---

### 7. Views & Dashboard

#### Access Control Mixin
```python
class SecurityAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Enforce staff-only access and log all access."""

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        # Log access to SecurityAuditLog
        SecurityAuditLog.log(request, action='view_dashboard', ...)
        return super().dispatch(request, *args, **kwargs)
```

#### Dashboard View
- Latest run with scores and grade
- Trend charts (scores over time, findings over time)
- Recent runs list
- Quick actions (run assessment, export)

#### Run Detail View
- Full run details
- All tests grouped by category
- All findings with severity badges
- Executive summary display
- Export buttons (CSV, PDF)

#### API Endpoints
- `GET /api/test/<pk>/` - Test details with evidence
- `GET /api/finding/<pk>/` - Finding details (decrypted)
- `GET /api/trends/` - Score trend data for charts
- `GET /api/finding-trends/` - Finding status trends
- `GET /api/improvement/` - Improvement metrics
- `GET /api/remediation/<pk>/` - Get remediation prompt

#### Export Views
- CSV export of all findings
- PDF/HTML report generation

---

### 8. Django Admin Interface

Color-coded, filterable admin for security data:

#### SecurityRunAdmin
- List: timestamp, status, grade, bitsight, findings, tests, triggered_by
- All fields read-only (append-only model)
- Inlines for Score, Tests, Findings

#### SecurityFindingAdmin
- List: finding_id, title, severity (color-coded), cvss, status, quick_win, acknowledged
- Filters: severity, status, quick_win, acknowledged, effort
- Actions: mark_as_quick_win, unmark_as_quick_win
- Color coding:
  - Severity: red=critical, orange=high, yellow=medium, blue=low, gray=info
  - Status: blue=new, yellow=recurring, green=fixed, red=regressed

#### SecurityAuditLogAdmin
- Completely read-only
- No add/change/delete permissions
- List: timestamp, user_email, action, resource_type, ip_address, success

---

### 9. Management Command

```bash
python manage.py run_security_assessment [--type full|quick|targeted] [--report] [--json] [--triggered-by manual|scheduled|ci]
```

Flow:
1. Create SecurityRun record (status=running)
2. Run SecurityScanner.run_all_tests()
3. Calculate SecurityScore
4. Save all test results and findings
5. Analyze finding status vs previous run
6. Detect quick wins
7. Generate reports
8. Update run summary counts
9. Set status=completed
10. Output results

---

### 10. Security Infrastructure

#### Rate Limiting
```python
@rate_limit_api(requests_per_minute=60, requests_per_hour=1000)
def api_view(request):
    pass

def secure_compare_api_key(provided, expected) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(provided.encode(), expected.encode())
```

#### Security Logging
```python
def log_security_event(event_type, severity, message, details=None, request=None, user=None, notify_immediately=False):
    """
    Log security events with optional admin notification.
    event_type: login_failure, login_lockout, signup_blocked, rate_limit, csrf_failure,
                permission_denied, data_breach_attempt, vulnerability_scan, bot_activity,
                admin_override, data_export, api_anomaly
    severity: debug, info, warning, error, critical
    """
```

#### Django-Axes Integration
```python
AXES_FAILURE_LIMIT = 5  # Lock after 5 failed attempts
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ACCESS_FAILURE_LOG = True
```

---

### 11. Environment Variables Required

```
# Encryption keys (generate with Fernet.generate_key())
SECURITY_DATA_ENCRYPTION_KEY=your-base64-fernet-key
OAUTH_TOKEN_ENCRYPTION_KEY=fallback-key

# Optional
SECURITY_SCAN_SCHEDULE=0 6 * * *  # Daily at 6 AM
SECURITY_ALERT_EMAIL=security@yourcompany.com
```

---

### 12. Database Migrations

Create migrations for:
1. Initial models (SecurityRun, SecurityScore, SecurityTest, SecurityFinding, SecurityAuditLog)
2. AcknowledgedFinding model
3. Acknowledgment fields on SecurityFinding
4. Status tracking fields (status, first_seen_run_id, occurrence_count)
5. Notes fields on SecurityRun

---

### 13. Tests to Create

- `test_models.py` - Model creation, encryption/decryption, property accessors
- `test_scanner.py` - Scanner execution, finding generation
- `test_scoring.py` - Score calculations, grade thresholds
- `test_finding_tracker.py` - Status analysis, trend data
- `test_quick_win_detector.py` - Detection patterns
- `test_views.py` - Access control, API responses
- `test_admin.py` - Admin interface functionality

---

### 14. Key Security Principles

1. **Tier-0 Encryption:** All sensitive security data encrypted at rest
2. **Append-Only Ledger:** SecurityScore records never updated after creation
3. **Immutable Audit Trail:** Runs and audit logs cannot be modified
4. **Integrity Verification:** SHA-256 hashing of run data
5. **Staff-Only Access:** Dashboard behind @staff_member_required
6. **Complete Audit Logging:** All access to security data logged
7. **Finding Lifecycle:** Track new/recurring/fixed/regressed across runs
8. **Risk Acknowledgment:** Document accepted risks without fixing
9. **Quick Win Detection:** Prioritize easy fixes
10. **AI-Assisted Remediation:** Generate prompts for Claude/ChatGPT to help fix issues

---

### 15. Integration Points

- Scheduled runs via django-apscheduler or cron
- CI/CD integration via management command with --triggered-by ci
- Email alerts for critical findings
- Slack/Teams webhook for new findings
- CSV/PDF export for reporting
- API endpoints for external dashboards

---

## Implementation Order

1. Create security app and models with encryption
2. Implement CVSS calculator
3. Build scanner with 5-10 initial tests
4. Implement scoring engine
5. Create finding tracker
6. Build admin interface
7. Create dashboard views
8. Add management command
9. Implement report generator
10. Add quick win detection
11. Expand to 40+ tests
12. Add export functionality
13. Write comprehensive tests
14. Add CI/CD integration

---

## Success Criteria

- [ ] All 40+ security tests implemented and passing
- [ ] CVSS v3.1 scores calculated correctly
- [ ] SecurityScorecard grades match expected thresholds
- [ ] BitSight scores in 250-900 range
- [ ] Finding status tracking working across runs
- [ ] Quick win detection identifying easy fixes
- [ ] Executive summary readable by non-technical executives
- [ ] Remediation prompt generates useful AI input
- [ ] All security data encrypted at rest
- [ ] Complete audit trail of all access
- [ ] Dashboard loads in <2 seconds
- [ ] CSV/PDF exports functional
- [ ] Management command works in CI/CD

---

*This prompt provides complete specifications to recreate an enterprise-grade security assessment system. Present to your CISO/CIO to demonstrate the comprehensive security governance capabilities being implemented.*
