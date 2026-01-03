# ==============================================================================
# File: docs/wlj_security_risk_scoring.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic risk scoring model for signup fraud detection
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# Version: 1.0
# ==============================================================================

# WLJ Risk Scoring Model

## Document Purpose

This document defines a deterministic risk scoring system to classify signup attempts as low, medium, or high risk. The model is designed to be transparent, auditable, and tunable based on observed attack patterns.

## Core Principles

1. **Deterministic** - Same inputs always produce same score
2. **Explainable** - Every score can be broken down into contributing factors
3. **Tunable** - Weights and thresholds adjustable without code changes
4. **Fast** - Score calculation must complete in < 50ms
5. **Privacy-preserving** - No PII stored in scoring logs

---

## Risk Signals

### Signal Categories

| Category | Weight | Description |
|----------|--------|-------------|
| CAPTCHA Score | 30% | reCAPTCHA v3 or hCaptcha score |
| IP Reputation | 25% | IP quality and history |
| Email Domain | 20% | Email domain classification |
| Behavioral | 15% | Form timing and interaction patterns |
| Device | 10% | Browser fingerprint and device signals |

### Total Weight: 100%

---

## Signal Definitions

### 1. CAPTCHA Score (30% weight)

**Source:** reCAPTCHA v3 API response

**Raw Score Range:** 0.0 to 1.0 (Google's score, higher = more human)

**Risk Conversion:**

| reCAPTCHA Score | Risk Contribution | Description |
|-----------------|-------------------|-------------|
| 0.9 - 1.0 | 0.0 | Very likely human |
| 0.7 - 0.9 | 0.1 | Likely human |
| 0.5 - 0.7 | 0.3 | Uncertain |
| 0.3 - 0.5 | 0.6 | Possibly bot |
| 0.0 - 0.3 | 1.0 | Likely bot |

**Calculation:**
```python
def captcha_risk(recaptcha_score: float) -> float:
    """Convert reCAPTCHA score to risk score (0-1, higher = riskier)."""
    if recaptcha_score >= 0.9:
        return 0.0
    elif recaptcha_score >= 0.7:
        return 0.1
    elif recaptcha_score >= 0.5:
        return 0.3
    elif recaptcha_score >= 0.3:
        return 0.6
    else:
        return 1.0
```

---

### 2. IP Reputation (25% weight)

**Sources:**
- IPQualityScore API (primary)
- MaxMind GeoIP2 (fallback)
- Internal blocklist

**Risk Signals:**

| Signal | Risk Contribution | Weight |
|--------|-------------------|--------|
| Known VPN/Proxy | +0.3 | 30% of IP score |
| TOR exit node | +0.5 | 50% of IP score |
| Datacenter IP | +0.4 | 40% of IP score |
| Recently abused | +0.6 | 60% of IP score |
| On internal blocklist | +1.0 | 100% (override) |
| High-risk country | +0.2 | 20% of IP score |
| Residential, clean | 0.0 | Baseline |

**IP Reputation Tiers:**

| IPQS Fraud Score | Risk Contribution |
|------------------|-------------------|
| 0 - 25 | 0.0 (Clean) |
| 25 - 50 | 0.2 (Low risk) |
| 50 - 75 | 0.5 (Medium risk) |
| 75 - 85 | 0.8 (High risk) |
| 85 - 100 | 1.0 (Very high risk) |

**Calculation:**
```python
def ip_reputation_risk(ipqs_response: dict) -> float:
    """Calculate IP risk from IPQualityScore response."""
    fraud_score = ipqs_response.get('fraud_score', 50)

    # Base risk from fraud score
    if fraud_score <= 25:
        base_risk = 0.0
    elif fraud_score <= 50:
        base_risk = 0.2
    elif fraud_score <= 75:
        base_risk = 0.5
    elif fraud_score <= 85:
        base_risk = 0.8
    else:
        base_risk = 1.0

    # Additional signals
    if ipqs_response.get('tor', False):
        base_risk = min(1.0, base_risk + 0.3)
    if ipqs_response.get('vpn', False):
        base_risk = min(1.0, base_risk + 0.2)
    if ipqs_response.get('recent_abuse', False):
        base_risk = min(1.0, base_risk + 0.3)

    return base_risk
```

---

### 3. Email Domain Risk (20% weight)

**Classification Categories:**

| Category | Risk Contribution | Examples |
|----------|-------------------|----------|
| Disposable | 1.0 | 10minutemail, guerrillamail, tempmail |
| Free (high-abuse) | 0.3 | mail.ru, yandex.ru |
| Free (normal) | 0.1 | gmail.com, outlook.com, yahoo.com |
| Corporate | 0.0 | company domains with MX records |
| Educational | 0.0 | .edu domains |
| Unknown | 0.2 | New or unclassified domains |

**Disposable Email Detection:**

1. Check against static blocklist (2000+ domains)
2. Check against real-time API (Kickbox, ZeroBounce)
3. Pattern matching for known formats

**Calculation:**
```python
DISPOSABLE_DOMAINS = load_disposable_domains()  # Set of ~2000 domains
HIGH_ABUSE_FREE = {'mail.ru', 'yandex.ru', 'qq.com', '163.com'}
NORMAL_FREE = {'gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com', 'icloud.com'}

def email_domain_risk(email: str) -> float:
    """Calculate email domain risk score."""
    domain = email.split('@')[1].lower()

    # Check disposable
    if domain in DISPOSABLE_DOMAINS:
        return 1.0

    # Check high-abuse free
    if domain in HIGH_ABUSE_FREE:
        return 0.3

    # Check normal free
    if domain in NORMAL_FREE:
        return 0.1

    # Check for educational
    if domain.endswith('.edu') or domain.endswith('.ac.uk'):
        return 0.0

    # Check for MX record (corporate indicator)
    if has_valid_mx_record(domain):
        return 0.0

    # Unknown domain
    return 0.2
```

---

### 4. Behavioral Signals (15% weight)

**Signals Collected:**

| Signal | Measurement | Risk Interpretation |
|--------|-------------|---------------------|
| Form completion time | Seconds from page load to submit | < 3s = bot, > 300s = suspicious |
| Field focus events | Count of focus/blur on fields | 0 = bot, low = suspicious |
| Mouse movement | Has mouse moved on page | False = possible bot |
| Keystroke timing | Variance in typing speed | Zero variance = bot |
| Paste detection | Was email/password pasted | May indicate automation |

**Risk Calculation:**

```python
def behavioral_risk(signals: dict) -> float:
    """Calculate behavioral risk from client-side signals."""
    risk = 0.0

    # Form completion time
    completion_time = signals.get('completion_time_seconds', 30)
    if completion_time < 3:
        risk += 0.4  # Too fast, likely bot
    elif completion_time < 5:
        risk += 0.2  # Suspiciously fast
    elif completion_time > 300:
        risk += 0.1  # Unusually slow

    # Field interactions
    focus_events = signals.get('field_focus_count', 0)
    if focus_events == 0:
        risk += 0.3  # No field focus = bot
    elif focus_events < 3:
        risk += 0.1  # Very few interactions

    # Mouse movement
    if not signals.get('has_mouse_movement', True):
        risk += 0.2  # No mouse = possible bot

    # Keystroke patterns
    keystroke_variance = signals.get('keystroke_variance', 50)
    if keystroke_variance == 0:
        risk += 0.3  # Zero variance = automated
    elif keystroke_variance < 10:
        risk += 0.1  # Very consistent timing

    return min(1.0, risk)
```

---

### 5. Device Fingerprint (10% weight)

**Fingerprint Components:**

| Component | Description |
|-----------|-------------|
| User Agent | Browser and OS string |
| Screen Resolution | Width x Height |
| Timezone | Browser timezone |
| Language | Browser language settings |
| Plugins | Installed browser plugins |
| Canvas Hash | Canvas rendering fingerprint |
| WebGL Hash | WebGL rendering fingerprint |
| Audio Hash | AudioContext fingerprint |

**Risk Signals:**

| Signal | Risk Contribution |
|--------|-------------------|
| Fingerprint seen with different accounts | +0.5 per previous account |
| Headless browser detected | +0.8 |
| Missing expected APIs | +0.4 |
| Inconsistent fingerprint (tampered) | +0.6 |
| Known automation tool signature | +1.0 |
| Clean, unique fingerprint | 0.0 |

**Calculation:**
```python
def device_fingerprint_risk(fingerprint: dict, fingerprint_hash: str) -> float:
    """Calculate device fingerprint risk."""
    risk = 0.0

    # Check for headless browser indicators
    if fingerprint.get('webdriver', False):
        risk += 0.8

    # Check for automation tools
    if fingerprint.get('phantom', False) or fingerprint.get('selenium', False):
        return 1.0  # Known automation

    # Check for missing APIs (bot indicator)
    missing_apis = fingerprint.get('missing_apis', [])
    if len(missing_apis) > 3:
        risk += 0.4

    # Check fingerprint history (same device, different accounts)
    previous_accounts = get_accounts_for_fingerprint(fingerprint_hash)
    if len(previous_accounts) > 0:
        risk += min(0.5, 0.2 * len(previous_accounts))

    # Check for inconsistencies (tampered fingerprint)
    if has_fingerprint_inconsistencies(fingerprint):
        risk += 0.6

    return min(1.0, risk)
```

---

## Combined Risk Score Calculation

### Formula

```
Total Risk Score = (
    (CAPTCHA_RISK × 0.30) +
    (IP_RISK × 0.25) +
    (EMAIL_RISK × 0.20) +
    (BEHAVIORAL_RISK × 0.15) +
    (DEVICE_RISK × 0.10)
)
```

### Implementation

```python
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class RiskScoreResult:
    total_score: float
    risk_level: str
    breakdown: Dict[str, float]
    signals: Dict[str, Any]
    recommended_action: str

def calculate_risk_score(
    recaptcha_score: float,
    ip_info: dict,
    email: str,
    behavioral_signals: dict,
    device_fingerprint: dict,
    fingerprint_hash: str
) -> RiskScoreResult:
    """
    Calculate comprehensive risk score for signup attempt.

    Returns:
        RiskScoreResult with total score, level, breakdown, and recommended action
    """
    # Calculate individual risk scores
    captcha = captcha_risk(recaptcha_score)
    ip = ip_reputation_risk(ip_info)
    email_risk = email_domain_risk(email)
    behavioral = behavioral_risk(behavioral_signals)
    device = device_fingerprint_risk(device_fingerprint, fingerprint_hash)

    # Apply weights
    weighted = {
        'captcha': captcha * 0.30,
        'ip_reputation': ip * 0.25,
        'email_domain': email_risk * 0.20,
        'behavioral': behavioral * 0.15,
        'device': device * 0.10
    }

    total = sum(weighted.values())

    # Determine risk level and action
    if total <= 0.3:
        level = 'LOW'
        action = 'ALLOW'
    elif total <= 0.6:
        level = 'MEDIUM'
        action = 'CAPTCHA_CHALLENGE'
    elif total <= 0.8:
        level = 'HIGH'
        action = 'PHONE_VERIFICATION'
    else:
        level = 'CRITICAL'
        action = 'BLOCK'

    return RiskScoreResult(
        total_score=round(total, 3),
        risk_level=level,
        breakdown=weighted,
        signals={
            'captcha_raw': recaptcha_score,
            'ip_fraud_score': ip_info.get('fraud_score'),
            'email_domain': email.split('@')[1],
            'completion_time': behavioral_signals.get('completion_time_seconds'),
            'fingerprint_hash': fingerprint_hash[:16]  # Truncated for privacy
        },
        recommended_action=action
    )
```

---

## Risk Thresholds

### Default Thresholds

| Risk Score | Level | Action |
|------------|-------|--------|
| 0.00 - 0.30 | LOW | Allow signup, standard flow |
| 0.30 - 0.60 | MEDIUM | Show visible CAPTCHA challenge |
| 0.60 - 0.80 | HIGH | CAPTCHA + offer phone verification |
| 0.80 - 1.00 | CRITICAL | Block signup, log for review |

### Threshold Configuration

```python
# settings.py or environment variables
RISK_THRESHOLDS = {
    'LOW_MAX': float(os.getenv('RISK_THRESHOLD_LOW', 0.30)),
    'MEDIUM_MAX': float(os.getenv('RISK_THRESHOLD_MEDIUM', 0.60)),
    'HIGH_MAX': float(os.getenv('RISK_THRESHOLD_HIGH', 0.80)),
    # Above HIGH_MAX = CRITICAL
}

RISK_ACTIONS = {
    'LOW': 'ALLOW',
    'MEDIUM': 'CAPTCHA_CHALLENGE',
    'HIGH': 'PHONE_VERIFICATION',
    'CRITICAL': 'BLOCK'
}
```

---

## Enforcement Actions

### Action Definitions

| Action | Description | User Experience |
|--------|-------------|-----------------|
| `ALLOW` | Proceed with signup | Seamless, invisible friction |
| `CAPTCHA_CHALLENGE` | Show visible CAPTCHA | Checkbox or image challenge |
| `PHONE_VERIFICATION` | Request phone number | Optional but recommended |
| `BLOCK` | Reject signup | Generic error message |

### Action Implementation

```python
def enforce_action(action: str, request, form) -> HttpResponse:
    """Enforce the recommended action based on risk score."""

    if action == 'ALLOW':
        # Proceed with account creation
        return create_pending_account(form)

    elif action == 'CAPTCHA_CHALLENGE':
        # Show visible CAPTCHA
        if request.POST.get('captcha_response'):
            if verify_captcha(request.POST['captcha_response']):
                return create_pending_account(form)
            else:
                return render_captcha_error(request)
        return render_captcha_form(request, form)

    elif action == 'PHONE_VERIFICATION':
        # Offer phone verification
        return render_phone_verification_form(request, form, optional=True)

    elif action == 'BLOCK':
        # Log and reject
        log_blocked_signup(request, form)
        return render_generic_error(request)

    else:
        raise ValueError(f"Unknown action: {action}")
```

---

## Override Rules

### Automatic Blocks (Bypass Scoring)

These conditions trigger immediate block regardless of score:

| Condition | Reason |
|-----------|--------|
| Email on global blocklist | Known bad actor |
| IP on internal blocklist | Previous confirmed abuse |
| Fingerprint linked to 3+ accounts | Multi-account abuse |
| Honeypot field filled | Bot detected |
| Rate limit exceeded | Flood protection |

### Automatic Allows (Trusted Indicators)

These conditions reduce risk score:

| Condition | Score Reduction |
|-----------|-----------------|
| Corporate email domain | -0.1 |
| Educational email | -0.1 |
| Known good IP range | -0.05 |
| Returning verified user (same fingerprint) | -0.2 |

---

## Logging and Auditing

### Score Logging Schema

```python
@dataclass
class SignupRiskLog:
    timestamp: datetime
    request_id: str
    email_hash: str  # SHA256 of email
    ip_hash: str     # SHA256 of IP
    fingerprint_hash: str

    # Scores
    total_score: float
    risk_level: str
    action_taken: str

    # Breakdown (for audit)
    captcha_score: float
    ip_risk: float
    email_risk: float
    behavioral_risk: float
    device_risk: float

    # Outcome
    signup_completed: bool
    verification_method: str  # 'email', 'phone', 'none'
```

### Retention Policy

- Raw logs: 90 days
- Aggregated metrics: Indefinite
- PII (email, IP): Hashed, never stored raw

---

## Tuning and Calibration

### Monitoring Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| False positive rate | < 0.5% | > 1% |
| Bot block rate | > 95% | < 90% |
| CAPTCHA challenge rate | 5-15% | > 25% |
| Phone verification rate | < 5% | > 10% |

### Calibration Process

1. **Weekly Review**
   - Analyze blocked signups
   - Check for false positives (support tickets)
   - Adjust weights if patterns emerge

2. **Monthly Tuning**
   - Review threshold effectiveness
   - Compare predicted vs actual abuse
   - Update disposable email list

3. **Incident Response**
   - If attack detected, tighten thresholds
   - Add new signals if attack bypassed detection
   - Document and share learnings

---

## Example Scenarios

### Scenario 1: Legitimate User (Gmail, Residential IP)

```
Input:
- reCAPTCHA: 0.9
- IP: Residential, clean history
- Email: user@gmail.com
- Behavior: 45s completion, normal interactions
- Device: Chrome on Windows, unique fingerprint

Calculation:
- CAPTCHA: 0.0 × 0.30 = 0.00
- IP: 0.0 × 0.25 = 0.00
- Email: 0.1 × 0.20 = 0.02
- Behavioral: 0.0 × 0.15 = 0.00
- Device: 0.0 × 0.10 = 0.00

Total: 0.02 → LOW → ALLOW
```

### Scenario 2: Suspicious User (Disposable Email, VPN)

```
Input:
- reCAPTCHA: 0.6
- IP: VPN detected, medium fraud score
- Email: user@tempmail.org
- Behavior: 8s completion, low interactions
- Device: Normal fingerprint

Calculation:
- CAPTCHA: 0.3 × 0.30 = 0.09
- IP: 0.5 × 0.25 = 0.125
- Email: 1.0 × 0.20 = 0.20
- Behavioral: 0.2 × 0.15 = 0.03
- Device: 0.0 × 0.10 = 0.00

Total: 0.445 → MEDIUM → CAPTCHA_CHALLENGE
```

### Scenario 3: Bot Attack (Automated, Datacenter)

```
Input:
- reCAPTCHA: 0.2
- IP: Datacenter, high fraud score
- Email: random@guerrillamail.com
- Behavior: 1s completion, no interactions
- Device: Headless browser detected

Calculation:
- CAPTCHA: 1.0 × 0.30 = 0.30
- IP: 0.9 × 0.25 = 0.225
- Email: 1.0 × 0.20 = 0.20
- Behavioral: 0.7 × 0.15 = 0.105
- Device: 0.8 × 0.10 = 0.08

Total: 0.91 → CRITICAL → BLOCK
```

---

## Related Documents

- `docs/wlj_security_signup_threat_model.md` - Threat model (Phase 1)
- `docs/wlj_security_signup_flow.md` - Target signup flow (Phase 2)
- `docs/wlj_security_controls.md` - Security controls (Phase 4)

---

*This document is part of the WLJ Secure Signup & Anti-Fraud System project.*
