# WLJ Timestamp Precision — Architecture & Rollout

**Status:** Phase 1 (foundation) SHIPPED 2026-07-20. Phases 2–3 designed, deferred.
**Owner module:** `apps/core/truth/precision.py` (companion to `apps/core/truth/temporal.py`).
**Origin:** the Health Sync "Newest data · Heart Rate · Today · 12:00 PM at 6:12 AM" incident
(see `docs/wlj_claude_changelog.md`, 2026-07-20 `fix(health)`).

---

## 1. Recommendation

**Yes — timestamp precision should be a first-class truth concept in WLJ, adopted
incrementally per-domain (never a big-bang migration).**

WLJ is a Personal Truth Platform. A stored timestamp that claims a precision its source
never provided is a *fabricated fact* — the same category of defect as an invented value.
The Health Sync bug was one visible symptom of a systemic pattern: date-only data from a
source is stored at a manufactured "noon" (or midnight, or 10 PM for sleep), which both
invents a clock time and — before local noon — invents a value in the **future**.

**Are the current guardrails sufficient?** They are sufficient to prevent the *reported
harm* but **not** the whole class:

- `temporal.py` + the Health Sync surface guard already ensure WLJ never *displays* a
  future instant, and the ingest fix + `precision.resolve_instant` ensure new heart-rate
  and weight rows are never stored in the future.
- But a date-only value synced *after* noon is still stored at a fabricated 12:00 PM, and
  eight other health-ingest paths (glucose, blood pressure, body temperature, body-comp,
  generic daily metrics, sleep) still fabricate sub-day precision on their date-only path.
  Nothing yet records *that these are DAY-precise*, so any consumer (the assistant, charts,
  exports) will read "12:00 PM" as a real measured time.

So a foundation is warranted. The fix is not another detector — it is to **carry the true
precision alongside the timestamp** so no layer ever has to guess. Because that touches
~30 observed-moment fields across 6+ apps, it is rolled out per-domain as each Layer-1
domain is certified, not all at once.

---

## 2. The model (`apps/core/truth/precision.py`)

One vocabulary, one set of deterministic rules, reused by every domain:

- **`Precision`** — ordered vocabulary: `SECOND < MINUTE < HOUR < DAY < MONTH < YEAR`,
  plus `UNKNOWN` (coarsest). `rank()`, `coarser(a,b)`, `is_subday(p)`.
- **`infer_precision(raw)`** — the precision a raw source value *actually* carries
  (`date`→DAY, `datetime`→SECOND, `"2026"`→YEAR, `"2026-07"`→MONTH, `"…T05:54"`→MINUTE,
  `"…T05:54:13"`→SECOND, else UNKNOWN).
- **`resolve_instant(value, fallback_date, now)` → `(aware_datetime | None, precision)`** —
  THE rule for writing any observed-moment timestamp. A real instant is kept verbatim; a
  date-only/month/year value is placed at local **noon clamped to ≤ now** (never future)
  and reported at DAY/MONTH/YEAR precision so the fabricated sub-part is never trusted.
- **`format_instant(dt, precision, now)`** — render honestly at precision: DAY → "Today" /
  "July 20" (never a clock time); MINUTE/SECOND → "Today • 5:54 AM"; MONTH → "July 2026";
  YEAR → "2026"; UNKNOWN → "date unknown". The reference formatter every presentation layer
  (web, iOS, CoS narration) should adopt.

**Invariant:** `resolve_instant` never returns an instant later than `now`, and never
returns a precision finer than the source provided. That makes the "future noon / invented
12:00 PM" class *structurally impossible* at any adopting write site.

---

## 3. Rollout

### Phase 1 — Foundation (SHIPPED 2026-07-20)
- `precision.py` + tests (`apps/core/truth/tests/test_precision.py`, 18 tests).
- First adopters (dogfood, behavior-identical to the incident fixes): heart-rate and
  weight ingest in `apps/mobile/views.py` now derive `recorded_at` via `resolve_instant`.
- Health Sync surface guard (`build_health_sync_status`) already clamps any future
  displayed instant. *No schema change, no visible behavior change beyond the bug fixes.*

### Phase 2 — Persist precision per observed timestamp (DEFERRED; per-domain)
Add a companion precision to each *observed-moment* timestamp so precision survives storage:

- A reusable `TemporalPrecisionMixin` (or an `observed_precision` `CharField(choices=Precision.ALL)`
  paired with an `observed_at` field), adopted domain-by-domain **as each Layer-1 domain is
  certified** (Health first — it owns the largest surface and the incident).
- At ingest, write both the instant (`resolve_instant`[0]) and its precision
  (`resolve_instant`[1]). The plumbing already returns precision (`_precision`) at the two
  Phase-1 adopters — Phase 2 stops discarding it.
- **Promotion trigger:** begin a domain's Phase 2 when that domain enters truth
  certification, or when a precision-related trust bug is reported against it. Do not
  migrate a domain speculatively.

### Phase 3 — Presentation adopts precision (DEFERRED)
- The Health Sync JSON emits `precision` beside `newest_data`/`last_record_at`; iOS
  `HealthSyncDate` renders DAY as "Today"/"July 20" (no clock time) — replacing the current
  always-append-a-time behavior. Ships with the next app build (App Store), not Railway.
- Web/CoS surfaces call `format_instant` instead of ad-hoc `strftime`.

---

## 4. Fabrication-site inventory (as of 2026-07-20)

### A. STORAGE fabrication — fake time persisted to a `DateTimeField` (the real concern)
All in `apps/mobile/views.py` health ingest; pattern = real `_sample_dt` when present,
else fabricate. **Bold = migrated to `resolve_instant` in Phase 1.**

| Line | Field | Domain | Fallback | Phase-1 |
|------|-------|--------|----------|---------|
| ~799 | `WeightEntry.recorded_at` | weight | noon (was uncapped) | **✅ resolve_instant** |
| ~1071 | `HeartRateEntry.recorded_at` | heart rate | `min(noon, now)` | **✅ resolve_instant** |
| ~947 | `SleepEntry.bedtime` | sleep | 10 PM prior night | deferred |
| ~1156 | `GlucoseEntry.recorded_at` | glucose | noon | deferred |
| ~1912 | `WeightEntry.recorded_at` | body-fat row | noon | deferred |
| ~2153 | `WeightEntry.recorded_at` | lean-mass row | noon | deferred |
| ~2403 | `BloodPressureEntry.recorded_at` | blood pressure | noon | deferred |
| ~2482 | `BodyTemperatureEntry.recorded_at` | body temperature | noon | deferred |
| ~1248 | `BloodOxygenEntry.recorded_at` | blood oxygen | `now()` (no noon) | deferred |
| ~2691 | `HeartRateEventEntry.recorded_at` | HR events | `now()` | deferred |

Deferred sites are protected *today* by the Health Sync surface guard (never displays a
future instant); their residual issue is a fabricated *sub-day* precision that Phase 2
resolves. Repair migrations for existing future-dated rows exist for weight (`health/0098`)
and heart rate (`health/0105`); add per-domain repairs alongside each Phase-2 adoption.

Seed/fixture fabrication (`setup_app_review_account.py`, `certification_fixtures.py`) is
intentional demo data — out of scope.

### B. READ-PATH fabrication — NOT persisted (display/ordering only, lower priority)
`apps/core/ai_events/adapters/*` build in-memory `EventRecord.timestamp` from a date via
**midnight**; `apps/dashboard/services/daily_activity_service.py` and several
`ai_predictions/*` rules do likewise for row dicts / math. These never write to the DB and
their source of truth is the row's own date; they should adopt `format_instant` for display
in Phase 3 but carry no storage-truth risk.

### C. Breadth of observed-moment fields (Phase-2 surface, ~30 fields)
Health (~16: the `*Entry.recorded_at` set, `SleepEntry.bedtime/wake_time`, `IntakeLog.taken_at`,
`HealthKitDailyMetric.recorded_at`, `MealGlucoseResponse.meal_consumed_at`), Medical
(`LabPanel/LabResult.collected_at`, `reported_at`), Meals (`prepared_at`, `consumed_at`,
`occurred_at`), Life (`purchased_at`, `performed_at`, `received_date`), plus `signals`
(`scheduled_time`/`actual_time`) and misc `occurred_at`/`observed_at`/`measured_at`.

---

## 5. Verification
`apps/core/truth/tests/test_precision.py` (18) proves the invariants; the Phase-1 ingest
adopters are covered by `apps/mobile/tests/test_health_sync_status.py` (heart-rate real-time,
date-only-never-future, self-heal) — all green alongside the Health Sync truth suite.
