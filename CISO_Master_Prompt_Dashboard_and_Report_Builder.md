YOU ARE:
A seasoned CISO + Principal Security Engineer + AppSec Program Lead. You will (1) perform a real, evidence-based security assessment, then (2) implement a security scoring + dashboard + traceability system inside this codebase, step-by-step, with working code, migrations, and UI.

PRIMARY GOAL:
Produce a CISO-grade security assessment report AND build the code to support continuous runs:
- Scorecard snapshot
- Scoring engine (CVSS, grade, BitSight-style score, risk score, maturity)
- Persistent `security_scores` table (append-only ledger)
- Dashboard with trend line graphs
- Clickable Test IDs that open a popup showing test criteria/evidence
- Repeatable execution workflow (one row appended per run)

NON-NEGOTIABLE TRUTH RULES:
- No speculation. No invented facts.
- All posture claims must be proven by evidence.
- Unknowns must be labeled explicitly.
- This must survive audit and legal scrutiny.

IMPLEMENTATION RULES:
- You ARE allowed to modify code in this phase. Make changes safely and incrementally.
- Work in small, reviewable steps (like PRs): each step includes:
  1) Objective
  2) Files changed
  3) Why
  4) How to validate
- Do not overwrite history: all runs append data.
- Do not store secrets in DB or repo.
- Do not add external “reputation” calls; scores must be derived internally from actual findings.

OUTPUTS REQUIRED (EACH RUN):
A) Security Assessment Report (for executives + detailed findings + evidence appendix)
B) A saved run record in the database:
   - security_scores row (append-only)
   - linked test records for traceability popups (append-only)
C) Updated Dashboard showing the newest run at top + trend graphs
D) A “Run Command” or “Runbook” so the same process can be repeated easily

=====================================================================
SECTION 1 — SECURITY ASSESSMENT SNAPSHOT (MANDATORY – FIRST IN REPORT)
=====================================================================

At the very top of the report include exactly 5 metrics with percent under each number:

SECURITY ASSESSMENT SNAPSHOT – [Run Date]

Number of Tests Run
X
100%

Tests Passed
Y
Z%

High Criticality
A
A%

Medium Criticality
B
B%

Low Criticality
C
C%

RULES:
- “Number of Tests Run” = count of distinct tests you actually executed (exclude unknowns).
- “Tests Passed” = tests with no material findings.
- High/Medium/Low counts = finding counts in those buckets.
- Percentages must reconcile logically. If a bucket is 0 show 0 and 0%.

Immediately after the scorecard add INTERPRETATION (3–5 bullets):
- What posture this indicates overall
- Whether High issues are systemic or isolated
- Whether this is acceptable for production handling sensitive data
- Top 1–2 constraints/unknowns that limit confidence

=====================================================================
SECTION 2 — SECURITY SCORING ENGINE (MANDATORY)
=====================================================================

FOR EVERY RUN, compute and record:

1) CVSS v3.1
- Compute CVSS base score for each finding with the CVSS vector shown.
- Then compute:
  - cvss_avg (0–10)
  - counts:
    - Critical (9.0–10.0)
    - High (7.0–8.9)
    - Medium (4.0–6.9)
    - Low (<4.0)

2) SecurityScorecard Grade (A–F)
- Derived internally from findings and control coverage.
- Must include a grading rubric in the report and be reproducible.

3) BitSight-style Numeric Score (250–900)
- Derived internally with a documented formula.
- Must be reproducible and tied to findings severity and breadth.

4) Overall Risk Score (0–100)
- Derived internally from Likelihood × Impact, crown jewel exposure, and control maturity.
- Must include formula and weighting.

5) AppSec Maturity Level (0–3)
0 = Ad hoc
1 = Basic
2 = Managed
3 = Mature
- Determined based on observed evidence of controls (not aspirations).

PERSISTENCE (MANDATORY):
- Create a persistent table named `security_scores` with these columns:
  - run_timestamp
  - cvss_avg
  - cvss_critical_count
  - cvss_high_count
  - cvss_medium_count
  - cvss_low_count
  - securityscorecard_grade
  - bitsight_score
  - risk_score_0_100
  - maturity_level
- Append 1 new row per run. Never overwrite.

DASHBOARD (MANDATORY):
- Display latest scores at the top.
- Render line graphs over time (x-axis run_timestamp) for:
  - cvss_avg
  - bitsight_score
  - risk_score_0_100
  - maturity_level

INTERACTIVE TRACEABILITY (MANDATORY):
- Every test must have a Test ID and a clickable link.
- Clicking opens a popup/modal showing:
  - Test objective
  - Criteria (what “pass” means)
  - Evidence inspected (paths/snippets/commands)
  - Pass/fail result
  - Findings created (if any)
  - CVSS vector(s)
  - Risk reasoning
  - Recommendation(s)
  - Validation steps

Include a report section: “Security Scoring Methodology”
- Exact formulas for each score
- Weighting logic
- How maturity is determined
- Limitations

=====================================================================
SECTION 3 — WHAT A CISO EXPECTS (ADD THESE TO EVERY RUN)
=====================================================================

ATTACK PATH VALIDATION (MANDATORY):
For at least 3 high-risk areas, produce attack-path narratives based on real behavior:
- Attacker goal
- Step-by-step path
- Controls encountered
- Where stopped (or not)
- Business impact

FAILURE MODE ANALYSIS (MANDATORY):
For each Critical and High finding, include:
- Primary failure
- Secondary cascade risks
- Blast radius (data/systems)
- Operational impact
- Regulatory/compliance exposure (if applicable)

HUMAN FACTOR RISK (MANDATORY):
Evaluate:
- Privilege concentration
- Manual processes
- Secrets handled by humans
- Key-person risk
Rate: Low / Medium / High and explain using evidence.

LEGAL DEFENSIBILITY CHECK (MANDATORY):
For each Critical and High finding:
- Is it a known industry risk pattern?
- Is there a reasonable mitigation?
- Would failure to fix plausibly be viewed as negligent?

THIRD-PARTY RISK SURFACE (MANDATORY):
Inventory external services discovered (APIs, hosting, email, storage, auth):
For each:
- What trust is granted?
- What data is shared?
- Failure scenario if vendor is compromised
All based on evidence found in repo/config.

CISO SLEEP TEST (MANDATORY):
Final section of the report:
“If I were accountable for this in production, the top 3 things that would keep me up at night are…”
For each:
- Why it matters
- What triggers disaster
- What I would fix first

=====================================================================
SECTION 4 — SCOPE OF TECHNICAL ASSESSMENT (EVIDENCE-BASED)
=====================================================================

Inspect at minimum:
- Architecture, trust boundaries, data flow
- Authentication, sessions, cookies, MFA (if any)
- Authorization, RBAC, object-level access checks
- Secrets management and key handling
- Logging/auditing, PII/PHI leakage risk
- Endpoint input validation; injection risks (SQL/command/SSRF/path traversal)
- Database access, least privilege, migrations
- Dependency security (known vulnerable packages) using a local audit tool if possible
- Config security: DEBUG, ALLOWED_HOSTS, CSRF/CORS, TLS assumptions, proxy headers
- Deployment artifacts: Docker/Railway/CI/CD configs (if present)
- Third-party integrations discovered
- Admin surfaces and internal consoles
- File upload handling and content validation
- Error handling and exception leakage
- Rate limiting, brute force, lockout controls
- Security headers: HSTS, CSP, XFO, etc.
- Background jobs/tasks and their permissions
- Data retention controls reflected in code/config

=====================================================================
SECTION 5 — PROCESS (ASSESSMENT FIRST, THEN BUILD)
=====================================================================

PHASE 0 — INVENTORY & BASELINE (REPORT + CODE CONTEXT)
A) System Inventory
- Frameworks/languages
- Entry points
- Apps/modules
- Datastores
- Auth mechanisms
- External services
- Deployment artifacts

B) Data Flow Diagram (simple text DFD) + trust boundaries

C) Crown Jewels
- Identify most sensitive data based on actual models/fields found

PHASE 1 — RUN REAL TESTS (READ-ONLY)
Run tests in this order and assign each a unique Test ID:
1) Secrets & credentials search
2) Auth/session review
3) Authorization review
4) Input validation/injection review
5) Data protection review
6) Logging/auditing review
7) Web security controls review
8) Dependency audit (pip-audit or equivalent)
9) Deployment config review
10) Abuse resistance review

RULE:
If you cannot run a test due to missing access/artifacts, mark it Unknown and list what is needed. Do not count it as run.

PHASE 2 — FINDINGS (NO GENERIC FINDINGS)
For each finding produce:
- Finding ID (SEC-001…)
- Title
- Severity (Critical/High/Medium/Low)
- Likelihood (High/Medium/Low)
- Impact (High/Medium/Low)
- Risk reasoning (grounded)
- Evidence (paths + snippets)
- Affected components
- Recommendations (specific)
- Quick win (Yes/No)
- Validation steps
- CVSS v3.1 vector + base score

PHASE 3 — EXECUTIVE REPORT PACKAGE
Deliver report with:
1) Executive Summary (1 page max)
   - Overall posture
   - Top 5 risks
   - Top 5 actions (prioritized)
   - What’s working well
   - Unknowns/Assumptions
2) System Overview (inventory + DFD + crown jewels)
3) Detailed Findings (table + deep dives)
4) Hardening Roadmap (0–7 / 8–30 / 31–90 days, tied to findings)
5) Evidence Appendix (commands + key outputs + files inspected)
6) Mandatory CISO sections (attack paths, failure modes, etc.)

PHASE 4 — BUILD THE IMPLEMENTATION (WRITE CODE)
Implement a “Security Runs” feature in the application so results are stored and visualized.

YOU MUST:
A) Create database models & migrations:
- security_scores (as defined above)
- security_tests (append-only; one row per Test ID per run)
- security_findings (append-only; linked to tests and run)
Include fields needed to support the popup and evidence traceability.

B) Create a repeatable “run” workflow:
- A management command or internal tool to:
  - execute tests
  - record per-test results
  - record findings
  - compute scores
  - append one row to security_scores
- Ensure idempotency per run: do not duplicate a run if re-executed accidentally (use run_timestamp + unique run_id).

C) Create dashboard UI:
- Latest run scores at top
- Trend line graphs for each metric over time
- Table of tests/finding counts
- Clicking Test ID opens popup showing criteria/evidence/result

D) Graphs:
- Use a simple, maintainable approach appropriate to the stack:
  - If Django: a small JS chart library or server-rendered data endpoints
- Provide clean UI and documented endpoints.

E) Provide a “Runbook”:
- How to run a new assessment
- How to view dashboard
- How to validate outputs

CRITICAL:
- Clickable criteria popup must show “criteria used for each test” in a way that is reproducible.

=====================================================================
SECTION 6 — COMMANDS YOU MAY RUN (READ-ONLY) DURING ASSESSMENT
=====================================================================

- Print repo tree
- Search for secrets:
  SECRET, KEY, TOKEN, PASSWORD, AWS, TWILIO, OPENAI, DEXCOM, CLOUDINARY, PRIVATE, CERT
- Identify settings/config modules
- Dependency audit (pip-audit or equivalent) and include outputs
- Any framework-appropriate static checks (read-only)

=====================================================================
SECTION 7 — HOW YOU START (MANDATORY)
=====================================================================

FIRST:
1) Print repo inventory (top-level + relevant directories)
2) Identify frameworks/entry points
3) Identify where configs/settings live
4) Propose your checklist of tests you will run (with Test IDs)
THEN:
Execute PHASE 1 tests and build the report and findings.
FINALLY:
Proceed into PHASE 4 and implement the scoring storage + dashboard + popup traceability + run workflow.


=====================================================================
SECTION 8 — SECURITY OF THE SECURITY SYSTEM (TIER-0)
=====================================================================

The Security Assessment System itself is a Tier-0 asset.

GOAL:
If the main application is compromised, attackers must NOT be able to read:
- Findings
- Scores
- Attack paths
- Evidence
- Roadmaps

A) DATA ENCRYPTION (MANDATORY)
- Encrypt at rest:
  - security_scores
  - security_tests
  - security_findings
- Field-level encryption for:
  - Evidence
  - Recommendations
  - Attack paths
  - Failure modes
  - CISO sleep test
- Keys:
  - Never stored in code or DB
  - Loaded from env or KMS
  - Rotatable
- Encrypt in transit:
  - TLS only
  - No plaintext endpoints

B) ACCESS CONTROL (MANDATORY)
- Separate roles:
  - SecurityAdmin (full)
  - SecurityViewer (read-only)
- Hard isolation:
  - Separate route namespace
  - Dedicated middleware
- MFA required for all security roles

C) DEFENSE-IN-DEPTH
Minimum 3 layers:
1) Auth
2) Authorization
3) Encryption
Optional elite:
- IP allowlist
- Hardware security keys (WebAuthn)

D) COMPROMISE ASSUMPTION MODEL
Design assuming:
“The main app will be breached.”

Therefore:
- DB dump ≠ readable security data
- Admin access ≠ security access
- Keys never persisted in storage

E) AUDITABILITY & TAMPER DETECTION
Log all:
- Dashboard access
- Finding views
- Exports
Logs include:
- User
- Timestamp
- IP
- Action
Optional elite:
- Hash chain or digital signature on runs

F) EXPORT CONTROL
- No public exports
- No generic APIs
- All exports:
  - Explicit approval
  - Encrypted
  - Logged

G) SELF-ASSESSMENT
Every run must include:
“Security of the Security System” review:
- Encryption verified?
- Keys isolated?
- Access logs present?
- Non-security users blocked?

H) DISASTER SCENARIO
Include:
“If this system is breached…”
- What exposed?
- Secondary risks?
- Incident response steps?

BEGIN.
