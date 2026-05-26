# Improvement Tasks - Prioritized Backlog

**Created:** 2026-01-20
**Status:** Active - Working through with user dialog

---

## Task List (Priority Order)

### Task 1: Add Sleep Tracking to Health Module
**Status:** ✅ Complete
**Impact:** High - Sleep is a fundamental health metric
**Completed:** 2026-01-20

### Task 2: Add Goal Progress/Milestones to Purpose Module
**Status:** ✅ Complete
**Impact:** High - Goals feel abandoned without visible progress
**Completed:** 2026-01-20

**Scope (completed):**
- **2A:** Core milestone model + progress visuals + encouragement stat + auto-complete prompt + celebration modal + SMS reminders
- **2B:** Dashboard goal progress widget with visual treatment + Quarterly Review dismissible tile
- **2C:** AI integration - journal/milestone cross-referencing and proactive coaching

**Deferred to Future Task:**
- **Year in Review Feature** - Comprehensive annual review appearing Dec 31/Jan 1 with:
  - In-depth analysis of the year's accomplishments across all modules
  - Goals completed, milestones achieved, journal insights
  - Health trends, faith journey, purpose progress
  - Prompts user for next year's planning and annual direction
  - Should be a rich, celebratory, reflective experience
  - Consider: exportable summary, shareable achievements, goal-setting wizard for new year

### Task 3: Add Recurring Transactions to Finance Module
**Status:** ✅ Complete
**Impact:** High - All finance entry is manual
**Completed:** 2026-01-20

**Scope (completed):**
- **3A:** RecurringTransaction model + RecurringTransactionService for generating instances
- **3B:** Forms + Views + Templates for managing recurring transactions
- **3C:** Management command + Dashboard widget for upcoming recurring

### Task 4: Implement Daily Reminders for Faith Module
**Status:** ✅ Complete
**Impact:** High - Model fields exist but aren't being used
**Completed:** 2026-01-20

**Scope (completed):**
- Added `generate_faith_reminders` scheduled job to wsgi.py (daily at 6 AM UTC)
- Job calls existing `generate_daily_reminders` management command
- Creates in-app/email notifications for prayers with `remind_daily=True`
- Creates notifications for active reading plans not yet completed
- Respects all user preference toggles

### Task 5: Add Quick-Capture Journal Mode
**Status:** ⏸️ On Hold (revisit after 2026-01-27)
**Impact:** High - Current entry flow has too much friction

### Task 6: Customizable Dashboard
**Status:** ✅ Complete
**Impact:** Medium - User controls their dashboard experience
**Completed:** 2026-01-20

**Scope (completed):**
- Drag-and-drop tile reordering
- Show/hide toggles for each tile (AI Insights mandatory)
- Tile sizing (small/medium/large)
- Setup banner for new/existing users
- 19 configurable tiles with module dependencies

### Task 7: Add Deadline Badges for Goals
**Status:** ✅ Complete
**Impact:** Medium - Creates urgency for approaching deadlines
**Completed:** 2026-01-20

**Scope (completed):**
- Deadline properties on LifeGoal model (is_overdue, days_until_due, deadline_urgency, deadline_badge_text)
- User preference toggle (show_goal_deadline_badges, default: True)
- Encouraging badge language: "Due in X days", "Past target date", "🎉 Completed!"
- Badges on goal_list, home, goal_detail, dashboard widget

### Task 8: Add Bill Due Date Reminders to Finance
**Status:** ⏸️ On Hold (revisit after 2026-02-03)
**Impact:** Medium - Proactive financial guidance

### Task 9: Enhanced AI Assistant - Intelligent Search & Query Gateway
**Status:** ⚪ Pending
**Impact:** HIGH - Core feature that makes the Assistant the single search tool for all of WLJ

**Vision:** The AI Assistant becomes the intelligent gateway to everything - personal data first, external APIs second, general knowledge third - all filtered through WLJ values.

**Query Resolution Hierarchy:**
1. **Personal Data (WLJ)** - Journal, Health, Goals, Faith, Organize, Finance, Capture
2. **External APIs** - Connected data sources (future: calendar, fitness trackers, etc.)
3. **OpenAI with Context** - General questions answered within WLJ culture/values

**WLJ Culture Filter:**
- Faith-positive, wellness-focused, encouraging tone
- Refuse inappropriate content (pornography, harmful content, crude humor)
- Redirect to positive alternatives: "Have you explored our Faith module or Reading Plans?"
- Protect user privacy and dignity

**Technical Components:**
1. Intent detection - Is this a search? What type?
2. Query parsing - Extract module, keywords, date ranges
3. Search execution - Query appropriate models/APIs
4. Result injection - Feed results into AI context
5. Values guardrails - Filter requests and responses through WLJ culture

### Task 10: Add Real-Time Processing Status for Capture
**Status:** ⚪ Pending
**Impact:** Medium - Users don't know when transcription completes

### Task 11: Add Wearable Sync (Fitbit/Apple Health)
**Status:** ⚪ Pending
**Impact:** High but complex - Reduces manual health data entry

### Task 12: Connect Prayers/Scripture/Reflections in Faith
**Status:** ⚪ Pending
**Impact:** Medium - Creates integrated spiritual journey

### Task 13: Add Proactive AI Coaching Interventions
**Status:** ⚪ Pending
**Impact:** Medium - AI should coach, not just respond

### Task 14: Add Journal Export (PDF/JSON)
**Status:** ⚪ Pending
**Impact:** Medium - Data portability

### Task 15: Add Tabbed Preferences Navigation
**Status:** ⚪ Pending
**Impact:** Medium - 60+ fields is overwhelming

### Task 16: Add Household Sharing for Life/Finance
**Status:** ⚪ Pending
**Impact:** High but complex - Enables family use

### Task 17: Add Lab Results Storage to Health
**Status:** ⚪ Pending
**Impact:** Medium - Medical continuity for provider visits

### Task 18: Add Community Features for Reading Plans
**Status:** ⚪ Pending
**Impact:** Medium - Accountability for spiritual growth

### Task 19: Build Cross-Module Integration Layer
**Status:** ⚪ Pending
**Impact:** High but complex - Links features across modules

### Task 20: Mobile-First Quick Action Redesign
**Status:** ⚪ Pending
**Impact:** Medium - Optimize for phone usage

### Task 21: "My Story" Document Upload for CoS
**Status:** ⚪ Pending
**Impact:** High - Lets CoS deeply understand the user from day one
**Context:** During calibration, the user wants to share extensive background (autobiography, life story, values doc) that's too long for chat. Build a document upload feature ("My Story" or "About Me") that the CoS always has access to. The uploaded text gets extracted and injected into the CoS system context so the AI knows the user's full background — not just what's in the data models.
**Scope:**
- File upload endpoint (PDF, text, Word) with pdfplumber/docx extraction
- Storage tied to user profile (new model or field on UserPreferences)
- Text injection into `build_calibration_system_injection()` and `build_cos_context()`
- UI: upload area on Assistant page or Settings, with preview/edit/delete
- Size limit + summarization for very long documents (token budget)

### Task 23: Deterministic renderer trust-surface stabilization (FOLLOW-UP — ARCHITECTURAL)
**Status:** ⚪ Pending — Architectural pass, not urgent but important
**Impact:** High — closes a structural gap in WLJ's trust discipline
**Source:** Surfaced by the 2026-05-26 "Drop this and go to Fish Oil now" trust bug investigation. The narrow at_risk_item fix shipped in that PR is complete; this task is the broader architectural follow-up the investigation exposed.

**Architectural insight:**
WLJ has TWO output paths that emit user-facing language, not one:

```
Raw Data → Signals → CoS context → LLM → User       (LLM path)
Raw Data → Signals → deterministic renderer → User  (deterministic path)
```

All prior trust-stabilization work (rhythm composer, IntakeLog provenance, affirmation auto-complete disable, Section 10 RHYTHM AWARENESS prompt rules) lives on the LLM path. The deterministic renderer (`apps/ai/beth_checkin_renderer.py`) bypasses every one of those safeguards. The 2026-05-26 incident proved it has its own discipline gaps.

**Scope (not yet committed, for separate PR):**
1. **Audit every deterministic phrasing template** in `beth_checkin_renderer.py` (and any sibling renderers) against the same trust rules the LLM path follows: never invent urgency, cite sources, no first-person feelings, respect time-window gating, no inferred adherence.
2. **Add per-template provenance comments** linking each hardcoded sentence to the signal that justifies it (analogous to IntakeLog.source).
3. **Add architectural test** that the renderer module does not import any LLM-only modules, AND that every f-string emitted to users is keyed against a deterministic input (no "drop this and go" without a proven anchor in the actionable window).
4. **Consider centralizing the time-window discipline** — currently `_ANCHOR_AT_RISK_WINDOW_MINUTES = 45` lives in this one file, but the same concept (anchor proximity gating) likely applies in other renderers / action prioritizers. A shared `time_windows.actionable_window_minutes()` would prevent the same bug class from recurring elsewhere.
5. **Consider per-user threshold calibration** — hardcoded 45/40/25/10 min thresholds were tuned for one assumed schedule cadence. A user with a sparse schedule could hit drift-CRITICAL constantly. Worth real-usage data first.

**Why NOT done in the 2026-05-26 PR:** Out of scope. The user explicitly required smallest-blast-radius fix for the trust-critical bug. The architectural pass deserves its own deliberation and is a Phase-3-class follow-up.

**Test plan:**
- Lock-in tests for each template family (NUDGE/PRESSING/CRITICAL with anchor/without anchor)
- Property tests: "for any drift, any anchor minutes_to_anchor > window, directive does not name the anchor"
- Cross-renderer integration tests (morning, midday, evening, end_of_day all behave consistently)

**Trust-risk classification:** Latent — the current state-after-fix is correct for the known incident pattern. Other deterministic templates may have similar latent bugs that just haven't surfaced yet. This task is preventive hygiene, not a patch.

---

### Task 22: Fix stale IntakeLog field names in quick_reply / SMS handlers (FOLLOW-UP DEFECT — DEFERRED)
**Status:** ⚪ Pending — High priority follow-up
**Impact:** Medium-High — affected handlers fail at runtime (silent breakage of medicine quick-reply + SMS-reply flows)
**Source:** Discovered during 2026-05-23 trust stabilization PR audit; defensively annotated but NOT fixed in that PR to preserve scope.

**Files:**
- `apps/ai/quick_reply_handlers.py` — `handle_skip_medicine`, `handle_mark_medicine_group_taken`, `handle_skip_medicine_group` (3 sites)
- `apps/sms/services.py` — `_mark_medicine_taken`, `_mark_medicine_skipped` (2 sites)

**Issue:** Legacy `IntakeLog` field names still referenced:
```
date        → should be: scheduled_date
time        → should be: scheduled_time
status      → should be: log_status
```
The current `IntakeLog` schema uses the `scheduled_*` / `log_status` field names. These handlers were written against an older schema and were not migrated. `update_or_create(date=..., time=..., defaults={'status': ...})` and `objects.create(..., status=...)` will raise `TypeError: ... got unexpected keyword arguments` when invoked.

**Why not fixed in trust PR:** Out of scope for the IntakeLog stabilization PR (trust contract was the focus). The trust PR added `source=IntakeLog.SOURCE_QUICK_REPLY` / `SOURCE_SMS_REPLY` kwargs defensively so provenance is captured when these handlers are corrected.

**Scope to fix:**
- Replace `date=` → `scheduled_date=` in all 5 sites
- Replace `time=` → `scheduled_time=` in all 5 sites
- Replace `status=` → `log_status=` in all 5 sites
- Add explicit `user=...` arg where missing (some sites omit it; `IntakeLog` requires it via `UserOwnedModel`)
- For `get_or_create`/`update_or_create`, include `schedule=` in the lookup key so the row matches existing scheduled-dose logs instead of creating duplicates
- Use `log.mark_taken(source=IntakeLog.SOURCE_QUICK_REPLY)` / `mark_skipped(..., source=...)` instead of raw `objects.create()` so grace-period late detection runs

**Test plan:**
- Integration test for `handle_mark_medicine_group_taken` confirming an `IntakeLog` is created against the right schedule for the right user and with `source='quick_reply'`
- Integration test for SMS `_mark_medicine_taken` confirming an `IntakeLog` is created with `source='sms_reply'`
- Negative test: pre-existing log for same (user, intake, schedule, date) is updated, not duplicated

**Trust risk:** The defect's blast radius is "feature does not work" rather than "feature does wrong thing." So unlike the inferred-completion bug, this defect cannot cause an item to falsely show as completed — it just fails silently. Still high-priority because users tapping the assistant's quick-reply buttons today get no DB write.

---

## TODO: Owner Financial Command Center — Polish

**Spec:** `docs/owner/ultimate_financial_command_center.md`

- [x] **Phase 3 — Ultimate UI:** Charts, power user diagnostics, CSV export, per-call audit ledger
- [x] **Phase 4 — Scenario Simulator:** Backend + form UI with projections
- [x] **Phase 5 — Budget Guardrails:** Model, check command, warning tiles, budgets page
- [x] **Extend telemetry** to all 9 LLM call sites
- [x] **Daily cost rollup tables** for fast chart queries
- [ ] **Sync BillingProfile** tier changes into `UserSubscriptionSnapshot` automatically
- [ ] **Stacked feature cost chart** (nice-to-have)
- [ ] **Model mix pie chart** (nice-to-have)

---

## Progress Log

### 2026-02-22
- Owner Financial Command Center Phases 3-5 complete
- Telemetry extended to 9 call sites across codebase
- 7 dashboard pages: Overview, Per-User, Features, Vendors, Audit Ledger, Simulator, Budgets
- Daily cost chart, CSV export, budget guardrail cards, power user drill-down

### 2026-02-21
- Owner Financial Command Center Phase 1 + 2 implemented
- Telemetry integrated into _call_api and intent_service
- Dashboard live at /owner/finance/ with 4 pages

### 2026-01-20
- Created initial task list from comprehensive app analysis
- Starting dialog on Task 1 (Sleep Tracking)

