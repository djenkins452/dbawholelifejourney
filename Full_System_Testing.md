ROLE
You are Claude Code acting as a senior QA lead + security reviewer for a production launch of a Python/Django + JavaScript web app called “Whole Life Journey (WLJ)”. Your job is to run a full top-to-bottom system test, document evidence, and produce an executive-ready assessment with scoring, risks, and a clear Go/No-Go recommendation.

NON-NEGOTIABLES
- Do NOT change production data. All tests must run locally or in a dedicated staging environment.
- If you must change code to enable testing, keep changes minimal, clearly documented, and behind settings flags. No “random refactors.”
- Every claim in the final report must point to evidence: logs, screenshots, test outputs, coverage reports, or specific file paths/lines.
- If something can’t be tested (missing env, missing docs, missing seed data), call it out and provide a fix plan.

OBJECTIVE
1) Create an industry-standard test protocol for WLJ (Django + JS).
2) Execute the protocol end-to-end: unit → integration → system → end-to-end → security → performance → deployment checks.
3) Score the app using a transparent rubric.
4) Produce:
   A) Executive Summary (1–2 pages)
   B) Detailed Report (deep technical)
   C) Evidence Pack (saved outputs)
   D) Go-Live Checklist + Go/No-Go decision

WHAT “INDUSTRY PROTOCOL” MEANS HERE
Follow a practical, widely-used structure similar to:
- Test Strategy + Traceability (what we test and why)
- Test Pyramid (unit > integration > E2E)
- OWASP-style security checks (common web risks)
- Release readiness gates (coverage, critical bugs, security, performance, monitoring)

PHASE 0 — DISCOVERY (NO TESTS YET)
1) Read the repo structure and identify:
   - Django apps, settings modules, env handling, static build pipeline
   - Auth approach (session/auth, allauth, custom)
   - Key user flows (login, dashboard, major modules)
   - External integrations (OpenAI, Twilio, Dexcom, Cloudinary, email, payments if any)
2) Produce a short “System Map”:
   - Main modules/features
   - Data stores (Postgres/SQLite), caches, queues
   - External services and which features rely on them
3) Identify existing tests and tools already present:
   - pytest/unittest, coverage, playwright/cypress, linting, CI config

OUTPUT AFTER PHASE 0 (create these files)
- /docs/testing/TEST_STRATEGY.md
- /docs/testing/SYSTEM_MAP.md
- /docs/testing/TEST_INVENTORY.md (what exists today)
- /docs/testing/ENV_REQUIREMENTS_FOR_TESTING.md (what env vars are needed)

PHASE 1 — BUILD THE TEST PLAN (BEFORE RUNNING)
Create a test plan that includes:
1) Test levels:
   A) Unit tests (models, services, utils)
   B) Integration tests (DB + Django views/API + forms)
   C) System tests (full stack, staging-like)
   D) End-to-end UI tests (browser automation)
2) Critical user journeys (must-pass):
   - Account creation / login / logout / password reset
   - Navigation shell + each major tile/module loads
   - Create/read/update/delete for core records (journal entries, goals, etc. based on WLJ)
   - File uploads/media where applicable (Cloudinary/static)
   - Admin paths (if present)
3) Non-functional tests:
   - Security checks (top web risks)
   - Performance sanity (page load / slow endpoints / DB hotspots)
   - Reliability (error handling, timeouts, background tasks)
   - Accessibility quick check (basic keyboard + contrast check if feasible)
4) Test data plan:
   - Seed data approach (fixtures/factory)
   - Fake external services using mocks/sandbox modes
5) Entry/Exit Criteria (release gates):
   - Zero open Critical/High defects
   - Coverage threshold (set a realistic goal; start with 70% overall, with higher on critical modules)
   - Security: no known critical vuln in dependencies; no obvious OWASP critical issues
   - E2E: all critical journeys pass in a clean run
   - No unhandled 500s in major flows

OUTPUT AFTER PHASE 1
- /docs/testing/MASTER_TEST_PLAN.md
- /docs/testing/RELEASE_GATES.md
- /docs/testing/CRITICAL_USER_JOURNEYS.md
- /docs/testing/TEST_DATA_PLAN.md

PHASE 2 — SET UP THE TOOLING (MINIMAL, STANDARD)
Prefer these tools (only add what’s missing):
- Python/Django:
  - pytest + pytest-django (or Django TestCase if already used)
  - coverage.py
- JS/UI E2E:
  - Playwright (preferred) or Cypress (if already in use)
- Code quality:
  - ruff (lint) + black (format) if aligned with repo
- Security:
  - pip-audit (dependency vulnerability scan)
  - bandit (basic Python security scan)
- Performance sanity:
  - Django Debug Toolbar locally (optional)
  - simple endpoint timing + DB query counts in tests where possible

If adding tools, update:
- requirements-dev.txt (or equivalent)
- README or docs for how to run tests

PHASE 3 — EXECUTE TESTS (RUN + FIX ONLY WHAT’S REQUIRED TO TEST)
Run tests in this order and capture outputs.

A) STATIC CHECKS (fast fail)
1) Lint/format checks
2) Django system checks
3) Migrations check (no missing migrations)

B) UNIT + INTEGRATION
1) Run pytest (or manage.py test)
2) Generate coverage report (HTML + terminal summary)
3) Add missing tests for:
   - High-risk logic (auth, permissions, payments, integrations, data transforms)
   - Any areas with repeated bugs from history (look at commits/issues if available)

C) SYSTEM / SMOKE TEST
1) Start the app in a staging-like config
2) Run a smoke checklist manually once (record screenshots)
3) Ensure:
   - no console errors
   - no server 500s
   - static assets load correctly
   - login session works across pages

D) END-TO-END (E2E)
1) Write Playwright tests for each critical journey
2) Use stable selectors (data-testid). If missing, add minimal data-testid attributes.
3) Run E2E headless + one headed run for screenshots/videos.

E) SECURITY PASS (PRACTICAL, NOT “THEORETICAL”)
1) pip-audit results
2) bandit results
3) Django security settings review:
   - DEBUG off in staging/prod
   - SECURE_SSL_REDIRECT, HSTS (as appropriate)
   - CSRF, session cookie flags (Secure/HttpOnly/SameSite)
   - Allowed hosts, CORS/CSRF origins sanity
4) OWASP-style spot checks:
   - Auth: brute force protections / rate limiting if present
   - Broken access control: try accessing another user’s objects
   - Injection: forms/search endpoints (basic tests)
   - File upload validation
   - Secret leakage (keys in repo, verbose logs)

F) PERFORMANCE SANITY
1) Identify slowest endpoints with quick timing (top 5)
2) Check DB query explosion in common pages
3) Note obvious wins (indexes, select_related/prefetch_related) but do not refactor broadly.

EVIDENCE PACK (SAVE EVERYTHING)
Create:
- /docs/testing/evidence/
  - test-runs/
  - coverage/
  - e2e-results/ (screenshots/videos)
  - security-scans/
  - smoke-test-screenshots/
  - logs/

PHASE 4 — DEFECT MANAGEMENT (TRACK LIKE A REAL QA RUN)
Create a defects log with:
- ID, Title, Severity (Critical/High/Medium/Low)
- Steps to reproduce
- Expected vs Actual
- Evidence link (screenshot/log)
- Suspected root cause (file/module)
- Fix status
- Retest status

OUTPUT
- /docs/testing/DEFECTS.md
- /docs/testing/DEFECTS.csv (optional)

PHASE 5 — SCORING / RANKING (TRANSPARENT RUBRIC)
Create a score out of 100 with weighted categories:

1) Functional Correctness — 30
- Do critical journeys pass reliably?
- Any data integrity issues?

2) Reliability & Error Handling — 15
- Any unhandled 500s?
- Graceful failures for external services?

3) Security Posture — 20
- Dependency vulnerabilities
- Basic OWASP checks
- Settings hygiene

4) Performance & Scalability Readiness — 10
- Any obvious slow paths
- DB query health in main pages

5) Maintainability / Test Quality — 15
- Coverage %, meaningful tests, flake rate
- Clear fixtures/factories and stable selectors

6) Release Readiness / Operability — 10
- Logging, monitoring hooks, env clarity
- Deployment repeatability, migration safety

SCORING RULES
- Any open Critical defect caps total score at 69 (No-Go range).
- Any High security finding caps score at 79 until fixed.
- Provide both:
  - Total score
  - Sub-scores with justification + evidence references

PHASE 6 — FINAL REPORTS (EXECUTIVE + DETAILED)
Deliver these files:

1) /docs/testing/WLJ_TEST_ASSESSMENT_EXEC_SUMMARY.md
Must include:
- Overall Score + Go/No-Go recommendation
- “What’s working well” (3–7 bullets)
- Top risks (ranked)
- Must-fix items before launch (short list)
- Nice-to-have items after launch
- Estimated effort bands (S/M/L) for must-fix items (no fake timelines)

2) /docs/testing/WLJ_TEST_ASSESSMENT_DETAILED_REPORT.md
Must include:
- Test strategy recap
- Environments used
- Tools used + versions
- Test results by level (unit/integration/system/e2e)
- Coverage numbers + where gaps remain
- Security scan results + remediation guidance
- Performance notes + hotspot list
- Defects summary (by severity)
- Release gate checklist pass/fail

3) /docs/testing/GO_LIVE_CHECKLIST.md
Must include:
- Pre-launch checklist (env, secrets, DEBUG off, migrations, static, backups)
- Launch-day checklist (monitoring, logs, rollback plan)
- Post-launch checklist (first 24–72h checks)

4) /docs/testing/TRACEABILITY_MATRIX.md
A simple mapping:
- Critical Journey → Test(s) covering it → Evidence path

FINAL STEP — PRESENT THE RESULT IN CHAT
After generating all artifacts, print:
- The final score
- Go/No-Go
- The top 5 must-fix issues (with file references)
- Exact commands to rerun the full test suite in one shot

COMMANDS (YOU MUST INCLUDE REAL ONES)
You must provide a “one command per layer” list, such as:
- Lint
- Unit/Integration
- Coverage
- E2E
- Security scans
- Full “all-in” script (Makefile or shell) if appropriate

IMPORTANT CONTEXT ABOUT WLJ
- WLJ is a Django web app with multiple modules (Journal/Faith/Health/Life/etc.) and external integrations.
- Treat external services as mocked/sandboxed wherever possible.
- Focus on “last mile before go-live”: stability, security, release gates, and confidence.

BEGIN NOW
Start with Phase 0. Create the docs files first, then proceed through the phases in order. Do not skip scoring or the executive summary.
