# ==============================================================================
# File: docs/wlj_security_signup_flow.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Target signup flow design with progressive friction
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Target Signup Flow with Progressive Friction

## Document Purpose

This document defines the target signup flow for Whole Life Journey that implements progressive friction - a security pattern that increases verification requirements only when risk signals appear, keeping the experience smooth for legitimate users.

## Design Principles

1. **Low friction by default** - Legitimate users should experience minimal interruption
2. **Risk-proportionate response** - Friction increases only when risk signals are detected
3. **Fail secure** - When in doubt, add friction rather than allow abuse
4. **Transparent to users** - Users understand why additional verification is needed
5. **Reversible decisions** - Blocked users can appeal through support

---

## Account States

### State Definitions

| State | Description | Capabilities |
|-------|-------------|--------------|
| `pending` | Account created, email not verified | View-only dashboard, no AI features |
| `verified` | Email verified, standard user | Full access except high-trust features |
| `trusted` | Long-term verified user with good history | Full access, higher rate limits |
| `restricted` | Flagged for suspicious activity | Limited features, under review |
| `suspended` | Confirmed abuse | No access, must contact support |

### State Transitions

```
[New Signup] → pending → verified → trusted
                  ↓          ↓
              suspended  restricted → suspended
                              ↓
                          verified (after review)
```

---

## Signup Flow Stages

### Stage 1: Initial Form Submission

**User Actions:**
1. Navigate to `/accounts/signup/`
2. Enter email address
3. Enter password (with confirmation)
4. Submit form

**System Actions:**
1. Validate email format
2. Check password strength (min 8 chars, complexity rules)
3. **Honeypot field check** - Reject if filled (bots only)
4. **Invisible CAPTCHA score** - Collect reCAPTCHA v3 score silently
5. **Rate limit check** - Per-IP signup attempts

**Risk Signals Collected:**
- reCAPTCHA v3 score (0.0 - 1.0)
- IP address and reputation
- Time to complete form (too fast = bot)
- Browser fingerprint hash
- Email domain classification

### Stage 2: Risk Evaluation

**Immediate Evaluation (before account creation):**

```python
risk_score = calculate_risk_score(
    captcha_score=0.9,      # Weight: 30%
    ip_reputation=0.7,       # Weight: 25%
    email_domain_risk=0.1,   # Weight: 20%
    form_timing=0.8,         # Weight: 15%
    fingerprint_risk=0.2     # Weight: 10%
)
```

**Risk Thresholds:**

| Score Range | Risk Level | Action |
|-------------|------------|--------|
| 0.0 - 0.3 | LOW | Proceed to email verification |
| 0.3 - 0.6 | MEDIUM | Show visible CAPTCHA challenge |
| 0.6 - 0.8 | HIGH | CAPTCHA + phone verification option |
| 0.8 - 1.0 | CRITICAL | Block signup, log for review |

### Stage 3: Account Creation

**For LOW risk signups:**
1. Create account in `pending` state
2. Send email verification link
3. Redirect to "check your email" page
4. Log signup attempt with risk score

**For MEDIUM risk signups:**
1. Display visible CAPTCHA (reCAPTCHA v2 checkbox or hCaptcha)
2. On CAPTCHA success → proceed as LOW risk
3. On CAPTCHA failure → increment risk, retry limit of 3

**For HIGH risk signups:**
1. Display visible CAPTCHA
2. After CAPTCHA success, offer phone verification (optional)
3. If phone verified → create account, mark as higher trust
4. If phone skipped → create account with usage restrictions

**For CRITICAL risk signups:**
1. Display generic error: "Unable to create account. Please try again later."
2. Log full details for security review
3. Do NOT reveal reason for block

### Stage 4: Email Verification

**Verification Token Rules:**
- Token expires in 24 hours
- One-time use only
- Invalidated if new token requested
- Maximum 3 resend requests per hour

**User Flow:**
1. User clicks link in email
2. Token validated
3. Account state: `pending` → `verified`
4. Redirect to Terms of Service acceptance

**If token expired/invalid:**
1. Show "Link expired" message
2. Offer to resend verification email
3. Rate limit resend requests

### Stage 5: Terms of Service Acceptance

**User Actions:**
1. View Terms of Service
2. Check acceptance checkbox
3. Submit acceptance

**System Actions:**
1. Create `TermsAcceptance` record with:
   - Timestamp
   - IP address
   - User agent
   - Terms version
2. Redirect to onboarding wizard

### Stage 6: Onboarding Wizard

**Steps (existing flow):**
1. Welcome
2. Theme selection
3. Module toggles
4. AI coaching preferences
5. Location/timezone
6. Complete

**Security Additions:**
- AI features require explicit consent checkboxes
- Personal Assistant requires additional data consent
- Preferences saved incrementally (not lost on abandon)

### Stage 7: Dashboard Access

**First-time User Restrictions:**
- AI features limited to 5 requests/day for first 7 days
- No bulk export features for first 30 days
- Gradual trust building based on usage patterns

---

## Progressive Friction Decision Tree

```
                         ┌─────────────────┐
                         │  Signup Request │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │ Honeypot Check  │
                         └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │ FILLED      │ EMPTY       │
                    ▼             │             │
              ┌─────────┐        │             │
              │  BLOCK  │        │             │
              │  (Bot)  │        │             │
              └─────────┘        ▼             │
                         ┌───────────────┐    │
                         │ Rate Limit    │    │
                         │ Check         │    │
                         └───────┬───────┘    │
                                 │            │
                   ┌─────────────┼────────────┤
                   │ EXCEEDED    │ OK         │
                   ▼             │            │
             ┌─────────┐        │            │
             │ BLOCK   │        │            │
             │ (Flood) │        │            │
             └─────────┘        ▼            │
                         ┌───────────────┐   │
                         │ Disposable    │   │
                         │ Email Check   │   │
                         └───────┬───────┘   │
                                 │           │
                   ┌─────────────┼───────────┤
                   │ DISPOSABLE  │ OK        │
                   ▼             │           │
             ┌─────────┐        │           │
             │ BLOCK + │        │           │
             │ Message │        │           │
             └─────────┘        ▼           │
                         ┌───────────────┐  │
                         │ Calculate     │  │
                         │ Risk Score    │  │
                         └───────┬───────┘  │
                                 │          │
            ┌────────────────────┼──────────┼────────────────┐
            │ LOW (0-0.3)        │ MED      │ HIGH           │ CRITICAL
            │                    │ (0.3-0.6)│ (0.6-0.8)      │ (0.8-1.0)
            ▼                    ▼          ▼                ▼
     ┌─────────────┐     ┌───────────┐  ┌─────────────┐  ┌─────────┐
     │ Create      │     │ Show      │  │ CAPTCHA +   │  │ BLOCK   │
     │ Account     │     │ CAPTCHA   │  │ Phone       │  │ + Log   │
     │ (pending)   │     │ Challenge │  │ Verification│  └─────────┘
     └──────┬──────┘     └─────┬─────┘  └──────┬──────┘
            │                  │               │
            │           ┌──────▼──────┐       │
            │           │ CAPTCHA     │       │
            │           │ Passed?     │       │
            │           └──────┬──────┘       │
            │                  │              │
            │     ┌────────────┼────────────┐ │
            │     │ NO         │ YES        │ │
            │     ▼            │            │ │
            │  ┌──────┐       │            │ │
            │  │Retry │       │            │ │
            │  │(max 3)│      │            │ │
            │  └──────┘       ▼            ▼ │
            │          ┌─────────────────────┴──┐
            └──────────►  Send Verification     │
                       │  Email                 │
                       └───────────┬────────────┘
                                   │
                                   ▼
                         ┌─────────────────┐
                         │ Email Verified? │
                         └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │ NO          │ YES         │
                    ▼             ▼             │
              ┌───────────┐  ┌────────────┐    │
              │ Reminder  │  │ Account    │    │
              │ Emails    │  │ → verified │    │
              │ (1, 3, 7d)│  └─────┬──────┘    │
              └───────────┘        │           │
                                   ▼           │
                         ┌─────────────────┐   │
                         │ Terms of Service│   │
                         │ Acceptance      │   │
                         └────────┬────────┘   │
                                  │            │
                                  ▼            │
                         ┌─────────────────┐   │
                         │ Onboarding      │   │
                         │ Wizard          │   │
                         └────────┬────────┘   │
                                  │            │
                                  ▼            │
                         ┌─────────────────┐   │
                         │ Dashboard       │   │
                         │ (with limits)   │   │
                         └─────────────────┘   │
```

---

## Rate Limiting Checkpoints

### Signup Endpoint Rate Limits

| Limit Type | Threshold | Window | Action on Exceed |
|------------|-----------|--------|------------------|
| Per IP | 5 signups | 1 hour | Block + CAPTCHA on next attempt |
| Per IP | 20 signups | 24 hours | Hard block for 24 hours |
| Per Session | 3 signups | 1 hour | Block session |
| Global | 100 signups | 1 minute | Alert ops team |

### Email Verification Rate Limits

| Limit Type | Threshold | Window | Action on Exceed |
|------------|-----------|--------|------------------|
| Resend per user | 3 | 1 hour | "Try again later" |
| Resend per IP | 10 | 1 hour | Temporary IP block |

### Password Reset Rate Limits

| Limit Type | Threshold | Window | Action on Exceed |
|------------|-----------|--------|------------------|
| Per email | 3 | 1 hour | "If email exists, we sent a link" |
| Per IP | 10 | 1 hour | Add CAPTCHA |

---

## Phone Verification (High-Risk Only)

### When Required

Phone verification is **optional** but **recommended** for HIGH risk signups:
- Users can skip but face feature restrictions
- Skipping adds +0.1 to ongoing risk score

### Implementation

1. **SMS-based verification**
   - Use Twilio Verify API
   - 6-digit code, 10-minute expiry
   - 3 attempts maximum

2. **Phone number validation**
   - Reject VOIP numbers (optional, configurable)
   - Reject numbers from high-risk countries (configurable)
   - Store hashed phone number only

3. **Privacy considerations**
   - Phone number hashed with salt
   - Not displayed anywhere in UI
   - Used only for abuse detection

---

## Invisible CAPTCHA Integration

### reCAPTCHA v3 Configuration

```python
RECAPTCHA_V3_SITE_KEY = env('RECAPTCHA_V3_SITE_KEY')
RECAPTCHA_V3_SECRET_KEY = env('RECAPTCHA_V3_SECRET_KEY')

# Score thresholds
RECAPTCHA_SCORE_THRESHOLD_LOW = 0.7    # Very likely human
RECAPTCHA_SCORE_THRESHOLD_MEDIUM = 0.5  # Possibly human
RECAPTCHA_SCORE_THRESHOLD_HIGH = 0.3    # Possibly bot
# Below 0.3 = Likely bot
```

### Implementation Points

1. **Load script on signup page**
   ```html
   <script src="https://www.google.com/recaptcha/api.js?render=SITE_KEY"></script>
   ```

2. **Execute on form submit**
   ```javascript
   grecaptcha.execute('SITE_KEY', {action: 'signup'})
     .then(token => { /* include in form */ });
   ```

3. **Verify server-side**
   ```python
   response = requests.post(
       'https://www.google.com/recaptcha/api/siteverify',
       data={'secret': SECRET_KEY, 'response': token}
   )
   score = response.json()['score']
   ```

---

## Honeypot Field Implementation

### Form Field

```html
<!-- Hidden from humans, visible to bots -->
<div style="position: absolute; left: -9999px;">
  <label for="website">Website (leave blank)</label>
  <input type="text" name="website" id="website" autocomplete="off" tabindex="-1">
</div>
```

### Server Validation

```python
def clean_website(self):
    website = self.cleaned_data.get('website')
    if website:
        # Bot detected - log and reject silently
        logger.warning(f"Honeypot triggered: {self.request.META.get('REMOTE_ADDR')}")
        raise forms.ValidationError("Unable to create account")
    return website
```

---

## Feature Restrictions by Account State

### Pending Accounts (Email Not Verified)

| Feature | Access |
|---------|--------|
| View dashboard | ✅ (limited) |
| Journal entries | ❌ |
| AI coaching | ❌ |
| Health tracking | ❌ |
| Settings | ✅ (limited) |
| Verification reminder | ✅ (banner shown) |

### Verified Accounts (First 7 Days)

| Feature | Access |
|---------|--------|
| All basic features | ✅ |
| AI coaching | ✅ (5 requests/day) |
| Personal Assistant | ❌ (requires 7 days) |
| Bulk export | ❌ (requires 30 days) |
| API access | ❌ (requires 30 days) |

### Trusted Accounts (30+ Days, Good Standing)

| Feature | Access |
|---------|--------|
| All features | ✅ |
| AI coaching | ✅ (higher limits) |
| Personal Assistant | ✅ |
| Bulk export | ✅ |
| API access | ✅ |

### Restricted Accounts

| Feature | Access |
|---------|--------|
| View own data | ✅ |
| Create new content | ❌ |
| AI features | ❌ |
| Must contact support | ✅ (banner shown) |

---

## Error Messages

### User-Facing Messages

| Scenario | Message |
|----------|---------|
| Disposable email | "Please use a permanent email address. Temporary email services are not supported." |
| Rate limited | "Too many signup attempts. Please try again in [X] minutes." |
| CAPTCHA failed | "Please complete the security check to continue." |
| Generic block | "Unable to create account at this time. Please try again later or contact support." |
| Email exists | "If this email is registered, you'll receive a password reset link." |

### Internal Logging

All blocks logged with:
- Timestamp
- IP address
- Email (hashed for privacy)
- Risk score breakdown
- Block reason code
- User agent
- Fingerprint hash

---

## Monitoring & Alerts

### Real-time Alerts

| Metric | Threshold | Alert |
|--------|-----------|-------|
| Signup failures/min | > 50 | PagerDuty |
| Block rate | > 20% of attempts | Slack |
| CAPTCHA challenges/min | > 100 | Slack |
| Phone verification requests/hr | > 50 | Slack |

### Daily Reports

- Total signups (successful vs blocked)
- Risk score distribution
- Top blocked IPs
- Top blocked email domains
- False positive candidates (low-risk blocks)

---

## Related Documents

- `docs/wlj_security_signup_threat_model.md` - Threat model (Phase 1)
- `docs/wlj_security_risk_scoring.md` - Risk scoring details (Phase 3)
- `docs/wlj_security_controls.md` - Security controls (Phase 4)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
