# ==============================================================================
# File: docs/wlj_security_controls.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Layered security controls for signup anti-fraud system
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Security Controls by Layer

## Document Purpose

This document specifies concrete, configurable security controls across application, infrastructure, identity, and monitoring layers. Each control includes default settings and rationale for why it matters.

---

## Control Layers Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     MONITORING & RESPONSE                        │
│  (Logging, Alerting, Incident Response, Analytics)              │
├─────────────────────────────────────────────────────────────────┤
│                     IDENTITY LAYER                               │
│  (Authentication, Email Verification, MFA, Session Management)  │
├─────────────────────────────────────────────────────────────────┤
│                     APPLICATION LAYER                            │
│  (Form Validation, Rate Limiting, CAPTCHA, Honeypots)           │
├─────────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE LAYER                         │
│  (WAF, CDN, IP Reputation, DDoS Protection)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Application Layer Controls

### 1.1 Form Validation

| Control | Default | Rationale |
|---------|---------|-----------|
| Email format validation | Strict RFC 5322 | Reject malformed emails early |
| Email domain MX check | Enabled | Verify email can receive mail |
| Password minimum length | 8 characters | Balance security and usability |
| Password complexity | Letter + number required | Prevent trivial passwords |
| Password breach check | Enabled (HaveIBeenPwned) | Block known compromised passwords |

**Implementation:**

```python
# apps/users/validators.py

import re
import hashlib
import requests
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

def validate_email_strict(email: str) -> None:
    """Strict email validation with MX record check."""
    # Standard format validation
    EmailValidator()(email)

    # Extract domain
    domain = email.split('@')[1].lower()

    # Check MX record exists
    if not has_mx_record(domain):
        raise ValidationError("Email domain does not accept mail.")

def validate_password_strength(password: str) -> None:
    """Validate password meets security requirements."""
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")

    if not re.search(r'[a-zA-Z]', password):
        raise ValidationError("Password must contain at least one letter.")

    if not re.search(r'\d', password):
        raise ValidationError("Password must contain at least one number.")

def check_password_breached(password: str) -> bool:
    """Check if password appears in known breaches (k-anonymity)."""
    sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    response = requests.get(
        f'https://api.pwnedpasswords.com/range/{prefix}',
        timeout=5
    )

    if response.status_code == 200:
        for line in response.text.splitlines():
            hash_suffix, count = line.split(':')
            if hash_suffix == suffix:
                return True
    return False
```

### 1.2 Honeypot Fields

| Control | Default | Rationale |
|---------|---------|-----------|
| Honeypot field name | `website` | Common field bots fill |
| Honeypot visibility | CSS hidden | Invisible to humans |
| Action on trigger | Silent reject | Don't reveal detection |

**Implementation:**

```html
<!-- templates/account/signup.html -->
<div style="position: absolute; left: -9999px; top: -9999px;">
    <label for="id_website">Website</label>
    <input type="text" name="website" id="id_website"
           autocomplete="off" tabindex="-1">
</div>
```

```python
# apps/users/forms.py

class SignupForm(forms.Form):
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_website(self):
        if self.cleaned_data.get('website'):
            logger.warning(f"Honeypot triggered from IP: {self.request_ip}")
            raise forms.ValidationError("Unable to create account.")
        return ''
```

### 1.3 API Request Validation

| Control | Default | Rationale |
|---------|---------|-----------|
| CSRF protection | Enabled | Prevent cross-site attacks |
| Content-Type validation | application/json only | Reject unexpected formats |
| Request size limit | 10KB for signup | Prevent payload attacks |
| JSON schema validation | Enabled | Reject malformed requests |

**Implementation:**

```python
# apps/users/views.py

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

@csrf_protect
@require_POST
def signup_api(request):
    # Validate content type
    if request.content_type != 'application/json':
        return JsonResponse({'error': 'Invalid content type'}, status=415)

    # Validate request size
    if len(request.body) > 10 * 1024:  # 10KB
        return JsonResponse({'error': 'Request too large'}, status=413)

    # Parse and validate JSON
    try:
        data = json.loads(request.body)
        validate_signup_schema(data)
    except (json.JSONDecodeError, ValidationError) as e:
        return JsonResponse({'error': 'Invalid request'}, status=400)
```

### 1.4 Rate Limiting (Application Level)

| Limit | Threshold | Window | Action |
|-------|-----------|--------|--------|
| Signup attempts per IP | 5 | 1 hour | Show CAPTCHA |
| Signup attempts per IP | 20 | 24 hours | Block IP |
| Failed logins per IP | 10 | 15 min | Show CAPTCHA |
| Failed logins per account | 5 | 15 min | Lock account |
| Password reset per email | 3 | 1 hour | Throttle |
| Email verification resend | 3 | 1 hour | Throttle |

**Implementation:**

```python
# apps/users/rate_limits.py

from django.core.cache import cache
from django.http import HttpResponseTooManyRequests

def check_rate_limit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """
    Check and increment rate limit.

    Returns:
        (allowed: bool, remaining: int)
    """
    current = cache.get(key, 0)
    if current >= limit:
        return False, 0

    # Increment with atomic operation
    try:
        new_count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        new_count = 1

    return True, limit - new_count

def rate_limit_signup(ip_address: str) -> bool:
    """Check signup rate limits for IP."""
    # Hourly limit
    hourly_key = f"signup:hourly:{ip_address}"
    allowed, _ = check_rate_limit(hourly_key, limit=5, window=3600)
    if not allowed:
        return False

    # Daily limit
    daily_key = f"signup:daily:{ip_address}"
    allowed, _ = check_rate_limit(daily_key, limit=20, window=86400)
    return allowed
```

---

## 2. Infrastructure Layer Controls

### 2.1 WAF (Web Application Firewall) Rules

**Provider:** Cloudflare (recommended) or Railway Edge

| Rule | Action | Rationale |
|------|--------|-----------|
| Block known bad IPs | Block | Threat intelligence |
| Block TOR exit nodes | Challenge | High abuse potential |
| Rate limit /accounts/signup/ | 10 req/min/IP | Prevent floods |
| Rate limit /accounts/login/ | 20 req/min/IP | Prevent brute force |
| Block datacenter IPs | Challenge | Reduce bot traffic |
| Block countries (configurable) | Challenge | Geographic risk |

**Cloudflare WAF Configuration:**

```yaml
# cloudflare-waf-rules.yaml (reference)

rules:
  - name: "Block Known Bad IPs"
    expression: "(cf.threat_score gt 30)"
    action: "block"

  - name: "Challenge TOR"
    expression: "(cf.edge.server_ip in $cf.tor)"
    action: "challenge"

  - name: "Rate Limit Signup"
    expression: "(http.request.uri.path eq \"/accounts/signup/\")"
    action: "rate_limit"
    rate_limit:
      requests_per_period: 10
      period: 60

  - name: "Challenge Datacenter IPs"
    expression: "(cf.bot_management.score lt 30)"
    action: "challenge"
```

### 2.2 IP Reputation Service

**Provider:** IPQualityScore (primary), MaxMind (backup)

| Check | Threshold | Action |
|-------|-----------|--------|
| Fraud score | > 85 | Block |
| Fraud score | 50-85 | CAPTCHA |
| VPN detected | true | +0.2 risk |
| TOR detected | true | +0.3 risk |
| Proxy detected | true | +0.2 risk |
| Recent abuse | true | +0.3 risk |

**Integration:**

```python
# apps/users/services/ip_reputation.py

import requests
from django.conf import settings
from django.core.cache import cache

def get_ip_reputation(ip_address: str) -> dict:
    """Get IP reputation from IPQualityScore."""
    cache_key = f"ip_reputation:{ip_address}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    response = requests.get(
        'https://ipqualityscore.com/api/json/ip/'
        f'{settings.IPQS_API_KEY}/{ip_address}',
        params={
            'strictness': 1,
            'allow_public_access_points': True
        },
        timeout=5
    )

    if response.status_code == 200:
        data = response.json()
        # Cache for 1 hour
        cache.set(cache_key, data, 3600)
        return data

    # Fallback to neutral on API failure
    return {'fraud_score': 50, 'vpn': False, 'tor': False}
```

### 2.3 CDN Bot Protection

**Provider:** Cloudflare Bot Management or Turnstile

| Feature | Setting | Rationale |
|---------|---------|-----------|
| Bot score threshold | < 30 = challenge | Filter automated traffic |
| Super Bot Fight Mode | Enabled | Block known bad bots |
| Browser integrity check | Enabled | Verify real browsers |
| JavaScript detection | Enabled | Require JS execution |

### 2.4 DDoS Protection

| Control | Setting | Rationale |
|---------|---------|-----------|
| Layer 7 protection | Enabled | Application-layer attacks |
| Rate limiting (edge) | 100 req/sec/IP | Prevent floods |
| Challenge on anomaly | Enabled | Unusual traffic patterns |
| Geographic blocking | Configurable | Block high-risk regions |

---

## 3. Identity Layer Controls

### 3.1 Password Policy

| Control | Default | Rationale |
|---------|---------|-----------|
| Minimum length | 8 characters | NIST 800-63B recommendation |
| Maximum length | 128 characters | Allow passphrases |
| Complexity required | Letter + number | Balance security/usability |
| Breached password check | Enabled | Block known compromised |
| Password history | Last 5 | Prevent reuse |
| Password age | None (no expiry) | NIST recommends against forced rotation |

### 3.2 Email Verification

| Control | Default | Rationale |
|---------|---------|-----------|
| Required for access | Yes (pending state) | Verify email ownership |
| Token expiry | 24 hours | Balance security/usability |
| Token length | 32 characters | Sufficient entropy |
| One-time use | Yes | Prevent token reuse |
| Resend rate limit | 3 per hour | Prevent abuse |
| Verification reminder | 1, 3, 7 days | Re-engage users |

**Token Generation:**

```python
# apps/users/services/email_verification.py

import secrets
from django.utils import timezone
from datetime import timedelta

def generate_verification_token() -> str:
    """Generate secure verification token."""
    return secrets.token_urlsafe(32)

def create_verification(user) -> EmailVerification:
    """Create email verification record."""
    # Invalidate existing tokens
    EmailVerification.objects.filter(
        user=user,
        verified_at__isnull=True
    ).update(invalidated=True)

    return EmailVerification.objects.create(
        user=user,
        token=generate_verification_token(),
        expires_at=timezone.now() + timedelta(hours=24)
    )

def verify_token(token: str) -> tuple[bool, str]:
    """
    Verify email token.

    Returns:
        (success: bool, error_message: str)
    """
    try:
        verification = EmailVerification.objects.get(
            token=token,
            invalidated=False,
            verified_at__isnull=True
        )
    except EmailVerification.DoesNotExist:
        return False, "Invalid or expired verification link."

    if verification.expires_at < timezone.now():
        return False, "Verification link has expired."

    # Mark as verified
    verification.verified_at = timezone.now()
    verification.save()

    # Update user state
    verification.user.email_verified = True
    verification.user.save()

    return True, ""
```

### 3.3 MFA (Multi-Factor Authentication)

| Control | Default | Rationale |
|---------|---------|-----------|
| MFA available | Yes (optional) | Provide strong security option |
| MFA methods | TOTP, WebAuthn | Industry standards |
| MFA for high-risk actions | Recommended | Protect sensitive operations |
| Recovery codes | 10 codes | Account recovery |
| Remember device | 30 days | Reduce friction for trusted devices |

**WebAuthn (Biometric) - Already Implemented:**
- Registration and login views in `apps/users/views.py`
- `WebAuthnCredential` model for credential storage
- Platform authenticator support (Face ID, Touch ID, Windows Hello)

### 3.4 Session Management

| Control | Default | Rationale |
|---------|---------|-----------|
| Session duration | 14 days | Balance security/usability |
| Idle timeout | 24 hours | Automatic logout |
| Concurrent sessions | Unlimited | Allow multiple devices |
| Session binding | IP + User-Agent | Detect hijacking |
| Secure cookie | Yes (HTTPS only) | Prevent interception |
| HttpOnly cookie | Yes | Prevent XSS access |
| SameSite cookie | Lax | CSRF protection |

**Session Configuration:**

```python
# settings.py

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 14 * 24 * 60 * 60  # 14 days
SESSION_COOKIE_SECURE = True  # Require HTTPS
SESSION_COOKIE_HTTPONLY = True  # No JS access
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
```

### 3.5 Account Lockout

| Control | Default | Rationale |
|---------|---------|-----------|
| Failed login threshold | 5 attempts | Before lockout |
| Lockout duration | 15 minutes | Temporary block |
| Lockout scope | Per account | Target specific account |
| IP-based lockout | 10 attempts | Broader protection |
| Admin notification | On lockout | Awareness |

---

## 4. Monitoring & Response Controls

### 4.1 Logging Requirements

| Event | Log Level | Fields |
|-------|-----------|--------|
| Signup attempt | INFO | timestamp, ip_hash, email_hash, risk_score, outcome |
| Signup blocked | WARNING | timestamp, ip_hash, block_reason, risk_breakdown |
| Login attempt | INFO | timestamp, ip_hash, email_hash, success |
| Login failed | WARNING | timestamp, ip_hash, email_hash, failure_reason |
| Rate limit hit | WARNING | timestamp, ip_hash, limit_type, count |
| Account locked | WARNING | timestamp, email_hash, trigger |
| Suspicious activity | WARNING | timestamp, ip_hash, activity_type, details |

**Logging Implementation:**

```python
# apps/users/logging.py

import logging
import hashlib
from django.conf import settings

security_logger = logging.getLogger('security')

def hash_pii(value: str) -> str:
    """Hash PII for logging (one-way, salted)."""
    salted = f"{settings.SECRET_KEY}:{value}"
    return hashlib.sha256(salted.encode()).hexdigest()[:16]

def log_signup_attempt(request, email: str, risk_score: float, outcome: str):
    """Log signup attempt with hashed PII."""
    security_logger.info(
        "signup_attempt",
        extra={
            'ip_hash': hash_pii(get_client_ip(request)),
            'email_hash': hash_pii(email),
            'risk_score': risk_score,
            'outcome': outcome,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200]
        }
    )

def log_signup_blocked(request, reason: str, risk_breakdown: dict):
    """Log blocked signup attempt."""
    security_logger.warning(
        "signup_blocked",
        extra={
            'ip_hash': hash_pii(get_client_ip(request)),
            'block_reason': reason,
            'risk_breakdown': risk_breakdown
        }
    )
```

### 4.2 Alerting Thresholds

| Metric | Threshold | Alert Channel | Severity |
|--------|-----------|---------------|----------|
| Signup blocks/min | > 50 | PagerDuty | Critical |
| Failed logins/min | > 100 | PagerDuty | Critical |
| Rate limit hits/min | > 200 | Slack | Warning |
| Bot score failures/hr | > 500 | Slack | Warning |
| CAPTCHA challenges/hr | > 1000 | Slack | Info |
| New disposable domain | Any | Email | Info |

**Alert Configuration:**

```python
# apps/users/alerts.py

from django.core.cache import cache
import requests

def check_and_alert(metric: str, threshold: int, window: int = 60):
    """Check metric against threshold and alert if exceeded."""
    cache_key = f"alert_metric:{metric}"
    current = cache.get(cache_key, 0)

    if current >= threshold:
        # Check if already alerted recently
        alert_key = f"alert_sent:{metric}"
        if not cache.get(alert_key):
            send_alert(metric, current, threshold)
            cache.set(alert_key, True, 300)  # 5 min cooldown

def send_alert(metric: str, value: int, threshold: int):
    """Send alert to configured channel."""
    alert_config = ALERT_CONFIG.get(metric, {})

    if alert_config.get('channel') == 'pagerduty':
        send_pagerduty_alert(metric, value, threshold)
    elif alert_config.get('channel') == 'slack':
        send_slack_alert(metric, value, threshold)
```

### 4.3 Incident Response Procedures

| Incident | Detection | Immediate Action | Follow-up |
|----------|-----------|------------------|-----------|
| Bot flood | High signup blocks | Tighten rate limits | Analyze patterns |
| Credential stuffing | Login failures spike | Enable CAPTCHA | Check for compromises |
| Account takeover | User report | Lock account | Investigate, reset |
| Abuse campaign | Pattern detected | Block source IPs | Update blocklists |
| Zero-day bypass | Manual detection | Emergency patch | Post-mortem |

### 4.4 Analytics Dashboard

**Key Metrics to Track:**

| Metric | Purpose | Update Frequency |
|--------|---------|------------------|
| Signups (success/blocked) | Conversion tracking | Real-time |
| Risk score distribution | Threshold tuning | Hourly |
| Block reasons breakdown | Pattern analysis | Daily |
| Geographic distribution | Risk assessment | Daily |
| CAPTCHA solve rate | Friction analysis | Daily |
| Email verification rate | Funnel analysis | Daily |
| Time to verification | UX measurement | Weekly |

---

## 5. Control Configuration Summary

### Environment Variables

```bash
# .env (example configuration)

# CAPTCHA
RECAPTCHA_V3_SITE_KEY=your-site-key
RECAPTCHA_V3_SECRET_KEY=your-secret-key
RECAPTCHA_SCORE_THRESHOLD=0.5

# IP Reputation
IPQS_API_KEY=your-ipqs-key
IPQS_STRICTNESS=1

# Rate Limits
SIGNUP_RATE_LIMIT_HOURLY=5
SIGNUP_RATE_LIMIT_DAILY=20
LOGIN_RATE_LIMIT_PER_IP=10
LOGIN_RATE_LIMIT_PER_ACCOUNT=5

# Risk Thresholds
RISK_THRESHOLD_LOW=0.30
RISK_THRESHOLD_MEDIUM=0.60
RISK_THRESHOLD_HIGH=0.80

# Email Verification
EMAIL_VERIFICATION_EXPIRY_HOURS=24
EMAIL_VERIFICATION_RESEND_LIMIT=3

# Session
SESSION_DURATION_DAYS=14
SESSION_IDLE_TIMEOUT_HOURS=24
```

### Django Settings

```python
# settings.py (security-related)

# CAPTCHA
RECAPTCHA_V3_SITE_KEY = env('RECAPTCHA_V3_SITE_KEY')
RECAPTCHA_V3_SECRET_KEY = env('RECAPTCHA_V3_SECRET_KEY')
RECAPTCHA_SCORE_THRESHOLD = float(env('RECAPTCHA_SCORE_THRESHOLD', 0.5))

# Rate Limiting
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# Session Security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
```

---

## Control Implementation Checklist

### Phase 1: Immediate (Week 1-2)

- [ ] Honeypot field on signup form
- [ ] Application-level rate limiting
- [ ] Basic logging for signup/login
- [ ] Email format validation
- [ ] Password strength requirements

### Phase 2: Short-term (Week 3-4)

- [ ] reCAPTCHA v3 integration
- [ ] Disposable email blocking
- [ ] IP reputation API integration
- [ ] Enhanced logging with hashed PII
- [ ] Basic alerting setup

### Phase 3: Medium-term (Month 2)

- [ ] WAF rules configuration
- [ ] Behavioral signal collection
- [ ] Device fingerprinting
- [ ] Full risk scoring implementation
- [ ] Analytics dashboard

### Phase 4: Long-term (Month 3+)

- [ ] Phone verification option
- [ ] Advanced anomaly detection
- [ ] ML-based risk scoring (optional)
- [ ] Automated incident response
- [ ] Regular tuning and review process

---

## Related Documents

- `docs/wlj_security_signup_threat_model.md` - Threat model (Phase 1)
- `docs/wlj_security_signup_flow.md` - Target signup flow (Phase 2)
- `docs/wlj_security_risk_scoring.md` - Risk scoring model (Phase 3)
- `docs/wlj_security_engineering_spec.md` - Engineering specification (Phase 5)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
