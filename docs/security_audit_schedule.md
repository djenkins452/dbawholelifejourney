# Annual Security Audit Schedule

**Created:** 2026-01-12 (CISO Review)
**Last Updated:** 2026-01-12
**Owner:** Danny Jenkins (admin@wholelifejourney.com)

## Overview

This document outlines the annual security audit schedule and procedures for Whole Life Journey. Regular security audits are essential for maintaining compliance and protecting user data.

---

## Annual Audit Calendar

### Q1 (January - March)

| Week | Activity | Owner |
|------|----------|-------|
| Jan Week 1 | Annual key rotation (all encryption keys) | Engineering |
| Jan Week 2 | Dependency audit (npm audit, pip-audit) | Engineering |
| Jan Week 3 | SSL/TLS certificate review | DevOps |
| Feb Week 1 | Access control review (Railway, GitHub, Stripe) | Admin |
| Feb Week 2 | Privacy policy review for compliance | Legal/Admin |
| Mar Week 1 | OWASP Top 10 vulnerability scan | Engineering |
| Mar Week 2 | Penetration testing (external or internal) | Security |

### Q2 (April - June)

| Week | Activity | Owner |
|------|----------|-------|
| Apr Week 1 | Database backup verification test | DevOps |
| Apr Week 2 | Disaster recovery drill | DevOps |
| May Week 1 | Third-party service audit (Stripe, OpenAI, etc.) | Engineering |
| May Week 2 | API endpoint security review | Engineering |
| Jun Week 1 | Session management audit | Engineering |
| Jun Week 2 | User access pattern analysis | Security |

### Q3 (July - September)

| Week | Activity | Owner |
|------|----------|-------|
| Jul Week 1 | Mid-year dependency update | Engineering |
| Jul Week 2 | Security logging review | Security |
| Aug Week 1 | Incident response plan review | Admin |
| Aug Week 2 | Employee security training | Admin |
| Sep Week 1 | Code security review (SAST) | Engineering |
| Sep Week 2 | Infrastructure security scan | DevOps |

### Q4 (October - December)

| Week | Activity | Owner |
|------|----------|-------|
| Oct Week 1 | GDPR/CCPA compliance audit | Legal/Admin |
| Oct Week 2 | Data retention policy enforcement | Engineering |
| Nov Week 1 | Security documentation review | Engineering |
| Nov Week 2 | Emergency contact verification | Admin |
| Dec Week 1 | Year-end security report | Security |
| Dec Week 2 | Plan next year's security roadmap | All |

---

## Continuous Monitoring

These activities run continuously or on a regular schedule:

| Activity | Frequency | Tool/Method |
|----------|-----------|-------------|
| Error monitoring | Continuous | Railway logs |
| Security event logging | Continuous | wlj.security logger |
| Rate limiting monitoring | Daily | Admin console |
| Failed login tracking | Continuous | Security logger |
| reCAPTCHA score monitoring | Daily | Admin review |
| Soft-delete cleanup | Weekly (Sunday 3AM) | APScheduler job |
| Database backup | Daily | Railway automatic |

---

## Audit Checklists

### Dependency Audit Checklist

```bash
# Python dependencies
pip-audit
safety check

# JavaScript dependencies (if applicable)
npm audit

# Check for known vulnerabilities
pip install pip-audit
pip-audit --desc
```

- [ ] No critical vulnerabilities
- [ ] High vulnerabilities addressed within 7 days
- [ ] Medium vulnerabilities addressed within 30 days
- [ ] Document any accepted risks

### OWASP Top 10 Checklist

- [ ] A01: Broken Access Control - Review auth decorators
- [ ] A02: Cryptographic Failures - Review encryption implementation
- [ ] A03: Injection - Review all user inputs (SQL, XSS, Command)
- [ ] A04: Insecure Design - Review architecture
- [ ] A05: Security Misconfiguration - Review settings.py
- [ ] A06: Vulnerable Components - Run dependency audit
- [ ] A07: Authentication Failures - Review login/session handling
- [ ] A08: Data Integrity Failures - Review serialization
- [ ] A09: Logging Failures - Review security logging
- [ ] A10: SSRF - Review all external API calls

### Access Control Review

- [ ] Railway dashboard access (2FA enabled)
- [ ] GitHub repository access (2FA enabled)
- [ ] Stripe dashboard access (2FA enabled)
- [ ] Database access (restricted to Railway)
- [ ] Admin console access (staff flag required)
- [ ] Review inactive admin accounts

### Third-Party Service Audit

| Service | Last Reviewed | Status | Notes |
|---------|--------------|--------|-------|
| Railway | | | Hosting platform |
| Stripe | | | Payment processing |
| OpenAI | | | AI features |
| Cloudinary | | | Image storage |
| Resend | | | Email delivery |
| Google APIs | | | Calendar integration |
| Dexcom | | | CGM integration |
| FatSecret | | | Nutrition data |
| Bible API | | | Scripture lookups |

---

## Compliance Requirements

### GDPR Compliance

- [ ] Data processing register maintained
- [ ] Privacy policy current
- [ ] Data export feature functional
- [ ] Data deletion feature functional
- [ ] Consent mechanisms working
- [ ] Data retention policy enforced

### CCPA/CPRA Compliance

- [ ] Do not sell declaration accurate
- [ ] Rights request process functional
- [ ] 45-day response capability
- [ ] Opt-out mechanisms working

### COPPA Compliance

- [ ] Age verification functioning
- [ ] Under-13 blocking working
- [ ] No data collected from minors

---

## Incident Response

### Severity Levels

| Level | Description | Response Time |
|-------|-------------|---------------|
| Critical | Active data breach, system compromise | Immediate |
| High | Vulnerability with active exploit | 4 hours |
| Medium | Vulnerability without active exploit | 24 hours |
| Low | Minor security issue | 7 days |

### Response Steps

1. **Detect** - Identify the security event
2. **Contain** - Limit the impact
3. **Eradicate** - Remove the threat
4. **Recover** - Restore normal operations
5. **Document** - Record the incident
6. **Review** - Update procedures as needed

---

## Audit Documentation

All audit results should be documented:

1. Date of audit
2. Scope of audit
3. Findings (critical, high, medium, low)
4. Remediation actions
5. Verification of remediation
6. Sign-off

---

## Audit History

| Date | Type | Findings | Status |
|------|------|----------|--------|
| 2026-01-12 | CISO Review | Initial security hardening | Completed |

---

## Contact Information

**Security Team:**
- Admin: admin@wholelifejourney.com
- Privacy: privacy@wholelifejourney.com

**Emergency Security Issues:**
- Rotate affected keys immediately
- Document incident
- Review audit logs
