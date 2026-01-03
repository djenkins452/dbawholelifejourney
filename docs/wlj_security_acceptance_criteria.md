# ==============================================================================
# File: docs/wlj_security_acceptance_criteria.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Measurable acceptance criteria for signup security validation
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Signup Security Acceptance Criteria

## Document Purpose

This document establishes clear pass/fail rules to validate the effectiveness of signup security controls. Each criterion is measurable, testable, and directly tied to the security requirements.

---

## Acceptance Criteria Categories

1. **Bot Flood Protection**
2. **Email Verification Enforcement**
3. **Rate Limiting Behavior**
4. **Risk Scoring Outcomes**
5. **Logging and Alert Generation**

---

## 1. Bot Flood Protection

### AC-BOT-001: Honeypot Detection

**Requirement:** Bots that fill honeypot fields must be silently rejected.

| Criteria | Pass Condition |
|----------|----------------|
| Honeypot field present | Hidden field exists in signup form |
| Filled honeypot → reject | Form submission with honeypot filled returns error |
| No error leakage | Error message is generic ("Unable to create account") |
| Logging | Honeypot trigger logged with IP hash |

**Test Case:**
```python
def test_honeypot_blocks_bots(self):
    """AC-BOT-001: Honeypot field blocks automated submissions."""
    response = self.client.post('/accounts/signup/', {
        'email': 'test@example.com',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        'website': 'http://spam.com'  # Honeypot filled
    })
    self.assertEqual(response.status_code, 400)
    self.assertIn('Unable to create account', response.json()['message'])
    self.assertFalse(User.objects.filter(email='test@example.com').exists())
```

### AC-BOT-002: reCAPTCHA v3 Integration

**Requirement:** All signup attempts must have reCAPTCHA v3 score evaluated.

| Criteria | Pass Condition |
|----------|----------------|
| Token required | Signup without token returns 400 |
| Score recorded | SignupAttempt.captcha_score populated |
| Low score → challenge | Score < 0.5 triggers visible CAPTCHA |
| Very low score → block | Score < 0.3 blocks signup |

**Test Cases:**
```python
def test_captcha_token_required(self):
    """AC-BOT-002: Signup requires reCAPTCHA token."""
    response = self.client.post('/accounts/signup/', {
        'email': 'test@example.com',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        # No recaptcha_token
    })
    self.assertEqual(response.status_code, 400)
    self.assertIn('captcha', response.json()['error'].lower())

def test_low_captcha_triggers_challenge(self):
    """AC-BOT-002: Low CAPTCHA score requires visible challenge."""
    with mock.patch('apps.users.services.captcha.RecaptchaService.verify') as m:
        m.return_value = {'success': True, 'score': 0.4}
        response = self.client.post('/accounts/signup/', {
            'email': 'test@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'valid_token'
        })
    self.assertEqual(response.status_code, 202)
    self.assertEqual(response.json()['status'], 'captcha_required')
```

### AC-BOT-003: Behavioral Analysis

**Requirement:** Form completion behavior must be analyzed for automation signals.

| Criteria | Pass Condition |
|----------|----------------|
| Timing captured | completion_time_seconds recorded |
| Fast submission flagged | < 3 seconds adds risk score |
| No interaction flagged | Zero focus events adds risk score |
| Score impact | Behavioral signals affect total risk score |

**Test Case:**
```python
def test_fast_completion_increases_risk(self):
    """AC-BOT-003: Suspiciously fast form completion increases risk."""
    attempt = create_signup_attempt(
        behavioral_signals={'completion_time_seconds': 1}
    )
    self.assertGreater(attempt.behavioral_score, 0.3)
    self.assertIn('fast_completion', attempt.risk_factors)
```

---

## 2. Email Verification Enforcement

### AC-EMAIL-001: Disposable Email Blocking

**Requirement:** Signup with disposable email domains must be blocked.

| Criteria | Pass Condition |
|----------|----------------|
| Blocklist checked | Domain checked against DisposableEmailDomain |
| Disposable → reject | Signup with disposable email returns error |
| User-friendly message | Error explains permanent email required |
| Logging | Block reason recorded as 'disposable_email' |

**Test Cases:**
```python
def test_disposable_email_blocked(self):
    """AC-EMAIL-001: Disposable email domains are blocked."""
    DisposableEmailDomain.objects.create(domain='tempmail.org')
    response = self.client.post('/accounts/signup/', {
        'email': 'user@tempmail.org',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        'recaptcha_token': 'valid'
    })
    self.assertEqual(response.status_code, 400)
    self.assertIn('permanent email', response.json()['message'])

def test_legitimate_email_allowed(self):
    """AC-EMAIL-001: Legitimate emails are allowed."""
    response = self.client.post('/accounts/signup/', {
        'email': 'user@gmail.com',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        'recaptcha_token': 'valid'
    })
    self.assertIn(response.status_code, [200, 201, 202])
```

### AC-EMAIL-002: Verification Token Security

**Requirement:** Email verification tokens must follow security best practices.

| Criteria | Pass Condition |
|----------|----------------|
| Token length | >= 32 characters |
| Token expiry | Expires after 24 hours |
| Single use | Token invalidated after verification |
| Old tokens invalidated | New token request invalidates old tokens |

**Test Cases:**
```python
def test_token_length(self):
    """AC-EMAIL-002: Verification tokens have sufficient entropy."""
    verification = VerificationService().create_verification(self.user)
    self.assertGreaterEqual(len(verification.token), 32)

def test_token_expires(self):
    """AC-EMAIL-002: Tokens expire after 24 hours."""
    verification = VerificationService().create_verification(self.user)
    self.assertLessEqual(
        (verification.expires_at - verification.created_at).total_seconds(),
        24 * 60 * 60
    )

def test_token_single_use(self):
    """AC-EMAIL-002: Tokens can only be used once."""
    verification = VerificationService().create_verification(self.user)
    success1, _, _ = VerificationService().verify_token(verification.token)
    success2, _, _ = VerificationService().verify_token(verification.token)
    self.assertTrue(success1)
    self.assertFalse(success2)

def test_new_token_invalidates_old(self):
    """AC-EMAIL-002: New token request invalidates previous tokens."""
    v1 = VerificationService().create_verification(self.user)
    v2 = VerificationService().create_verification(self.user)
    v1.refresh_from_db()
    self.assertTrue(v1.invalidated)
    self.assertFalse(v2.invalidated)
```

### AC-EMAIL-003: Pending Account State

**Requirement:** Unverified accounts must have limited access.

| Criteria | Pass Condition |
|----------|----------------|
| State = pending | Unverified users have pending status |
| AI features blocked | AI endpoints return 403 for pending users |
| Journal blocked | Journal create returns 403 for pending users |
| Verification banner | Dashboard shows verification reminder |

**Test Cases:**
```python
def test_pending_user_ai_blocked(self):
    """AC-EMAIL-003: Pending users cannot access AI features."""
    user = User.objects.create_user(email='test@example.com')
    user.email_verified = False
    user.save()
    self.client.force_login(user)

    response = self.client.post('/ai/coaching/')
    self.assertEqual(response.status_code, 403)
    self.assertIn('verify', response.json()['message'].lower())

def test_pending_user_sees_banner(self):
    """AC-EMAIL-003: Pending users see verification banner."""
    user = User.objects.create_user(email='test@example.com')
    user.email_verified = False
    user.save()
    self.client.force_login(user)

    response = self.client.get('/dashboard/')
    self.assertContains(response, 'verify your email')
```

### AC-EMAIL-004: Resend Rate Limiting

**Requirement:** Verification email resend must be rate limited.

| Criteria | Pass Condition |
|----------|----------------|
| Limit enforced | Max 3 resends per hour |
| User-friendly message | Throttle message shows wait time |
| Counter resets | Counter resets after 1 hour |

**Test Case:**
```python
def test_resend_rate_limit(self):
    """AC-EMAIL-004: Verification resend is rate limited."""
    user = User.objects.create_user(email='test@example.com')
    self.client.force_login(user)

    # First 3 should succeed
    for i in range(3):
        response = self.client.post('/accounts/resend-verification/')
        self.assertEqual(response.status_code, 200)

    # 4th should be throttled
    response = self.client.post('/accounts/resend-verification/')
    self.assertEqual(response.status_code, 429)
    self.assertIn('wait', response.json()['message'].lower())
```

---

## 3. Rate Limiting Behavior

### AC-RATE-001: Per-IP Signup Limits

**Requirement:** Individual IPs must be rate limited on signup attempts.

| Criteria | Pass Condition |
|----------|----------------|
| Hourly limit | 5 signups per IP per hour |
| Daily limit | 20 signups per IP per 24 hours |
| CAPTCHA on exceed | Exceeding hourly limit triggers CAPTCHA |
| Block on daily exceed | Exceeding daily limit blocks signup |

**Test Cases:**
```python
def test_hourly_limit_triggers_captcha(self):
    """AC-RATE-001: 6th signup attempt triggers CAPTCHA."""
    for i in range(5):
        response = self.client.post('/accounts/signup/', {
            'email': f'user{i}@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'valid'
        })
        self.assertNotEqual(response.json().get('status'), 'captcha_required')

    # 6th attempt should require CAPTCHA
    response = self.client.post('/accounts/signup/', {
        'email': 'user5@example.com',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        'recaptcha_token': 'valid'
    })
    self.assertEqual(response.json()['status'], 'captcha_required')

def test_daily_limit_blocks(self):
    """AC-RATE-001: 21st signup attempt is blocked."""
    for i in range(20):
        # Bypass hourly limit for testing
        with mock.patch('apps.users.rate_limits.check_signup_limit') as m:
            m.return_value = (True, 'allow')
            self.client.post('/accounts/signup/', {
                'email': f'user{i}@example.com',
                'password1': 'SecurePass123',
                'password2': 'SecurePass123',
                'recaptcha_token': 'valid'
            })

    # 21st should be blocked
    response = self.client.post('/accounts/signup/', {
        'email': 'user20@example.com',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        'recaptcha_token': 'valid'
    })
    self.assertEqual(response.status_code, 429)
```

### AC-RATE-002: Login Rate Limits

**Requirement:** Login attempts must be rate limited to prevent brute force.

| Criteria | Pass Condition |
|----------|----------------|
| Per-IP limit | 10 failed logins per IP per 15 min |
| Per-account limit | 5 failed logins per account per 15 min |
| Account lockout | Account locked after threshold |
| Lockout duration | 15 minute lockout period |

**Test Cases:**
```python
def test_account_lockout(self):
    """AC-RATE-002: Account locks after 5 failed attempts."""
    user = User.objects.create_user(
        email='test@example.com',
        password='CorrectPassword123'
    )

    for i in range(5):
        response = self.client.post('/accounts/login/', {
            'login': 'test@example.com',
            'password': 'WrongPassword'
        })

    # 6th attempt with correct password should still fail
    response = self.client.post('/accounts/login/', {
        'login': 'test@example.com',
        'password': 'CorrectPassword123'
    })
    self.assertContains(response, 'locked', status_code=200)
```

### AC-RATE-003: Password Reset Limits

**Requirement:** Password reset requests must be rate limited.

| Criteria | Pass Condition |
|----------|----------------|
| Per-email limit | 3 requests per email per hour |
| Uniform response | Same response for valid/invalid emails |
| No enumeration | Cannot determine if email exists |

**Test Case:**
```python
def test_password_reset_rate_limit(self):
    """AC-RATE-003: Password reset limited to 3 per hour."""
    for i in range(3):
        response = self.client.post('/accounts/password/reset/', {
            'email': 'test@example.com'
        })
        self.assertEqual(response.status_code, 200)

    # 4th should be throttled
    response = self.client.post('/accounts/password/reset/', {
        'email': 'test@example.com'
    })
    self.assertEqual(response.status_code, 429)
```

---

## 4. Risk Scoring Outcomes

### AC-RISK-001: Risk Score Calculation

**Requirement:** Risk scores must be calculated deterministically from inputs.

| Criteria | Pass Condition |
|----------|----------------|
| All signals weighted | 5 signal categories contribute to score |
| Weights sum to 100% | CAPTCHA(30) + IP(25) + Email(20) + Behavior(15) + Device(10) |
| Score range | 0.0 to 1.0 |
| Deterministic | Same inputs produce same score |

**Test Cases:**
```python
def test_risk_score_deterministic(self):
    """AC-RISK-001: Same inputs produce same risk score."""
    inputs = {
        'recaptcha_score': 0.8,
        'ip_info': {'fraud_score': 30},
        'email': 'user@gmail.com',
        'behavioral_signals': {'completion_time_seconds': 30},
        'device_fingerprint': {},
        'fingerprint_hash': 'abc123'
    }

    score1 = calculate_risk_score(**inputs)
    score2 = calculate_risk_score(**inputs)

    self.assertEqual(score1.total_score, score2.total_score)
    self.assertEqual(score1.risk_level, score2.risk_level)

def test_risk_score_range(self):
    """AC-RISK-001: Risk scores are between 0.0 and 1.0."""
    # Test with extreme inputs
    low_risk = calculate_risk_score(
        recaptcha_score=0.95,
        ip_info={'fraud_score': 0},
        email='user@company.com',
        behavioral_signals={'completion_time_seconds': 45},
        device_fingerprint={},
        fingerprint_hash='abc'
    )
    self.assertGreaterEqual(low_risk.total_score, 0.0)
    self.assertLessEqual(low_risk.total_score, 1.0)

    high_risk = calculate_risk_score(
        recaptcha_score=0.1,
        ip_info={'fraud_score': 95, 'tor': True},
        email='user@tempmail.org',
        behavioral_signals={'completion_time_seconds': 1},
        device_fingerprint={'webdriver': True},
        fingerprint_hash='xyz'
    )
    self.assertGreaterEqual(high_risk.total_score, 0.0)
    self.assertLessEqual(high_risk.total_score, 1.0)
```

### AC-RISK-002: Risk Level Thresholds

**Requirement:** Risk levels must trigger appropriate actions.

| Risk Level | Score Range | Action |
|------------|-------------|--------|
| LOW | 0.00 - 0.30 | Allow |
| MEDIUM | 0.30 - 0.60 | CAPTCHA challenge |
| HIGH | 0.60 - 0.80 | Phone verification |
| CRITICAL | 0.80 - 1.00 | Block |

**Test Cases:**
```python
def test_risk_level_thresholds(self):
    """AC-RISK-002: Risk levels map to correct actions."""
    test_cases = [
        (0.15, 'LOW', 'ALLOW'),
        (0.45, 'MEDIUM', 'CAPTCHA_CHALLENGE'),
        (0.70, 'HIGH', 'PHONE_VERIFICATION'),
        (0.90, 'CRITICAL', 'BLOCK'),
    ]

    for score, expected_level, expected_action in test_cases:
        result = RiskScoreResult(
            total_score=score,
            risk_level='',
            breakdown={},
            signals={},
            recommended_action=''
        )
        result = apply_thresholds(result)

        self.assertEqual(result.risk_level, expected_level)
        self.assertEqual(result.recommended_action, expected_action)
```

### AC-RISK-003: Override Rules

**Requirement:** Certain conditions must override normal scoring.

| Condition | Override Action |
|-----------|-----------------|
| IP on blocklist | Immediate block |
| Email on blocklist | Immediate block |
| Honeypot triggered | Immediate block |
| Fingerprint with 3+ accounts | Immediate block |

**Test Case:**
```python
def test_blocklist_overrides_scoring(self):
    """AC-RISK-003: IP blocklist overrides risk score."""
    IPBlocklist.objects.create(ip_address='1.2.3.4')

    # Even with perfect signals, blocked IP is rejected
    result = evaluate_signup(
        ip_address='1.2.3.4',
        recaptcha_score=0.99,
        email='legit@company.com'
    )

    self.assertEqual(result.recommended_action, 'BLOCK')
    self.assertEqual(result.block_reason, 'blocklist')
```

---

## 5. Logging and Alert Generation

### AC-LOG-001: Security Event Logging

**Requirement:** All security-relevant events must be logged.

| Event | Required Fields |
|-------|-----------------|
| Signup attempt | timestamp, ip_hash, email_hash, risk_score, outcome |
| Signup blocked | timestamp, ip_hash, block_reason, risk_breakdown |
| Login failed | timestamp, ip_hash, email_hash, failure_reason |
| Rate limit hit | timestamp, ip_hash, limit_type, count |
| Account locked | timestamp, email_hash, trigger |

**Test Cases:**
```python
def test_signup_attempt_logged(self):
    """AC-LOG-001: Signup attempts are logged with required fields."""
    with self.assertLogs('security', level='INFO') as logs:
        self.client.post('/accounts/signup/', {
            'email': 'test@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'valid'
        })

    log_message = logs.output[0]
    self.assertIn('signup_attempt', log_message)
    self.assertIn('ip_hash', log_message)
    self.assertIn('email_hash', log_message)
    self.assertIn('risk_score', log_message)
    # Ensure raw email not logged
    self.assertNotIn('test@example.com', log_message)

def test_blocked_signup_logged(self):
    """AC-LOG-001: Blocked signups include block reason."""
    IPBlocklist.objects.create(ip_address='127.0.0.1')

    with self.assertLogs('security', level='WARNING') as logs:
        self.client.post('/accounts/signup/', {
            'email': 'test@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'valid'
        })

    log_message = logs.output[0]
    self.assertIn('signup_blocked', log_message)
    self.assertIn('blocklist', log_message)
```

### AC-LOG-002: PII Protection

**Requirement:** No raw PII must appear in logs.

| Data | Logging Rule |
|------|--------------|
| Email | SHA-256 hash only |
| IP address | SHA-256 hash only |
| Password | Never logged |
| Phone number | Never logged |

**Test Case:**
```python
def test_no_pii_in_logs(self):
    """AC-LOG-002: Raw PII never appears in logs."""
    test_email = 'sensitiveuser@example.com'
    test_password = 'MySuperSecretPassword123'

    with self.assertLogs('security', level='DEBUG') as logs:
        self.client.post('/accounts/signup/', {
            'email': test_email,
            'password1': test_password,
            'password2': test_password,
            'recaptcha_token': 'valid'
        })

    all_logs = '\n'.join(logs.output)
    self.assertNotIn(test_email, all_logs)
    self.assertNotIn(test_password, all_logs)
    self.assertNotIn('sensitiveuser', all_logs)
```

### AC-LOG-003: Alert Thresholds

**Requirement:** Security alerts must fire at defined thresholds.

| Metric | Threshold | Alert Type |
|--------|-----------|------------|
| Signup blocks/min | > 50 | Critical (PagerDuty) |
| Failed logins/min | > 100 | Critical (PagerDuty) |
| Rate limit hits/min | > 200 | Warning (Slack) |
| CAPTCHA challenges/hr | > 1000 | Info (Slack) |

**Test Case:**
```python
def test_block_rate_alert(self):
    """AC-LOG-003: High block rate triggers alert."""
    with mock.patch('apps.users.alerts.send_pagerduty_alert') as alert_mock:
        for i in range(51):
            cache.incr('metric:signup_blocks_per_min')

        check_alert_thresholds()

        alert_mock.assert_called_once()
        call_args = alert_mock.call_args[0]
        self.assertIn('signup_blocks', call_args[0])
```

### AC-LOG-004: SignupAttempt Record Creation

**Requirement:** Every signup attempt must create an audit record.

| Field | Required |
|-------|----------|
| id (UUID) | Yes |
| email_hash | Yes |
| ip_hash | Yes |
| risk_score | Yes |
| status | Yes |
| created_at | Yes |

**Test Case:**
```python
def test_signup_creates_attempt_record(self):
    """AC-LOG-004: Every signup creates SignupAttempt record."""
    initial_count = SignupAttempt.objects.count()

    self.client.post('/accounts/signup/', {
        'email': 'test@example.com',
        'password1': 'SecurePass123',
        'password2': 'SecurePass123',
        'recaptcha_token': 'valid'
    })

    self.assertEqual(SignupAttempt.objects.count(), initial_count + 1)

    attempt = SignupAttempt.objects.latest('created_at')
    self.assertIsNotNone(attempt.id)
    self.assertIsNotNone(attempt.email_hash)
    self.assertIsNotNone(attempt.ip_hash)
    self.assertIsNotNone(attempt.risk_score)
    self.assertIn(attempt.status, ['pending', 'allowed', 'blocked', 'challenged'])
```

---

## Acceptance Criteria Summary

### Critical (Must Pass)

| ID | Criteria | Status |
|----|----------|--------|
| AC-BOT-001 | Honeypot detection | ⬜ |
| AC-BOT-002 | reCAPTCHA integration | ⬜ |
| AC-EMAIL-001 | Disposable email blocking | ⬜ |
| AC-EMAIL-002 | Token security | ⬜ |
| AC-EMAIL-003 | Pending account state | ⬜ |
| AC-RATE-001 | Per-IP signup limits | ⬜ |
| AC-RISK-001 | Risk score calculation | ⬜ |
| AC-RISK-002 | Risk level thresholds | ⬜ |
| AC-LOG-001 | Security event logging | ⬜ |
| AC-LOG-002 | PII protection | ⬜ |

### High Priority (Should Pass)

| ID | Criteria | Status |
|----|----------|--------|
| AC-BOT-003 | Behavioral analysis | ⬜ |
| AC-EMAIL-004 | Resend rate limiting | ⬜ |
| AC-RATE-002 | Login rate limits | ⬜ |
| AC-RATE-003 | Password reset limits | ⬜ |
| AC-RISK-003 | Override rules | ⬜ |
| AC-LOG-003 | Alert thresholds | ⬜ |
| AC-LOG-004 | SignupAttempt records | ⬜ |

---

## Validation Process

1. **Unit Tests:** Run all AC-* test cases
2. **Integration Tests:** Test full signup flow end-to-end
3. **Load Tests:** Verify rate limits under concurrent load
4. **Security Scan:** Run automated security scanning
5. **Manual Review:** Security team reviews implementation
6. **Staging Validation:** Full test in staging environment
7. **Production Monitoring:** Monitor metrics for 7 days post-deploy

---

## Related Documents

- `docs/wlj_security_signup_threat_model.md` - Threat model (Phase 1)
- `docs/wlj_security_signup_flow.md` - Target signup flow (Phase 2)
- `docs/wlj_security_risk_scoring.md` - Risk scoring model (Phase 3)
- `docs/wlj_security_controls.md` - Security controls (Phase 4)
- `docs/wlj_security_engineering_spec.md` - Engineering specification (Phase 5)
- `docs/wlj_security_test_plan.md` - Security test plan (Phase 7)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
