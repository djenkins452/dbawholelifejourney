# ==============================================================================
# File: apps/security/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security Assessment models - scores, tests, findings (Tier-0 encrypted)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Security Assessment Models

SECURITY (Tier-0):
- All sensitive fields are encrypted at rest using Fernet AES-256
- Encryption key loaded from SECURITY_DATA_ENCRYPTION_KEY env var
- Falls back to OAUTH_TOKEN_ENCRYPTION_KEY if not set
- Never stores keys in code or database

Models:
- SecurityRun: Master record for each assessment run
- SecurityScore: Computed scores for a run (append-only)
- SecurityTest: Individual test results with criteria/evidence
- SecurityFinding: Detailed findings with CVSS scores
- SecurityAuditLog: Access logging for compliance
"""

import hashlib
import json
import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


# ==============================================================================
# Encryption Utilities (Tier-0 Security)
# ==============================================================================

def get_security_fernet():
    """
    Get Fernet instance for security data encryption.

    Uses dedicated SECURITY_DATA_ENCRYPTION_KEY if set,
    otherwise falls back to OAUTH_TOKEN_ENCRYPTION_KEY.

    NEVER stores keys in database or code.
    """
    from cryptography.fernet import Fernet

    key = getattr(settings, 'SECURITY_DATA_ENCRYPTION_KEY', None)
    if not key:
        key = getattr(settings, 'OAUTH_TOKEN_ENCRYPTION_KEY', None)

    if not key:
        logger.warning(
            "Security data encryption key not configured. "
            "Set SECURITY_DATA_ENCRYPTION_KEY in environment."
        )
        return None

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error(f"Invalid security encryption key: {e}")
        return None


def encrypt_security_data(plaintext: str) -> str:
    """Encrypt sensitive security data for storage."""
    if not plaintext:
        return ''

    fernet = get_security_fernet()
    if fernet is None:
        # Development fallback - log warning
        logger.warning("Storing security data WITHOUT encryption (dev mode)")
        return f"UNENCRYPTED:{plaintext}"

    try:
        return fernet.encrypt(plaintext.encode()).decode()
    except Exception as e:
        logger.error(f"Security data encryption failed: {e}")
        raise


def decrypt_security_data(ciphertext: str) -> str:
    """Decrypt security data from storage."""
    if not ciphertext:
        return ''

    if ciphertext.startswith('UNENCRYPTED:'):
        logger.warning("Reading unencrypted security data (dev mode)")
        return ciphertext[12:]

    fernet = get_security_fernet()
    if fernet is None:
        raise ValueError("Cannot decrypt: encryption key not configured")

    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.error(f"Security data decryption failed: {e}")
        raise ValueError("Decryption failed - key may have changed")


# ==============================================================================
# Custom Encrypted Field
# ==============================================================================

class EncryptedTextField(models.TextField):
    """
    TextField that encrypts data at rest.

    Automatically encrypts on save and decrypts on load.
    Stores as regular text field (encrypted string).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        """Encrypt before saving to database."""
        if value is None:
            return value
        if isinstance(value, str):
            return encrypt_security_data(value)
        return encrypt_security_data(str(value))

    def from_db_value(self, value, expression, connection):
        """Decrypt when loading from database."""
        if value is None:
            return value
        try:
            return decrypt_security_data(value)
        except Exception as e:
            logger.error(f"Failed to decrypt field: {e}")
            return "[DECRYPTION_FAILED]"

    def to_python(self, value):
        """Handle value conversion."""
        if value is None:
            return value
        if isinstance(value, str) and not value.startswith('gAAAAA'):
            # Already decrypted or plain text
            return value
        return value


class EncryptedJSONField(models.TextField):
    """
    JSONField that encrypts data at rest.

    Stores JSON as encrypted text.
    """

    def get_prep_value(self, value):
        """Serialize and encrypt before saving."""
        if value is None:
            return None
        json_str = json.dumps(value, default=str)
        return encrypt_security_data(json_str)

    def from_db_value(self, value, expression, connection):
        """Decrypt and deserialize when loading."""
        if value is None:
            return None
        try:
            decrypted = decrypt_security_data(value)
            return json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt JSON field: {e}")
            return {"error": "DECRYPTION_FAILED"}

    def to_python(self, value):
        """Handle value conversion."""
        if value is None:
            return value
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


# ==============================================================================
# Security Run Model (Master Record)
# ==============================================================================

class SecurityRun(models.Model):
    """
    Master record for a security assessment run.

    Each run generates:
    - One SecurityScore record
    - Multiple SecurityTest records
    - Multiple SecurityFinding records

    Append-only: runs are never modified after completion.
    """

    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Run metadata
    run_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    # Run configuration
    run_type = models.CharField(max_length=50, default='full')  # full, quick, targeted
    triggered_by = models.CharField(max_length=100, default='manual')  # manual, scheduled, ci

    # Summary counts (for quick queries without decryption)
    total_tests = models.IntegerField(default=0)
    passed_tests = models.IntegerField(default=0)
    failed_tests = models.IntegerField(default=0)
    total_findings = models.IntegerField(default=0)
    critical_findings = models.IntegerField(default=0)
    high_findings = models.IntegerField(default=0)
    medium_findings = models.IntegerField(default=0)
    low_findings = models.IntegerField(default=0)

    # Finding status tracking (for cross-run trending)
    new_findings = models.IntegerField(default=0, help_text='Findings appearing for the first time')
    fixed_findings = models.IntegerField(default=0, help_text='Findings that were fixed since last run')
    regressed_findings = models.IntegerField(default=0, help_text='Previously fixed findings that reappeared')
    recurring_findings = models.IntegerField(default=0, help_text='Findings that still exist from previous run')

    # Encrypted sensitive data
    _executive_summary = EncryptedTextField(blank=True, default='')
    _attack_paths = EncryptedJSONField(blank=True, null=True)
    _failure_modes = EncryptedJSONField(blank=True, null=True)
    _ciso_sleep_test = EncryptedTextField(blank=True, default='')
    _remediation_prompt = EncryptedTextField(blank=True, default='')

    # Integrity verification
    run_hash = models.CharField(max_length=64, blank=True)  # SHA-256 of run data

    # User notes/annotations (not encrypted - for quick display)
    notes = models.TextField(blank=True, default='', help_text='User notes about this assessment run')
    notes_updated_at = models.DateTimeField(null=True, blank=True)
    notes_updated_by = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ['-run_timestamp']
        indexes = [
            models.Index(fields=['-run_timestamp']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Security Run {self.run_timestamp.strftime('%Y-%m-%d %H:%M')}"

    @property
    def executive_summary(self):
        return self._executive_summary

    @executive_summary.setter
    def executive_summary(self, value):
        self._executive_summary = value

    @property
    def attack_paths(self):
        return self._attack_paths

    @attack_paths.setter
    def attack_paths(self, value):
        self._attack_paths = value

    @property
    def failure_modes(self):
        return self._failure_modes

    @failure_modes.setter
    def failure_modes(self, value):
        self._failure_modes = value

    @property
    def ciso_sleep_test(self):
        return self._ciso_sleep_test

    @ciso_sleep_test.setter
    def ciso_sleep_test(self, value):
        self._ciso_sleep_test = value

    @property
    def remediation_prompt(self):
        return self._remediation_prompt

    @remediation_prompt.setter
    def remediation_prompt(self, value):
        self._remediation_prompt = value

    def compute_hash(self) -> str:
        """Compute integrity hash of run data."""
        data = f"{self.id}:{self.run_timestamp}:{self.total_tests}:{self.total_findings}"
        return hashlib.sha256(data.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if not self.run_hash:
            self.run_hash = self.compute_hash()
        super().save(*args, **kwargs)


# ==============================================================================
# Security Score Model (Append-Only Ledger)
# ==============================================================================

class SecurityScore(models.Model):
    """
    Computed security scores for a run.

    APPEND-ONLY: Never update or delete scores.
    Each run creates exactly one score record.

    Scores:
    - CVSS average and counts by severity
    - SecurityScorecard grade (A-F)
    - BitSight-style score (250-900)
    - Risk score (0-100)
    - Maturity level (0-3)
    """

    GRADE_CHOICES = [
        ('A', 'A - Excellent'),
        ('B', 'B - Good'),
        ('C', 'C - Fair'),
        ('D', 'D - Poor'),
        ('F', 'F - Critical'),
    ]

    MATURITY_CHOICES = [
        (0, 'Ad Hoc'),
        (1, 'Basic'),
        (2, 'Managed'),
        (3, 'Mature'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.OneToOneField(SecurityRun, on_delete=models.CASCADE, related_name='score')

    # Timestamp (denormalized for easy trending)
    run_timestamp = models.DateTimeField(db_index=True)

    # CVSS Statistics
    cvss_avg = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.00'))
    cvss_critical_count = models.IntegerField(default=0)  # 9.0-10.0
    cvss_high_count = models.IntegerField(default=0)      # 7.0-8.9
    cvss_medium_count = models.IntegerField(default=0)    # 4.0-6.9
    cvss_low_count = models.IntegerField(default=0)       # 0.1-3.9
    cvss_none_count = models.IntegerField(default=0)      # 0.0

    # Derived Scores
    securityscorecard_grade = models.CharField(max_length=1, choices=GRADE_CHOICES, default='C')
    bitsight_score = models.IntegerField(default=500)  # 250-900
    risk_score_0_100 = models.IntegerField(default=50)  # 0-100
    maturity_level = models.IntegerField(choices=MATURITY_CHOICES, default=1)

    # Encrypted methodology documentation
    _scoring_methodology = EncryptedJSONField(blank=True, null=True)

    class Meta:
        ordering = ['-run_timestamp']
        indexes = [
            models.Index(fields=['-run_timestamp']),
            models.Index(fields=['securityscorecard_grade']),
        ]

    def __str__(self):
        return f"Score {self.run_timestamp.strftime('%Y-%m-%d')}: Grade {self.securityscorecard_grade}, BitSight {self.bitsight_score}"

    @property
    def scoring_methodology(self):
        return self._scoring_methodology

    @scoring_methodology.setter
    def scoring_methodology(self, value):
        self._scoring_methodology = value

    def save(self, *args, **kwargs):
        # Denormalize timestamp from run
        if self.run and not self.run_timestamp:
            self.run_timestamp = self.run.run_timestamp
        super().save(*args, **kwargs)


# ==============================================================================
# Security Test Model
# ==============================================================================

class SecurityTest(models.Model):
    """
    Individual security test result.

    Each test has:
    - Unique test ID (e.g., SEC-T001)
    - Category and description
    - Pass/Fail/Unknown result
    - Criteria (what "pass" means)
    - Evidence (encrypted)
    """

    RESULT_PASS = 'pass'
    RESULT_FAIL = 'fail'
    RESULT_UNKNOWN = 'unknown'
    RESULT_SKIPPED = 'skipped'

    RESULT_CHOICES = [
        (RESULT_PASS, 'Pass'),
        (RESULT_FAIL, 'Fail'),
        (RESULT_UNKNOWN, 'Unknown'),
        (RESULT_SKIPPED, 'Skipped'),
    ]

    CATEGORY_CHOICES = [
        ('secrets', 'Secrets & Credentials'),
        ('auth', 'Authentication & Sessions'),
        ('authz', 'Authorization'),
        ('input', 'Input Validation'),
        ('data', 'Data Protection'),
        ('logging', 'Logging & Auditing'),
        ('web', 'Web Security'),
        ('deps', 'Dependencies'),
        ('deploy', 'Deployment'),
        ('abuse', 'Abuse Resistance'),
        ('infra', 'Infrastructure'),
        ('compliance', 'Compliance'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(SecurityRun, on_delete=models.CASCADE, related_name='tests')

    # Test identification
    test_id = models.CharField(max_length=20, db_index=True)  # e.g., SEC-T001
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField()

    # Test criteria (what constitutes pass/fail)
    criteria = models.TextField()

    # Result
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    result_details = models.TextField(blank=True)

    # Encrypted evidence (file paths, code snippets, command outputs)
    _evidence = EncryptedJSONField(blank=True, null=True)

    # Timing
    executed_at = models.DateTimeField(default=timezone.now)
    duration_ms = models.IntegerField(default=0)

    class Meta:
        ordering = ['test_id']
        indexes = [
            models.Index(fields=['run', 'test_id']),
            models.Index(fields=['category']),
            models.Index(fields=['result']),
        ]
        unique_together = [['run', 'test_id']]

    def __str__(self):
        return f"{self.test_id}: {self.title} ({self.result})"

    @property
    def evidence(self):
        return self._evidence

    @evidence.setter
    def evidence(self, value):
        self._evidence = value


# ==============================================================================
# Security Finding Model
# ==============================================================================

class SecurityFinding(models.Model):
    """
    Detailed security finding with CVSS scoring.

    Linked to one or more tests that discovered it.
    """

    SEVERITY_CRITICAL = 'critical'
    SEVERITY_HIGH = 'high'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_LOW = 'low'
    SEVERITY_INFO = 'info'

    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, 'Critical'),
        (SEVERITY_HIGH, 'High'),
        (SEVERITY_MEDIUM, 'Medium'),
        (SEVERITY_LOW, 'Low'),
        (SEVERITY_INFO, 'Informational'),
    ]

    LIKELIHOOD_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    IMPACT_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(SecurityRun, on_delete=models.CASCADE, related_name='findings')
    test = models.ForeignKey(SecurityTest, on_delete=models.CASCADE, related_name='findings', null=True)

    # Finding identification
    finding_id = models.CharField(max_length=20, db_index=True)  # e.g., SEC-001
    title = models.CharField(max_length=200)

    # Classification
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    likelihood = models.CharField(max_length=10, choices=LIKELIHOOD_CHOICES)
    impact = models.CharField(max_length=10, choices=IMPACT_CHOICES)

    # CVSS v3.1
    cvss_vector = models.CharField(max_length=100, blank=True)  # e.g., AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N
    cvss_score = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('0.0'))

    # Encrypted sensitive details
    _description = EncryptedTextField()
    _risk_reasoning = EncryptedTextField(blank=True, default='')
    _evidence = EncryptedJSONField(blank=True, null=True)
    _affected_components = EncryptedJSONField(blank=True, null=True)
    _recommendations = EncryptedJSONField(blank=True, null=True)
    _validation_steps = EncryptedTextField(blank=True, default='')

    # Remediation metadata (not encrypted - for queries)
    is_quick_win = models.BooleanField(default=False)
    remediation_effort = models.CharField(max_length=20, default='medium')  # low, medium, high

    # Acknowledgment tracking (links to AcknowledgedFinding via finding_key)
    finding_key = models.CharField(max_length=100, blank=True, db_index=True)  # Stable key for acknowledgment matching
    is_acknowledged = models.BooleanField(default=False)
    acknowledgment_justification = models.TextField(blank=True)

    # Finding status tracking (for cross-run trending)
    STATUS_NEW = 'new'
    STATUS_RECURRING = 'recurring'
    STATUS_FIXED = 'fixed'
    STATUS_REGRESSED = 'regressed'

    STATUS_CHOICES = [
        (STATUS_NEW, 'New'),
        (STATUS_RECURRING, 'Recurring'),
        (STATUS_FIXED, 'Fixed'),
        (STATUS_REGRESSED, 'Regressed'),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
        help_text='Finding lifecycle status compared to previous runs',
    )
    first_seen_run_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='Run ID when this finding was first detected',
    )
    occurrence_count = models.IntegerField(
        default=1,
        help_text='Number of times this finding has appeared across runs',
    )

    class Meta:
        ordering = ['-cvss_score', 'finding_id']
        indexes = [
            models.Index(fields=['run', 'severity']),
            models.Index(fields=['cvss_score']),
            models.Index(fields=['finding_id']),
        ]
        unique_together = [['run', 'finding_id']]

    def __str__(self):
        return f"{self.finding_id}: {self.title} (CVSS {self.cvss_score})"

    # Property accessors for encrypted fields
    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value):
        self._description = value

    @property
    def risk_reasoning(self):
        return self._risk_reasoning

    @risk_reasoning.setter
    def risk_reasoning(self, value):
        self._risk_reasoning = value

    @property
    def evidence(self):
        return self._evidence

    @evidence.setter
    def evidence(self, value):
        self._evidence = value

    @property
    def affected_components(self):
        return self._affected_components

    @affected_components.setter
    def affected_components(self, value):
        self._affected_components = value

    @property
    def recommendations(self):
        return self._recommendations

    @recommendations.setter
    def recommendations(self, value):
        self._recommendations = value

    @property
    def validation_steps(self):
        return self._validation_steps

    @validation_steps.setter
    def validation_steps(self, value):
        self._validation_steps = value


# ==============================================================================
# Acknowledged Finding (Risk Acceptance Tracking)
# ==============================================================================

class AcknowledgedFinding(models.Model):
    """
    Track acknowledged/accepted security findings.

    When a finding is detected but you intentionally accept the risk,
    document it here with justification. The finding will still be
    reported in assessments but marked as "acknowledged" in the dashboard.

    This ensures:
    - Full visibility into ALL security issues
    - Clear documentation of why risks were accepted
    - Audit trail for compliance
    - Easy identification of what needs fixing vs what's accepted

    NOTE: Acknowledged != Fixed. These are risks you've decided to accept,
    not issues that have been resolved.
    """

    STATUS_ACTIVE = 'active'
    STATUS_EXPIRED = 'expired'
    STATUS_SUPERSEDED = 'superseded'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_SUPERSEDED, 'Superseded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Finding identification (matches finding_id from scanner like SEC-001, SEC-002, etc.)
    finding_id = models.CharField(max_length=20, unique=True, db_index=True)
    title = models.CharField(max_length=200)

    # Risk acceptance details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    justification = models.TextField(help_text="Why is this risk being accepted?")
    mitigating_controls = models.TextField(
        blank=True,
        help_text="What compensating controls reduce this risk?"
    )
    accepted_risk_level = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low - Minimal business impact'),
            ('medium', 'Medium - Moderate impact, compensating controls in place'),
            ('high', 'High - Significant impact but accepted for business reasons'),
        ],
        default='medium'
    )

    # Approval tracking
    acknowledged_by = models.CharField(max_length=100)  # Name of person accepting risk
    acknowledged_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When should this acknowledgment be reviewed? Leave blank for indefinite."
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, help_text="Additional context or future remediation plans")

    class Meta:
        ordering = ['finding_id']
        verbose_name = 'Acknowledged Finding'
        verbose_name_plural = 'Acknowledged Findings'

    def __str__(self):
        return f"{self.finding_id}: {self.title} ({self.status})"

    @property
    def is_expired(self):
        """Check if acknowledgment has expired and needs review."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    @classmethod
    def is_acknowledged(cls, finding_id: str) -> bool:
        """Check if a finding_id is currently acknowledged."""
        return cls.objects.filter(
            finding_id=finding_id,
            status=cls.STATUS_ACTIVE
        ).exists()

    @classmethod
    def get_acknowledgment(cls, finding_id: str):
        """Get active acknowledgment for a finding_id, if any."""
        return cls.objects.filter(
            finding_id=finding_id,
            status=cls.STATUS_ACTIVE
        ).first()


# ==============================================================================
# Security Audit Log (Access Tracking)
# ==============================================================================

class SecurityAuditLog(models.Model):
    """
    Audit log for all access to security data.

    Tracks:
    - Dashboard views
    - Finding access
    - Report exports
    - Any security data access
    """

    ACTION_VIEW_DASHBOARD = 'view_dashboard'
    ACTION_VIEW_RUN = 'view_run'
    ACTION_VIEW_FINDING = 'view_finding'
    ACTION_EXPORT = 'export'
    ACTION_RUN_ASSESSMENT = 'run_assessment'

    ACTION_CHOICES = [
        (ACTION_VIEW_DASHBOARD, 'View Dashboard'),
        (ACTION_VIEW_RUN, 'View Run Details'),
        (ACTION_VIEW_FINDING, 'View Finding'),
        (ACTION_EXPORT, 'Export Data'),
        (ACTION_RUN_ASSESSMENT, 'Run Assessment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='security_audit_logs'
    )
    user_email = models.EmailField(blank=True)  # Denormalized for history
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # What
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    resource_type = models.CharField(max_length=50, blank=True)  # run, finding, etc.
    resource_id = models.CharField(max_length=50, blank=True)

    # Outcome
    success = models.BooleanField(default=True)
    details = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f"{self.timestamp}: {self.user_email} - {self.action}"

    @classmethod
    def log(cls, request, action, resource_type='', resource_id='', success=True, details=None):
        """Create an audit log entry."""
        user = request.user if request.user.is_authenticated else None

        # Get IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

        return cls.objects.create(
            user=user,
            user_email=user.email if user else '',
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else '',
            success=success,
            details=details,
        )
