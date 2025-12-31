# ==============================================================================
# File: docs/wlj_security_review.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security review report with findings and remediation status
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-30
# ==============================================================================

# WLJ Security Review Report

**Project:** Whole Life Journey
**Review Date:** December 28, 2025
**Reviewer Role:** Senior Information Security Officer
**Classification:** Internal - Confidential

---

## 1. EXECUTIVE SUMMARY

### 1.1 Overall Security Posture: **MODERATE RISK**

The Whole Life Journey application demonstrates a **generally sound security foundation** with appropriate use of Django's built-in security features. The application implements proper authentication via django-allauth, enforces authorization through user-scoped queries, and utilizes standard security headers in production.

However, the review identified several **significant security concerns** that require attention, particularly in the areas of:
- Credential and API key management
- Third-party data sharing without explicit consent
- Sensitive health data storage without encryption
- Missing rate limiting and monitoring controls

### 1.2 Key Themes

1. **Positive Controls**: Email-based authentication, CSRF protection, HTTPS enforcement in production, user data isolation through consistent query filtering
2. **Critical Gaps**: Plaintext storage of OAuth credentials, API key exposure to frontend, unencrypted health data
3. **Operational Gaps**: No rate limiting, limited audit logging, no error alerting/monitoring
4. **Compliance Alignment**: Generally aligned with OWASP Top 10 principles; gaps in NIST 800-53 control families for encryption and monitoring

### 1.3 Reasonable Diligence Assessment

The system demonstrates **reasonable security diligence for an early-stage personal application** but would require remediation of critical findings before handling a larger user base or meeting enterprise compliance requirements.

---

## 2. METHODOLOGY

### 2.1 Review Scope

This security review was conducted through static code analysis of the following components:
- Django settings and configuration (`config/settings.py`)
- Authentication and authorization mechanisms (`apps/users/`)
- Data models across all application modules
- API integrations (OpenAI, Bible API, Google Calendar)
- Deployment configuration (Procfile, requirements.txt)
- Middleware and access control patterns

### 2.2 Review Approach

The review applied a threat modeling perspective considering:
- **Anonymous attackers** (pre-authentication)
- **Authenticated low-privilege users** (horizontal privilege escalation)
- **Malicious insiders** (data exfiltration, abuse)
- **Automated attacks** (brute force, credential stuffing)
- **Accidental exposure** (misconfiguration, information leakage)

### 2.3 Limitations

- This review is based on static code analysis only; no dynamic testing or penetration testing was performed
- Third-party service configurations (Railway, Cloudinary, OpenAI) were not directly audited
- Database contents and actual production configurations were not examined
- This is not a formal compliance audit or certification assessment

---

## 3. FINDINGS BY CATEGORY

### 3.1 CRITICAL FINDINGS

---

#### Finding C-1: Google OAuth Client Secret Stored in Plaintext

**Description:**
The `GoogleCalendarCredential` model stores OAuth tokens and the client secret in plaintext database fields.

**Affected Area:**
`apps/life/models.py` (lines 909-1070)

```python
class GoogleCalendarCredential(models.Model):
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    client_secret = models.CharField(max_length=500)  # PLAINTEXT
```

**Risk Level:** CRITICAL

**Likelihood of Exploitation:** Medium - Requires database access (SQL injection, backup exposure, insider threat)

**Potential Impact:**
- Full compromise of users' Google Calendar access
- Ability to read, modify, or delete calendar events
- Potential pivot to other Google services if broader scopes granted
- Regulatory notification requirements if breach occurs

**Regulatory Reference:**
- NIST SP 800-53 SC-28 (Protection of Information at Rest)
- OWASP A02:2021 - Cryptographic Failures

---

#### Finding C-2: Bible API Key Exposed to Frontend

**Description:**
The Bible API key is passed to the frontend template context, making it visible in HTML page source.

**Affected Area:**
`apps/users/views.py` (line 130)

```python
context['api_key'] = getattr(settings, 'BIBLE_API_KEY', '')
```

**Risk Level:** CRITICAL

**Likelihood of Exploitation:** High - Any authenticated user can view page source

**Potential Impact:**
- API key abuse and quota exhaustion
- Unauthorized use of organization's API credentials
- Potential billing impact if API has cost tiers
- Credential compromise visible to all application users

**Regulatory Reference:**
- OWASP A07:2021 - Identification and Authentication Failures
- NIST SP 800-53 IA-5 (Authenticator Management)

---

#### Finding C-3: User Data Transmitted to OpenAI Without Explicit Consent

**Description:**
Journal entries containing highly personal content (health concerns, family matters, spiritual reflections) are sent to OpenAI's API for AI coaching features. The data sharing is not explicitly consented to on a per-feature basis.

**Affected Area:**
`apps/ai/services.py` (lines 178-199)

```python
def analyze_journal_entry(self, entry_text: str, mood: str = None, ...):
    prompt = f"""The user just wrote this journal entry:
    "{entry_text[:1500]}"
    """
```

**Risk Level:** CRITICAL

**Likelihood of Exploitation:** N/A - This is a design issue, not an exploit

**Potential Impact:**
- Privacy violations under various jurisdictions (GDPR, CCPA)
- Reputational damage if users learn their intimate thoughts are shared with AI
- Regulatory enforcement actions
- Loss of user trust

**Regulatory Reference:**
- GDPR Article 7 (Conditions for Consent)
- CCPA Section 1798.100 (Consumer Right to Know)
- NIST Privacy Framework PR.PO-P1 (Data Processing Purposes)

---

### 3.2 HIGH SEVERITY FINDINGS

---

#### Finding H-1: No Object-Level Permission Enforcement Framework

**Description:**
User data isolation relies entirely on developers remembering to add `filter(user=request.user)` to every queryset. There is no systematic enforcement mechanism.

**Affected Area:**
All views accessing user-owned data

**Risk Level:** HIGH

**Likelihood of Exploitation:** Low-Medium - Requires developer error in new code

**Potential Impact:**
- Horizontal privilege escalation
- Unauthorized access to other users' personal data
- Privacy breach affecting all application modules

**Regulatory Reference:**
- OWASP A01:2021 - Broken Access Control
- NIST SP 800-53 AC-3 (Access Enforcement)

---

#### Finding H-2: Health Data Stored Without Encryption

**Description:**
Protected health information (weight, heart rate, blood glucose) is stored in plaintext database fields.

**Affected Area:**
`apps/health/models.py` (WeightEntry, HeartRateEntry, GlucoseEntry)

**Risk Level:** HIGH

**Likelihood of Exploitation:** Medium - Requires database access

**Potential Impact:**
- Exposure of sensitive medical information
- HIPAA violations if application expands to handle PHI formally
- Regulatory notification requirements
- Reputational harm

**Regulatory Reference:**
- HIPAA 45 CFR 164.312(a)(2)(iv) (Encryption)
- NIST SP 800-53 SC-28 (Protection of Information at Rest)

---

#### Finding H-3: No Rate Limiting on Authentication Endpoints

**Description:**
Login, registration, and password reset endpoints have no rate limiting configured.

**Affected Area:**
Authentication flows via django-allauth

**Risk Level:** HIGH

**Likelihood of Exploitation:** High - Standard automated attack

**Potential Impact:**
- Account takeover through credential stuffing
- Denial of service through login attempt floods
- User lockout abuse

**Regulatory Reference:**
- OWASP A07:2021 - Identification and Authentication Failures
- NIST SP 800-53 AC-7 (Unsuccessful Login Attempts)

---

#### Finding H-4: Django Admin at Default Path

**Description:**
The Django admin interface is accessible at the predictable `/admin/` path.

**Affected Area:**
`config/urls.py` (line 26)

**Risk Level:** HIGH

**Likelihood of Exploitation:** Medium - Easy discovery, requires additional attack

**Potential Impact:**
- Targeted brute force attacks against admin accounts
- Increased attack surface exposure
- Admin compromise leads to full system control

**Regulatory Reference:**
- NIST SP 800-53 CM-7 (Least Functionality)

---

### 3.3 MEDIUM SEVERITY FINDINGS

---

#### Finding M-1: No SameSite Cookie Attribute Configured

**Description:**
Session and CSRF cookies do not explicitly set the SameSite attribute.

**Affected Area:**
`config/settings.py`

**Risk Level:** MEDIUM

**Potential Impact:** Cross-site request forgery vulnerability in certain browser configurations

---

#### Finding M-2: Soft-Deleted Records Never Permanently Removed

**Description:**
The soft delete mechanism marks records as deleted but no background task permanently removes them after the 30-day retention period.

**Affected Area:**
`apps/core/models.py` (SoftDeleteModel)

**Risk Level:** MEDIUM

**Potential Impact:** Violation of data retention policies; deleted data persists indefinitely

---

#### Finding M-3: Missing Content-Security-Policy Header

**Description:**
No Content-Security-Policy header is configured to restrict resource loading.

**Affected Area:**
`config/settings.py`

**Risk Level:** MEDIUM

**Potential Impact:** XSS attacks can load resources from arbitrary domains

---

#### Finding M-4: DEBUG Logging Enabled for Production Modules

**Description:**
Application loggers are set to DEBUG level even in production.

**Affected Area:**
`config/settings.py` (lines 255-264)

```python
'cloudinary': {'level': 'DEBUG'},
'apps': {'level': 'DEBUG'},
```

**Risk Level:** MEDIUM

**Potential Impact:** Sensitive information may be logged; increased log storage costs

---

#### Finding M-5: No Error Alerting or Monitoring Integration

**Description:**
No error tracking service (Sentry, Rollbar) is configured for production.

**Affected Area:**
`config/settings.py`

**Risk Level:** MEDIUM

**Potential Impact:** Security incidents may go undetected; delayed incident response

---

#### Finding M-6: Predictable User Avatar Paths

**Description:**
Avatar upload paths use sequential user IDs, enabling enumeration.

**Affected Area:**
`apps/users/models.py` (line 15-19)

```python
return f'avatars/user_{instance.id}/avatar.{ext}'
```

**Risk Level:** MEDIUM

**Potential Impact:** User enumeration; potential privacy concerns

---

#### Finding M-7: No File Type Validation Beyond Extension

**Description:**
File uploads rely on filename extension rather than magic number validation.

**Affected Area:**
`apps/life/models.py` (Document model)

**Risk Level:** MEDIUM

**Potential Impact:** Malicious file upload with renamed extension

---

#### Finding M-8: Database Connection May Not Enforce SSL

**Description:**
PostgreSQL connection string does not explicitly require SSL mode.

**Affected Area:**
`config/settings.py` (lines 124-127)

**Risk Level:** MEDIUM

**Potential Impact:** Man-in-the-middle attacks on database connections (if not secured at infrastructure level)

---

#### Finding M-9: Development Dependencies in Production

**Description:**
Linting and development tools are included in main requirements.txt.

**Affected Area:**
`requirements.txt` (lines 52-55)

**Risk Level:** MEDIUM

**Potential Impact:** Increased attack surface; unnecessary code in production

---

#### Finding M-10: HTMX CSRF Token Handling Unverified

**Description:**
HTMX middleware is enabled but CSRF token inclusion in HTMX requests is not explicitly configured.

**Affected Area:**
`config/settings.py` (line 91)

**Risk Level:** MEDIUM

**Potential Impact:** HTMX requests may bypass CSRF protection if not properly configured

---

### 3.4 LOW SEVERITY FINDINGS

---

#### Finding L-1: Minimum Password Length Uses Django Default

**Description:**
MinimumLengthValidator uses default 8-character minimum; consider 12+ for enhanced security.

**Affected Area:**
`config/settings.py` (lines 142-155)

**Risk Level:** LOW

---

#### Finding L-2: No Two-Factor Authentication for Admin

**Description:**
Admin accounts lack two-factor authentication option.

**Risk Level:** LOW

---

#### Finding L-3: Email Verification Disabled

**Description:**
`ACCOUNT_EMAIL_VERIFICATION = "none"` - users can register with any email.

**Affected Area:**
`config/settings.py` (line 289)

**Risk Level:** LOW

---

#### Finding L-4: psycopg2-binary Used Instead of psycopg2

**Description:**
Binary distribution is harder to audit than source-compiled version.

**Affected Area:**
`requirements.txt` (line 7)

**Risk Level:** LOW

---

---

## 4. POSITIVE OBSERVATIONS

The following security controls are implemented correctly and demonstrate security awareness:

### 4.1 Authentication & Authorization
- **Email-based authentication** prevents username enumeration
- **Email enumeration prevention** enabled (`ACCOUNT_PREVENT_ENUMERATION = True`)
- **Custom User model** using AbstractBaseUser with proper password hashing
- **Terms acceptance tracking** with audit trail (IP address, user agent)
- **Onboarding enforcement middleware** ensures users complete required steps
- **LoginRequiredMixin** consistently used across protected views
- **User-scoped queries** consistently filter by `user=request.user`

### 4.2 Session & CSRF
- **CSRF middleware** enabled and properly ordered
- **Secure cookies** in production (SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE)
- **Session remember** feature properly configured

### 4.3 Transport Security
- **SSL redirect** enforced in production
- **HSTS headers** configured with 1-year max-age, including subdomains and preload
- **Security middleware** enabled (XSS filter, content type sniffing prevention)

### 4.4 Data Protection
- **Soft delete** implementation preserves data integrity
- **Environment variable** usage for all secrets (no hardcoded credentials in code)
- **.env file** properly excluded in .gitignore
- **Terms versioning** supports consent re-acquisition when terms change

### 4.5 Deployment Security
- **Gunicorn** used for production WSGI
- **WhiteNoise** for static file serving with manifest-based caching
- **Cloudinary** for media storage (removes file handling from application server)

### 4.6 Code Quality
- **Django 5.x** current LTS version
- **Type hints** and **docstrings** throughout codebase
- **Comprehensive test suite** (877 tests documented)
- **Consistent coding patterns** across modules

---

## 5. GAPS & RISK ACCEPTANCE CONSIDERATIONS

The following risks should be explicitly acknowledged by leadership:

### 5.1 Data Classification
The application handles multiple categories of sensitive data:
- **Personal Identifiable Information (PII)**: Name, email, location
- **Protected Health Information (PHI)**: Weight, heart rate, blood glucose
- **Sensitive Personal Data**: Journal entries, prayer requests, faith reflections
- **Third-Party Credentials**: Google OAuth tokens

**Risk Acceptance Required:** Leadership should formally classify this data and apply appropriate controls based on classification.

### 5.2 Third-Party Data Sharing
User data is shared with:
- **OpenAI** for AI coaching features (journal content, health data, faith content)
- **Cloudinary** for media storage (user avatars, document uploads)
- **Railway** for hosting (all application data)

**Risk Acceptance Required:** Privacy policy must disclose these data processors. User consent mechanism should be implemented for AI features.

### 5.3 Regulatory Compliance Gaps
If the application expands or handles data in certain jurisdictions:
- **HIPAA**: Health data storage would require encryption and additional controls
- **GDPR**: Right to erasure implementation (soft delete may not suffice)
- **CCPA**: Consumer data disclosure requirements

**Risk Acceptance Required:** Leadership should determine applicable regulations and implement gap remediation.

### 5.4 Residual Risk Statement
Even with all findings addressed, residual risks remain:
- Third-party service vulnerabilities (Railway, Cloudinary, OpenAI)
- Zero-day vulnerabilities in dependencies
- Social engineering attacks against users
- Insider threats from administrative users

---

## 6. OVERALL RISK STATEMENT

### 6.1 Industry Best Practices Assessment

| Area | Alignment | Notes |
|------|-----------|-------|
| Authentication | **ALIGNED** | Django-allauth, email-based, enumeration prevention |
| Authorization | **PARTIALLY ALIGNED** | User filtering present but no systematic enforcement |
| Encryption in Transit | **ALIGNED** | HTTPS enforced, HSTS enabled |
| Encryption at Rest | **NOT ALIGNED** | Sensitive data stored in plaintext |
| Secrets Management | **PARTIALLY ALIGNED** | Environment variables used, but API key exposed |
| Input Validation | **ALIGNED** | Django ORM prevents SQL injection |
| Logging & Monitoring | **NOT ALIGNED** | No centralized logging or alerting |
| Rate Limiting | **NOT ALIGNED** | No rate limiting implemented |

### 6.2 Leadership Assertion

**Can leadership reasonably state they followed industry best practices?**

**Answer: PARTIALLY**

The application demonstrates reasonable security practices for an early-stage personal application. The core Django security features are properly utilized. However, the critical findings (C-1, C-2, C-3) represent gaps that would not withstand scrutiny in a formal security audit or regulatory examination.

### 6.3 Recommended Priority Actions

**Immediate (Phase 1 - 1 Week):**
1. Remove Bible API key from frontend context (C-2)
2. Implement server-side proxy for Bible API calls
3. Add explicit AI data sharing consent toggle in user preferences (C-3)
4. Implement django-axes or similar rate limiting (H-3)

**Short-Term (Phase 2 - 2-3 Weeks):**
1. Encrypt Google OAuth credentials in database (C-1)
2. Encrypt sensitive health data fields (H-2)
3. Implement object-level permission mixin (H-1)
4. Move admin to custom URL path (H-4)
5. Configure SameSite cookie attributes (M-1)

**Medium-Term (Phase 3 - 1 Month):**
1. Implement Content-Security-Policy headers (M-3)
2. Integrate Sentry or similar error monitoring (M-5)
3. Implement soft delete cleanup task (M-2)
4. Add file magic number validation (M-7)
5. Split dev/prod requirements (M-9)

**Long-Term (Phase 4 - 2+ Months):**
1. Add two-factor authentication for admin (L-2)
2. Implement automated dependency vulnerability scanning
3. Conduct penetration testing
4. Update Privacy Policy for AI data processing

---

## 7. APPENDICES

### Appendix A: Files Reviewed

- `config/settings.py`
- `config/urls.py`
- `apps/users/models.py`
- `apps/users/middleware.py`
- `apps/users/views.py`
- `apps/ai/services.py`
- `apps/ai/models.py`
- `apps/life/models.py`
- `apps/health/models.py`
- `apps/core/models.py`
- `apps/core/email_backends.py`
- `apps/admin_console/views.py`
- `Procfile`
- `requirements.txt`
- `.gitignore`
- `.env.example`

### Appendix B: Framework References

- **NIST Cybersecurity Framework 2.0**
- **NIST SP 800-53 Rev. 5** (Security and Privacy Controls)
- **OWASP Top 10:2021**
- **OWASP Application Security Verification Standard (ASVS) 4.0**

### Appendix C: Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-28 | Security Review (Claude) | Initial security review |

---

*This report is intended for internal use only and contains sensitive security information. Distribution should be limited to authorized personnel with a legitimate need to know.*
