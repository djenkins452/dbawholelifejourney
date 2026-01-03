# ==============================================================================
# File: docs/wlj_security_test_plan.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive signup security test plan with test cases
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Signup Security Test Plan

## Document Purpose

This test plan ensures signup defenses work correctly under normal usage and abusive conditions. It includes manual test cases, automated tests, and abuse simulations.

---

## Test Categories

1. **Manual Test Cases** - Human verification of user flows
2. **Automated Unit Tests** - Component-level testing
3. **Automated Integration Tests** - End-to-end flow testing
4. **Abuse Simulations** - Adversarial testing
5. **Performance Tests** - Load and stress testing

---

## 1. Manual Test Cases

### 1.1 Happy Path - Normal User Signup

**Test ID:** MAN-001
**Priority:** Critical
**Preconditions:** None

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to /accounts/signup/ | Signup form displayed |
| 2 | Enter valid email (Gmail, etc.) | Field accepts input |
| 3 | Enter strong password | Field accepts input, strength indicator shows |
| 4 | Confirm password | Passwords match |
| 5 | Complete invisible CAPTCHA | No visible challenge for normal users |
| 6 | Submit form | Success message, redirected to "check email" page |
| 7 | Check email inbox | Verification email received within 2 minutes |
| 8 | Click verification link | Redirected to Terms of Service page |
| 9 | Accept terms | Redirected to onboarding wizard |
| 10 | Complete onboarding | Redirected to dashboard |

**Pass Criteria:** All steps complete without errors

---

### 1.2 Email Verification Flow

**Test ID:** MAN-002
**Priority:** Critical
**Preconditions:** Account created, not verified

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Login with unverified account | Login succeeds |
| 2 | Navigate to dashboard | Dashboard shows verification banner |
| 3 | Try to access AI coaching | 403 error, "verify email" message |
| 4 | Try to create journal entry | 403 error, "verify email" message |
| 5 | Click "Resend verification" | Success message, email sent |
| 6 | Click resend 3 more times | Rate limit message after 3rd |
| 7 | Verify email via link | Account upgraded to verified |
| 8 | Access AI coaching | Feature now accessible |

**Pass Criteria:** Unverified accounts blocked from protected features

---

### 1.3 Disposable Email Rejection

**Test ID:** MAN-003
**Priority:** High
**Preconditions:** None

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to signup | Form displayed |
| 2 | Enter email: test@10minutemail.com | Field accepts input |
| 3 | Complete form and submit | Error: "Please use a permanent email address" |
| 4 | Try email: test@guerrillamail.com | Same error |
| 5 | Try email: test@tempmail.org | Same error |
| 6 | Try email: test@gmail.com | Signup proceeds normally |

**Pass Criteria:** All known disposable domains rejected with clear message

---

### 1.4 Rate Limiting Experience

**Test ID:** MAN-004
**Priority:** High
**Preconditions:** Clear browser/IP state

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1-5 | Create 5 signup attempts | All attempts proceed (success or fail) |
| 6 | Create 6th signup attempt | Visible CAPTCHA challenge shown |
| 7 | Complete CAPTCHA | Signup proceeds |
| 8-20 | Create 14 more attempts | CAPTCHA required each time |
| 21 | Create 21st attempt | Blocked: "Too many attempts, try again later" |

**Pass Criteria:** Rate limits enforce progressively stricter friction

---

### 1.5 Password Security

**Test ID:** MAN-005
**Priority:** High
**Preconditions:** None

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enter password: "123" | Error: minimum 8 characters |
| 2 | Enter password: "12345678" | Error: must include letter |
| 3 | Enter password: "password" | Error: must include number |
| 4 | Enter password: "Password1" | Check against breach database |
| 5 | Enter known breached password | Warning: password found in data breach |
| 6 | Enter unique strong password | Accepted |

**Pass Criteria:** Weak and breached passwords rejected

---

### 1.6 Account Lockout

**Test ID:** MAN-006
**Priority:** High
**Preconditions:** Verified account exists

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1-5 | Attempt login with wrong password | "Invalid credentials" each time |
| 6 | Attempt login with wrong password | "Account temporarily locked" |
| 7 | Attempt login with correct password | Still locked |
| 8 | Wait 15 minutes | Account unlocks |
| 9 | Login with correct password | Login succeeds |

**Pass Criteria:** Account locks after 5 failed attempts, unlocks after 15 minutes

---

## 2. Automated Unit Tests

### 2.1 Risk Score Calculation Tests

```python
# apps/users/tests/test_risk_scoring.py

from django.test import TestCase
from apps.users.services.risk_scoring import calculate_risk_score

class RiskScoreCalculationTests(TestCase):
    """Unit tests for risk score calculation."""

    def test_low_risk_user(self):
        """Perfect signals produce low risk score."""
        result = calculate_risk_score(
            recaptcha_score=0.95,
            ip_info={'fraud_score': 10, 'vpn': False, 'tor': False},
            email='user@company.com',
            behavioral_signals={
                'completion_time_seconds': 45,
                'field_focus_count': 10,
                'has_mouse_movement': True,
                'keystroke_variance': 50
            },
            device_fingerprint={},
            fingerprint_hash='unique123'
        )
        self.assertLess(result.total_score, 0.3)
        self.assertEqual(result.risk_level, 'LOW')
        self.assertEqual(result.recommended_action, 'ALLOW')

    def test_high_risk_user(self):
        """Suspicious signals produce high risk score."""
        result = calculate_risk_score(
            recaptcha_score=0.3,
            ip_info={'fraud_score': 80, 'vpn': True, 'tor': False},
            email='user@tempmail.org',
            behavioral_signals={
                'completion_time_seconds': 2,
                'field_focus_count': 0,
                'has_mouse_movement': False,
                'keystroke_variance': 0
            },
            device_fingerprint={'webdriver': True},
            fingerprint_hash='bot123'
        )
        self.assertGreater(result.total_score, 0.6)
        self.assertIn(result.risk_level, ['HIGH', 'CRITICAL'])

    def test_weight_distribution(self):
        """Verify weights sum to 1.0."""
        weights = {
            'captcha': 0.30,
            'ip_reputation': 0.25,
            'email_domain': 0.20,
            'behavioral': 0.15,
            'device': 0.10
        }
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_score_bounds(self):
        """Scores always between 0.0 and 1.0."""
        # Test with extremes
        for _ in range(100):
            result = calculate_risk_score(
                recaptcha_score=random.random(),
                ip_info={'fraud_score': random.randint(0, 100)},
                email=random.choice(['a@b.com', 'a@temp.org']),
                behavioral_signals={'completion_time_seconds': random.randint(1, 300)},
                device_fingerprint={},
                fingerprint_hash='test'
            )
            self.assertGreaterEqual(result.total_score, 0.0)
            self.assertLessEqual(result.total_score, 1.0)

    def test_deterministic(self):
        """Same inputs produce same outputs."""
        inputs = {
            'recaptcha_score': 0.75,
            'ip_info': {'fraud_score': 40},
            'email': 'test@example.com',
            'behavioral_signals': {'completion_time_seconds': 30},
            'device_fingerprint': {},
            'fingerprint_hash': 'abc'
        }
        results = [calculate_risk_score(**inputs) for _ in range(10)]
        scores = [r.total_score for r in results]
        self.assertEqual(len(set(scores)), 1)  # All identical
```

### 2.2 Rate Limiter Tests

```python
# apps/users/tests/test_rate_limits.py

from django.test import TestCase
from django.core.cache import cache
from apps.users.rate_limits import RateLimiter, check_signup_limit

class RateLimiterTests(TestCase):
    """Unit tests for rate limiting."""

    def setUp(self):
        cache.clear()
        self.limiter = RateLimiter()

    def test_allows_under_limit(self):
        """Requests under limit are allowed."""
        for i in range(5):
            allowed, remaining, _ = self.limiter.check('test_key', 10, 60)
            self.assertTrue(allowed)
            self.assertEqual(remaining, 10 - (i + 1))

    def test_blocks_over_limit(self):
        """Requests over limit are blocked."""
        for i in range(10):
            self.limiter.check('test_key', 10, 60)

        allowed, remaining, reset = self.limiter.check('test_key', 10, 60)
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreater(reset, 0)

    def test_limit_resets(self):
        """Limit resets after window expires."""
        for i in range(10):
            self.limiter.check('test_key', 10, 1)  # 1 second window

        import time
        time.sleep(1.1)

        allowed, _, _ = self.limiter.check('test_key', 10, 1)
        self.assertTrue(allowed)

    def test_signup_hourly_limit(self):
        """Signup hourly limit triggers CAPTCHA."""
        for i in range(5):
            allowed, action = check_signup_limit(f'192.168.1.{i}')
            self.assertTrue(allowed)

        # Same IP, 6th attempt
        allowed, action = check_signup_limit('192.168.1.1')
        self.assertFalse(allowed)
        self.assertEqual(action, 'captcha')
```

### 2.3 Email Validation Tests

```python
# apps/users/tests/test_email_validation.py

from django.test import TestCase
from apps.users.models import DisposableEmailDomain
from apps.users.services.email_validation import is_disposable_email

class EmailValidationTests(TestCase):
    """Unit tests for email validation."""

    def setUp(self):
        # Seed disposable domains
        domains = ['tempmail.org', '10minutemail.com', 'guerrillamail.com']
        for domain in domains:
            DisposableEmailDomain.objects.create(domain=domain)

    def test_disposable_detected(self):
        """Known disposable domains are detected."""
        self.assertTrue(is_disposable_email('user@tempmail.org'))
        self.assertTrue(is_disposable_email('test@10minutemail.com'))
        self.assertTrue(is_disposable_email('fake@guerrillamail.com'))

    def test_legitimate_allowed(self):
        """Legitimate email domains pass."""
        self.assertFalse(is_disposable_email('user@gmail.com'))
        self.assertFalse(is_disposable_email('user@outlook.com'))
        self.assertFalse(is_disposable_email('user@company.com'))

    def test_case_insensitive(self):
        """Domain check is case insensitive."""
        self.assertTrue(is_disposable_email('USER@TEMPMAIL.ORG'))
        self.assertTrue(is_disposable_email('User@TempMail.Org'))

    def test_subdomain_not_bypassed(self):
        """Subdomains don't bypass detection."""
        self.assertTrue(is_disposable_email('user@sub.tempmail.org'))
```

### 2.4 Token Security Tests

```python
# apps/users/tests/test_verification_tokens.py

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User, EmailVerification
from apps.users.services.verification import VerificationService

class VerificationTokenTests(TestCase):
    """Unit tests for email verification tokens."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123'
        )
        self.service = VerificationService()

    def test_token_length(self):
        """Tokens have sufficient entropy."""
        verification = self.service.create_verification(self.user)
        self.assertGreaterEqual(len(verification.token), 32)

    def test_token_uniqueness(self):
        """Each token is unique."""
        tokens = set()
        for _ in range(100):
            v = self.service.create_verification(self.user)
            tokens.add(v.token)
        self.assertEqual(len(tokens), 100)

    def test_token_expiry(self):
        """Tokens expire after 24 hours."""
        verification = self.service.create_verification(self.user)
        expected_expiry = verification.created_at + timedelta(hours=24)
        self.assertAlmostEqual(
            verification.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=60  # Within 1 minute
        )

    def test_expired_token_rejected(self):
        """Expired tokens cannot be used."""
        verification = self.service.create_verification(self.user)
        verification.expires_at = timezone.now() - timedelta(hours=1)
        verification.save()

        success, error, user = self.service.verify_token(verification.token)
        self.assertFalse(success)
        self.assertIn('expired', error.lower())

    def test_token_single_use(self):
        """Tokens invalidated after use."""
        verification = self.service.create_verification(self.user)

        success1, _, _ = self.service.verify_token(verification.token)
        success2, _, _ = self.service.verify_token(verification.token)

        self.assertTrue(success1)
        self.assertFalse(success2)

    def test_new_token_invalidates_old(self):
        """New token invalidates previous tokens."""
        v1 = self.service.create_verification(self.user)
        v2 = self.service.create_verification(self.user)

        v1.refresh_from_db()
        self.assertTrue(v1.invalidated)
        self.assertFalse(v2.invalidated)

        success, _, _ = self.service.verify_token(v1.token)
        self.assertFalse(success)
```

---

## 3. Automated Integration Tests

### 3.1 Full Signup Flow Test

```python
# apps/users/tests/test_signup_integration.py

from django.test import TestCase, Client
from django.core import mail
from apps.users.models import User, SignupAttempt

class SignupIntegrationTests(TestCase):
    """End-to-end signup flow tests."""

    def setUp(self):
        self.client = Client()

    def test_complete_signup_flow(self):
        """Test full signup from form to verified account."""
        # Step 1: Submit signup form
        response = self.client.post('/accounts/signup/', {
            'email': 'newuser@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'test_token'
        })
        self.assertEqual(response.status_code, 201)

        # Step 2: Verify user created in pending state
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.email_verified)

        # Step 3: Verify email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('verify', mail.outbox[0].subject.lower())

        # Step 4: Extract token from email
        verification = user.email_verifications.latest('created_at')

        # Step 5: Verify email
        response = self.client.get(f'/accounts/verify-email/{verification.token}/')
        self.assertEqual(response.status_code, 302)  # Redirect to terms

        # Step 6: Verify user state updated
        user.refresh_from_db()
        self.assertTrue(user.email_verified)

        # Step 7: Verify SignupAttempt created
        attempt = SignupAttempt.objects.filter(
            email_hash__isnull=False
        ).latest('created_at')
        self.assertEqual(attempt.status, 'completed')

    def test_captcha_challenge_flow(self):
        """Test signup with CAPTCHA challenge for medium risk."""
        with mock.patch('apps.users.services.captcha.RecaptchaService.verify') as m:
            m.return_value = {'success': True, 'score': 0.4}

            response = self.client.post('/accounts/signup/', {
                'email': 'mediumrisk@example.com',
                'password1': 'SecurePass123',
                'password2': 'SecurePass123',
                'recaptcha_token': 'test_token'
            })

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['status'], 'captcha_required')
        self.assertIn('site_key', response.json())

    def test_blocked_signup_flow(self):
        """Test blocked signup for high risk."""
        with mock.patch('apps.users.services.captcha.RecaptchaService.verify') as m:
            m.return_value = {'success': True, 'score': 0.1}

            response = self.client.post('/accounts/signup/', {
                'email': 'highrisk@example.com',
                'password1': 'SecurePass123',
                'password2': 'SecurePass123',
                'recaptcha_token': 'test_token'
            })

        self.assertEqual(response.status_code, 403)
        self.assertIn('unable', response.json()['message'].lower())
        self.assertFalse(User.objects.filter(email='highrisk@example.com').exists())
```

### 3.2 Rate Limiting Integration Tests

```python
# apps/users/tests/test_rate_limit_integration.py

from django.test import TestCase, Client
from django.core.cache import cache

class RateLimitIntegrationTests(TestCase):
    """Integration tests for rate limiting behavior."""

    def setUp(self):
        cache.clear()
        self.client = Client()

    def test_signup_rate_limit_progression(self):
        """Test progressive rate limiting on signup."""
        emails = [f'user{i}@example.com' for i in range(25)]

        results = []
        for i, email in enumerate(emails):
            response = self.client.post('/accounts/signup/', {
                'email': email,
                'password1': 'SecurePass123',
                'password2': 'SecurePass123',
                'recaptcha_token': 'test'
            }, REMOTE_ADDR='192.168.1.100')
            results.append((i, response.status_code, response.json().get('status')))

        # First 5 should succeed without challenge
        for i in range(5):
            self.assertNotEqual(results[i][2], 'captcha_required')

        # 6-20 should require CAPTCHA
        for i in range(5, 20):
            self.assertEqual(results[i][2], 'captcha_required')

        # 21+ should be blocked
        for i in range(20, 25):
            self.assertEqual(results[i][1], 429)

    def test_different_ips_independent(self):
        """Rate limits are per-IP."""
        for i in range(5):
            response = self.client.post('/accounts/signup/', {
                'email': f'user{i}@example.com',
                'password1': 'SecurePass123',
                'password2': 'SecurePass123',
                'recaptcha_token': 'test'
            }, REMOTE_ADDR='192.168.1.1')
            self.assertNotEqual(response.json().get('status'), 'blocked')

        # Different IP should not be rate limited
        response = self.client.post('/accounts/signup/', {
            'email': 'differentip@example.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'test'
        }, REMOTE_ADDR='192.168.1.2')
        self.assertNotEqual(response.json().get('status'), 'captcha_required')
```

---

## 4. Abuse Simulations

### 4.1 Bot Flood Simulation

**Test ID:** ABUSE-001
**Purpose:** Verify system handles automated signup floods

```python
# apps/users/tests/test_abuse_simulations.py

import concurrent.futures
from django.test import TestCase, Client
from django.core.cache import cache

class BotFloodSimulation(TestCase):
    """Simulate bot flood attack."""

    def test_concurrent_signups_blocked(self):
        """Rapid concurrent signups from same IP blocked."""
        cache.clear()

        def attempt_signup(i):
            client = Client()
            return client.post('/accounts/signup/', {
                'email': f'bot{i}@example.com',
                'password1': 'BotPass123',
                'password2': 'BotPass123',
                'recaptcha_token': 'bot_token'
            }, REMOTE_ADDR='10.0.0.1')

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(attempt_signup, i) for i in range(100)]
            results = [f.result() for f in futures]

        # Count outcomes
        blocked = sum(1 for r in results if r.status_code == 429)
        challenged = sum(1 for r in results if r.json().get('status') == 'captcha_required')
        allowed = sum(1 for r in results if r.status_code in [200, 201])

        # Assertions
        self.assertGreater(blocked, 70)  # Most should be blocked
        self.assertLess(allowed, 10)     # Very few should pass

    def test_honeypot_catches_bots(self):
        """Bots filling honeypot are blocked."""
        responses = []
        for i in range(50):
            response = self.client.post('/accounts/signup/', {
                'email': f'bot{i}@example.com',
                'password1': 'BotPass123',
                'password2': 'BotPass123',
                'website': 'http://spam.com',  # Honeypot
                'recaptcha_token': 'bot_token'
            })
            responses.append(response)

        # All should be blocked
        blocked = sum(1 for r in responses if r.status_code == 400)
        self.assertEqual(blocked, 50)
```

### 4.2 Credential Stuffing Simulation

**Test ID:** ABUSE-002
**Purpose:** Verify login protections against credential stuffing

```python
class CredentialStuffingSimulation(TestCase):
    """Simulate credential stuffing attack."""

    def setUp(self):
        cache.clear()
        # Create a real user
        self.user = User.objects.create_user(
            email='realuser@example.com',
            password='RealPassword123'
        )

    def test_account_lockout_on_stuffing(self):
        """Accounts lock after repeated failures."""
        # Simulate credential stuffing
        for i in range(10):
            self.client.post('/accounts/login/', {
                'login': 'realuser@example.com',
                'password': f'WrongPassword{i}'
            })

        # Try correct password
        response = self.client.post('/accounts/login/', {
            'login': 'realuser@example.com',
            'password': 'RealPassword123'
        })

        # Should still be locked
        self.assertContains(response, 'locked')

    def test_no_email_enumeration(self):
        """Cannot determine if email exists via login errors."""
        # Non-existent email
        response1 = self.client.post('/accounts/login/', {
            'login': 'nonexistent@example.com',
            'password': 'AnyPassword123'
        })

        # Existing email, wrong password
        response2 = self.client.post('/accounts/login/', {
            'login': 'realuser@example.com',
            'password': 'WrongPassword123'
        })

        # Same error message for both
        self.assertEqual(
            response1.content,
            response2.content
        )
```

### 4.3 Disposable Email Bypass Attempts

**Test ID:** ABUSE-003
**Purpose:** Verify disposable email detection cannot be bypassed

```python
class DisposableEmailBypassSimulation(TestCase):
    """Attempt to bypass disposable email detection."""

    def setUp(self):
        DisposableEmailDomain.objects.create(domain='tempmail.org')

    def test_subdomain_bypass_blocked(self):
        """Subdomains of disposable domains blocked."""
        bypass_attempts = [
            'user@sub.tempmail.org',
            'user@mail.tempmail.org',
            'user@123.tempmail.org',
        ]

        for email in bypass_attempts:
            response = self.client.post('/accounts/signup/', {
                'email': email,
                'password1': 'SecurePass123',
                'password2': 'SecurePass123',
                'recaptcha_token': 'test'
            })
            self.assertEqual(response.status_code, 400, f"Failed for {email}")

    def test_plus_addressing_tracked(self):
        """Plus addressing variations tracked as same email."""
        # First signup
        response1 = self.client.post('/accounts/signup/', {
            'email': 'user@gmail.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'test'
        })
        self.assertEqual(response1.status_code, 201)

        # Variation attempt
        response2 = self.client.post('/accounts/signup/', {
            'email': 'user+tag@gmail.com',
            'password1': 'SecurePass123',
            'password2': 'SecurePass123',
            'recaptcha_token': 'test'
        })
        # Should be flagged as potential duplicate
        self.assertIn('already', response2.json().get('message', '').lower())
```

### 4.4 Proxy Rotation Simulation

**Test ID:** ABUSE-004
**Purpose:** Verify IP-independent detection works

```python
class ProxyRotationSimulation(TestCase):
    """Simulate attack using rotating proxy IPs."""

    def test_fingerprint_detects_same_device(self):
        """Same device fingerprint flagged across IPs."""
        fingerprint = {'hash': 'same_device_fp_12345'}

        responses = []
        for i in range(10):
            response = self.client.post('/accounts/signup/', {
                'email': f'proxy{i}@example.com',
                'password1': 'ProxyPass123',
                'password2': 'ProxyPass123',
                'recaptcha_token': 'test',
                'fingerprint': fingerprint
            }, REMOTE_ADDR=f'10.0.0.{i}')
            responses.append(response)

        # After 3 accounts with same fingerprint, should be flagged
        high_risk = sum(
            1 for r in responses[3:]
            if r.json().get('status') in ['captcha_required', 'blocked']
        )
        self.assertGreater(high_risk, 5)

    def test_behavioral_catches_automation(self):
        """Automated behavior detected regardless of IP."""
        bot_behavior = {
            'completion_time_seconds': 0.5,  # Too fast
            'field_focus_count': 0,
            'has_mouse_movement': False,
            'keystroke_variance': 0
        }

        responses = []
        for i in range(20):
            response = self.client.post('/accounts/signup/', {
                'email': f'automated{i}@example.com',
                'password1': 'AutoPass123',
                'password2': 'AutoPass123',
                'recaptcha_token': 'test',
                'behavioral': bot_behavior
            }, REMOTE_ADDR=f'10.0.0.{i}')
            responses.append(response)

        # All should be challenged or blocked
        challenged_or_blocked = sum(
            1 for r in responses
            if r.json().get('status') in ['captcha_required', 'blocked']
            or r.status_code in [403, 429]
        )
        self.assertEqual(challenged_or_blocked, 20)
```

---

## 5. Performance Tests

### 5.1 Load Test Specification

**Test ID:** PERF-001
**Tool:** Locust or k6

```python
# locustfile.py

from locust import HttpUser, task, between

class SignupUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def signup(self):
        import uuid
        email = f"{uuid.uuid4()}@loadtest.com"
        self.client.post('/accounts/signup/', {
            'email': email,
            'password1': 'LoadTestPass123',
            'password2': 'LoadTestPass123',
            'recaptcha_token': 'load_test'
        })

# Target: 100 signups/second with p99 < 500ms
```

### 5.2 Rate Limit Stress Test

**Test ID:** PERF-002
**Purpose:** Verify rate limiting under load

```python
class RateLimitStressTest(TestCase):
    """Stress test rate limiting performance."""

    def test_rate_limit_performance(self):
        """Rate limiting should not add significant latency."""
        import time

        cache.clear()
        latencies = []

        for i in range(1000):
            start = time.time()
            check_signup_limit('192.168.1.1')
            latencies.append((time.time() - start) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        p99_latency = sorted(latencies)[990]

        self.assertLess(avg_latency, 5)   # < 5ms average
        self.assertLess(p99_latency, 20)  # < 20ms p99
```

---

## Test Execution Schedule

### Pre-Deployment

| Test Type | Frequency | Automation |
|-----------|-----------|------------|
| Unit tests | Every commit | CI/CD |
| Integration tests | Every PR | CI/CD |
| Manual test cases | Before release | QA team |

### Post-Deployment

| Test Type | Frequency | Automation |
|-----------|-----------|------------|
| Smoke tests | After deploy | CI/CD |
| Abuse simulations | Weekly | Scheduled job |
| Performance tests | Weekly | Scheduled job |
| Security scans | Daily | Automated |

---

## Test Environment Requirements

### Staging Environment

- Matches production configuration
- Separate database (can be reset)
- Rate limits at production values
- External API mocking available

### Test Data

- Seed 1000 disposable email domains
- Seed 100 blocked IPs
- Test user accounts at each state (pending, verified, locked)

---

## Related Documents

- `docs/wlj_security_acceptance_criteria.md` - Acceptance criteria (Phase 6)
- `docs/wlj_security_engineering_spec.md` - Engineering specification (Phase 5)
- `docs/wlj_security_controls.md` - Security controls (Phase 4)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
