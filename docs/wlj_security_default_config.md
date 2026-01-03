# ==============================================================================
# File: docs/wlj_security_default_config.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Recommended default configuration for signup security
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Signup Security - Recommended Default Configuration

## Document Purpose

This document provides a clear, opinionated default configuration for the WLJ secure signup system that can be deployed immediately. All values are production-ready and balance security with user experience.

---

## Configuration Version

**Version:** 1.0.0
**Effective Date:** 2026-01-02
**Review Schedule:** Quarterly

---

## Quick Start

Copy these environment variables to your `.env` file:

```bash
# ==============================================================================
# WLJ SIGNUP SECURITY CONFIGURATION v1.0.0
# ==============================================================================

# --- CAPTCHA (reCAPTCHA v3) ---
RECAPTCHA_V3_SITE_KEY=your-site-key-here
RECAPTCHA_V3_SECRET_KEY=your-secret-key-here
RECAPTCHA_SCORE_THRESHOLD=0.5

# --- IP REPUTATION (IPQualityScore) ---
IPQS_API_KEY=your-ipqs-key-here
IPQS_STRICTNESS=1
IPQS_CACHE_TTL=3600

# --- RATE LIMITS ---
SIGNUP_RATE_LIMIT_HOURLY=5
SIGNUP_RATE_LIMIT_DAILY=20
LOGIN_RATE_LIMIT_PER_IP=10
LOGIN_RATE_LIMIT_PER_ACCOUNT=5
PASSWORD_RESET_RATE_LIMIT=3

# --- RISK THRESHOLDS ---
RISK_THRESHOLD_LOW=0.30
RISK_THRESHOLD_MEDIUM=0.60
RISK_THRESHOLD_HIGH=0.80

# --- EMAIL VERIFICATION ---
EMAIL_VERIFICATION_EXPIRY_HOURS=24
EMAIL_VERIFICATION_RESEND_LIMIT=3
EMAIL_VERIFICATION_TOKEN_LENGTH=32

# --- ACCOUNT LOCKOUT ---
ACCOUNT_LOCKOUT_THRESHOLD=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=15

# --- SESSION SECURITY ---
SESSION_DURATION_DAYS=14
SESSION_IDLE_TIMEOUT_HOURS=24
```

---

## Detailed Configuration

### 1. CAPTCHA Configuration

#### reCAPTCHA v3 (Invisible CAPTCHA)

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `RECAPTCHA_V3_SITE_KEY` | (required) | N/A | Public site key from Google |
| `RECAPTCHA_V3_SECRET_KEY` | (required) | N/A | Secret key from Google |
| `RECAPTCHA_SCORE_THRESHOLD` | 0.5 | 0.1 - 0.9 | Score below this triggers visible CAPTCHA |

**Tuning Notes:**
- Lower threshold (0.3) = more lenient, fewer challenges
- Higher threshold (0.7) = stricter, more false positives
- Start at 0.5, adjust based on false positive rate

#### reCAPTCHA v2 (Fallback Challenge)

| Setting | Default | Description |
|---------|---------|-------------|
| `RECAPTCHA_V2_SITE_KEY` | (optional) | For visible CAPTCHA challenges |
| `RECAPTCHA_V2_SECRET_KEY` | (optional) | For visible CAPTCHA verification |

---

### 2. IP Reputation Configuration

#### IPQualityScore Integration

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `IPQS_API_KEY` | (required) | N/A | API key from IPQualityScore |
| `IPQS_STRICTNESS` | 1 | 0-2 | 0=lenient, 1=balanced, 2=strict |
| `IPQS_CACHE_TTL` | 3600 | 300-86400 | Cache duration in seconds |

**Fraud Score Interpretation:**

| Score Range | Risk Level | Default Action |
|-------------|------------|----------------|
| 0 - 25 | Clean | Allow |
| 25 - 50 | Low Risk | Allow |
| 50 - 75 | Medium Risk | Monitor |
| 75 - 85 | High Risk | Challenge |
| 85 - 100 | Critical | Block |

---

### 3. Rate Limiting Configuration

#### Signup Rate Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `SIGNUP_RATE_LIMIT_HOURLY` | 5 | 3-10 | Max signups per IP per hour |
| `SIGNUP_RATE_LIMIT_DAILY` | 20 | 10-50 | Max signups per IP per 24 hours |
| `SIGNUP_RATE_LIMIT_SESSION` | 3 | 1-5 | Max signups per session |

**Enforcement Actions:**

| Limit Exceeded | Action |
|----------------|--------|
| Hourly limit | Show visible CAPTCHA |
| Daily limit | Block for 24 hours |
| Session limit | Block session |

#### Login Rate Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `LOGIN_RATE_LIMIT_PER_IP` | 10 | 5-20 | Failed logins per IP per 15 min |
| `LOGIN_RATE_LIMIT_PER_ACCOUNT` | 5 | 3-10 | Failed logins per account per 15 min |

#### Password Reset Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `PASSWORD_RESET_RATE_LIMIT` | 3 | 2-5 | Requests per email per hour |
| `PASSWORD_RESET_IP_LIMIT` | 10 | 5-20 | Requests per IP per hour |

---

### 4. Risk Scoring Configuration

#### Risk Thresholds

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `RISK_THRESHOLD_LOW` | 0.30 | 0.20-0.40 | Max score for "allow" |
| `RISK_THRESHOLD_MEDIUM` | 0.60 | 0.50-0.70 | Max score for "challenge" |
| `RISK_THRESHOLD_HIGH` | 0.80 | 0.70-0.90 | Max score for "phone verify" |

**Risk Level Actions:**

| Risk Level | Score Range | Action | User Experience |
|------------|-------------|--------|-----------------|
| LOW | 0.00 - 0.30 | Allow | Seamless signup |
| MEDIUM | 0.30 - 0.60 | CAPTCHA | Single checkbox challenge |
| HIGH | 0.60 - 0.80 | Phone (optional) | CAPTCHA + phone option |
| CRITICAL | 0.80 - 1.00 | Block | Generic error message |

#### Risk Signal Weights

| Signal | Weight | Description |
|--------|--------|-------------|
| CAPTCHA Score | 30% | reCAPTCHA v3 bot detection |
| IP Reputation | 25% | IPQualityScore fraud score |
| Email Domain | 20% | Disposable/risky domain check |
| Behavioral | 15% | Form completion patterns |
| Device | 10% | Browser fingerprint signals |

**Note:** Weights are not configurable by default. Contact security team for adjustments.

---

### 5. Email Verification Configuration

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `EMAIL_VERIFICATION_EXPIRY_HOURS` | 24 | 1-72 | Token validity period |
| `EMAIL_VERIFICATION_RESEND_LIMIT` | 3 | 2-5 | Resends per hour |
| `EMAIL_VERIFICATION_TOKEN_LENGTH` | 32 | 32-64 | Token entropy (characters) |

**Reminder Schedule:**

| Day | Action |
|-----|--------|
| 1 | First reminder email |
| 3 | Second reminder email |
| 7 | Final reminder email |
| 14 | Account flagged for cleanup |

---

### 6. Account Security Configuration

#### Account Lockout

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `ACCOUNT_LOCKOUT_THRESHOLD` | 5 | 3-10 | Failed attempts before lockout |
| `ACCOUNT_LOCKOUT_DURATION_MINUTES` | 15 | 5-60 | Lockout duration |

#### Password Policy

| Setting | Default | Description |
|---------|---------|-------------|
| `PASSWORD_MIN_LENGTH` | 8 | Minimum password length |
| `PASSWORD_REQUIRE_LETTER` | true | Must contain letter |
| `PASSWORD_REQUIRE_NUMBER` | true | Must contain number |
| `PASSWORD_CHECK_BREACHED` | true | Check HaveIBeenPwned |

---

### 7. Session Configuration

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `SESSION_DURATION_DAYS` | 14 | 1-30 | Session cookie lifetime |
| `SESSION_IDLE_TIMEOUT_HOURS` | 24 | 1-168 | Inactivity timeout |
| `SESSION_COOKIE_SECURE` | true | N/A | HTTPS only |
| `SESSION_COOKIE_HTTPONLY` | true | N/A | No JS access |
| `SESSION_COOKIE_SAMESITE` | Lax | Strict/Lax/None | CSRF protection |

---

### 8. Logging Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `SECURITY_LOG_LEVEL` | INFO | Minimum log level |
| `SECURITY_LOG_PII` | false | Never log raw PII |
| `SECURITY_LOG_RETENTION_DAYS` | 90 | Log retention period |

**Events Logged:**

| Event | Level | Logged Fields |
|-------|-------|---------------|
| Signup attempt | INFO | ip_hash, email_hash, risk_score, outcome |
| Signup blocked | WARNING | ip_hash, block_reason, risk_breakdown |
| Login failed | WARNING | ip_hash, email_hash, failure_reason |
| Account locked | WARNING | email_hash, trigger |
| Rate limit hit | WARNING | ip_hash, limit_type |

---

### 9. Alert Configuration

| Metric | Threshold | Alert Type | Channel |
|--------|-----------|------------|---------|
| Signup blocks/min | > 50 | Critical | PagerDuty |
| Failed logins/min | > 100 | Critical | PagerDuty |
| Rate limit hits/min | > 200 | Warning | Slack |
| CAPTCHA challenges/hr | > 1000 | Info | Slack |
| New disposable domain | Any | Info | Email |

---

## Django Settings

Add to `settings.py`:

```python
# ==============================================================================
# SIGNUP SECURITY CONFIGURATION
# ==============================================================================

import os

# CAPTCHA
RECAPTCHA_V3_SITE_KEY = os.getenv('RECAPTCHA_V3_SITE_KEY')
RECAPTCHA_V3_SECRET_KEY = os.getenv('RECAPTCHA_V3_SECRET_KEY')
RECAPTCHA_SCORE_THRESHOLD = float(os.getenv('RECAPTCHA_SCORE_THRESHOLD', 0.5))

# IP Reputation
IPQS_API_KEY = os.getenv('IPQS_API_KEY')
IPQS_STRICTNESS = int(os.getenv('IPQS_STRICTNESS', 1))
IPQS_CACHE_TTL = int(os.getenv('IPQS_CACHE_TTL', 3600))

# Rate Limits
SIGNUP_RATE_LIMITS = {
    'hourly': int(os.getenv('SIGNUP_RATE_LIMIT_HOURLY', 5)),
    'daily': int(os.getenv('SIGNUP_RATE_LIMIT_DAILY', 20)),
}
LOGIN_RATE_LIMITS = {
    'per_ip': int(os.getenv('LOGIN_RATE_LIMIT_PER_IP', 10)),
    'per_account': int(os.getenv('LOGIN_RATE_LIMIT_PER_ACCOUNT', 5)),
}

# Risk Thresholds
RISK_THRESHOLDS = {
    'low': float(os.getenv('RISK_THRESHOLD_LOW', 0.30)),
    'medium': float(os.getenv('RISK_THRESHOLD_MEDIUM', 0.60)),
    'high': float(os.getenv('RISK_THRESHOLD_HIGH', 0.80)),
}

# Email Verification
EMAIL_VERIFICATION = {
    'expiry_hours': int(os.getenv('EMAIL_VERIFICATION_EXPIRY_HOURS', 24)),
    'resend_limit': int(os.getenv('EMAIL_VERIFICATION_RESEND_LIMIT', 3)),
    'token_length': int(os.getenv('EMAIL_VERIFICATION_TOKEN_LENGTH', 32)),
}

# Account Lockout
ACCOUNT_LOCKOUT = {
    'threshold': int(os.getenv('ACCOUNT_LOCKOUT_THRESHOLD', 5)),
    'duration_minutes': int(os.getenv('ACCOUNT_LOCKOUT_DURATION_MINUTES', 15)),
}

# Session Security
SESSION_COOKIE_AGE = int(os.getenv('SESSION_DURATION_DAYS', 14)) * 24 * 60 * 60
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

---

## Configuration Profiles

### Development Profile

For local development with relaxed settings:

```bash
# Development overrides
RECAPTCHA_SCORE_THRESHOLD=0.1  # More lenient
SIGNUP_RATE_LIMIT_HOURLY=100   # Higher for testing
SIGNUP_RATE_LIMIT_DAILY=1000
LOGIN_RATE_LIMIT_PER_IP=100
ACCOUNT_LOCKOUT_DURATION_MINUTES=1
```

### Staging Profile

Mirrors production with some monitoring additions:

```bash
# Use production values
# Add verbose logging
SECURITY_LOG_LEVEL=DEBUG
```

### Production Profile

Use defaults from this document.

---

## Tuning Guidelines

### When to Tighten Security

- Bot attacks detected (high block rate)
- Abuse reports increasing
- AI cost anomalies
- Credential stuffing detected

**Actions:**
1. Lower `RECAPTCHA_SCORE_THRESHOLD` to 0.6
2. Reduce rate limits by 50%
3. Enable phone verification for MEDIUM risk

### When to Relax Security

- False positive rate > 1%
- User complaints about friction
- Support tickets about blocks

**Actions:**
1. Raise `RECAPTCHA_SCORE_THRESHOLD` to 0.4
2. Increase `SIGNUP_RATE_LIMIT_HOURLY` to 10
3. Review and prune IP blocklist

### Monitoring Metrics

| Metric | Target | Alert If |
|--------|--------|----------|
| False positive rate | < 0.5% | > 1% |
| Bot block rate | > 95% | < 90% |
| Signup success rate | > 98% | < 95% |
| CAPTCHA challenge rate | 5-15% | > 25% |
| Average risk score | 0.15 | > 0.30 |

---

## Third-Party Service Setup

### reCAPTCHA v3 Setup

1. Go to https://www.google.com/recaptcha/admin
2. Register new site with reCAPTCHA v3
3. Add domains: `wholelifejourney.com`, `localhost`
4. Copy Site Key and Secret Key to env vars

### IPQualityScore Setup

1. Register at https://www.ipqualityscore.com/
2. Subscribe to IP Reputation API
3. Copy API key to `IPQS_API_KEY`
4. Set strictness based on tolerance

### Kickbox Email Validation (Optional)

1. Register at https://kickbox.com/
2. Subscribe to verification API
3. Copy API key to `KICKBOX_API_KEY`

---

## Rollout Checklist

### Pre-Deployment

- [ ] All environment variables set
- [ ] reCAPTCHA keys configured and tested
- [ ] IPQS API key valid
- [ ] Rate limit cache configured (Redis recommended)
- [ ] Logging destination configured
- [ ] Alert channels configured

### Deployment

- [ ] Database migrations applied
- [ ] Disposable email domains seeded
- [ ] Feature flags enabled
- [ ] Smoke tests passing

### Post-Deployment (Day 1-7)

- [ ] Monitor false positive rate
- [ ] Review blocked signups for legitimacy
- [ ] Check alert thresholds
- [ ] Verify logging working
- [ ] Test account recovery flows

### Ongoing

- [ ] Weekly: Review metrics dashboard
- [ ] Monthly: Update disposable email list
- [ ] Quarterly: Full configuration review
- [ ] On-incident: Immediate threshold review

---

## Support Procedures

### User Blocked Incorrectly

1. User contacts support
2. Support verifies user identity
3. Check `SignupAttempt` record for block reason
4. If false positive, whitelist email/IP
5. User retries signup

### Abuse Detected

1. Alert triggers
2. Review attack pattern
3. Tighten relevant thresholds
4. Block identified bad actors
5. Document in incident log

---

## Related Documents

- `docs/wlj_security_signup_threat_model.md` - Threat model
- `docs/wlj_security_signup_flow.md` - Signup flow design
- `docs/wlj_security_risk_scoring.md` - Risk scoring model
- `docs/wlj_security_controls.md` - Security controls
- `docs/wlj_security_engineering_spec.md` - Engineering specification
- `docs/wlj_security_acceptance_criteria.md` - Acceptance criteria
- `docs/wlj_security_test_plan.md` - Test plan

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-02 | Initial release |

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
