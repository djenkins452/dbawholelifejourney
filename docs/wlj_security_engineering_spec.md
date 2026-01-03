# ==============================================================================
# File: docs/wlj_security_engineering_spec.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Implementation-ready engineering specification for secure signup
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Secure Signup Engineering Specification

## Document Purpose

This document translates the security design into implementation-ready specifications for engineers. It defines data models, API endpoints, storage rules, and third-party integrations needed to build the secure signup system.

---

## 1. Data Models

### 1.1 SignupAttempt Model

Tracks every signup attempt for risk analysis and audit purposes.

```python
# apps/users/models.py

from django.db import models
from django.utils import timezone
import uuid

class SignupAttempt(models.Model):
    """
    Records every signup attempt for security analysis.

    Privacy: Email and IP are hashed. Raw values never stored.
    Retention: 90 days, then aggregated and purged.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ALLOWED = 'allowed', 'Allowed'
        CHALLENGED = 'challenged', 'Challenged'
        BLOCKED = 'blocked', 'Blocked'
        COMPLETED = 'completed', 'Completed'
        ABANDONED = 'abandoned', 'Abandoned'

    class BlockReason(models.TextChoices):
        NONE = '', 'None'
        RATE_LIMITED = 'rate_limited', 'Rate Limited'
        HIGH_RISK_SCORE = 'high_risk', 'High Risk Score'
        DISPOSABLE_EMAIL = 'disposable_email', 'Disposable Email'
        HONEYPOT = 'honeypot', 'Honeypot Triggered'
        BLOCKLIST = 'blocklist', 'IP/Email Blocklist'
        CAPTCHA_FAILED = 'captcha_failed', 'CAPTCHA Failed'

    # Identity (hashed for privacy)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email_hash = models.CharField(max_length=64, db_index=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    fingerprint_hash = models.CharField(max_length=64, db_index=True, blank=True)

    # Risk Assessment
    risk_score = models.FloatField(default=0.0)
    risk_level = models.CharField(max_length=20, default='unknown')
    captcha_score = models.FloatField(null=True, blank=True)
    ip_reputation_score = models.FloatField(null=True, blank=True)
    email_risk_score = models.FloatField(null=True, blank=True)
    behavioral_score = models.FloatField(null=True, blank=True)
    device_score = models.FloatField(null=True, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    block_reason = models.CharField(
        max_length=30,
        choices=BlockReason.choices,
        default=BlockReason.NONE,
        blank=True
    )

    # Verification
    captcha_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    # Metadata
    user_agent = models.CharField(max_length=500, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Link to created user (if successful)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='signup_attempts'
    )

    class Meta:
        db_table = 'users_signup_attempt'
        indexes = [
            models.Index(fields=['created_at', 'status']),
            models.Index(fields=['ip_hash', 'created_at']),
            models.Index(fields=['email_hash', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"SignupAttempt {self.id} - {self.status}"
```

### 1.2 EmailVerification Model

Tracks email verification tokens with security constraints.

```python
# apps/users/models.py

class EmailVerification(models.Model):
    """
    Secure email verification tokens.

    Security:
    - Tokens are single-use
    - Tokens expire after 24 hours
    - Only one active token per user at a time
    """

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='email_verifications'
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    invalidated = models.BooleanField(default=False)

    # Audit
    verification_ip = models.CharField(max_length=45, blank=True)

    class Meta:
        db_table = 'users_email_verification'
        indexes = [
            models.Index(fields=['token', 'invalidated']),
            models.Index(fields=['user', 'created_at']),
        ]

    @property
    def is_valid(self) -> bool:
        """Check if token is still valid."""
        return (
            not self.invalidated and
            self.verified_at is None and
            self.expires_at > timezone.now()
        )
```

### 1.3 IPBlocklist Model

Maintains blocklist of known bad IPs.

```python
# apps/users/models.py

class IPBlocklist(models.Model):
    """
    IP addresses blocked from signup.

    Can be individual IPs or CIDR ranges.
    """

    class BlockType(models.TextChoices):
        MANUAL = 'manual', 'Manual Block'
        AUTOMATED = 'automated', 'Automated Detection'
        TEMPORARY = 'temporary', 'Temporary Block'

    ip_address = models.CharField(max_length=45, db_index=True)  # IPv4 or IPv6
    cidr_range = models.CharField(max_length=50, blank=True)  # Optional CIDR
    block_type = models.CharField(
        max_length=20,
        choices=BlockType.choices,
        default=BlockType.AUTOMATED
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)  # Null = permanent
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'users_ip_blocklist'
        indexes = [
            models.Index(fields=['ip_address']),
            models.Index(fields=['expires_at']),
        ]

    @classmethod
    def is_blocked(cls, ip_address: str) -> bool:
        """Check if IP is blocked."""
        now = timezone.now()
        return cls.objects.filter(
            models.Q(ip_address=ip_address) |
            models.Q(cidr_range__contains=ip_address),  # Simplified, needs CIDR logic
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        ).exists()
```

### 1.4 DisposableEmailDomain Model

Maintains list of disposable email domains.

```python
# apps/users/models.py

class DisposableEmailDomain(models.Model):
    """
    Known disposable/temporary email domains.

    Updated periodically from public lists and internal detection.
    """

    domain = models.CharField(max_length=255, unique=True, db_index=True)
    added_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=50, default='manual')  # 'manual', 'api', 'detection'
    confirmed = models.BooleanField(default=True)

    class Meta:
        db_table = 'users_disposable_email_domain'

    @classmethod
    def is_disposable(cls, email: str) -> bool:
        """Check if email domain is disposable."""
        domain = email.split('@')[1].lower()
        return cls.objects.filter(domain=domain, confirmed=True).exists()
```

---

## 2. API Endpoints

### 2.1 Signup Endpoint

```
POST /accounts/signup/
```

**Request Body:**
```json
{
    "email": "user@example.com",
    "password": "securePassword123",
    "password_confirm": "securePassword123",
    "recaptcha_token": "v3_token_here",
    "fingerprint": {
        "hash": "fp_abc123...",
        "components": {
            "user_agent": "Mozilla/5.0...",
            "screen_resolution": "1920x1080",
            "timezone": "America/New_York",
            "language": "en-US"
        }
    },
    "behavioral": {
        "completion_time_seconds": 45,
        "field_focus_count": 8,
        "has_mouse_movement": true,
        "keystroke_variance": 47.3
    }
}
```

**Response (Success - 201):**
```json
{
    "status": "pending_verification",
    "message": "Please check your email to verify your account.",
    "next_step": "email_verification"
}
```

**Response (CAPTCHA Required - 202):**
```json
{
    "status": "captcha_required",
    "message": "Please complete the security check.",
    "captcha_type": "recaptcha_v2",
    "site_key": "public_site_key"
}
```

**Response (Blocked - 403):**
```json
{
    "status": "blocked",
    "message": "Unable to create account at this time.",
    "support_url": "/help/contact/"
}
```

### 2.2 Email Verification Endpoint

```
GET /accounts/verify-email/<token>/
```

**Response (Success - 200):**
```json
{
    "status": "verified",
    "message": "Email verified successfully.",
    "redirect": "/accounts/terms/"
}
```

**Response (Invalid - 400):**
```json
{
    "status": "error",
    "message": "Verification link is invalid or expired.",
    "action": "resend_verification"
}
```

### 2.3 Resend Verification Endpoint

```
POST /accounts/resend-verification/
```

**Request Body:**
```json
{
    "email": "user@example.com"
}
```

**Response (Always 200 - don't leak email existence):**
```json
{
    "status": "sent",
    "message": "If this email is registered, you will receive a verification link."
}
```

### 2.4 CAPTCHA Verification Endpoint

```
POST /accounts/verify-captcha/
```

**Request Body:**
```json
{
    "signup_attempt_id": "uuid-here",
    "captcha_response": "user_response_token"
}
```

**Response (Success - 200):**
```json
{
    "status": "verified",
    "message": "Verification complete.",
    "next_step": "create_account"
}
```

---

## 3. Data Storage Rules

### 3.1 Data Classification

| Data Type | Classification | Storage Rule |
|-----------|---------------|--------------|
| Email (raw) | PII | **NEVER STORE** in logs |
| Email (hashed) | Pseudonymized | Store for 90 days |
| IP Address (raw) | PII | **NEVER STORE** in logs |
| IP Address (hashed) | Pseudonymized | Store for 90 days |
| Password | Secret | Hash with Argon2, never log |
| Verification token | Secret | Store hashed, expire in 24h |
| Risk scores | Operational | Store for 90 days |
| Fingerprint hash | Pseudonymized | Store for 90 days |
| User agent | Semi-PII | Truncate to 200 chars |
| Country code | Aggregate | Store indefinitely |

### 3.2 Hash Functions

```python
# apps/users/security.py

import hashlib
from django.conf import settings

def hash_email(email: str) -> str:
    """
    Hash email for storage.

    Uses salted SHA-256 for one-way transformation.
    Salt is the Django SECRET_KEY to prevent rainbow tables.
    """
    normalized = email.lower().strip()
    salted = f"{settings.SECRET_KEY}:email:{normalized}"
    return hashlib.sha256(salted.encode()).hexdigest()

def hash_ip(ip_address: str) -> str:
    """
    Hash IP address for storage.

    Uses salted SHA-256 for one-way transformation.
    """
    salted = f"{settings.SECRET_KEY}:ip:{ip_address}"
    return hashlib.sha256(salted.encode()).hexdigest()

def hash_fingerprint(fingerprint_data: dict) -> str:
    """
    Hash device fingerprint for storage.

    Creates consistent hash from fingerprint components.
    """
    import json
    # Sort keys for consistent hashing
    normalized = json.dumps(fingerprint_data, sort_keys=True)
    salted = f"{settings.SECRET_KEY}:fp:{normalized}"
    return hashlib.sha256(salted.encode()).hexdigest()
```

### 3.3 Retention Policies

| Data | Retention | Purge Method |
|------|-----------|--------------|
| SignupAttempt records | 90 days | Daily cron job |
| EmailVerification (used) | 30 days | Daily cron job |
| EmailVerification (unused) | 7 days | Daily cron job |
| IPBlocklist (temporary) | Per expires_at | Hourly check |
| IPBlocklist (permanent) | Indefinite | Manual only |
| Aggregated metrics | Indefinite | N/A |

```python
# apps/users/management/commands/purge_old_signups.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.users.models import SignupAttempt, EmailVerification

class Command(BaseCommand):
    help = 'Purge old signup attempts and verification records'

    def handle(self, *args, **options):
        cutoff_90_days = timezone.now() - timedelta(days=90)
        cutoff_30_days = timezone.now() - timedelta(days=30)
        cutoff_7_days = timezone.now() - timedelta(days=7)

        # Purge old signup attempts
        deleted, _ = SignupAttempt.objects.filter(
            created_at__lt=cutoff_90_days
        ).delete()
        self.stdout.write(f"Deleted {deleted} old signup attempts")

        # Purge used verifications
        deleted, _ = EmailVerification.objects.filter(
            verified_at__isnull=False,
            verified_at__lt=cutoff_30_days
        ).delete()
        self.stdout.write(f"Deleted {deleted} old used verifications")

        # Purge expired unused verifications
        deleted, _ = EmailVerification.objects.filter(
            verified_at__isnull=True,
            expires_at__lt=cutoff_7_days
        ).delete()
        self.stdout.write(f"Deleted {deleted} expired verifications")
```

---

## 4. Rate Limiting Specification

### 4.1 Rate Limit Configuration

```python
# apps/users/rate_limits.py

from django.conf import settings

RATE_LIMITS = {
    'signup': {
        'per_ip_hourly': {
            'limit': int(settings.env('SIGNUP_RATE_LIMIT_HOURLY', 5)),
            'window': 3600,  # 1 hour
            'action': 'captcha'
        },
        'per_ip_daily': {
            'limit': int(settings.env('SIGNUP_RATE_LIMIT_DAILY', 20)),
            'window': 86400,  # 24 hours
            'action': 'block'
        },
        'per_session': {
            'limit': 3,
            'window': 3600,
            'action': 'block'
        },
        'global_per_minute': {
            'limit': 100,
            'window': 60,
            'action': 'alert'
        }
    },
    'login': {
        'per_ip': {
            'limit': 10,
            'window': 900,  # 15 minutes
            'action': 'captcha'
        },
        'per_account': {
            'limit': 5,
            'window': 900,
            'action': 'lockout'
        }
    },
    'password_reset': {
        'per_email': {
            'limit': 3,
            'window': 3600,
            'action': 'throttle'
        },
        'per_ip': {
            'limit': 10,
            'window': 3600,
            'action': 'captcha'
        }
    },
    'verification_resend': {
        'per_user': {
            'limit': 3,
            'window': 3600,
            'action': 'throttle'
        }
    }
}
```

### 4.2 Rate Limit Implementation

```python
# apps/users/rate_limits.py

from django.core.cache import cache
from typing import Tuple

class RateLimiter:
    """
    Token bucket rate limiter using Django cache.
    """

    def __init__(self, cache_prefix: str = 'ratelimit'):
        self.prefix = cache_prefix

    def check(
        self,
        key: str,
        limit: int,
        window: int
    ) -> Tuple[bool, int, int]:
        """
        Check rate limit and increment counter.

        Returns:
            (allowed: bool, remaining: int, reset_in: int)
        """
        cache_key = f"{self.prefix}:{key}"

        # Get current count
        current = cache.get(cache_key, 0)

        if current >= limit:
            # Get TTL for reset time
            ttl = cache.ttl(cache_key) or window
            return False, 0, ttl

        # Increment
        try:
            new_count = cache.incr(cache_key)
        except ValueError:
            # Key doesn't exist, create it
            cache.set(cache_key, 1, window)
            new_count = 1

        remaining = max(0, limit - new_count)
        return True, remaining, window

    def reset(self, key: str) -> None:
        """Reset rate limit counter."""
        cache_key = f"{self.prefix}:{key}"
        cache.delete(cache_key)


# Convenience functions
rate_limiter = RateLimiter()

def check_signup_limit(ip_address: str) -> Tuple[bool, str]:
    """
    Check all signup rate limits.

    Returns:
        (allowed: bool, action: str)
    """
    limits = RATE_LIMITS['signup']

    # Check hourly limit
    allowed, remaining, reset = rate_limiter.check(
        f"signup:hourly:{ip_address}",
        limits['per_ip_hourly']['limit'],
        limits['per_ip_hourly']['window']
    )
    if not allowed:
        return False, limits['per_ip_hourly']['action']

    # Check daily limit
    allowed, remaining, reset = rate_limiter.check(
        f"signup:daily:{ip_address}",
        limits['per_ip_daily']['limit'],
        limits['per_ip_daily']['window']
    )
    if not allowed:
        return False, limits['per_ip_daily']['action']

    return True, 'allow'
```

---

## 5. Email Verification Token Rules

### 5.1 Token Generation

```python
# apps/users/services/verification.py

import secrets
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from apps.users.models import EmailVerification

class VerificationService:
    """
    Handles email verification token lifecycle.
    """

    TOKEN_LENGTH = 32  # 256 bits of entropy
    EXPIRY_HOURS = 24
    MAX_RESENDS_PER_HOUR = 3

    def generate_token(self) -> str:
        """Generate cryptographically secure token."""
        return secrets.token_urlsafe(self.TOKEN_LENGTH)

    def create_verification(self, user) -> EmailVerification:
        """
        Create new verification token for user.

        Invalidates any existing tokens.
        """
        # Invalidate existing tokens
        EmailVerification.objects.filter(
            user=user,
            verified_at__isnull=True,
            invalidated=False
        ).update(invalidated=True)

        # Create new token
        return EmailVerification.objects.create(
            user=user,
            token=self.generate_token(),
            expires_at=timezone.now() + timedelta(hours=self.EXPIRY_HOURS)
        )

    def send_verification_email(self, user, verification: EmailVerification) -> bool:
        """Send verification email to user."""
        verify_url = f"{settings.SITE_URL}/accounts/verify-email/{verification.token}/"

        html_content = render_to_string('emails/verify_email.html', {
            'user': user,
            'verify_url': verify_url,
            'expiry_hours': self.EXPIRY_HOURS
        })

        try:
            send_mail(
                subject='Verify your Whole Life Journey account',
                message=f'Click here to verify: {verify_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_content,
                fail_silently=False
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")
            return False

    def verify_token(self, token: str, ip_address: str = '') -> Tuple[bool, str, User]:
        """
        Verify token and activate user.

        Returns:
            (success: bool, error_message: str, user: User|None)
        """
        try:
            verification = EmailVerification.objects.select_related('user').get(
                token=token,
                invalidated=False,
                verified_at__isnull=True
            )
        except EmailVerification.DoesNotExist:
            return False, "Invalid verification link.", None

        if not verification.is_valid:
            return False, "Verification link has expired.", None

        # Mark as verified
        verification.verified_at = timezone.now()
        verification.verification_ip = ip_address
        verification.save()

        # Update user
        user = verification.user
        user.email_verified = True
        user.save(update_fields=['email_verified'])

        return True, "", user

    def can_resend(self, user) -> Tuple[bool, int]:
        """
        Check if user can request another verification email.

        Returns:
            (allowed: bool, wait_seconds: int)
        """
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_count = EmailVerification.objects.filter(
            user=user,
            created_at__gte=one_hour_ago
        ).count()

        if recent_count >= self.MAX_RESENDS_PER_HOUR:
            # Find oldest in window to calculate wait time
            oldest = EmailVerification.objects.filter(
                user=user,
                created_at__gte=one_hour_ago
            ).order_by('created_at').first()

            if oldest:
                wait_until = oldest.created_at + timedelta(hours=1)
                wait_seconds = int((wait_until - timezone.now()).total_seconds())
                return False, max(0, wait_seconds)

        return True, 0
```

---

## 6. Third-Party Service Integrations

### 6.1 Approved Services

| Service | Use Case | Provider | Fallback |
|---------|----------|----------|----------|
| CAPTCHA | Bot detection | reCAPTCHA v3 | hCaptcha |
| IP Reputation | Fraud scoring | IPQualityScore | MaxMind |
| Email Validation | Deliverability | Kickbox | ZeroBounce |
| WAF | Edge protection | Cloudflare | Railway Edge |
| SMS (future) | Phone verification | Twilio Verify | N/A |

### 6.2 reCAPTCHA Integration

```python
# apps/users/services/captcha.py

import requests
from django.conf import settings

class RecaptchaService:
    """
    Google reCAPTCHA v3 integration.
    """

    VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'
    TIMEOUT = 5  # seconds

    def __init__(self):
        self.secret_key = settings.RECAPTCHA_V3_SECRET_KEY
        self.site_key = settings.RECAPTCHA_V3_SITE_KEY
        self.threshold = settings.RECAPTCHA_SCORE_THRESHOLD

    def verify(self, token: str, remote_ip: str = None) -> dict:
        """
        Verify reCAPTCHA token.

        Returns:
            {
                'success': bool,
                'score': float,  # 0.0 to 1.0
                'action': str,
                'error_codes': list
            }
        """
        try:
            response = requests.post(
                self.VERIFY_URL,
                data={
                    'secret': self.secret_key,
                    'response': token,
                    'remoteip': remote_ip
                },
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            return {
                'success': data.get('success', False),
                'score': data.get('score', 0.0),
                'action': data.get('action', ''),
                'error_codes': data.get('error-codes', [])
            }
        except requests.RequestException as e:
            logger.error(f"reCAPTCHA verification failed: {e}")
            # Fail open with medium score on API failure
            return {
                'success': True,
                'score': 0.5,
                'action': 'unknown',
                'error_codes': ['api_error']
            }

    def is_human(self, token: str, remote_ip: str = None) -> Tuple[bool, float]:
        """
        Simple check if token indicates human.

        Returns:
            (is_human: bool, score: float)
        """
        result = self.verify(token, remote_ip)
        score = result.get('score', 0.0)
        return score >= self.threshold, score
```

### 6.3 IPQualityScore Integration

```python
# apps/users/services/ip_reputation.py

import requests
from django.conf import settings
from django.core.cache import cache

class IPQualityService:
    """
    IPQualityScore.com integration for IP reputation.
    """

    BASE_URL = 'https://ipqualityscore.com/api/json/ip'
    CACHE_TTL = 3600  # 1 hour
    TIMEOUT = 5

    def __init__(self):
        self.api_key = settings.IPQS_API_KEY
        self.strictness = settings.IPQS_STRICTNESS

    def get_reputation(self, ip_address: str) -> dict:
        """
        Get IP reputation data.

        Returns cached result if available.
        """
        cache_key = f"ipqs:{ip_address}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            response = requests.get(
                f"{self.BASE_URL}/{self.api_key}/{ip_address}",
                params={
                    'strictness': self.strictness,
                    'allow_public_access_points': 'true',
                    'fast': 'true',
                    'lighter_penalties': 'true'
                },
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            # Cache successful response
            cache.set(cache_key, data, self.CACHE_TTL)
            return data

        except requests.RequestException as e:
            logger.error(f"IPQS lookup failed for {ip_address}: {e}")
            # Return neutral response on failure
            return {
                'success': False,
                'fraud_score': 50,
                'vpn': False,
                'tor': False,
                'proxy': False,
                'recent_abuse': False
            }

    def calculate_risk(self, ip_address: str) -> float:
        """
        Calculate risk score from IP reputation.

        Returns:
            Risk score 0.0 (safe) to 1.0 (dangerous)
        """
        data = self.get_reputation(ip_address)

        fraud_score = data.get('fraud_score', 50)

        # Base risk from fraud score
        if fraud_score <= 25:
            risk = 0.0
        elif fraud_score <= 50:
            risk = 0.2
        elif fraud_score <= 75:
            risk = 0.5
        elif fraud_score <= 85:
            risk = 0.8
        else:
            risk = 1.0

        # Adjustments for specific signals
        if data.get('tor', False):
            risk = min(1.0, risk + 0.3)
        if data.get('vpn', False):
            risk = min(1.0, risk + 0.2)
        if data.get('proxy', False):
            risk = min(1.0, risk + 0.2)
        if data.get('recent_abuse', False):
            risk = min(1.0, risk + 0.3)

        return risk
```

### 6.4 Email Validation Integration

```python
# apps/users/services/email_validation.py

import requests
from django.conf import settings
from django.core.cache import cache

class EmailValidationService:
    """
    Email validation and deliverability checking.

    Uses Kickbox API with ZeroBounce fallback.
    """

    KICKBOX_URL = 'https://api.kickbox.com/v2/verify'
    CACHE_TTL = 86400  # 24 hours
    TIMEOUT = 10

    def __init__(self):
        self.api_key = settings.KICKBOX_API_KEY

    def validate(self, email: str) -> dict:
        """
        Validate email address.

        Returns:
            {
                'valid': bool,
                'disposable': bool,
                'deliverable': str,  # 'deliverable', 'undeliverable', 'risky', 'unknown'
                'reason': str
            }
        """
        cache_key = f"email_valid:{email.lower()}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            response = requests.get(
                self.KICKBOX_URL,
                params={
                    'email': email,
                    'apikey': self.api_key
                },
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            result = {
                'valid': data.get('result') in ['deliverable', 'risky'],
                'disposable': data.get('disposable', False),
                'deliverable': data.get('result', 'unknown'),
                'reason': data.get('reason', '')
            }

            cache.set(cache_key, result, self.CACHE_TTL)
            return result

        except requests.RequestException as e:
            logger.error(f"Email validation failed for {email}: {e}")
            # Fail open on API error
            return {
                'valid': True,
                'disposable': False,
                'deliverable': 'unknown',
                'reason': 'api_error'
            }
```

---

## 7. Database Migrations

### 7.1 Migration Plan

```python
# apps/users/migrations/0025_signup_security.py

from django.db import migrations, models
import django.db.models.deletion
import uuid

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0024_convert_legacy_timezones'),
    ]

    operations = [
        # SignupAttempt model
        migrations.CreateModel(
            name='SignupAttempt',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4,
                    editable=False,
                    primary_key=True
                )),
                ('email_hash', models.CharField(db_index=True, max_length=64)),
                ('ip_hash', models.CharField(db_index=True, max_length=64)),
                ('fingerprint_hash', models.CharField(
                    blank=True,
                    db_index=True,
                    max_length=64
                )),
                ('risk_score', models.FloatField(default=0.0)),
                ('risk_level', models.CharField(default='unknown', max_length=20)),
                ('captcha_score', models.FloatField(blank=True, null=True)),
                ('ip_reputation_score', models.FloatField(blank=True, null=True)),
                ('email_risk_score', models.FloatField(blank=True, null=True)),
                ('behavioral_score', models.FloatField(blank=True, null=True)),
                ('device_score', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('allowed', 'Allowed'),
                        ('challenged', 'Challenged'),
                        ('blocked', 'Blocked'),
                        ('completed', 'Completed'),
                        ('abandoned', 'Abandoned')
                    ],
                    default='pending',
                    max_length=20
                )),
                ('block_reason', models.CharField(
                    blank=True,
                    choices=[
                        ('', 'None'),
                        ('rate_limited', 'Rate Limited'),
                        ('high_risk', 'High Risk Score'),
                        ('disposable_email', 'Disposable Email'),
                        ('honeypot', 'Honeypot Triggered'),
                        ('blocklist', 'IP/Email Blocklist'),
                        ('captcha_failed', 'CAPTCHA Failed')
                    ],
                    default='',
                    max_length=30
                )),
                ('captcha_verified', models.BooleanField(default=False)),
                ('phone_verified', models.BooleanField(default=False)),
                ('email_verified', models.BooleanField(default=False)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('country_code', models.CharField(blank=True, max_length=2)),
                ('created_at', models.DateTimeField(db_index=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='signup_attempts',
                    to='users.user'
                )),
            ],
            options={
                'db_table': 'users_signup_attempt',
                'ordering': ['-created_at'],
            },
        ),
        # Add indexes
        migrations.AddIndex(
            model_name='signupattempt',
            index=models.Index(
                fields=['created_at', 'status'],
                name='signup_created_status_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='signupattempt',
            index=models.Index(
                fields=['ip_hash', 'created_at'],
                name='signup_ip_created_idx'
            ),
        ),
        # EmailVerification model
        migrations.CreateModel(
            name='EmailVerification',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID'
                )),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('created_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField()),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('invalidated', models.BooleanField(default=False)),
                ('verification_ip', models.CharField(blank=True, max_length=45)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='email_verifications',
                    to='users.user'
                )),
            ],
            options={
                'db_table': 'users_email_verification',
            },
        ),
        # IPBlocklist model
        migrations.CreateModel(
            name='IPBlocklist',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID'
                )),
                ('ip_address', models.CharField(db_index=True, max_length=45)),
                ('cidr_range', models.CharField(blank=True, max_length=50)),
                ('block_type', models.CharField(
                    choices=[
                        ('manual', 'Manual Block'),
                        ('automated', 'Automated Detection'),
                        ('temporary', 'Temporary Block')
                    ],
                    default='automated',
                    max_length=20
                )),
                ('reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='users.user'
                )),
            ],
            options={
                'db_table': 'users_ip_blocklist',
            },
        ),
        # DisposableEmailDomain model
        migrations.CreateModel(
            name='DisposableEmailDomain',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID'
                )),
                ('domain', models.CharField(db_index=True, max_length=255, unique=True)),
                ('added_at', models.DateTimeField()),
                ('source', models.CharField(default='manual', max_length=50)),
                ('confirmed', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'users_disposable_email_domain',
            },
        ),
        # Add email_verified to User model
        migrations.AddField(
            model_name='user',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
    ]
```

---

## Related Documents

- `docs/wlj_security_signup_threat_model.md` - Threat model (Phase 1)
- `docs/wlj_security_signup_flow.md` - Target signup flow (Phase 2)
- `docs/wlj_security_risk_scoring.md` - Risk scoring model (Phase 3)
- `docs/wlj_security_controls.md` - Security controls (Phase 4)
- `docs/wlj_security_acceptance_criteria.md` - Acceptance criteria (Phase 6)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
