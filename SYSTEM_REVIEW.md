# SYSTEM REVIEW - Repeatable Audit Process

**Purpose:** This document defines the repeatable process for conducting a full system audit of the Whole Life Journey Django application. Use this for periodic reviews, before major releases, or after significant changes.

---

## AUDIT MASTER PROMPT

When starting a system review session, use the following prompt:

```
ROLE & RESPONSIBILITY

Act as a senior software architect, principal engineer, and QA lead with deep experience reviewing production-grade web applications.

You are conducting a FULL SYSTEM AUDIT of this codebase.

Your job is NOT to add new features.
Your job IS to evaluate quality, safety, structure, and long-term reliability.

-------------------------------------------------
PRIMARY OBJECTIVES
-------------------------------------------------

1. Perform a COMPLETE SYSTEM CHECK of the entire project:
   - Folder structure
   - App/module separation
   - Settings and configuration
   - Data flow
   - Error handling
   - Security posture
   - Maintainability
   - Scalability

2. Verify PROFESSIONAL CODING PRACTICES:
   - Clean, readable code
   - Consistent naming conventions
   - Clear separation of concerns
   - No duplicated logic
   - No "quick hacks" or fragile shortcuts
   - Good comments, with the name and path of the file at the top of every file

3. HARD-CODING REVIEW (CRITICAL):
   - Identify ANY hardcoded values that are likely to change over time
   - Recommend: Config files, Environment variables, Database-driven settings, Feature toggles

4. USER SAFETY & RESILIENCE:
   - The system must NEVER hard-crash due to unexpected user behavior
   - Validate: Defensive coding, Graceful fallbacks, Clear user-facing error messages

5. ERROR HANDLING & LOGGING (NON-NEGOTIABLE):
   - Confirm there is a global error-handling strategy
   - Ensure: No raw stack traces shown to users, Friendly error pages, Automatic error logging

6. ADMIN VISIBILITY:
   - Errors should surface in the admin area
   - Each error must be: Identifiable, Searchable, Actionable, Markable as resolved

7. UPDATE THIS DOCUMENT:
   - Add any new findings or patterns discovered during the review
```

---

## AUDIT CHECKLIST

### Phase 1: Codebase Structure (15 minutes)

- [ ] **Review folder structure**
  - All apps in `apps/` directory
  - Config in `config/`
  - Templates in `templates/`
  - Static files in `static/`

- [ ] **Check for artifact files**
  - `.bak` files to delete
  - `_old` files to delete
  - Review/diff artifact files to delete

- [ ] **Verify app organization**
  - Each app has: models.py, views.py, urls.py, tests/
  - No duplicate test files (tests.py AND tests/)

### Phase 2: Settings & Configuration (20 minutes)

- [ ] **Security settings**
  - DEBUG = False default
  - SECRET_KEY from environment
  - ALLOWED_HOSTS configured
  - HTTPS/HSTS in production
  - CSRF_TRUSTED_ORIGINS set

- [ ] **Database configuration**
  - DATABASE_URL for production
  - SQLite fallback for development

- [ ] **Logging configuration**
  - Console handler configured
  - App-level loggers defined
  - Production file/database logging (if implemented)

- [ ] **Third-party settings**
  - django-allauth configured
  - Cloudinary configured (if using)
  - OpenAI API key from environment

### Phase 3: Security Audit (30 minutes)

- [ ] **Authentication**
  - LoginRequiredMixin on all protected views
  - User-scoped queries (filter by user=request.user)
  - No username enumeration

- [ ] **Authorization**
  - Module-level access checks (FaithRequiredMixin, etc.)
  - Object-level permissions where needed

- [ ] **OWASP Top 10 Check**
  - No SQL injection (no raw queries)
  - No XSS (no |safe without justification)
  - CSRF protection enabled
  - No command injection
  - No path traversal

- [ ] **Input validation**
  - Form validation on all forms
  - Parameter validation in views
  - File upload validation

### Phase 4: Error Handling (20 minutes)

- [ ] **Exception handling**
  - No bare `except:` clauses
  - Specific exception types caught
  - Logging in exception handlers

- [ ] **Error pages**
  - Custom 404.html exists
  - Custom 500.html exists
  - Error handlers configured in urls.py

- [ ] **User-facing errors**
  - Friendly error messages
  - No stack traces shown to users
  - Recovery options provided

### Phase 5: Hardcoded Values (20 minutes)

- [ ] **API keys and secrets**
  - All from environment variables
  - No defaults that expose real keys

- [ ] **URLs and endpoints**
  - External APIs configurable
  - Domain names from settings

- [ ] **Magic numbers**
  - Time intervals (days=30, etc.) in constants
  - Thresholds and limits in settings
  - Pagination limits in constants

- [ ] **User-specific data**
  - No hardcoded emails in migrations
  - No hardcoded user IDs

### Phase 6: Code Quality (25 minutes)

- [ ] **File sizes**
  - No files over 1000 lines (split if needed)
  - Views and models properly sized

- [ ] **Code duplication**
  - Common patterns extracted to mixins
  - Utility functions in utils.py
  - No copy-paste code across apps

- [ ] **Documentation**
  - Module docstrings present
  - Class docstrings present
  - Complex methods documented
  - No stale TODO/FIXME markers

- [ ] **Naming conventions**
  - Clear, descriptive names
  - Consistent across codebase
  - Django conventions followed

### Phase 7: Admin Visibility (15 minutes)

- [ ] **Error logging model**
  - SystemError or similar model exists
  - Stores: timestamp, user, path, exception, traceback

- [ ] **Admin dashboard**
  - Error count visible
  - Recent errors list
  - Health status indicator

- [ ] **Health check endpoint**
  - /health/status/ or similar
  - Checks database, cache, APIs

### Phase 8: Testing (10 minutes)

- [ ] **Test coverage**
  - All apps have tests
  - Critical paths covered
  - Security-relevant code tested

- [ ] **Test patterns**
  - User setup includes onboarding completion
  - External services mocked
  - Clean test isolation

---

## KNOWN ISSUES TRACKING

### Issues Found in Previous Audits

| Issue | Status | Date Found | Date Fixed |
|-------|--------|------------|------------|
| Open redirect in TaskToggleView + 2 others | FIXED | 2025-12-28 | 2025-12-28 |
| Hardcoded Bible API key | FIXED | 2025-12-28 | 2025-12-28 |
| Bare except clauses (10+) | OPEN | 2025-12-28 | - |
| No custom error pages | OPEN | 2025-12-28 | - |
| Console-only logging | OPEN | 2025-12-28 | - |
| XSS risk in RandomPromptView | OPEN | 2025-12-28 | - |
| 29 backup files to clean | OPEN | 2025-12-28 | - |

### Patterns to Watch For

1. **New bare except clauses** - Always use specific exception types
2. **User input in redirects** - Always validate with `url_has_allowed_host_and_scheme()`
3. **|safe filter usage** - Must be justified and documented
4. **New hardcoded values** - Check for magic numbers, emails, URLs
5. **Large file growth** - Split files approaching 500+ lines

---

## METRICS TO TRACK

### Code Health Metrics

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| Test count | 857 | 900+ | Add tests for new features |
| Test pass rate | 100% | 100% | Never deploy with failures |
| Bare except count | 10+ | 0 | Must eliminate |
| Files > 500 lines | 6 | 3 | Split large files |
| Backup files | 29 | 0 | Clean regularly |

### Security Metrics

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| Open vulnerabilities | 2 CRIT, 5 HIGH | 0 | Fix before deploy |
| Auth coverage | 100% | 100% | All views protected |
| Input validation | ~80% | 100% | Validate all inputs |

---

## REMEDIATION PRIORITIES

### Priority 1: Security (Fix Immediately)
1. Fix open redirect vulnerability
2. Remove hardcoded API key
3. Replace bare except clauses
4. Add XSS escaping to HTMX responses
5. Fix unsafe IP extraction

### Priority 2: Error Handling (Fix This Week)
1. Create custom error pages
2. Add database error logging
3. Create health check endpoint
4. Add error dashboard widget

### Priority 3: Code Quality (Fix This Month)
1. Split large view files
2. Clean up backup files
3. Consolidate duplicated patterns
4. Externalize hardcoded values

### Priority 4: Documentation (Ongoing)
1. Add view method docstrings
2. Document complex business logic
3. Create help system content

---

## AUTOMATED AUDIT COMMANDS

Run these commands to check for common issues:

```bash
# Check for bare except clauses
grep -rn "except:" apps/ --include="*.py" | grep -v "except Exception"

# Check for |safe filter usage
grep -rn "|safe" templates/

# Check for hardcoded emails
grep -rn "@.*\.com" apps/ --include="*.py" | grep -v test

# Check for TODO/FIXME
grep -rn "TODO\|FIXME\|HACK\|XXX" apps/ --include="*.py"

# Count lines per file
find apps/ -name "*.py" -exec wc -l {} + | sort -n | tail -20

# Find backup files
find . -name "*.bak*" -o -name "*_old.py" -o -name "*.py.new*"

# Run security check
pip install bandit && bandit -r apps/ -ll

# Run tests
python manage.py test --parallel
```

---

## POST-AUDIT ACTIONS

After completing an audit:

1. **Update this document** with new findings
2. **Update SYSTEM_AUDIT_REPORT.md** with current status
3. **Create tickets/issues** for items needing fix
4. **Prioritize** based on security impact
5. **Schedule** remediation work
6. **Track** resolution dates

---

## AUDIT FREQUENCY

- **Full audit**: Quarterly or before major releases
- **Security scan**: Before each production deploy
- **Quick check**: After each feature branch merge
- **Automated checks**: On every CI/CD run

---

## REVISION HISTORY

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-28 | 1.0.0 | Initial audit process created |

---

*This document should be updated after each audit with new findings and resolved issues.*
