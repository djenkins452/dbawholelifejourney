# ==============================================================================
# File: docs/wlj_security_signup_threat_model.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Signup abuse threat model identifying risks and mitigations
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Signup Threat Model

## Document Purpose

This threat model identifies and documents all realistic signup abuse scenarios for the Whole Life Journey application. The goal is to ensure defenses are intentional, measurable, and proportionate to the risks.

## Current Signup Flow Overview

The WLJ signup flow uses django-allauth for authentication:
1. User navigates to signup page
2. User provides email address and password
3. Email verification sent (if configured)
4. User accepts Terms of Service
5. User completes onboarding wizard (6 steps)
6. User gains access to dashboard

**Key Files:**
- `apps/users/views.py` - AcceptTermsView, OnboardingWizardView
- `apps/users/forms.py` - ProfileForm, PreferencesForm
- `apps/users/models.py` - User, UserPreferences, TermsAcceptance

---

## Threat Categories

### 1. Bot Flood Attacks

**Description:** Automated scripts or bots creating large numbers of fake accounts rapidly.

**Attack Vectors:**
- Headless browser automation (Selenium, Puppeteer)
- Direct API requests bypassing frontend
- Form submission bots

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | HIGH | OpenAI API costs from AI coaching features |
| Data Quality | HIGH | Polluted analytics, skewed user metrics |
| System Stability | MEDIUM | Database bloat, query performance degradation |
| Reputation | LOW | Inactive accounts don't directly harm UX |

**Likelihood:** **HIGH** - Common attack, low barrier to execute

**Primary Mitigations:**
1. Rate limiting on signup endpoint (per IP, per session)
2. Invisible CAPTCHA (reCAPTCHA v3 or hCaptcha)
3. Honeypot fields in signup form
4. Device fingerprinting to detect automation

---

### 2. Disposable Email Abuse

**Description:** Using temporary/throwaway email services (10minutemail, guerrillamail, etc.) to create accounts that bypass email verification.

**Attack Vectors:**
- Disposable email services (thousands exist)
- Email alias patterns (+tag, subdomain variations)
- Self-hosted catch-all domains

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | MEDIUM | AI API costs from "free trial" abuse |
| Data Quality | HIGH | No way to re-engage users, bad analytics |
| System Stability | LOW | Email bounces don't affect core function |
| Reputation | LOW | Minimal direct user impact |

**Likelihood:** **HIGH** - Trivially easy, many free services

**Primary Mitigations:**
1. Maintain blocklist of known disposable email domains
2. Use third-party email validation API (Kickbox, ZeroBounce)
3. Require email verification before accessing AI features
4. Monitor for patterns (burst signups from similar domains)

---

### 3. Proxy/VPN Abuse

**Description:** Using VPNs, proxies, or TOR to mask true IP addresses for abuse activities.

**Attack Vectors:**
- Commercial VPN services
- Residential proxy networks
- TOR exit nodes
- Cloud provider IP ranges (AWS, GCP, Azure)

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | MEDIUM | Evades IP-based rate limiting |
| Data Quality | MEDIUM | Location data unreliable |
| System Stability | LOW | Traffic still legitimate volume |
| Reputation | LOW | Legitimate users also use VPNs |

**Likelihood:** **MEDIUM** - Requires more effort but common

**Primary Mitigations:**
1. IP reputation scoring (IPQualityScore, MaxMind)
2. Flag high-risk IPs for additional verification
3. Don't block VPNs outright (privacy-conscious users)
4. Track behavioral patterns beyond IP alone

---

### 4. Referral/Promo Code Abuse

**Description:** Exploiting referral systems, promotional codes, or new user bonuses.

**Attack Vectors:**
- Self-referral with multiple accounts
- Referral code sharing on forums
- Automated referral claim bots

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | HIGH | Direct financial loss from rewards |
| Data Quality | MEDIUM | Inflated referral metrics |
| System Stability | LOW | No performance impact |
| Reputation | MEDIUM | Legitimate users feel cheated |

**Likelihood:** **LOW** (currently) - WLJ doesn't have active referral program

**Primary Mitigations:**
1. Require verified email + phone for referral rewards
2. Delay reward payout (cooling-off period)
3. Device fingerprinting to detect same-device accounts
4. Manual review for high-value rewards

---

### 5. Credential Stuffing (Account Takeover Prep)

**Description:** Using breached credential lists to probe for valid email/password combinations during signup.

**Attack Vectors:**
- Testing if email exists via signup error messages
- Password reset enumeration
- Login probing with breached credentials

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | LOW | Minimal resource usage |
| Data Quality | LOW | Not creating fake data |
| System Stability | LOW | Probing is low-volume |
| Reputation | HIGH | User trust if accounts compromised |

**Likelihood:** **MEDIUM** - Common but requires existing breach data

**Primary Mitigations:**
1. Don't reveal if email exists ("check your email" for all)
2. Rate limit password reset requests
3. Account lockout after failed attempts
4. Notify users of suspicious login attempts
5. Support and encourage MFA/biometric login (already implemented)

---

### 6. Spam Account Registration

**Description:** Creating accounts to post spam content, phishing links, or abuse community features.

**Attack Vectors:**
- Profile bio/avatar abuse
- Journal entry spam (if public)
- Support ticket spam

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | LOW | Content storage is cheap |
| Data Quality | LOW | Private journals minimize spread |
| System Stability | LOW | No performance impact |
| Reputation | MEDIUM | If spam escapes to email/notifications |

**Likelihood:** **LOW** - WLJ is primarily private/personal data

**Primary Mitigations:**
1. Email verification before posting
2. Content moderation for any public-facing fields
3. Rate limit content creation for new accounts
4. AI-based spam detection for user-generated content

---

### 7. Resource Exhaustion (API Abuse)

**Description:** Creating accounts specifically to exploit AI features and exhaust API quotas.

**Attack Vectors:**
- Signup → use AI coaching → abandon account
- Scripted AI feature abuse
- Personal Assistant exploitation

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | HIGH | OpenAI API is expensive |
| Data Quality | MEDIUM | Pollutes AI usage analytics |
| System Stability | MEDIUM | Could hit rate limits |
| Reputation | LOW | No direct user impact |

**Likelihood:** **MEDIUM** - WLJ has valuable AI features

**Primary Mitigations:**
1. Tiered AI usage limits (free vs verified users)
2. Require email verification for AI features
3. Require AI consent and data consent explicitly
4. Track usage patterns for anomaly detection
5. Implement per-user daily/weekly AI call limits

---

### 8. Denial of Service via Signup

**Description:** Flooding signup endpoint to exhaust server resources or downstream services.

**Attack Vectors:**
- High-volume POST requests to signup
- Triggering expensive operations (email sending)
- Database write storms

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | MEDIUM | Email sending costs, server scaling |
| Data Quality | LOW | Attacks don't create valid data |
| System Stability | HIGH | Could degrade service for real users |
| Reputation | HIGH | Downtime hurts trust |

**Likelihood:** **LOW** - Requires significant resources, easier targets exist

**Primary Mitigations:**
1. WAF-level rate limiting (Cloudflare, Railway edge)
2. Application-level rate limiting
3. CAPTCHA on repeated failures
4. Queue email sending (don't block on send)

---

### 9. Account Enumeration

**Description:** Discovering valid user accounts through signup/login behavior differences.

**Attack Vectors:**
- Signup: "email already exists" error
- Login: Different error for valid vs invalid email
- Password reset: Timing differences

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | LOW | Minimal resource usage |
| Data Quality | LOW | Reconnaissance only |
| System Stability | LOW | Low-volume probing |
| Reputation | MEDIUM | Privacy concern for users |

**Likelihood:** **MEDIUM** - Common reconnaissance technique

**Primary Mitigations:**
1. Uniform responses regardless of email existence
2. Consistent timing for all operations
3. Generic error messages ("if this email exists, we sent a link")
4. Rate limit enumeration attempts

---

### 10. Social Engineering Setup

**Description:** Creating accounts with legitimate-looking profiles to later target real users.

**Attack Vectors:**
- Impersonation accounts
- Phishing preparation
- Trust building for future attacks

**Impact to WLJ:**
| Impact Area | Severity | Description |
|-------------|----------|-------------|
| Cost | LOW | Account creation is cheap |
| Data Quality | LOW | Fake accounts are isolated |
| System Stability | LOW | No performance impact |
| Reputation | MEDIUM | If impersonation affects users |

**Likelihood:** **LOW** - WLJ's private nature limits social features

**Primary Mitigations:**
1. No public user directory
2. Limited profile visibility
3. Report/flag mechanism for suspicious accounts
4. Identity verification for any public features

---

## Threat Summary Matrix

| Threat | Impact | Likelihood | Risk Score | Priority |
|--------|--------|------------|------------|----------|
| Bot Flood Attacks | HIGH | HIGH | **CRITICAL** | P1 |
| Disposable Email Abuse | MEDIUM | HIGH | **HIGH** | P1 |
| Resource Exhaustion (API) | HIGH | MEDIUM | **HIGH** | P1 |
| Denial of Service via Signup | HIGH | LOW | **MEDIUM** | P2 |
| Credential Stuffing | MEDIUM | MEDIUM | **MEDIUM** | P2 |
| Proxy/VPN Abuse | MEDIUM | MEDIUM | **MEDIUM** | P2 |
| Account Enumeration | MEDIUM | MEDIUM | **MEDIUM** | P2 |
| Spam Account Registration | LOW | LOW | **LOW** | P3 |
| Referral/Promo Abuse | LOW* | LOW | **LOW** | P3 |
| Social Engineering Setup | LOW | LOW | **LOW** | P3 |

*Risk increases significantly if referral program is implemented

---

## Recommended Mitigation Priorities

### Phase 1: Immediate (P1 Threats)

1. **Invisible CAPTCHA Integration**
   - Implement reCAPTCHA v3 or hCaptcha
   - Score-based challenge escalation
   - Silent for low-risk users

2. **Disposable Email Blocking**
   - Integrate email domain blocklist
   - Consider email validation API

3. **AI Feature Protection**
   - Require verified email for AI features
   - Implement usage limits per user

### Phase 2: Short-Term (P2 Threats)

4. **Rate Limiting**
   - Per-IP signup limits
   - Per-session request limits
   - Exponential backoff for failures

5. **IP Reputation Scoring**
   - Integrate IP quality service
   - Flag high-risk IPs for review

6. **Account Enumeration Prevention**
   - Uniform response messages
   - Consistent timing

### Phase 3: Medium-Term (P3 Threats)

7. **Device Fingerprinting**
   - Track device signatures
   - Detect multi-account abuse

8. **Behavioral Analysis**
   - Monitor signup patterns
   - Anomaly detection for abuse

---

## Metrics for Success

| Metric | Current | Target | Measurement Method |
|--------|---------|--------|-------------------|
| Bot signup rate | Unknown | <1% | Automation detection flags |
| Disposable email signups | Unknown | <2% | Email domain analysis |
| AI abuse incidents | Unknown | 0/month | Usage anomaly alerts |
| Signup success rate (legit users) | ~95% | >98% | User journey analytics |
| False positive blocks | Unknown | <0.5% | User complaints + review |

---

## Review Schedule

- **Monthly:** Review abuse metrics and adjust thresholds
- **Quarterly:** Full threat model review
- **On-Incident:** Immediate review after any abuse event

---

## Related Documents

- `docs/wlj_security_review.md` - Overall security findings
- `docs/wlj_security_signup_flow.md` - Target signup flow design (Phase 2)
- `docs/wlj_security_risk_scoring.md` - Risk scoring model (Phase 3)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
