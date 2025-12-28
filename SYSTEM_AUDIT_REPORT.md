# SYSTEM AUDIT REPORT

**Project:** Whole Life Journey - Django 5.x Personal Wellness/Journaling Application
**Audit Date:** December 28, 2025
**Auditor:** Claude Code (Automated System Analysis)
**Version:** 1.0.0

---

## EXECUTIVE SUMMARY

### Overall System Health Score: 7.2/10

The Whole Life Journey application is a **well-structured, production-ready Django 5.x application** with solid foundational practices. The codebase demonstrates professional architecture with 11 feature apps, comprehensive test coverage (857 tests), and proper separation of concerns. However, there are **critical security issues** that require immediate attention, along with several areas needing improvement for long-term maintainability.

### Risk Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 2 | Open redirect vulnerability, hardcoded API key |
| **HIGH** | 5 | Bare except clauses, missing error logging, XSS risk, file validation |
| **MEDIUM** | 12 | Hardcoded values, missing input validation, code duplication |
| **LOW** | 15 | Documentation gaps, large files, minor best practice violations |

---

## TOP RISKS (RANKED BY SEVERITY)

### 1. CRITICAL: Open Redirect Vulnerability
**Location:** `apps/life/views.py:356-359`
**Issue:** User-controlled `next` parameter used directly in `redirect()` without validation.
```python
next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
if next_url:
    return redirect(next_url)  # DANGER: No validation
```
**Impact:** Attackers can redirect authenticated users to malicious sites for phishing.
**Fix:** Validate `next_url` using `django.utils.http.url_has_allowed_host_and_scheme()`.

### 2. CRITICAL: Hardcoded API Key in Source Code
**Location:** `config/settings.py:396`
**Issue:** Bible API key hardcoded as default fallback value.
```python
BIBLE_API_KEY = os.environ.get('BIBLE_API_KEY', 'mwa_ZKeSL5nB0VZ_tcRxt')
```
**Impact:** API key exposed in version control; can be used to exhaust API quota.
**Fix:** Remove default value; require explicit environment variable configuration.

### 3. HIGH: Bare Exception Handling (10+ Locations)
**Locations:**
- `apps/users/views.py:125, 136, 296`
- `apps/ai/dashboard_ai.py:184, 203, 213, 235, 269`
- `apps/admin_console/views.py:429, 433`
- `run_tests.py:47, 57`

**Issue:** Bare `except:` clauses catch ALL exceptions including `SystemExit` and `KeyboardInterrupt`, hiding actual errors.
```python
try:
    from apps.life.models import GoogleCalendarCredential
    credential = self.request.user.google_calendar_credential
except:  # BAD: Catches everything
    context['google_calendar_connected'] = False
```
**Fix:** Replace with specific exception types (`except (ImportError, ObjectDoesNotExist) as e:`) and add logging.

### 4. HIGH: No Persistent Error Logging
**Issue:** Logging only outputs to console; no file/database logging for production.
**Impact:** Railway logs are ephemeral; past errors cannot be reviewed; no error patterns visible.
**Fix:** Add database-backed error logging model and admin visibility.

### 5. HIGH: Missing Custom Error Pages
**Issue:** No `handler404`, `handler500` configured; no custom error templates.
**Impact:** Users see raw Django error pages or generic browser errors.
**Fix:** Create `templates/404.html`, `templates/500.html` and configure handlers in `urls.py`.

### 6. HIGH: XSS Risk in HTMX Response
**Location:** `apps/journal/views.py:402-410`
**Issue:** Raw HTML returned without escaping in `RandomPromptView`:
```python
return HttpResponse(f"""
    <p class="prompt-text">{prompt.text}</p>
    {f'<p class="prompt-scripture">{prompt.scripture_reference}...'}
```
**Fix:** Use `django.utils.html.escape()` on all dynamic content.

### 7. HIGH: Unsafe Client IP Extraction
**Location:** `apps/users/views.py:206-211`
**Issue:** Trusting `HTTP_X_FORWARDED_FOR` header without validating trusted proxies.
**Impact:** Attackers can spoof IP addresses for audit logs.
**Fix:** Only trust X-Forwarded-For from configured proxies; use django-ipware.

---

## AREAS DONE WELL

### 1. Security Foundations
- **CSRF protection** properly enabled with middleware
- **HTTPS enforcement** in production with HSTS preload
- **Session cookies** marked secure
- **Password validation** with 4 validators
- **XSS protection headers** enabled

### 2. Authentication & Authorization
- **Custom User model** with email-based authentication
- **LoginRequiredMixin** used consistently across all views
- **User-scoped queries** - all database queries filter by `user=request.user`
- **Module-level access control** (FaithRequiredMixin, LifeAccessMixin)
- **Terms acceptance enforcement** via middleware with audit trail

### 3. Architecture & Organization
- **11 well-organized Django apps** following separation of concerns
- **Database-driven configuration** for AI prompts, coaching styles, themes
- **Abstract base models** (TimeStampedModel, SoftDeleteModel, UserOwnedModel)
- **Soft delete pattern** implemented correctly with 30-day retention
- **Service layer** for complex operations (AIService, HelpChatService)

### 4. Testing
- **857 tests** across all apps
- **Comprehensive test mixins** for user creation with onboarding
- **Factory pattern** for test object creation
- **Mock patterns** for external services (OpenAI API)
- **Test run tracking** in admin console

### 5. Documentation
- **Excellent module/class docstrings** throughout codebase
- **Comprehensive CLAUDE.md** with project context
- **Help text** on model fields for admin/forms
- **Management command help** properly defined
- **Clean code** with no stale TODO/FIXME markers

### 6. Database Design
- **Proper foreign key relationships** with appropriate CASCADE/SET_NULL
- **Soft delete** prevents accidental data loss
- **User ownership** enforced at model level
- **Timezone handling** with user preferences

---

## AREAS NEEDING IMMEDIATE ATTENTION

### Security (Must Fix Before Next Deploy)

| Issue | Location | Effort | Priority |
|-------|----------|--------|----------|
| Open redirect vulnerability | life/views.py:356 | 1 hour | CRITICAL |
| Hardcoded API key | config/settings.py:396 | 30 min | CRITICAL |
| Bare except clauses (10+) | Multiple files | 2 hours | HIGH |
| XSS in HTMX response | journal/views.py:402 | 1 hour | HIGH |
| Unsafe IP extraction | users/views.py:206 | 1 hour | HIGH |

### Error Handling (Should Fix Soon)

| Issue | Impact | Effort |
|-------|--------|--------|
| No custom error pages | Poor user experience on errors | 2 hours |
| Console-only logging | Cannot review past errors | 3 hours |
| No error dashboard | Admin has no visibility | 4 hours |
| No health check endpoint | Cannot monitor system status | 2 hours |

### Input Validation (Should Fix)

| Issue | Location | Risk |
|-------|----------|------|
| Timezone not validated | users/views.py:367 | Invalid data in DB |
| Year/month not validated | life/views.py:376 | Exception disclosure |
| File upload no type check | admin_console/views.py:98 | Malicious file upload |

---

## AREAS TO IMPROVE LATER

### Code Quality (Low Priority)

1. **Split large files:**
   - `apps/life/views.py` (1496 lines) → Split into domain-specific view files
   - `apps/life/models.py` (1069 lines) → Split by domain
   - `apps/health/views.py` (1212 lines) → Consider splitting

2. **Reduce code duplication:**
   - Create `UserOwnedListView` base class (eliminates 76 repeated filter patterns)
   - Consolidate timezone logic into `apps/core/utils.py`
   - Create reusable form widget styling utilities

3. **Clean up artifacts:**
   - Delete 29 backup files (.bak, .bak2, settings_old.py)
   - Remove orphan `users/` directory at root
   - Delete review artifact files (app_diffs.txt, phase2_diff.txt, etc.)

### Configuration (Medium Priority)

1. **Externalize hardcoded values:**
   - Create `config/constants.py` for magic numbers (days=30, [:5] limits)
   - Move CSRF_TRUSTED_ORIGINS to environment variable
   - Centralize achievement thresholds and pagination limits

2. **User-specific data in migrations:**
   - `apps/faith/migrations/0003_migrate_existing_verses_to_danny.py` - Hardcoded email
   - `apps/journal/migrations/0002_import_chatgpt_journal.py` - Hardcoded email

### Documentation (Low Priority)

1. **Add docstrings to View methods** (get_context_data, post, etc.)
2. **Add file path comments** to top of files (optional convention)
3. **Create help system documentation** (docs/help/ structure referenced but not implemented)

---

## CONCRETE RECOMMENDATIONS

### Immediate Actions (Before Next Deploy)

```python
# 1. Fix open redirect - apps/life/views.py
from django.utils.http import url_has_allowed_host_and_scheme

def post(self, request, pk):
    # ... existing code ...
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('life:task_list')

# 2. Fix hardcoded API key - config/settings.py
BIBLE_API_KEY = os.environ.get('BIBLE_API_KEY', '')
if not BIBLE_API_KEY:
    import logging
    logging.warning("BIBLE_API_KEY not set - Scripture lookups will be disabled")

# 3. Fix bare except - Replace ALL instances with:
except (ImportError, ObjectDoesNotExist) as e:
    logger.warning(f"Failed to load Google Calendar: {e}")
    context['google_calendar_connected'] = False
```

### Short-Term Improvements (Within 1 Week)

1. **Create SystemError model for error logging:**
```python
# apps/core/models.py
class SystemError(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=500)
    exception_type = models.CharField(max_length=200)
    message = models.TextField()
    traceback = models.TextField()
    is_resolved = models.BooleanField(default=False)
```

2. **Add custom error handlers:**
```python
# config/urls.py
handler404 = 'apps.core.views.custom_404'
handler500 = 'apps.core.views.custom_500'
```

3. **Create health check endpoint:**
```python
# apps/core/views.py
def health_check(request):
    checks = {
        'database': check_database(),
        'cache': check_cache(),
        'ai_api': check_openai_api(),
    }
    return JsonResponse({'status': 'healthy' if all(checks.values()) else 'degraded', 'checks': checks})
```

### Long-Term Improvements (Within 1 Month)

1. **Integrate error tracking service** (Sentry recommended)
2. **Add rate limiting** on sensitive endpoints (django-ratelimit)
3. **Split large files** into domain-specific modules
4. **Create UserOwnedListView** base class
5. **Implement comprehensive audit logging**

---

## RELEASE CHECKLIST

Use this before each production deployment:

### Security
- [ ] No hardcoded secrets in code (check `grep -r "api_key\|secret\|password"`)
- [ ] All user input validated
- [ ] No bare except clauses
- [ ] HTTPS enforced in production
- [ ] CSRF tokens in all forms
- [ ] No open redirect vulnerabilities

### Testing
- [ ] All 857+ tests pass
- [ ] No new test failures
- [ ] Security-relevant code has test coverage

### Error Handling
- [ ] Custom error pages exist (404, 500)
- [ ] Logging configured for production
- [ ] No debug information exposed

### Configuration
- [ ] All environment variables set
- [ ] Database migrations applied
- [ ] Static files collected

---

## AUTOMATED CHECKS SUGGESTED

Add these to CI/CD pipeline:

```yaml
# .github/workflows/audit.yml
- name: Security Scan
  run: |
    pip install bandit safety
    bandit -r apps/ -ll
    safety check

- name: Code Quality
  run: |
    pip install flake8 black isort
    flake8 apps/
    black --check apps/
    isort --check-only apps/

- name: Test Suite
  run: |
    python manage.py test --parallel

- name: Check for Secrets
  run: |
    pip install detect-secrets
    detect-secrets scan --all-files
```

---

## CONCLUSION

The Whole Life Journey application has a **solid foundation** with proper Django architecture, comprehensive testing, and good separation of concerns. The main areas requiring attention are:

1. **Critical security fixes** (open redirect, hardcoded API key)
2. **Error handling improvements** (bare except clauses, logging)
3. **Admin visibility** for system health and errors
4. **Code cleanup** (large files, duplicate patterns, artifact files)

**Estimated total remediation effort:**
- Critical fixes: 4-6 hours
- High priority fixes: 8-10 hours
- Medium priority improvements: 16-20 hours
- Low priority cleanup: 8-12 hours

The application is **production-ready** with the critical security fixes applied. The remaining improvements can be addressed incrementally over time.

---

*Report generated by Claude Code System Audit*
*Last updated: 2025-12-28*
