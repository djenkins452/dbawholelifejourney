# Vegas Ops Wall v2 — Implementation Handoff

**Project:** Whole Life Journey (Django 5.x personal wellness app)
**Date:** 2026-02-21
**Implemented by:** Claude Code (Opus)
**Branch:** `claude/dreamy-kare` → merged to `main`

---

## What Was Built

A complete rebuild of the admin Operations Wall — the internal monitoring dashboard for the app's 15 intelligence engines. The v1 wall had simple tiles with in-memory anomaly detection. V2 replaces it with persistent observability, a deterministic cognition layer (SAME), admin action audit trails, and a Bloomberg/NASA-style dark UI.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   SAME Engine                        │
│         (System Autonomous Monitoring Engine)         │
│                                                       │
│  Heartbeats → 7 Detectors → Reconcile → Narrate     │
└──────────────┬────────────────────────┬──────────────┘
               │                        │
       ┌───────▼───────┐      ┌────────▼────────┐
       │  OpsAnomaly   │      │ NarrativeSnapshot│
       │  (persistent) │      │  (posture +      │
       │               │      │   plain English)  │
       └───────────────┘      └──────────────────┘
               │
       ┌───────▼───────┐
       │ AdminAction    │
       │ (audit trail)  │
       └───────────────┘
```

The system runs on a polling loop (2-second interval from the browser). Each poll:
1. Computes heartbeats for all engines (expected cadence vs actual last run)
2. Runs SAME's 7 anomaly detectors
3. Reconciles anomaly lifecycle (new → active → resolved)
4. Generates a narrative snapshot (posture, headline, bullets, recommendations)
5. Returns JSON to the Vegas UI

---

## Files Created (6 new files)

### 1. `apps/core/ai_observability/heartbeat.py`
Heartbeat calculator. Compares each engine's expected run cadence against its actual last `EngineRun` timestamp.

**Key functions:**
- `get_cadence_config()` — Merges hardcoded `ENGINE_CADENCES` dict with database `EngineExpectedCadence` overrides. DB wins.
- `compute_heartbeats()` — Returns a dict of `{engine_name: {status, last_run, seconds_overdue, interval}}` for all enabled engines. Status is one of: `OK`, `LATE` (within jitter window), `MISSED` (past jitter), `ERROR` (last run failed).
- `compute_and_save_heartbeats()` — Calls `compute_heartbeats()` then persists each as an `EngineHeartbeat` record.
- `get_latest_heartbeats()` — Returns the most recent heartbeat per engine (used by the UI).
- `seed_cadence_config()` — Populates `EngineExpectedCadence` from defaults using `get_or_create`.

**Jitter mapping:** Engines with a 5-minute cadence get 2 minutes of grace. 1-hour cadence gets 5 minutes. Daily gets 1 hour. Weekly gets 1 day.

### 2. `apps/core/ai_observability/same_engine.py`
The SAME (System Autonomous Monitoring Engine). Fully deterministic — no OpenAI calls. This is the "brain" that watches all the other engines.

**Entry point:** `run_same()` → returns `{heartbeats, anomalies, narrative}`

**7 Anomaly Detectors:**

| Detector | What It Catches | Threshold |
|----------|----------------|-----------|
| `_detect_missed_runs` | Engine hasn't run on schedule | Heartbeat status = MISSED |
| `_detect_error_spikes` | Burst of failures | >30% error rate in last 20 runs |
| `_detect_confidence_volatility` | Erratic confidence scores | StdDev > 0.15 over last 20 runs |
| `_detect_suppression_storm` | Arbitration layer over-suppressing | >60% suppression rate in last 50 decisions |
| `_detect_looping_reminders` | Same reminder repeated too often | Same scenario >3 times in last 20 decisions |
| `_detect_engine_starvation` | Engine producing 0 output | 0 output items in last 10 runs |
| `_detect_delivery_retry_spike` | Delivery system retrying excessively | >40% retry rate in last 20 delivery runs |

**Anomaly Reconciliation (`_reconcile_anomalies`):**
- New anomaly detected → create `OpsAnomaly` record (status=active)
- Existing anomaly still active → update `last_seen`, increment `occurrence_count`
- Previously active anomaly no longer detected → set status=resolved, add `resolved_at`
- Matching key: `(anomaly_type, engine_name)`

**Narrative Generation (`_generate_narrative`):**
Builds an `OpsNarrativeSnapshot` with:
- `posture`: "OK" / "DEGRADED" / "AT_RISK" based on anomaly severity
- `headline`: Plain English summary (e.g., "2 engines need attention — error spike in PIE, missed run in PRIE")
- `bullets_now`: What's happening right now (list of strings)
- `recommendations`: What the admin should do (list of strings)
- `watching_next`: What SAME is monitoring going forward (list of strings)

### 3. `apps/core/ai_observability/tests_ops_wall_v2.py`
42 tests covering:
- All 5 new models (creation, constraints, string representations)
- Heartbeat calculator (OK, LATE, MISSED status; database cadence overrides; save/retrieve)
- SAME detectors (missed run creates anomaly, resolved when recovered, error spike detection, suppression storm detection, confidence volatility)
- Anomaly reconciliation lifecycle (create → update → resolve)
- Narrative generation (posture mapping, anomaly references in text)
- Stream endpoint (JSON structure, incremental cursor filtering, 403 for non-staff)
- Admin actions (creates AdminIntervention, trace ID generated, 403 for non-staff, acknowledge resolves anomaly)

**MFA handling in tests:** Staff users hit `MFAEnforcementMiddleware` which redirects to MFA verification. Tests use a `_login_staff(client, user)` helper that calls `force_login()` AND sets `session['mfa_verified'] = True`.

### 4. `apps/core/migrations/0079_vegas_ops_wall_v2_models.py`
Django migration creating all 5 new database tables:
- `core_engine_expected_cadence`
- `core_engine_heartbeat`
- `core_admin_intervention`
- `core_ops_anomaly`
- `core_ops_narrative_snapshot`

### 5. `templates/admin_console/all_engines.html`
All Engines view — a searchable table showing every engine with:
- Engine name
- Expected interval (human-readable: "5 min", "1 hour", "daily", "weekly")
- Monitoring status (enabled/disabled)
- Last run time
- Status badge (OK/LATE/MISSED/ERROR)
- Last duration

Dark theme matching the ops wall. Client-side search filtering via `addEventListener` on the search input.

### 6. `docs/OPS_WALL_V2_REPORT.md`
Architecture documentation with diagrams, anomaly threshold table, admin action reference, cadence extension guide, route table, and test coverage summary.

---

## Files Modified (7 existing files)

### 7. `apps/core/ai_observability/models.py`
Added 5 new Django models after the existing `DecisionRecord`:

```python
class EngineExpectedCadence(models.Model):
    engine_name = models.CharField(max_length=100, unique=True)
    expected_interval_seconds = models.IntegerField()
    jitter_seconds = models.IntegerField(default=300)
    is_enabled = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    # timestamps...

class EngineHeartbeat(models.Model):
    engine_name = models.CharField(max_length=100, db_index=True)
    status = models.CharField(choices=OK/LATE/MISSED/ERROR)
    last_run_at = models.DateTimeField(null=True)
    seconds_overdue = models.IntegerField(default=0)
    checked_at = models.DateTimeField(auto_now_add=True)

class AdminIntervention(models.Model):
    user = models.ForeignKey('users.User')
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=200)
    detail = models.JSONField(default=dict)
    trace_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

class OpsAnomaly(models.Model):
    anomaly_type = models.CharField(choices=[7 types])
    engine_name = models.CharField()
    severity = models.CharField(choices=P1/P2/P3)
    status = models.CharField(choices=active/acknowledged/resolved)
    message = models.TextField()
    detail = models.JSONField()
    first_seen / last_seen / resolved_at
    occurrence_count = models.IntegerField(default=1)

class OpsNarrativeSnapshot(models.Model):
    posture = models.CharField(choices=OK/DEGRADED/AT_RISK)
    headline = models.TextField()
    bullets_now = models.JSONField()  # list of strings
    recommendations = models.JSONField()
    watching_next = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
```

All use `app_label = "core"` with custom `db_table` names prefixed `core_`.

### 8. `apps/core/ai_observability/admin.py`
Registered all 5 new models in Django admin:
- `EngineExpectedCadence` — editable (admin can change cadence/jitter)
- All others — read-only with appropriate list displays, filters, search

### 9. `apps/core/ai_observability/ops_views.py`
Complete rewrite. Kept `OperationsWallView` (template renderer), replaced/added:

- **`OpsStreamView`** (GET `/admin-console/ops/stream/`) — JSON polling endpoint. Returns:
  ```json
  {
    "ts": "ISO timestamp",
    "posture": "OK|DEGRADED|AT_RISK",
    "engine_cards": [...],
    "narrative": {headline, bullets_now, recommendations, watching_next},
    "anomalies": [...],
    "feed": [...],
    "feed_cursor": "ISO timestamp for incremental updates"
  }
  ```
  Supports `?since=` parameter for incremental feed updates.

- **`OpsActionView`** (POST `/admin-console/ops/actions/`) — Admin action endpoint. Accepts JSON `{action, target}`. Actions:
  - `rerun_engine` — Re-runs a specific engine
  - `clear_suppression_cache` — Clears arbitration suppression cache
  - `acknowledge_anomaly` — Sets anomaly status to acknowledged
  - `resolve_anomaly` — Marks anomaly as resolved
  - `restart_scheduler` — Placeholder for scheduler restart
  Every action creates an `AdminIntervention` audit record with a UUID trace ID.

- **`AllEnginesView`** (GET `/admin-console/ops/all-engines/`) — Table view of all engines.

### 10. `apps/admin_console/urls.py`
Added 4 new URL patterns:
```python
path("ops/stream/", OpsStreamView.as_view(), name="ops_stream"),
path("ops/actions/", OpsActionView.as_view(), name="ops_actions"),
path("ops/all-engines/", AllEnginesView.as_view(), name="ops_all_engines"),
path("ops/poll/", OpsStreamView.as_view(), name="ops_poll"),  # Legacy compat
```

### 11. `templates/admin_console/operations_wall.html`
Complete UI rewrite — Vegas/Bloomberg/SOC dark theme:

**Layout sections (top to bottom):**
1. **Header bar** — "INTELLIGENCE OPS" title + Freeze/All Engines buttons + clock
2. **System Posture Banner** — Full-width colored bar (green OK, amber DEGRADED, red AT_RISK) with pulse animation + headline text
3. **SAME Narration Bar** — 3-column layout: "Right Now" bullets | "Recommendations" | "Watching Next"
4. **Engine Cards Grid** — One card per engine showing: status badge, cadence label, miss count, error count, 12-bar sparkline (last 12 runs), last run time, mean duration
5. **Watchlist Panel** — Active anomaly cards with severity color (P1=red, P2=amber, P3=blue), type, engine, message, occurrence count, action buttons
6. **SOC Live Feed** — Scrolling monospace feed of engine runs and decisions with filter buttons (All / Errors / Decisions)
7. **Toast container** — Bottom-right notification toasts for action results

**Technical details:**
- All JavaScript uses `addEventListener()` inside `<script nonce="{{ csp_nonce }}">` (CSP compliant — no inline handlers)
- 2-second polling interval with freeze/resume toggle
- Incremental feed updates using cursor parameter
- Action buttons use event delegation on the watchlist container
- Dynamic element creation for cards, feed items, anomalies
- Color scheme: `--ops-bg: #0a0e1a`, `--ops-surface: #141825`, green/amber/red for status

### 12. `apps/core/fixtures/release_notes.json`
Added new release note (pk 82):
> "Operations Wall Upgraded to Vegas v2" — describes SAME engine, heartbeats, anomaly tracking, admin actions, and dark monitoring UI.

### 13. `docs/wlj_claude_changelog.md`
Added changelog entry for 2026-02-21 documenting all changes, new files, modified files, and rationale.

---

## Database Schema (5 new tables)

```sql
-- Engine cadence configuration (admin-editable)
core_engine_expected_cadence
  id, engine_name (unique), expected_interval_seconds, jitter_seconds, is_enabled, notes, created_at, updated_at

-- Heartbeat snapshots (one per engine per check cycle)
core_engine_heartbeat
  id, engine_name (indexed), status (OK/LATE/MISSED/ERROR), last_run_at, seconds_overdue, checked_at

-- Admin action audit trail
core_admin_intervention
  id, user_id (FK→users_user), action, target, detail (JSON), trace_id, created_at

-- Persistent anomaly records
core_ops_anomaly
  id, anomaly_type, engine_name, severity (P1/P2/P3), status (active/acknowledged/resolved), message, detail (JSON), first_seen, last_seen, resolved_at, occurrence_count

-- SAME narrative snapshots
core_ops_narrative_snapshot
  id, posture (OK/DEGRADED/AT_RISK), headline, bullets_now (JSON array), recommendations (JSON array), watching_next (JSON array), created_at
```

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin-console/ops/` | Render Operations Wall HTML |
| GET | `/admin-console/ops/stream/` | JSON poll — engine cards, narrative, anomalies, feed |
| GET | `/admin-console/ops/stream/?since=<ISO>` | Incremental feed updates only |
| POST | `/admin-console/ops/actions/` | Execute admin action `{action, target}` |
| GET | `/admin-console/ops/all-engines/` | All engines table view |

All endpoints require staff user + MFA verified.

---

## Engine Inventory

The app has 15 intelligence engines across 3 phases:

**Interpretation Phase (process input signals):**
- PIE (Pattern Interpretation Engine) — detects behavioral patterns
- SAE (Signal Aggregation Engine) — aggregates daily signals
- PRIE (Predictive Intelligence Engine) — generates predictions

**Execution Phase (decide + act):**
- UAL (Universal Arbitration Layer) — single-decision arbitration
- Intervention Engine — generates interventions
- Pattern Analyzer — extended pattern detection
- Narrative Engine — generates user-facing narratives
- Scenario Evaluator — evaluates intervention scenarios
- Surface Allocator — allocates surface real estate
- Confidence Scorer — scores confidence levels
- Delivery Engine — delivers interventions to users

**Post-Execution Phase (learn + observe):**
- Feedback Processor — processes user feedback
- Monica (AI Chat) — conversational AI assistant
- SAME (System Autonomous Monitoring Engine) — THIS engine, watches all the others

9 of the 15 engines are already instrumented with `@log_engine_run` decorator that writes `EngineRun` records. The heartbeat system works with whatever engines have run data.

---

## How SAME Works (Step by Step)

1. **Heartbeat Check:** For each engine with a configured cadence, compare `expected_interval + jitter` against the timestamp of the last `EngineRun`. Classify as OK/LATE/MISSED/ERROR.

2. **Anomaly Detection:** Run 7 independent detectors. Each returns a list of `{anomaly_type, engine_name, severity, message, detail}` dicts.

3. **Reconciliation:** Compare detected anomalies against existing active `OpsAnomaly` records:
   - Match key = `(anomaly_type, engine_name)`
   - New detection + no existing record → INSERT new active anomaly
   - New detection + existing record → UPDATE `last_seen`, increment `occurrence_count`
   - No detection + existing active record → SET `status=resolved`, `resolved_at=now`

4. **Narrative:** Build a snapshot:
   - Posture = AT_RISK if any P1, DEGRADED if any P2, else OK
   - Headline = count of active anomalies + top 2 summarized
   - Bullets = one line per active anomaly
   - Recommendations = action suggestions based on anomaly types
   - Watching = engines that were recently resolved or borderline

---

## Test Coverage

42 tests in `apps/core/ai_observability/tests_ops_wall_v2.py`:

- **Model tests (5):** Create and verify all 5 new models
- **Heartbeat tests (5):** OK/LATE/MISSED status, DB override, save+retrieve
- **SAME tests (5):** Missed run detection, resolution, narrative creation, posture mapping
- **Detection tests (4):** Error spike, suppression storm, confidence volatility (detected + not detected)
- **Stream endpoint tests (3):** JSON structure, cursor-based incremental, 403 for non-staff
- **Action tests (4):** Audit trail creation, trace ID, 403 for non-staff, acknowledge→resolve
- **View access tests (3):** All 3 views return 403 for non-staff
- **Reconciliation tests (3):** Create new, update existing, resolve stale
- **Integration tests (10):** Various edge cases

All tests pass. Run with:
```bash
python3 manage.py test apps.core.ai_observability.tests_ops_wall_v2 -v 1 --failfast
```

---

## Known Limitations / Future Work

1. **SSE not implemented** — Still uses 2-second HTTP polling. Could upgrade to Server-Sent Events for real-time push.
2. **SAME runs on poll** — Currently triggered by the browser poll. Should be a background celery task running on its own schedule (e.g., every 60 seconds).
3. **6 engines not yet instrumented** — Only 9/15 engines have `@log_engine_run`. The remaining 6 will show "no data" in heartbeats until instrumented.
4. **No ML baselines** — Thresholds are hardcoded (30% error rate, 0.15 stddev, etc.). Could learn normal baselines per engine over time.
5. **No auto-remediation** — Admin actions are manual. Could add automatic remediation for low-severity anomalies (e.g., auto-rerun on single missed run).
6. **Narrative is template-based** — Could enhance with OpenAI for more natural language, but deterministic approach is intentionally chosen for reliability.

---

## How to Extend

**Add a new engine to monitoring:**
1. Add entry to `ENGINE_CADENCES` in `ops_aggregates.py` OR create `EngineExpectedCadence` record in Django admin
2. Ensure the engine uses `@log_engine_run` decorator so `EngineRun` records are created
3. SAME will automatically pick it up on next cycle

**Add a new anomaly detector:**
1. Create `_detect_new_thing()` function in `same_engine.py`
2. Return list of `{anomaly_type, engine_name, severity, message, detail}` dicts
3. Add the anomaly_type to `OpsAnomaly.ANOMALY_TYPES` choices
4. Call the detector from `run_same()` and extend the `all_anomalies` list
5. Add narrative handling in `_build_recommendations()`

**Add a new admin action:**
1. Add handler function in `ops_views.py` (e.g., `_action_my_thing(target)`)
2. Add case to `_execute_action()` switch
3. UI buttons are generated dynamically from anomaly cards — or add a dedicated button in the template
