# Medication & Supplement Intelligence v2 — Phase 2: Gap Analysis & Migration Strategy

**Status:** Phase 2 — ANALYSIS & PLANNING ONLY. No implementation, no code, no migrations, no model creation, no UI changes.
**Date:** 2026-06-27.
**Inputs:** Phase 1 spec (`docs/MEDICATION_SUPPLEMENT_INTELLIGENCE_V2.md`), the prior current-state audit, and fresh evidence verification (defect status + model-ownership inventory) performed for this phase.
**Purpose:** Convert the Phase 1 target architecture into a safe, evidence-based, least-disruption implementation roadmap.

> **Two Phase-1 corrections established by this phase's evidence pass (Evidence Supremacy):**
> 1. **Providers already exist** — `apps.health.MedicalProvider` (`apps/health/models.py:3619`) + `apps.health.ProviderStaff` (`:3816`). Phase 1's proposed new `Provider` model is **cancelled**; we reuse `MedicalProvider` and add an FK bridge from `Intake`.
> 2. **All medication ownership lives in `apps/health`**, not `apps/medical`. `apps/medical` is a **labs-only** domain (8 models, all lab/document/audit). This resolves Phase 1 Open Question **O-2**: new medication models belong in `apps/health`, beside `Intake`.

---

## 1. Executive Summary

Phase 2 audits the live codebase against the Phase 1 target and produces an implementation roadmap. The headline is favorable and now sharper than Phase 1 estimated:

- **Stabilization is mostly done.** Of the five blocking defects, **D1 (dead PIE subscriber) and D2 (adherence-chart drift) are FIXED and deployed** (changelog 2026-06-27). **D3 (`intake_subtype` not rendered) and D4 (no AI med-CRUD intent) remain OPEN.** **D5 (duplicate dose enumerations) is PARTIALLY consolidated** — `medicine_utils` is now internally canonical, but EAE and two `dashboard_v2` paths still enumerate independently.
- **The reuse surface is larger than Phase 1 assumed.** Beyond the known assets, the codebase already owns a **provider/care-team model** (`MedicalProvider`/`ProviderStaff`), a **stateless drug-lookup service** (`apps/scan/services/medicine_lookup.py` — RxNorm/FDA-NDC/AI), a **labs stack** (`apps/medical`), a **medical document pipeline** (`MedicalDocument`), and a **HIPAA-style audit log** (`MedicalAuditLog`). These are reused, not rebuilt.
- **Genuinely new models shrink to a justified core.** Phase 1 proposed five new models; Phase 2 cancels `Provider`, confirms four (`MedicationEvent`, `TreatmentPlan`, `IntakeExperiment`/`ExperimentObservation`, `MedicationScanDraft`), and adds five clinical-context models that the evidence proves absent (`Prescription`, `Pharmacy`, `MedicalCondition`, `DrugAllergy`, `SideEffectReport`) plus an optional `DrugClass` reference catalog.
- **The cornerstone risk is historical truth.** WLJ has no append-only history today and **cannot reconstruct past dose changes** — existing `Intake` rows are present-tense projections. The migration therefore **starts tracking history going forward** from a single backfilled "started" event per active med, and explicitly refuses to fabricate historical changes.

**Recommended next action:** ship a small **Phase 2.5 stabilization PR** (finish D3, D5; optionally D4) *before* any schema growth, then proceed to the additive data-model work (Phase 3) gated on resolving the four remaining open questions in Section 12.

---

## 2. Current Model Inventory

Verdict legend: **Reuse** (canonical, use as-is) · **Extend** (add fields/FKs) · **New** (justified, absent today) · **Leave** (unrelated, do not touch).

### 2.1 Medication core (apps/health)

| Model | File:line | Purpose | Canonical? | Verdict |
|-------|-----------|---------|-----------|---------|
| `Intake` | `health:2282` | Unified med+supplement current truth (`intake_type`); dose/freq/supply/refill + free-text provider/pharmacy/rx | **Yes** | **Extend** (add FKs to provider/pharmacy/prescription/drug_class; `ndc_code`, structured `strength`, `sig_text`, `current_event`, `expiration_date`, `monitoring_requirements`) |
| `IntakeSchedule` | `health:2609` | Dosing plan (per-time, per-weekday) | Yes | **Reuse** (optional: promote to SoftDelete — O-7) |
| `IntakeLog` | `health:2732` | Dose events (taken/missed/skipped/late) + insulin per-event dose | Yes | **Reuse** |

### 2.2 People / places / Rx (apps/health)

| Model | File:line | Purpose | Canonical? | Verdict |
|-------|-----------|---------|-----------|---------|
| `MedicalProvider` | `health:3619` | Prescribing physician/care provider — contact, NPI, specialty (incl. `pharmacy`) | **Yes** | **Reuse** (cancels Phase-1 `Provider`). Bridge: `Intake.provider` FK |
| `ProviderStaff` | `health:3816` | Provider's staff (PA, nurse, pharmacist) FK→provider | Yes | **Reuse** |
| Pharmacy | — | *None dedicated*; free-text `Intake.pharmacy` (`:2433`) | No | **New** (small dedicated model — O-8 RESOLVED; not `MedicalProvider` specialty=pharmacy) |
| Prescription | — | *None*; Rx fields denormalized on `Intake` (`rx_number :2438`, supply/refill `:2416`) | No | **New** (Rx distinct from regimen) |

### 2.3 Clinical context (mostly absent)

| Concept | File:line | Current state | Verdict |
|---------|-----------|---------------|---------|
| Medical condition / problem list | — | Absent. Closest: `Intake.purpose` free text (`:2365`); `ai_memory` `"health_condition"` tag (`ai_memory/models.py:38`) | **New** `MedicalCondition` |
| Drug allergy | `health:3949` | `NutritionGoals.allergies` JSON = **dietary**, not clinical | **New** `DrugAllergy` |
| Symptom / side effect (general) | `health:106/209` | Only cycle-specific (`CycleDailyLog.symptoms`); med side-effects only in `IntakeLog.notes`/`prn_reason` | **New** `SideEffectReport` |
| Drug class / catalog | `scan/services/medicine_lookup.py:121` | Stateless RxNorm/FDA-NDC/AI lookup → `MedicineResult` dataclass; nothing persisted. `Intake.category` (`:2473`) = coarse grouping | **New** optional `DrugClass` reference catalog; **Reuse** the lookup service for enrichment |

### 2.4 Labs / documents / audit (apps/medical — labs-only domain)

| Model | File:line | Purpose | Verdict |
|-------|-----------|---------|---------|
| `LabResult` / `LabTestCatalog` / `LabTestAlias` / `LabPanel` / `LabEducationContent` | `medical:495/37/130/236/164` | Canonical lab stack | **Reuse** (cross-domain joins, physician export) |
| `MedicalDocument` (+ `ImportBatch`, `ImportErrorRow`) | `medical:306/369/433` | PDF import pipeline; links to `life.Document` | **Reuse** (pharmacy-paperwork ingestion) |
| `MedicalAuditLog` | `medical:731` | HIPAA-style no-PHI audit; lab-centric `ACTION_CHOICES` | **Extend** (add medication action choices) or **New** med-specific audit — decision in §6 |

### 2.5 Image / scan / staging

| Model | File:line | Purpose | Verdict |
|-------|-----------|---------|---------|
| `ScanLog` | `scan:18` | AI-camera scan log; `CATEGORY_MEDICINE`/`SUPPLEMENT`; **stores no raw image** (`:135`) | **Reuse** (telemetry/audit of scans) |
| `ImageAnalysis` | `scan:221` | GenericFK analysis store, dedup hash, `'medical'` source; no raw image | **Reuse** (closest staging surface) |
| Med scan draft / staging | — | *None* — bottle scan today = unsaved prefilled form | **New** `MedicationScanDraft` |
| `MedicationImage` | — | *None* — no raw image retained anywhere | **New** (optional, consented; PHI) |

### 2.6 Cross-domain models (joins; all Reuse / Leave)

`GlucoseEntry` (`health:1054`), `MealGlucoseResponse` (`health:6306`), `WeightEntry` (`health:519`), `BodyCompositionEntry` (`health:4592`), `SleepEntry` (`health:4161`), `BloodPressureEntry` (`health:1232`), `HeartRateEntry` (`health:713`), `WorkoutSession` (`health:1660`), `StepsEntry` (`health:760`), `FoodEntry` (`health:3230`), `DailyNutritionSummary` (`health:3512`), `WaterEntry` (`health:874`), `LifeGoal` (`purpose:190`), `CalendarEvent` (`calendar_engine:13`), **`DailyHealthSummary`** (`health:5956`, 80+ fields — primary fast join). All **Reuse**; none modified by this initiative.

### 2.7 Experiments / exports

| Concept | Current state | Verdict |
|---------|---------------|---------|
| Experiment / hypothesis framework | **Absent** (only billing free-trials) | **New** `IntakeExperiment` + `ExperimentObservation` |
| Export | GDPR export incl. `Intake`/`IntakeLog` (`users/services/data_export.py:67`); Excel via openpyxl; PDF via WeasyPrint in `capture` (**not in requirements.txt**) | **Extend** (Physician Mode export; add WeasyPrint dep) |

---

## 3. Target-to-Current Gap Matrix

| Capability (Phase 1) | Current implementation | Current source of truth | Gap | Reuse? | Modify? | Add? | Risk | Phase |
|---|---|---|---|---|---|---|---|---|
| Unified med+supplement record | `Intake` (`intake_type`) | `Intake` | None | ✅ | — | — | Low | — |
| Adherence authority | `medicine_utils._enumerate_expected_doses` | `medicine_utils` | EAE + 2 dashboards still divergent (D5) | ✅ | ✅ collapse copies | — | Med (drift) | 2.5 |
| Append-only treatment history | None (Intake overwrites) | — | **No history; cannot reconstruct past** | — | — | ✅ `MedicationEvent` | **High** | 3 |
| Treatment grouping by goal/condition | None | — | Absent | — | — | ✅ `TreatmentPlan` | Med | 3 |
| Prescribing provider (structured) | `Intake.prescribing_doctor` free text | `MedicalProvider` exists, unlinked | FK bridge missing | ✅ MedicalProvider | ✅ add `Intake.provider` FK | — | Low | 3 |
| Pharmacy (structured) | `Intake.pharmacy` free text | — | No model | partial | ✅ | ✅ `Pharmacy` (small) | Low | 3 |
| Prescription record | Denormalized on `Intake` | — | No Rx entity | — | — | ✅ `Prescription` | Med | 3 |
| Drug class / interactions | `medicine_lookup` service (runtime) | none persisted | No catalog | ✅ service | — | ✅ `DrugClass` (opt) | Med | 3/8 |
| Medical condition / problem list | `Intake.purpose` text | — | Absent | — | — | ✅ `MedicalCondition` | Med | 3 |
| Drug allergy | dietary JSON only | — | Absent | — | — | ✅ `DrugAllergy` | Med (safety) | 3 |
| Side effects | `IntakeLog.notes` text | — | No structured report | — | — | ✅ `SideEffectReport` | Med | 3 |
| Image staging w/ confidence | unsaved prefilled form | — | No staging model | ✅ scan path | ✅ | ✅ `MedicationScanDraft` | Med (OCR truth) | 4 |
| Image evidence retention | none (no raw image) | — | Absent (intentional) | — | — | ✅ `MedicationImage` (consented) | High (PHI) | 4 |
| NDC / strength / SIG extraction | partial (Vision) | `Intake.dose` free text | Structured fields missing | ✅ Vision+lookup | ✅ Intake fields | — | Med | 3/4 |
| `intake_subtype` UI (insulin) | form field, template drops it | `Intake.intake_subtype` | Not rendered (D3) | — | ✅ template | — | Med | 2.5 |
| AI med CRUD | log-only intents | — | No create/update/delete (D4) | — | — | ✅ confirmed-write intents | Med (safety) | 2.5/5 |
| PIE medicine insights | subscriber now fires `run_insights` | PIE | No `rules_medicine.py` rules yet | ✅ PIE | — | ✅ rule file | Med | 5 |
| PRIE medicine forecasts | none | — | No refill/adherence forecast | ✅ PRIE | — | ✅ rule file | Low | 5/8 |
| EAE medicine signals | `medication_adherence`/`supplement_adherence` exist | EAE | New types (trend, momentum, refill_risk, instability, monitoring_gap) absent | ✅ EAE | ✅ add types | — | Med | 5/8 |
| Cross-domain med↔biomarker | `medication_adherence_risk` detector only | CDCE/ai_signals | No med correlation detectors in CDCE | ✅ CDCE | ✅ add detectors | — | Med-High (false causation) | 8 |
| Beth state contract | `_contract` (summary/today/upcoming/alerts) + `medication_status` | `build_medicine_state` | No treatment/observations/monitoring/experiments sections | ✅ | ✅ extend `_contract` | — | Med | 5 |
| Beth visibility (dose/freq/side-effects) | names+count (facts) / full state (domain tool) | `build_medicine_state` | Per-med dose/freq/side-effects not surfaced | ✅ | ✅ | — | Med | 5 |
| Experiment framework | none | — | Absent | partial (CDCE/PRIE primitives) | — | ✅ models+engine | Med | 6 |
| Physician export | GDPR/Excel/print-PDF primitives | export services | No clinical export; WeasyPrint missing in reqs | ✅ patterns | ✅ extend | ✅ export view | Med | 7 |
| Observability (med ops) | EAE `wlj:ops:signal_production` | cache keys | No `wlj:ops:med_*` keys/panel | ✅ pattern | ✅ add keys | — | Med | per-phase |
| FHIR export | none | — | Absent | — | — | ✅ (optional, late) | Low | 7+ |

---

## 4. Stabilization Prerequisite Status

Verified against current code 2026-06-27 (not the original audit — the codebase has moved).

| ID | Defect | Fixed? | Committed/Deployed? | Open? | Blocks |
|----|--------|--------|---------------------|-------|--------|
| **D1** | Dead PIE subscriber (`check_medication_insights` import swallowed) | ✅ **FIXED** | ✅ changelog 2026-06-27 ("medication/weight/sleep subscribers fire `run_insights()`") | No | — (unblocks Phase 5 PIE) |
| **D2** | Adherence chart drift (`day_taken/day_total else 100`) | ✅ **FIXED** | ✅ changelog 2026-06-27 — chart now calls `calculate_daily_medicine_adherence`; zero-data → no-credit, not 100% | No | — |
| **D3** | `intake_subtype` not rendered in UI | ❌ **OPEN** | Form field exists (`forms.py:492/517`) but `intake_form.html` renders fields **explicitly** (`{{ form.priority/name/dose }}`) and **never outputs `{{ form.intake_subtype }}`** — verified. Insulin basal/bolus still UI-unreachable | **Yes** | Phase 4 image-first (insulin meds), full insulin intelligence |
| **D4** | No AI create/update/delete medication intent | ❌ **OPEN (by design)** | Only `take_medication`/`take_supplement`/`take_intake_by_time`/`email_intake_list` (log/read). No `Intake.objects.create` in handlers. Deliberately deferred to a write-authority phase | **Yes** | Phase 5 Beth-assisted entry (optional) |
| **D5** | Duplicate expected-dose enumerations | ⚠️ **PARTIAL** | `medicine_utils._enumerate_expected_doses` now the single in-module source (D2 collapsed two copies). **Still divergent:** EAE `signal_aggregation.py:485` walks schedules independently (semantics aligned, not unified); `dashboard_v2/services/dashboard_service.py:243` + `compliance/adapters/medication.py:34` enumerate inline. D2 changelog explicitly defers full consolidation to a dedicated PR | **Yes (partial)** | Phase 5/8 signal trust (engine-to-engine adherence agreement) |

**Conclusion:** the two highest-risk correctness defects (D1, D2) are resolved. **D3, D4, D5 must be finished before schema growth that depends on them** — bundled as **Phase 2.5** (Section 11). D5 in particular must close before new EAE signals (`treatment_momentum`, etc.) are built on top of a divergent denominator.

---

## 5. Migration Strategy

Principle: **additive, reversible, non-destructive, history-forward.** No existing reader breaks; every step independently shippable.

### 5.1 Additive fields (Phase 3)
All new `Intake` columns are **nullable** with safe defaults; free-text fields (`prescribing_doctor`, `pharmacy`, `rx_number`) are **retained as fallbacks**, never dropped. New FKs (`provider`, `pharmacy`, `prescription`, `drug_class`, `current_event`) are nullable. A field is migrated from free-text → FK **opportunistically** (on next user edit / scan confirm), never by a destructive bulk transform.

### 5.2 New models (Phase 3/4/6)
Introduced as parallel tables (Section 6). None replaces an existing model. `Intake` remains the head projection.

### 5.3 Data backfill
- **`MedicationEvent`:** backfill exactly **one** `event_type="started"` per active `Intake`, dated `Intake.start_date` (or `created_at` if null), `source="backfill"`, `reason="unknown"`. **No other historical events are synthesized.**
- **`TreatmentPlan`:** **no** auto-grouping — created only by explicit user/clinician action or a confirmed Beth suggestion. Auto-inferring conditions would fabricate clinical truth.
- **Provider/Pharmacy FKs:** **no** auto-matching of free-text names to `MedicalProvider` rows (fuzzy match risks wrong-provider linkage). Bridge is offered as a one-time user "link these" prompt, not an automatic migration.

### 5.4 Historical reconstruction limits (explicit)
> **The system cannot and must not fabricate historical dose changes.** WLJ has no prior change ledger; `Intake` is present-tense. Therefore: **history begins at migration.** Every dose/provider/status change *after* the `MedicationEvent` model ships is recorded; everything *before* is represented only by the single backfilled "started" event and whatever the user chooses to enter manually. The Timeline UI (Phase 3) labels pre-migration history as *"tracking started [date]; earlier history not recorded."* This is a correctness guarantee, not a limitation to paper over.

### 5.5 Rollback strategy
- **Schema:** every migration has a tested reverse migration; new nullable columns drop cleanly; new tables are independent (no existing FK depends on them), so they drop without cascade damage.
- **Behavior:** each phase is gated behind a **feature flag** (Section 5.6); disabling the flag reverts to current behavior with the new tables dormant (data retained, unread).
- **`MedicationEvent` immutability:** corrections are compensating events, so rollback never requires mutating history.

### 5.6 Feature flags
Use the existing flag system (`apps/core/context_processors.py` `feature_flags()`). Proposed: `features.health.medication_history` (Phase 3), `features.health.med_scan_v2` (Phase 4), `features.health.med_intelligence` (Phase 5), `features.health.med_experiments` (Phase 6), `features.health.physician_export` (Phase 7). Each phase ships dark, is validated, then enabled.

### 5.7 Admin migration tools
Read-only admin surfacing of `MedicationEvent`/drafts for support; a management-command-free approach for any prod backfill (**per WLJ memory: prod has no CLI — use data migrations**). The single "started"-event backfill runs as a `RunPython` data migration (idempotent, reversible).

### 5.8 User-facing transition behavior
Silent and additive: existing intake list/detail/forms work unchanged until a flag lights up a new surface (Timeline, scan-review, physician export). No forced re-entry, no data loss, no disruption. The first time a user edits a med post-migration, an optional "link provider/pharmacy?" prompt appears — declinable.

---

## 6. Model Decision Review

Challenging each proposed model against the evidence.

### 6.1 `MedicationEvent` — **JUSTIFIED (cornerstone)**
- **Covered by existing?** No. `IntakeLog` is dose-*events*, not regimen-*change* events. Nothing records "dose increased / provider changed / discontinued."
- **Owns truth?** Owns *change history*; `Intake` owns *current state*. `Intake.current_event` FK points to the head.
- **Contains:** `intake` FK, `event_type`, `effective_date`, `previous_value`/`new_value` (JSON), `reason`, `reason_detail`, `provider` FK (→`MedicalProvider`), `source`, `recorded_at`. **Immutable.**
- **Must NOT contain:** dose-taken logs (that's `IntakeLog`), any computed adherence, any LLM-authored field.
- **Rollback risk:** Low — additive table, no existing dependency. Immutability means no destructive rollback path.

### 6.2 `TreatmentPlan` — **JUSTIFIED (with caution)**
- **Covered?** No grouping concept exists. `LifeGoal` (`purpose:190`) is goal-tracking, not a clinical treatment grouping.
- **Owns truth?** Owns the *grouping + clinical goal narrative*; references (not owns) conditions/meds/provider.
- **Contains:** `name`, `condition` FK, `goal_narrative`, `started_date`, `status`, `primary_provider` FK.
- **Must NOT contain:** auto-inferred condition assignment (fabrication risk). Created only explicitly.
- **Rename?** Consider `IntakeTreatmentPlan` for namespace clarity. Decision deferred.
- **Rollback risk:** Low. **Caution:** do not let Phase 3 ship `TreatmentPlan` before `MedicalCondition`, or its `condition` FK dangles.

### 6.3 `IntakeExperiment` + `ExperimentObservation` — **JUSTIFIED**
- **Covered?** No experiment framework exists. CDCE `DomainCorrelation` + PRIE validation are *primitives* to reuse, not the framework.
- **Owns truth?** Owns hypothesis/protocol/observations; **captured metrics are read from canonical sources** (glucose/workout/etc.), never re-entered as truth.
- **Contains (`IntakeExperiment`):** `hypothesis`, `linked_intake`/`linked_plan` FK, `protocol` JSON, `metrics` list, `trigger`, `target_n`, `status`, `finding` (deterministic). **(`ExperimentObservation`):** `experiment` FK, `occurred_at`, `captured_metrics` JSON, `user_notes`, `context` JSON.
- **Must NOT contain:** any prescriptive recommendation; LLM-authored findings (finding is computed deterministically, narrated by Beth).
- **Rollback risk:** Low. Defer to Phase 6 — depends on stable canonical metric capture.

### 6.4 `MedicationScanDraft` — **JUSTIFIED**
- **Covered?** No. Today's "draft" is an unsaved prefilled form — cannot hold per-field confidence, multi-item batches, or document line-items. `ImageAnalysis` (`scan:221`) is close but generic and not medication-confirm-workflow shaped.
- **Owns truth?** Owns *nothing canonical* — explicitly staging. Sets `created_intake` FK on confirm, then is inert.
- **Contains:** `source_type`, `extraction_method`, `raw_extraction` JSON, `field_confidences` JSON, `overall_confidence`, `status`, `created_intake` FK, `image_ref`, `expires_at`.
- **Must NOT contain:** anything treated as truth pre-confirmation; long-lived PHI (auto-expires).
- **Rollback risk:** Low — ephemeral table.

### 6.5 Phase-2 ADDITIONS (proven absent by inventory)
- **`Prescription`** — JUSTIFIED. Rx is denormalized on `Intake`; a real Rx (written_date, refills_remaining, prescriber, pharmacy, sig) is distinct from the regimen. Contains the Rx fields; **must not** duplicate dose-schedule (that's `IntakeSchedule`).
- **`Pharmacy`** — JUSTIFIED but **small. RESOLVED (O-8):** a lightweight dedicated model (`name`, `phone`, `address`, `rx_account`) — chosen over overloading `MedicalProvider` with `specialty=pharmacy`. A pharmacy is represented in `Pharmacy` only, never also as a `MedicalProvider` row (no duplicate ownership).
- **`MedicalCondition`** — JUSTIFIED. No problem-list exists. Contains `name`, `icd_code` (opt), `status`, `diagnosed_date`, `provider` FK. **Must not** be auto-inferred.
- **`DrugAllergy`** — JUSTIFIED (safety). The only "allergies" today are dietary JSON. Contains `substance`, `reaction`, `severity`, `noted_date`. Powers duplicate/interaction *warnings* (never clinical assertions).
- **`SideEffectReport`** — JUSTIFIED. User-reported, never inferred. Contains `intake` FK, `symptom`, `severity`, `started_date`, `ongoing`, `notes`.
- **`DrugClass`** — JUSTIFIED but **optional/deferred**. `medicine_lookup.py` already resolves class data at runtime; persist into a catalog only when class-based logic (duplicate-class detection) ships (Phase 8). **Reuse the lookup service first.**

### 6.6 CANCELLED / reused
- **`Provider`** — **CANCELLED.** `apps.health.MedicalProvider` (`:3619`) + `ProviderStaff` (`:3816`) already exist. Reuse; add `Intake.provider` FK. This is the single biggest Phase-1 correction.
- **Audit log** — **REUSE/EXTEND** `MedicalAuditLog` (`medical:731`) by adding medication `ACTION_CHOICES`, rather than a new audit model — unless the apps/medical↔apps/health boundary makes that awkward (O-9).

---

## 7. Beth / CoS Integration Plan

Beth receives **structured composed state + rendered signals only** — never raw OCR, raw logs, or raw meals. All additions land on existing seams.

| Surface | File:line | Addition | Beth never sees |
|---------|-----------|----------|-----------------|
| `build_medicine_state` `_contract` | `state_builder.py:3736` | New sections: `treatment` (active plans, recent `MedicationEvent`s, momentum verdict), `observations` (pre-computed CDCE/EAE), `monitoring` (overdue labs/checks), `experiments` (read-only summary). Per-med: dose, frequency, sig, side-effects | raw `IntakeLog` rows |
| SAE medicine module | `MODULE_BUILDERS["medicine"]` `state_builder.py:5818` | Stays the single medicine module; no parallel domain | — |
| Standing/foundational facts | `cos_services/health_facts.py:58` | Extend `current_medications` fact to optionally include dose/frequency (composed) | raw extraction |
| Domain-state tool | `cos_services/domain_state.py` | Returns extended `_contract` (snapshot-only, no live compute) | — |
| History search | `query_intents` (`domain="medication"`) | Add `MedicationEvent`-backed history queries (dose-change timeline) | raw events unframed |
| EAE / CDCE / signal feed | `ai_eae/signal_aggregation.py`, `ai_signals/_DETECTORS`, `cdce_engine.py:893` | New signal types + detectors → unified feed as rendered verdicts | atomic signals |
| Physician export context | new export service | Reads composed state + canonical models; produces document | — |
| Experiment summaries | `_contract.experiments` | Deterministic finding string only | raw observations |

**Hard rule (WLJ memory — Beth = briefing consumer):** every new section carries its **verdict inside** (e.g., `treatment_momentum: "stable", momentum_reason: "<deterministic>"`). Beth narrates; she never derives. Injection stays at `cos_context.py:~3977` via `build_cos_intelligence` / the medicine `_contract`. **Streaming/non-streaming parity** is automatic (both route through the gateway → same runtime).

---

## 8. Safety & Medical Boundary Plan

Implementation rules per scenario. **Beth may: observe, track, educate, prompt physician discussion. Beth may not: diagnose, prescribe, recommend dose changes.** Enforced structurally (no med-write authority on active CoS path) + a pre-narration safety classifier.

| Scenario | Beth MAY | Beth may NOT | Default |
|----------|----------|--------------|---------|
| Medication suggestions | Surface adherence patterns; "worth discussing with your physician" | Suggest starting/stopping/switching a med | Redirect to physician |
| Glucose-related med review | Narrate glucose-vs-dose-change *observation* (deterministic, w/ evidence) | Say "increase/decrease your insulin" | Frame as discuss-with-doctor |
| Exercise-fueling experiments | Propose & run a structured carb-timing experiment; report deterministic finding | Prescribe a fueling protocol | "An observation about your body; keep testing or discuss" |
| Supplement warnings | "This may duplicate X / interact — worth checking with your pharmacist" | Assert an interaction as clinical fact | Inform, don't block, don't advise |
| Possible duplicate meds | Warn on same name/NDC/class at scan-confirm | Auto-merge or auto-delete | Ask user |
| Dose changes | Record a user/provider-reported change as `MedicationEvent`; ask who directed it | Recommend a dose value | Capture, never suggest |
| Missed doses | Note streaks; ask if anything changed | Scold; imply medical consequence | Neutral observation |
| Low-glucose patterns | Surface the pattern + flag for physician; suggest tracking | Diagnose hypoglycemia; advise treatment | Discuss-with-doctor + safety note |
| High-glucose patterns | Same | Diagnose; advise med change | Same |
| Physician discussion prompts | Generate "questions to discuss" from open observations/monitoring gaps | Frame any item as a recommendation | Neutral, evidence-linked |

**Enforcement layers:** (1) structural — Beth has no medication write on the active path (audit-confirmed `DAY1_ACTION_ALLOWLIST` excludes med mutation); (2) a safety classifier screens diagnose/prescribe intents → decline+redirect template *before* the LLM; (3) the composed verdict never contains advice, so narration cannot leak it; (4) fail-closed confirmation gates (Phase-1 §14) before any canonical write.

---

## 9. Physician Export Plan (MVP)

**Infrastructure already exists** — reuse, don't rebuild: GDPR export serializes `Intake`/`IntakeLog` (`users/services/data_export.py:67`); Excel via openpyxl (`health/views_export.py`); PDF via WeasyPrint template→bytes (`capture/services/pdf.py`). **One dependency gap: WeasyPrint is not in `requirements.txt`** — Phase 7 must add it.

**MVP contents (all from canonical models, deterministic):**
- Current medications: name, dose, frequency, route/form (if available), start date, prescriber (`MedicalProvider`), pharmacy
- Current supplements (same shape)
- Recent dose changes (from `MedicationEvent`, with reason + date)
- Adherence summary (per med, 7/30/90d — from `medicine_utils`, the one authority)
- Key trends: glucose (`GlucoseEntry`/`DailyHealthSummary`), weight (`WeightEntry`), key labs (`LabResult`)
- Questions for physician (deterministic from open observations + monitoring gaps)
- Allergies/conditions (once those models exist)

**Formats:** print-friendly HTML view (`@media print`, immediate) + server-side PDF (WeasyPrint). **FHIR deferred** (no existing FHIR; optional Phase 7+). **Framing:** labeled *"self-tracked data for discussion, not a medical record."*

---

## 10. Image Workflow Migration Plan

Evolve the existing scan path — **no parallel image system**.

```
CURRENT:  bottle image → OpenAI Vision → prefilled IntakeCreateView (URL params) → user saves
TARGET:   bottle/front/back/Rx-label/pharmacy-doc → extraction (Vision + medicine_lookup NDC + pdfplumber/OCR for docs)
          → MedicationScanDraft (per-field confidence) → duplicate detection (name/NDC/class vs active Intake)
          → user review/confirm (low-confidence fields blank+highlighted; Rx-vs-supplement forced)
          → UAIO/IntakeCreateView writes Intake + MedicationEvent → draft.status=confirmed
```

**Reuse:** `scan` Vision path (`vision.py:665`), `medicine_lookup.py` (NDC→RxNorm enrichment), `apps/medical` `pdf_text_extractor`/`ocr_extractor` (pharmacy PDFs), existing `ScanConsent`/AI-consent/rate-limit gates.

**Privacy decisions (recommended defaults):**
- **Raw images:** **NOT retained by default** — preserves the current no-raw-image posture (`ScanLog:135`). Retention is **opt-in** via a separate consent (`MedicationImage`, encrypted) for users who want an evidence trail.
- **Thumbnails:** not retained by default (same rule).
- **Extracted metadata:** retained (it's the point) — in `MedicationScanDraft` until confirm, then folded into `Intake`/`MedicationEvent`; draft auto-expires.
- **Consent:** reuse `ScanConsent`; add a distinct image-retention consent (medication images are PHI).
- **Audit trail:** log scan→draft→confirm transitions (extend `MedicalAuditLog` or `ScanLog`), capturing extraction method + confidence, never raw PHI.

---

## 11. Implementation Roadmap

Small, independently shippable phases. Each ships dark behind a flag, is validated, then enabled.

### Phase 2.5 — Finish Stabilization *(do first; no schema)*
- **Goal:** close D3, D5; decide D4.
- **Files:** `templates/health/intake/intake_form.html` (render `{{ form.intake_subtype }}`, conditional on insulin); `apps/core/ai_eae/signal_aggregation.py`, `apps/dashboard_v2/services/dashboard_service.py`, `apps/dashboard_v2/compliance/adapters/medication.py` (route to `medicine_utils._enumerate_expected_doses`).
- **Schema:** none. **UI:** subtype field appears for insulin. **Beth/CoS:** none. **Signals:** D5 unifies denominator. 
- **Tests:** template-renders-subtype; golden-master expected-dose parity across all enumerators; D2 regression guard.
- **Observability:** add `wlj:ops:adherence_calc` health metric.
- **Rollback:** template + calc revert; pure correctness.
- **User-visible:** insulin users can set basal/bolus; dashboard adherence numbers agree.

### Phase 3 — Data Model Evolution *(flag: `medication_history`)*
- **Goal:** append-only history + structured clinical context.
- **Files:** `apps/health/models.py` (+`MedicationEvent`, `TreatmentPlan`, `Prescription`, `Pharmacy`, `MedicalCondition`, `DrugAllergy`, `SideEffectReport`; extend `Intake`), `apps/health/forms.py`, `apps/health/admin.py`, migrations (additive + single backfill), `apps/health/views.py` (Timeline read view).
- **Schema:** new nullable columns + new tables; reverse migrations tested.
- **UI:** Timeline view; provider/pharmacy link prompt (declinable).
- **Beth/CoS:** `_contract.treatment` section.
- **Tests:** event immutability; backfill idempotency/reversibility; FK-bridge; schema-parity gate.
- **Observability:** `wlj:ops:med_events`.
- **Rollback:** disable flag → tables dormant; reverse migration drops cleanly.
- **User-visible:** "tracking started [date]; earlier history not recorded"; structured provider/pharmacy.

### Phase 4 — Image-First Ingestion *(flag: `med_scan_v2`)*
- **Goal:** staged draft → confirm → Intake+MedicationEvent.
- **Files:** `apps/scan/services/vision.py`, `apps/scan/models.py` (+`MedicationScanDraft`, optional `MedicationImage`), `apps/scan/views.py`, new review template, `apps/health/views.py` (confirm write).
- **Schema:** `MedicationScanDraft` (+ optional consented `MedicationImage`).
- **UI:** review/confirm screen (confidence flags, dup warning, Rx-vs-supplement toggle).
- **Beth/CoS:** none (pre-canonical).
- **Tests:** nothing canonical until confirm; low-confidence blanking; dedupe; consent gating; draft expiry.
- **Observability:** `wlj:ops:med_extraction` (confidence dist, confirm/reject rate).
- **Rollback:** flag off → old prefill path; drafts ephemeral.
- **User-visible:** richer scan + explicit review.

### Phase 5 — Beth Intelligence *(flag: `med_intelligence`)*
- **Goal:** PIE/PRIE rules, EAE signal types, extended `_contract`, safety classifier.
- **Files:** `apps/core/ai_insights/rules_medicine.py` (new), `apps/core/ai_predictions/rules_medicine.py` (new), `apps/core/ai_eae/signal_aggregation.py` (new types), `apps/core/ai_signals/cross_domain_signals.py` (detectors), `state_builder.py` (`_contract.observations/monitoring`), safety classifier.
- **Schema:** none (reads existing).
- **Beth/CoS:** observations/monitoring/momentum surfaced as verdicts; per-med dose/freq/side-effects.
- **Tests:** verdict-inside (no atomic leak); safety-classifier blocks diagnose/prescribe; streaming parity; no-zero-fill.
- **Observability:** `wlj:ops:med_signals`, `wlj:ops:med_analyzer` (6h ISE task).
- **Rollback:** flag off → current `_contract`.
- **User-visible:** Beth discusses treatment momentum, patterns, physician questions.

### Phase 6 — Learning Plans *(flag: `med_experiments`; user-facing name "Learning Plans", internal models `IntakeExperiment`/`ExperimentObservation`)*
- **Goal:** user-driven, deterministic experiments.
- **Files:** `apps/health/models.py` (+`IntakeExperiment`, `ExperimentObservation`), experiment service, trigger detection (`WorkoutSession`/`CalendarEvent`), `_contract.experiments`.
- **Schema:** two new tables.
- **Tests:** deterministic finding (no LLM authorship); metric capture from canonical sources; trigger detection.
- **Observability:** `wlj:ops:med_experiments`.
- **Rollback:** flag off → tables dormant.
- **User-visible:** Beth proposes/runs experiments, reports findings.

### Phase 7 — Physician Mode *(flag: `physician_export`)*
- **Goal:** printable + PDF clinical export.
- **Files:** `requirements.txt` (+WeasyPrint), export service, export template, `apps/health/views.py`, extend `data_export.py`.
- **Schema:** none.
- **Tests:** deterministic content; adherence via `medicine_utils`; "not a medical record" framing present.
- **Observability:** export counts.
- **Rollback:** flag off → no export button.
- **User-visible:** one-click physician summary.

### Phase 8 — Advanced Cross-Domain *(flag: gated on data volume)*
- **Goal:** CDCE med↔biomarker detectors, PRIE forecasts, `DrugClass` catalog, predictive observations.
- **Files:** `apps/core/ai_cross_domain/cdce_engine.py` (detectors), PRIE rules, optional `DrugClass`.
- **Tests:** strength thresholds; min co-occurrence; correlation-not-causation framing.
- **Observability:** correlation telemetry, physician-flag rate.
- **Rollback:** flag off.
- **User-visible:** deeper cross-domain observations.

---

## 12. Risks & Open Questions

### Risks (Phase-2-specific, beyond Phase-1 R1–R10)
| # | Risk | Mitigation |
|---|------|-----------|
| P2-R1 | Building new EAE signals on the still-divergent D5 denominator | **Close D5 in Phase 2.5 before Phase 5** |
| P2-R2 | Fabricating historical dose changes during backfill | Single "started" event only; explicit "earlier history not recorded" labeling (§5.4) |
| P2-R3 | Fuzzy provider/pharmacy auto-linking links the wrong provider | No auto-match; user-confirmed linking only |
| P2-R4 | `TreatmentPlan.condition` FK ships before `MedicalCondition` | Sequence within Phase 3: conditions before plans |
| P2-R5 | D3 unrendered subtype blocks correct insulin scan-import (Phase 4) | D3 is a Phase 2.5 prerequisite |
| P2-R6 | PHI image retention enabled without distinct consent | Opt-in only; default no-retention preserved |
| P2-R7 | Extending `MedicalAuditLog` (apps/medical) for apps/health med events crosses the app boundary | Decide O-9 before Phase 4 |

### Open Questions
- **O-1 (RESOLVED):** Providers/conditions/allergies in `apps/medical`? → **No.** Providers = `apps.health.MedicalProvider`; conditions/allergies absent. 
- **O-2 (RESOLVED):** Home for new models? → **`apps/health`** (apps/medical is labs-only).
- **O-3:** Image retention default — opt-in (recommended) vs opt-out. *Confirm.*
- **O-4:** Experiment trigger automation — auto-detect + user-confirm capture (recommended). *Confirm.*
- **O-5:** Supplement clinical depth — track at med parity, defer ingredient-interaction modeling. *Confirm.*
- **O-6:** FHIR demand — defer unless validated. *Confirm.*
- **O-7:** Promote `IntakeSchedule` to `SoftDeleteModel` (fix cascade asymmetry)? Low priority. *Decide in Phase 3.*
- **O-8 (new): RESOLVED (C4) — a dedicated lightweight `Pharmacy` model** (`name`, `phone`, `address`, `rx_account`), NOT `MedicalProvider` specialty=pharmacy. A given pharmacy is represented in `Pharmacy` only — never duplicated as a `MedicalProvider` row. `Prescription.pharmacy`/`Intake.pharmacy` FK point at `Pharmacy`. (Unblocks Sprint 2 modeling.)
- **O-9 (new): RESOLVED (C4 direction) — `MedicationEvent` is the canonical *clinical* history; any audit log is *operational/security* only.** They must not overlap in what they record. Recommendation: extend `MedicalAuditLog` action choices for medication events (modify-before-add); if the cross-app boundary proves awkward, a `apps/health` med-audit model is acceptable provided it records only operational/security events, never clinical change history (that is the ledger's sole domain). Backlog item to be slotted at Sprint 3.
- **O-10 (new):** `DrugClass` — **deferred to Sprint 8**; rely on runtime `medicine_lookup` until then. The `Intake.drug_class` FK is deferred together with the `DrugClass` model (do not build the FK before the model). *Confirmed.*

---

## 13. Recommended Next Action

1. **Ship Phase 2.5 (stabilization) first** — finish **D3** (render `intake_subtype`) and **D5** (unify the EAE + two `dashboard_v2` dose enumerators onto `medicine_utils`), and decide **D4**. No schema, pure correctness, unblocks everything downstream. This is the single highest-leverage next step and is safe to start on explicit instruction.
2. **Resolve remaining open questions O-3, O-4** (a short decision pass) — they gate Sprint 3/4 (capture) and Sprint 11 (Learning Plans) respectively, NOT Sprint 1/2. (O-8/O-9/O-10 resolved in §12 per the Design Assurance corrections.)
3. **Then begin Phase 3 (additive data model)** behind `features.health.medication_history`, starting with `MedicationEvent` + the single-event backfill, sequencing `MedicalCondition` before `TreatmentPlan`.

No implementation has been performed in this phase. Awaiting explicit instruction to proceed (recommended: authorize **Phase 2.5 stabilization**).

---

*End of Phase 2. Analysis and planning only — no code, no migrations, no model creation, no UI changes.*
