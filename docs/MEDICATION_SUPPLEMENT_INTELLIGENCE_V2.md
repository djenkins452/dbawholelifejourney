# Medication & Supplement Intelligence v2 — Canonical Architecture Specification

**Status:** Phase 1 (Greenfield Architecture Design) — DESIGN ONLY, no implementation.
**Author:** Architecture pass, 2026-06-27.
**Scope:** The target architecture for WLJ's Medication & Supplement domain, reconciled against the current codebase for least-disruption evolution.
**Companion:** Read alongside the prior *Medication & Supplement Tracking Architecture Audit* (current-state evidence, defects D1–D5).

> **Reading note.** This document designs the *ideal* system first (Sections 5–15), then reconciles it to what exists (Section 16 onward). The single most important finding from grounding investigation: **WLJ already has ~60% of the substrate.** The unified `Intake` model, the `medicine` SAE state builder with a composed `_contract` verdict, EAE `medication_adherence`/`supplement_adherence` signal types, the cross-domain `medication_adherence_risk` detector, and a production OpenAI-Vision bottle-scan → `IntakeCreateView` confirm path all ship today. This is therefore an **evolution blueprint**, not a rip-and-replace. Greenfield thinking is used to set the *target*; the migration is deliberately additive.

---

## 1. Executive Summary

WLJ's medication domain today is a competent **tracker**: it records what you take (`health.Intake`), when you take it (`IntakeSchedule`/`IntakeLog`), computes adherence (`medicine_utils`), snapshots state for Beth (`build_medicine_state`), and can ingest a bottle photo into a pre-filled form (`scan` app). That is the floor, not the ceiling.

**Medication & Supplement Intelligence v2** elevates the domain from *"did you take it?"* to *"is your treatment working, and what should you and your physician pay attention to?"* It does this by adding four capabilities the current system lacks:

1. **A treatment timeline** — meds change over time (dose up, dose down, started, stopped, switched). Today the canonical model overwrites; v2 makes change history first-class and immutable.
2. **Cross-domain treatment intelligence** — correlating adherence and dose changes against glucose, weight, sleep, labs, nutrition, and exercise, using the existing CDCE/EAE machinery, never the LLM.
3. **A user-driven experiment framework** — Beth helps the user *learn what works for their body* via structured, time-boxed, deterministic observation (not prescription).
4. **Physician Mode** — one-click, evidence-grade exports (med list, dose history, adherence, biometric trends, discussion questions) in printable/PDF and optionally FHIR form.

Every capability obeys the WLJ data-flow law: **Raw Data → Canonical State → Signals → Cross-Domain Intelligence → Beth → LLM narration.** The LLM never determines truth. OCR never becomes truth. Every image-derived value is staged, reviewed, and confirmed before it enters canonical state. UAIO remains the sole write authority.

The reconciliation finding is favorable: the target can be reached by **extending five well-defined seams** (SAE `MODULE_BUILDERS`, EAE `signal_computers`, `ai_signals` `_DETECTORS`, CDCE `CORRELATION_DETECTORS`, ISE `SCHEDULED_TASKS`) plus **three new canonical models** (`MedicationEvent`, `TreatmentPlan`, `IntakeExperiment`) and **one new staging model** (`MedicationScanDraft`). No existing canonical model is rebuilt; `Intake` remains the source of truth and gains history *around* it, not *inside* it.

---

## 2. Vision

WLJ should not become another medication reminder app. Reminder apps answer a yes/no question. WLJ should answer the questions that change outcomes:

- **Is my treatment working?** (effectiveness over time, against real biometrics)
- **What patterns are emerging?** (adherence drift, dose-response, side-effect correlations)
- **What should I pay attention to?** (refill risk, treatment instability, monitoring gaps)
- **What should I discuss with my physician?** (structured, evidence-backed talking points)

The domain becomes a **longitudinal treatment intelligence system**: it remembers every dose change, every provider decision, every stop/start, and it reads those against the body's response across all health domains. Beth narrates that intelligence — she never generates it, never diagnoses, never prescribes.

The differentiator vs. traditional trackers: **traditional trackers are write-once and present-tense; WLJ is append-only and longitudinal, and it reasons across domains.** A reminder app knows you take Mounjaro. WLJ knows your Lantus has been reduced three times as your weight fell 18 lbs, that your fasting glucose is most elevated the morning after <6h sleep, and that those are worth raising at your next endocrinology visit — and it can hand your physician a one-page evidence summary to support the conversation.

---

## 3. Guiding Principles

These are non-negotiable and govern every later section.

1. **LLM-last.** The LLM narrates composed, deterministic state objects with the verdict already inside. It never reasons from raw atomic signals and never determines clinical truth. *(WLJ memory: "Beth consumes briefings, not signals.")*
2. **Raw → State → Signals → Intelligence → Beth.** One direction. No request-path live computation of heavy analytics; compute in background, read from cache/snapshot. *(CLAUDE.md Observability rule.)*
3. **Single Source of Truth.** `health.Intake` is the canonical record of *what is currently taken*. Exactly one adherence authority (`medicine_utils`). No domain owns another domain's facts.
4. **Modify before adding.** Extend existing seams (EAE signal types, SAE builders, CDCE detectors) before inventing new subsystems. New models only where no existing model fits.
5. **OCR is never truth.** Every extracted value is a *draft* with a confidence score, staged separately, reviewed, and explicitly confirmed by the user before it touches canonical state.
6. **Append-only history.** Medication facts change over time. Changes are recorded as immutable events, never silent overwrites. The current `Intake` row is a projection of its event history.
7. **UAIO is the sole write authority.** All canonical writes flow through the orchestrator/confirmed-form path. Vision, signals, and Beth produce drafts and verdicts, never direct writes.
8. **Schema parity.** Any user-settable field exists consistently across model ↔ form ↔ API ↔ AI-intent schema ↔ handler ↔ prompt. *(CLAUDE.md AI Engineering rule.)*
9. **No silent failures.** No `except Exception: pass` on intelligence paths. Dead subscribers and swallowed imports are defects, not acceptable degradation. *(Defect D1.)*
10. **Observability required.** Every new signal, extraction, and calculation emits telemetry. If a capability bounds its coverage, it logs what it dropped.
11. **Safety is fail-closed.** When the system is uncertain (dose ambiguity, prescription vs supplement, conflicting bottles), it defaults to *ask the user*, never to *assume and write*.

---

## 4. Current-State Constraints

What the design must respect because it already exists and is correct, and what it must work around.

**Assets to build on (do not rebuild):**

| Asset | Location | Role in v2 |
|-------|----------|-----------|
| `Intake` (unified med+supplement, `intake_type`) | `apps/health/models.py:2282` | Remains canonical "current truth" |
| `IntakeSchedule` / `IntakeLog` | `apps/health/models.py:2609` / `:2732` | Remain the dosing-plan + dose-event records |
| `medicine_utils` adherence | `apps/health/medicine_utils.py:19` | Remains the **single** adherence authority |
| `build_medicine_state` + `_contract` verdict | `apps/core/ai_state/state_builder.py:3736`, `:5818` | Extended, not replaced — the Beth-facing composer |
| EAE signal types `medication_adherence`, `supplement_adherence` (+supplement pattern types) | `apps/core/ai_eae/signal_aggregation.py:53-135` | Extended with new types |
| Cross-domain `medication_adherence_risk` detector | `apps/core/ai_signals/cross_domain_signals.py:235` | Joined by new detectors |
| Bottle-scan Vision → prefilled `IntakeCreateView` | `apps/scan/services/vision.py:665`, `apps/health/views.py:3508` | Becomes the *draft-staging* entry point |
| Medical PDF/OCR extractors (`pdfplumber`+`pytesseract`) | `apps/medical/services/` | Reused for pharmacy-paperwork ingestion |
| GDPR data export already includes `Intake`/`IntakeLog` | `apps/users/services/data_export.py:67` | Foundation for Physician Mode export |
| `DailyHealthSummary` (80+ cross-domain fields) | `apps/health/models.py:5956` | Primary cross-domain join surface |
| CDCE correlation engine + `DomainCorrelation` | `apps/core/ai_cross_domain/cdce_engine.py:893` | Home for med↔biometric correlations |
| ISE scheduler + SAME 60s / ISE 300s cadence | `apps/core/ai_scheduler/scheduler_registry.py:14` | Home for the 6h medication analyzer |

**Constraints / known defects the design must not inherit:**

- **D1 — dead PIE subscriber:** `health.medication.taken` fires but `check_medication_insights` does not exist; the `ImportError` is swallowed. v2 must implement real PIE medicine rules and un-swallow the failure. *(`apps/core/events/subscribers.py:206`.)*
- **D2 — adherence chart drift:** the report's daily chart uses a logs-only denominator and defaults to 100% on zero logs, contradicting the `medicine_utils` headline. v2 routes *all* adherence reads through the one util. *(`apps/health/views.py:4538`.)*
- **D3 — orphaned `intake_subtype`:** in the form, never rendered; insulin basal/bolus unreachable in UI. v2's image-first + CRUD work fixes this. *(template absent.)*
- **D4 — no AI create/update intent:** "Would you like to add it?" is a dead-end. v2 adds confirmed create/update intents. *(`apps/ai/action_handlers.py:1899`.)*
- **D5 — four divergent "expected dose" enumerations:** v2 collapses to the single util. *(`apps/dashboard_v2/...`, `ai_eae/signal_aggregation.py`.)*
- **No append-only history today:** `Intake` overwrites. This is the single biggest greenfield gap.
- **No experiment framework, no FHIR, WeasyPrint not in `requirements.txt`.** All greenfield-with-known-pattern.

---

## 5. Proposed Architecture (Layered Overview)

```
┌─ LAYER 0: INGESTION ────────────────────────────────────────────────────────┐
│  Manual entry  │  Bottle image  │  Pharmacy PDF  │  Med-list photo  │ HealthKit │
│       │              │ (Vision)        │ (pdfplumber/OCR)   │ (Vision)      │  (sync)   │
└───────┼──────────────┼─────────────────┼────────────────────┼───────────────┼──────────┘
        │              ▼─────────────────▼────────────────────▼               │
        │        ┌───────────────────────────────────────────┐                │
        │        │  STAGING: MedicationScanDraft (per-field   │                │
        │        │  confidence, never canonical)              │                │
        │        └───────────────────┬───────────────────────┘                │
        │             user review + explicit confirm                          │
        ▼─────────────────────────────▼──────────────────────────────────────▼
┌─ LAYER 1: CANONICAL STATE (Single Source of Truth) ──────────────────────────┐
│  Intake (current) ── MedicationEvent (append-only history) ── TreatmentPlan   │
│  IntakeSchedule ── IntakeLog ── Provider ── Pharmacy ── Prescription           │
│  IntakeExperiment + ExperimentObservation                                     │
│         (writes ONLY via UAIO / confirmed forms)                              │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                 │ deterministic compute (background, cached)
                                 ▼
┌─ LAYER 2: SIGNALS (deterministic, typed, trust-classified) ──────────────────┐
│  medicine_utils (adherence authority)                                         │
│  EAE signal_computers: adherence, trend, momentum, refill_risk, instability   │
│  CDCE detectors: med↔glucose, dose-change↔weight, supplement↔biomarker        │
│  PIE rules_medicine.py  │  PRIE rules_medicine.py (refill/adherence forecast)  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                 ▼
┌─ LAYER 3: COMPOSED INTELLIGENCE (verdict inside) ────────────────────────────┐
│  build_medicine_state._contract  (extended: timeline, momentum, observations) │
│  build_cos_intelligence  (medicine verdict surfaced into every conversation)  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                 ▼
┌─ LAYER 4: BETH / LLM (narration only) ───────────────────────────────────────┐
│  Reads composed verdicts. Recognizes patterns. Suggests experiments &         │
│  physician discussions. NEVER diagnoses, prescribes, or writes directly.      │
└──────────────────────────────────────────────────────────────────────────────┘
┌─ CROSS-CUTTING: Physician Mode (export) │ Observability (telemetry) │ Safety ─┐
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key architectural decisions:**

- **AD-1 — History lives beside `Intake`, not inside it.** A new append-only `MedicationEvent` ledger records every started/stopped/dose-changed/provider-changed event. `Intake` stays the fast "current truth" projection. This preserves the single source of truth for *current* state while making history first-class.
- **AD-2 — Staging is a real model now, not an unsaved form.** The current "draft = pre-filled form" pattern works for one clean bottle but cannot represent multi-field confidence, multi-bottle batches, or pharmacy-document line items. A `MedicationScanDraft` model stages extraction with per-field confidence; it is explicitly *not* canonical and is consumed on confirm.
- **AD-3 — One medicine domain, extended.** All new intelligence composes into the existing `build_medicine_state._contract` and the `medicine` SAE module. We do not create a parallel "treatment" domain that Beth would have to reconcile.
- **AD-4 — Cross-domain reasoning stays deterministic.** Correlations are computed by CDCE/EAE detectors and stored as `DomainCorrelation`/signal rows with a narrative + evidence. Beth narrates the stored verdict; she never runs the correlation herself.

---

## 6. Domain Model

The target canonical model. Models marked **(exists)** are kept; **(extend)** gain fields; **(new)** are introduced. All new models inherit `UserOwnedModel`/`SoftDeleteModel` semantics unless noted.

### 6.1 Core records

- **`Intake`** *(exists, extend)* — `apps/health/models.py:2282`. Current truth for an actively-tracked substance. Already unified (`intake_type` med/supplement), with dose, frequency, schedule linkage, refill/supply, provider/pharmacy free-text fields, status lifecycle. **Extend with:** `ndc_code`, `strength` (structured: value+unit, distinct from free-text `dose`), `sig_text` (verbatim SIG/instructions as written), `drug_class` (FK → `DrugClass`), `provider` (FK → `Provider`, replacing free-text), `pharmacy` (FK → `Pharmacy`), `current_event` (FK → latest `MedicationEvent`), `expiration_date`, `monitoring_requirements` (e.g., "A1c q3mo"). Free-text fields are retained for backward-compat and downgraded to fallbacks.

- **`IntakeSchedule`** *(exists)* — dosing plan. Consider promoting to `SoftDeleteModel` to fix the cascade-asymmetry noted in the audit (low priority).

- **`IntakeLog`** *(exists)* — dose events (taken/missed/skipped/late) + per-event insulin dose fields. Remains the adherence event source.

### 6.2 History & treatment

- **`MedicationEvent`** *(new — the cornerstone)* — append-only, immutable ledger. One row per clinically-meaningful change. Fields: `intake` (FK), `event_type` (started | stopped | paused | resumed | dose_increased | dose_decreased | frequency_changed | provider_changed | pharmacy_changed | formulation_changed | discontinued), `effective_date`, `previous_value` / `new_value` (JSON snapshots of the changed attribute), `reason` (provider_directed | side_effect | cost | effectiveness | user_choice | other), `reason_detail`, `provider` (FK, nullable), `source` (manual | scan | pharmacy_doc | cos_confirmed), `recorded_at`. **Never updated, never hard-deleted** (correction = a new compensating event). This is what powers the Timeline (Section 5/§ Medication Timeline) and treatment-effectiveness reasoning.

- **`TreatmentPlan`** *(new)* — groups one or more `Intake`s pursuing a shared clinical goal (e.g., "Type 2 diabetes management" = Mounjaro + Lantus + metformin). Fields: `name`, `condition` (FK → `MedicalCondition`), `goal_narrative`, `started_date`, `status`, `primary_provider` (FK). Enables "is *this treatment* working" rather than "is this pill working," and frames cross-domain observations.

### 6.3 People, places, prescriptions

- **`Provider`** *(new — verify against `apps/medical`)* — prescribing physician. Fields: `name`, `specialty`, `practice`, `phone`, `notes`. *Open question O-3: a provider concept may already exist in `apps/medical`; reconcile before creating.*
- **`Pharmacy`** *(new)* — `name`, `phone`, `address`, `rx_account`.
- **`Prescription`** *(new)* — the prescription record distinct from the substance: `intake` (FK), `provider` (FK), `pharmacy` (FK), `rx_number`, `written_date`, `quantity`, `refills_authorized`, `refills_remaining`, `expiration_date`, `sig_text`. Multiple prescriptions over time map to the same `Intake` via `MedicationEvent`s.

### 6.4 Clinical context

- **`DrugClass`** *(new, reference data)* — `name`, `class_type` (e.g., GLP-1 agonist, basal insulin, statin), `monitoring_defaults`, `common_side_effects` (reference list, **not** user truth). Curated catalog, like `LabTestCatalog`.
- **`MedicalCondition`** *(new — verify against `apps/medical`)* — user's conditions; links treatments to indications.
- **`Allergy`** *(new — verify against `apps/medical`)* — substance + reaction; powers interaction/duplicate warnings.
- **`SideEffectReport`** *(new)* — user-reported, never inferred: `intake` (FK), `symptom`, `severity`, `started_date`, `ongoing`, `notes`. Distinct from the `DrugClass.common_side_effects` reference list. *(Audit found no side-effect field exists today; this fills the §5 Beth blind spot.)*

### 6.5 Images & staging

- **`MedicationScanDraft`** *(new — the staging model)* — holds extraction output pending confirmation. Fields: `user` (FK), `source_type` (bottle | pharmacy_pdf | med_list | manual_assist), `extraction_method` (vision | ocr | mixed), `raw_extraction` (JSON), `field_confidences` (JSON: per-field 0–1), `overall_confidence`, `status` (pending_review | confirmed | rejected | expired), `created_intake` (FK, nullable, set on confirm), `image_ref` (see image-retention decision below), `expires_at`. **Explicitly non-canonical.** Consumed by the review workflow; auto-expires.
- **`MedicationImage`** *(new, optional/consented)* — persisted bottle/document image evidence. Because medication images are PHI, **retention is opt-in and separately consented** (mirroring `ScanConsent`). Default behavior preserves the existing no-raw-image privacy posture; the model exists for users who *want* an evidence trail. Fields: `intake` (FK), `image` (encrypted storage), `image_type` (bottle | label | document), `captured_at`, `linked_event` (FK → `MedicationEvent`).

### 6.6 Relationships & versioning

- **Medication relationships** are expressed through `TreatmentPlan` membership and `DrugClass` (for "same-class duplicate" detection), not a free-form graph in v1.
- **Historical versions** are the `MedicationEvent` ledger + `Prescription` rows; the current `Intake` is always the head projection. No separate version table.

> **Design guardrail:** none of the above *replaces* `Intake`. `Intake` is the head; everything new is history, context, or staging *around* it. This keeps Single Source of Truth intact while making the domain longitudinal.

---

## 7. State Model

State is what Beth reads. It must be **composed and verdict-bearing**, computed in the background, cached, and read-only on the request path.

### 7.1 The extended `medicine` state contract

`build_medicine_state` already returns operational keys plus a `_contract` overlay (`summary` / `today` / `upcoming` / `alerts`) and a resolved `medication_status` + `medication_status_reason` verdict (`state_builder.py:3936-4050`). v2 extends the `_contract` with three new composed sections — **all verdicts pre-resolved, no atomic signals exposed:**

```
medicine._contract = {
  summary:        { active_meds, active_supplements, counts, ... }   # exists
  today:          { schedule_status_today, taken/missed/pending }    # exists
  upcoming:       { next_dose, refills_due }                         # exists
  alerts:         { refill_risk, missed_streak, ... }                # exists
  medication_status / _reason:  verdict                              # exists
  # --- NEW in v2 ---
  treatment:      {                                                  # NEW
                     active_plans: [{ name, momentum_verdict, since }],
                     recent_changes: [{ med, change, date, reason }],     # last 90d MedicationEvents
                     treatment_momentum: "improving|stable|unstable|insufficient_data",
                     momentum_reason: "<deterministic narrative>"
                  }
  observations:   [                                                  # NEW (from CDCE/EAE, pre-computed)
                     { code, domains:[...], strength, narrative, evidence, confidence,
                       discuss_with_physician: bool }
                  ]
  monitoring:     { due:[{label, last_done, overdue_by}], ... }      # NEW (e.g., A1c overdue)
  experiments:    { active:[{hypothesis, progress, current_finding}] } # NEW (read-only summary)
}
```

### 7.2 Composition rules

- **Verdict-inside.** `treatment_momentum`, each `observation`, and `medication_status` are *resolved strings/enums with a deterministic reason*, computed by Layer-2 signal code. Beth narrates them; she does not derive them. *(WLJ memory: Beth = briefing consumer.)*
- **No-zero-fill.** Absent data yields `insufficient_data`, never a fabricated 0 or 100. *(Mirrors EAE's no-zero-fill rule; fixes the spirit of D2.)*
- **Snapshot-first.** The contract is built by the 6h background analyzer and the SAME/PIE refresh, written to `UserState.state_data["medicine"]` and cached. Request-path readers (chat, domain_state tool) read the snapshot only.
- **Registration.** Stays in `MODULE_BUILDERS["medicine"]` (`state_builder.py:5818`). No new SAE module — one medicine domain.

### 7.3 What Beth can finally see (closing audit blind spots)

The audit found Beth never sees per-med dose, frequency, or side effects. v2's contract surfaces, per active med: `name, strength, sig_text, frequency, adherence_7d/30d, last_change, side_effects[]` — plus treatment momentum and physician-discussion observations. This is the concrete fix for the §5 visibility gap.

---

## 8. Signal Model

Signals are deterministic, typed, trust-classified, and emitted in the background. v2 **extends the three existing signal seams** rather than inventing a registry.

### 8.1 EAE base signals (extend `SIGNAL_TYPE_DOMAIN` + `signal_computers`)

`apps/core/ai_eae/signal_aggregation.py:53-135`. Existing: `medication_adherence`, `supplement_adherence`, `supplement_consistency_pattern`, `supplement_outcome_correlation`, `compliance_drift`. **New types:**

| Signal type | Class | Meaning | Computed from |
|-------------|-------|---------|---------------|
| `adherence_trend` | derived_pattern | 7d vs 30d adherence direction | `medicine_utils` over windows |
| `treatment_momentum` | derived_pattern | composite of adherence trend + recent dose changes + linked biomarker direction | `MedicationEvent` + adherence + DailyHealthSummary |
| `refill_risk` | inferred_behavior | projected days-to-empty vs lead time | `Intake.days_until_empty` + adherence |
| `treatment_instability` | derived_pattern | frequency of recent changes / on-off cycling | `MedicationEvent` density |
| `monitoring_gap` | derived_pattern | required lab/check overdue | `Intake.monitoring_requirements` vs `LabResult` recency |
| `dose_response_observation` | derived_pattern | biomarker shift co-timed with a dose change | `MedicationEvent` ± window vs biometric series |

All obey **no-zero-fill** (return `None` when no real data) and emit a confidence per the existing ladder (EXPLICIT > NOT_EXPECTED > DERIVED > ABSENCE). **D5 fix:** every "expected dose" count comes from the one `medicine_utils` enumerator; the divergent copies are deleted.

### 8.2 Cross-domain narrative signals (extend `_DETECTORS`)

`apps/core/ai_signals/cross_domain_signals.py:398-407`. Existing: `medication_adherence_risk`. **New detectors** (`_detect_*(state)` pure functions appended to `_DETECTORS`): `_detect_dose_change_biomarker_shift`, `_detect_supplement_outcome`, `_detect_monitoring_overdue`. Each returns the standard dict (`signal_code, domains[], severity, confidence, summary, evidence{}, recommended_action`) and flows into the unified feed.

### 8.3 PIE / PRIE rules (the real D1 fix)

- **`apps/core/ai_insights/rules_medicine.py`** *(new)* — register `BaseInsightRule` subclasses with `@register`: adherence-drop insight, missed-streak insight, side-effect-onset-after-change insight, monitoring-gap insight. This is the function set the dead `health.medication.taken` subscriber should have called. **Implement these and wire the subscriber to a real `run_insights(user, event)` path; remove the swallowed `ImportError`.**
- **`apps/core/ai_predictions/rules_medicine.py`** *(new)* — register `BasePredictionRule` subclasses with `@register_prediction`: refill-exhaustion forecast, adherence-trajectory forecast.

### 8.4 Signal taxonomy summary

```
Layer-2 medicine signal taxonomy
├─ Adherence:     medication_adherence*, supplement_adherence*, adherence_trend, compliance_drift*
├─ Treatment:     treatment_momentum, treatment_instability, dose_response_observation
├─ Operational:   refill_risk, monitoring_gap
├─ Cross-domain:  medication_adherence_risk*, dose_change_biomarker_shift, supplement_outcome*
└─ Predictive:    refill_exhaustion_forecast (PRIE), adherence_trajectory (PRIE)
   (* = already exists today)
```

---

## 9. Cross-Domain Intelligence

This is the heart of "is your treatment working." It is **entirely deterministic** — CDCE/EAE compute correlations and store verdicts; Beth narrates.

### 9.1 Mechanism

Home: **CDCE** (`apps/core/ai_cross_domain/cdce_engine.py`). Add medication-aware detectors to `CORRELATION_DETECTORS` (`:893`), which today has none for medication. Each detector reads canonical series (via `DailyHealthSummary` for fast rollups, or domain models for detail), computes co-occurrence/strength against the existing thresholds (0.30/0.50/0.70), and stores a `DomainCorrelation` with `narrative`, `strength`, `direction`, `evidence`, and a `discuss_with_physician` flag. Gated by domain-enabled + SAE freshness ≤6h (existing CDCE gate).

### 9.2 Canonical cross-domain joins (grounded in real models)

| Medication question | Joins against (canonical model, file:line) |
|---------------------|--------------------------------------------|
| Does glucose respond to dose changes? | `GlucoseEntry` (`health:1054`), `MealGlucoseResponse` (`health:6306`), `MedicationEvent` |
| Weight vs treatment (e.g., GLP-1) | `WeightEntry` (`health:519`), `BodyCompositionEntry` (`health:4592`) |
| Sleep ↔ next-day fasting glucose ↔ meds | `SleepEntry` (`health:4161`) + glucose + `Intake` |
| Exercise-induced lows vs insulin | `WorkoutSession` (`health:1660`), `StepsEntry` (`health:760`), glucose |
| Nutrition (protein/carbs) ↔ satiety on GLP-1 | `FoodEntry` (`health:3230`), `DailyNutritionSummary` (`health:3512`) |
| Labs vs treatment effectiveness | `LabResult` (`medical:495`), `LabPanel` (`medical:236`) |
| Vitals (BP/HR) vs medication | `BloodPressureEntry` (`health:1232`), `HeartRateEntry` (`health:713`) |
| Hydration ↔ supplement tolerance | `WaterEntry` (`health:874`) |
| Adherence vs schedule/illness changes | `IntakeLog` + `CalendarEvent` (`calendar_engine:13`) |
| Treatment goals | `LifeGoal` (`purpose:190`), `TreatmentPlan` |

`DailyHealthSummary` (`health:5956`, 80+ fields) is the primary fast join surface; it already aggregates glucose, weight, sleep, vitals, nutrition, and medication adherence per user-day.

### 9.3 Output contract

Each cross-domain finding becomes an `observation` in `medicine._contract.observations` (§7.1) with a deterministic narrative, evidence, confidence, and a `discuss_with_physician` boolean. Example stored verdict: *"Over the last 90 days, your three Lantus dose reductions each followed a ≥4 lb weight decrease (strength 0.71, 3/3 co-occurrences). Worth discussing with your endocrinologist."* Beth reads and narrates this; she never computes it and never frames it as advice.

---

## 10. Beth Intelligence

### 10.1 What Beth understands (reads from the composed contract)

- Current treatment (active plans, meds, supplements, doses, frequencies, SIG)
- Adherence (7d/30d, trend, missed streaks, per-med and per-supplement)
- Recent dose changes and their reasons (from `MedicationEvent`, last 90d)
- Treatment momentum verdict (improving/stable/unstable/insufficient_data)
- Refill risk and monitoring gaps
- Cross-domain observations flagged for physician discussion
- Active experiments and their current (deterministic) findings
- User-reported side effects

### 10.2 What Beth does with it

- **Recognizes patterns** by narrating stored observations ("your fasting glucose runs higher after short sleep").
- **Suggests experiments** ("want to test whether 20g carbs before long rides reduces your post-ride lows? I can track it over four rides").
- **Surfaces physician talking points** ("three things worth raising at your next visit…").
- **Helps organize** ("here's your current med list and recent changes for your appointment").
- **Asks clarifying questions** ("was that dose change your doctor's call or your own?") to enrich `MedicationEvent.reason`.

### 10.3 Hard boundaries (see Section 14 for the full safety model)

Beth **never** diagnoses, prescribes, recommends a dose/medication change, interprets labs as clinical findings, or contradicts a provider. When asked to, she declines and redirects to the physician-discussion framing. These boundaries are enforced structurally: Beth has **no write authority** over medication canonical state on the active CoS path (the audit confirmed `DAY1_ACTION_ALLOWLIST` has no medication mutation), and the safety gate (Section 14) classifies and blocks unsafe intents *before* narration.

---

## 11. Experiment Framework

A genuinely new capability: Beth helps the user **learn what works for their body** through structured, deterministic, time-boxed observation. **Not** prescription, **not** clinical trial — personal pattern discovery.

### 11.1 Model

- **`IntakeExperiment`** *(new)* — `user` (FK), `hypothesis` (text), `linked_intake` / `linked_plan` (FK, nullable), `protocol` (JSON: what to vary, what to measure, n iterations, trigger condition), `metrics` (list of canonical signals to capture, e.g., starting_glucose, lowest_glucose, recovery_time), `trigger` (e.g., "ride > 60 min"), `target_n`, `status` (proposed | active | complete | abandoned), `started_at`, `completed_at`, `finding` (deterministic summary, nullable).
- **`ExperimentObservation`** *(new)* — one row per iteration: `experiment` (FK), `occurred_at`, `captured_metrics` (JSON, pulled from canonical models — never typed-in-as-truth where a sensor exists), `user_notes`, `context` (JSON: linked workout/meal/etc.).

### 11.2 Flow

1. **Hypothesis** — Beth proposes or the user states one ("20g carbs before rides > 60 min may reduce post-ride lows").
2. **Protocol** — deterministic: which canonical metrics, trigger condition, target n (e.g., 4 rides).
3. **Collection** — when the trigger fires (detected from `WorkoutSession`/`CalendarEvent`), the system captures the metrics from canonical sources automatically and prompts only for subjective notes (energy, observations).
4. **Summary** — after target n, a **deterministic** summarizer computes the finding (e.g., "post-ride low was higher on all 4 carb rides; mean lowest glucose 78 vs 61"). Beth narrates the finding; she does not invent it.
5. **No prescription** — the finding is framed as *an observation about your body*, with a "worth discussing with your physician / want to keep testing?" close. Never "you should do X."

### 11.3 Reuse, not reinvention

The grounding investigation found **no experiment framework exists** — but the *primitives* do: CDCE's `DomainCorrelation` machinery (co-occurrence + strength), PRIE's `validate_predictions` daily task (predicted-vs-actual), and canonical metric capture. `IntakeExperiment` is a thin orchestration over these, not a new statistics engine.

---

## 12. Physician Mode

One-click, evidence-grade export for clinical visits.

### 12.1 Contents

- Current medication list (name, strength, SIG, frequency, prescriber, pharmacy)
- Current supplement list
- Dose/treatment **change history** (from `MedicationEvent`, with reasons and dates)
- Adherence summary (per med, 7/30/90d, from `medicine_utils`)
- Relevant biometric trends (glucose, weight, BP, labs) over the treatment window
- Cross-domain observations flagged `discuss_with_physician`
- Active experiments and their findings
- A generated **"questions to discuss"** list (deterministic from open observations + monitoring gaps)
- Allergies and conditions

### 12.2 Formats & reuse

- **PDF / printable** — reuse the `apps/capture/services/pdf.py` template→bytes pattern. **Constraint:** WeasyPrint is used there but **not in `requirements.txt`**; Physician Mode must add WeasyPrint (or reportlab) as an explicit dependency. *(Grounding finding.)*
- **Structured export** — extend the existing GDPR export (`apps/users/services/data_export.py`, which already serializes `Intake`/`IntakeLog`) with the new history/treatment models.
- **FHIR (Phase 7+, optional)** — no FHIR exists today (greenfield). If pursued, map `Intake`→`MedicationStatement`, `Prescription`→`MedicationRequest`, `LabResult`→`Observation`, `Allergy`→`AllergyIntolerance`, `Provider`→`Practitioner`. Treated as a later-phase enhancement, not v2 core.

### 12.3 Safety framing

The export is explicitly labeled *"user-reported and self-tracked data for discussion; not a medical record."* Observations are framed as patterns to discuss, never as findings or recommendations.

---

## 13. Image-First Workflow

The ideal capture experience, staged and confirmed — extending the existing scan pipeline.

### 13.1 Entry points (all converge on staging)

1. **Manual entry** — existing `MedicineForm`, enriched with new structured fields.
2. **Bottle image** — existing `scan` Vision path (`vision.py:665`), now writing a `MedicationScanDraft` instead of a URL-prefilled form.
3. **Pharmacy paperwork (PDF/photo)** — reuse `apps/medical/services/{pdf_text_extractor,ocr_extractor}.py` (`pdfplumber`+`pytesseract`) for documents; Vision for photos. Multi-line documents yield multiple draft line-items.
4. **Medication list photo** — Vision, multi-item extraction → multiple drafts.
5. **HealthKit** — sync continues to flow into health models via `apps/mobile` (unchanged).

### 13.2 Extraction targets

name, strength, SIG, dosage, frequency, prescribing physician, pharmacy, refill info, expiration, quantity, NDC (when present), **per-field confidence score**, overall confidence.

### 13.3 Staging → review → confirm (the law)

```
image/doc → extract → MedicationScanDraft (per-field confidence, status=pending_review)
   → REVIEW SCREEN:
        • every field editable
        • low-confidence fields BLANK + highlighted (never silently guessed)
        • prescription-vs-supplement toggle FORCED (never auto-classified as truth)
        • duplicate check: warn if name/NDC/drug-class matches an active Intake
        • "old bottle vs current Rx" prompt if a matching active med has a different dose
   → user edits + CONFIRMS
   → UAIO / IntakeCreateView writes Intake (+ MedicationEvent "started" or "dose_changed")
   → draft.status=confirmed, draft.created_intake set
   → optional: persist MedicationImage IF user consented to image retention
```

**No OCR value becomes canonical without explicit confirmation.** Drafts auto-expire (`expires_at`). The existing `ScanConsent` + AI-consent + rate-limit gates are reused; image retention is a *separate* opt-in because medication images are PHI.

---

## 14. Safety Model

Safety is **fail-closed**: uncertainty defaults to asking, never to assuming.

### 14.1 Beth's boundaries

| Beth NEVER | Beth MAY |
|------------|----------|
| Diagnose | Recognize and narrate stored patterns |
| Prescribe or recommend a medication | Suggest a structured experiment |
| Recommend a dose change (up/down/stop) | Suggest collecting more information |
| Interpret labs as clinical findings | Recommend discussing a trend with a physician |
| Override or contradict a provider | Provide general educational context (clearly labeled) |
| Assert drug interactions as fact | Surface a *possible* duplicate/interaction as "worth checking with your pharmacist" |
| Treat OCR/image text as truth | Help organize and export information |

Enforcement is **structural, not just prompt-based**: (a) Beth has no medication write authority on the active CoS path; (b) a safety classifier screens medication intents and routes diagnose/prescribe requests to a decline+redirect template *before* the LLM narrates; (c) all clinical-sounding output is gated through the composed verdict, which never contains advice.

### 14.2 Confirmation requirements before any canonical write

Every one of these **requires explicit user confirmation** (no silent write):

| Situation | Required behavior | Safe default |
|-----------|-------------------|--------------|
| **OCR uncertainty** (low field confidence) | Blank + highlight field; require user to fill/verify | Do not write the uncertain field |
| **Prescription vs supplement** | Forced explicit toggle on review | Classify as `medication` (stricter handling) until confirmed |
| **Dose ambiguity** ("1–2 tablets") | Show verbatim SIG; require user to set structured dose | Store SIG text; leave structured dose blank |
| **Frequency ambiguity** | Same — capture SIG verbatim, require structured choice | `as_needed`/`is_prn` until clarified |
| **"Take as needed"** | Set `is_prn=True`; do not generate fixed schedule | PRN, no adherence-miss penalties |
| **Multiple bottles, same medicine** | Treat as same `Intake`; ask if dose changed → if yes, `MedicationEvent` | Do not create a duplicate Intake |
| **Old bottle vs current Rx** | If active med exists with different dose, ask "current or historical?" | Assume historical; do not overwrite current truth |
| **Provider-directed change** | Ask "did your doctor direct this?" → set `MedicationEvent.reason=provider_directed` | Record reason as `unknown`, never assume |
| **Discontinued med** | `MedicationEvent` (discontinued) + `Intake.status` → completed; **never hard-delete** (preserve history) | Soft-complete, retain |
| **Duplicate supplement** | Warn on same name/ingredient/drug-class; ask merge vs separate | Do not auto-merge |
| **Possible interaction / allergy match** | Surface as "worth checking with your pharmacist" — never as a clinical assertion | Inform, do not block, do not advise |

### 14.3 Principle

When in doubt, **stage and ask**. The canonical state is only ever advanced by a confirmed user action through UAIO. The cost of a missing field is a follow-up question; the cost of a wrong silent write is a clinical-safety incident. The system always pays the former.

---

## 15. Observability

Every new capability emits telemetry. Background-compute → cache → read-only request path is mandatory (CLAUDE.md).

| Concern | Metric | Mechanism |
|---------|--------|-----------|
| Image parsing quality | per-field + overall confidence distribution; extraction method mix | `MedicationScanDraft` aggregates → `cache.set("wlj:ops:med_extraction", ...)` |
| Confirm vs reject rate | % drafts confirmed, fields edited per draft | draft lifecycle telemetry |
| Adherence calc health | runs, anomalies, **zero-data vs 100% guard** (D2 regression guard) | `medicine_utils` instrumentation |
| Signal generation | counts per signal type, confidence distribution, no-zero-fill compliance | extends EAE `wlj:ops:signal_production` (`ai_eae/tasks.py:23`) |
| Cross-domain observations | correlations found, strength distribution, physician-flag rate | CDCE telemetry |
| Beth reasoning inputs | which contract sections were populated vs `insufficient_data` | contract-build telemetry |
| False positives/negatives | user dismissals of observations/insights; experiment finding vs user-reported reality | feedback capture on `Insight`/`DomainCorrelation` dismiss |
| System health | analyzer run success, latency, snapshot freshness | ISE task telemetry + `wlj:ops:medicine_analyzer` |

**Cache-key convention:** `wlj:ops:<resource>` (e.g., `wlj:ops:med_extraction`, `wlj:ops:medicine_analyzer`), 25h TTL, written by the 6h background analyzer, read-only on the request path — never live-computed. A dedicated **Medicine Ops** panel (currently missing, per audit) surfaces these.

---

## 16. Migration Considerations

The path from today to v2, ordered for least disruption. **Additive-compatible** throughout (WLJ law: deferred = phased, additive).

1. **Stabilize first (Phase 2 prerequisites).** Fix D1 (dead subscriber → real `rules_medicine.py`), D2 (chart → `medicine_utils`), D5 (collapse expected-dose copies). These are correctness fixes that v2 depends on; they ship before new features.
2. **History without disruption.** Introduce `MedicationEvent` as a *parallel* ledger. Backfill a single "started" event per existing `Intake` from `start_date`. From then, every create/update/pause/complete writes an event. `Intake` behavior is unchanged for readers until the timeline UI consumes the ledger.
3. **Structured fields are additive.** New `Intake` fields (`ndc_code`, `strength`, FKs to `Provider`/`Pharmacy`) are nullable; free-text fields remain as fallbacks. Migrate free-text → FK opportunistically, never destructively.
4. **Staging replaces the prefill URL gradually.** `MedicationScanDraft` is introduced behind the existing scan path; the review screen becomes the new confirm step. The old URL-prefill remains functional until the draft flow is proven.
5. **Signals extend existing seams.** New EAE types, CDCE detectors, and `_DETECTORS` entries are pure additions to existing lists — no existing signal changes behavior.
6. **State contract grows, never breaks.** New `_contract` sections are additive; existing keys (`medication_status`, etc.) are untouched, preserving Beth's current behavior.
7. **Schema parity enforced per field.** Each new user-settable field lands across model + form + API + AI-intent + handler + prompt in one change set, gated by `test_intent_registration`.
8. **Dependencies.** WeasyPrint (Physician Mode PDF) added to `requirements.txt` explicitly when Phase 7 begins; FHIR deferred.

No canonical model is rebuilt. No existing reader breaks. Every phase is independently shippable and reversible.

---

## 17. Risks

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | **Clinical-safety overreach** — Beth drifts into advice | Severe (user harm, liability) | Structural no-write + pre-narration safety classifier + verdict-never-contains-advice; Section 14 confirmation gates |
| R2 | **OCR error becomes canonical truth** | Severe | Staging model + per-field confidence + forced confirm + blank-on-low-confidence; never write unconfirmed |
| R3 | **Adherence drift / contradictory numbers** (D2, D5) | High (trust erosion) | Single `medicine_utils` authority; delete divergent copies; no-zero-fill; regression guard telemetry |
| R4 | **History/`Intake` divergence** — ledger and head disagree | High | `Intake.current_event` pointer; all writes go through one path that updates both atomically; events immutable |
| R5 | **Silent intelligence failure** (D1 class) | High (invisible loss) | Un-swallow imports; real PIE/PRIE rules; observability on every signal; alert on analyzer failure |
| R6 | **Cross-domain false correlation** narrated as causation | Med-High | Strength thresholds + min co-occurrence n; "observation, discuss with physician" framing; never "because" |
| R7 | **PHI image retention** without proper consent | High (privacy) | Image retention opt-in + separate consent; default no-raw-image posture preserved |
| R8 | **Performance** — heavy analytics on request path | High (524 timeouts, per history) | 6h background analyzer → cache; request path read-only; mandatory per CLAUDE.md |
| R9 | **Scope sprawl** — v2 tries to do all phases at once | Med | Strict phase gates (Section 19); each phase independently shippable |
| R10 | **Schema drift** across model/form/API/intent | Med | Parity rule + `test_intent_registration` gate per field |

---

## 18. Open Questions

- **O-1 — `Provider`/`MedicalCondition`/`Allergy` ownership.** Do these already exist in `apps/medical`? If so, reference them rather than creating duplicates (Single Source of Truth). *Must verify before Phase 3 modeling.*
- **O-2 — Domain home for new models.** Do the history/treatment models live in `apps/health` (alongside `Intake`) or a new `apps/medication`? Recommendation: keep in `apps/health` to avoid a cross-app FK web and respect "one medicine domain," unless `apps/medical` already owns providers/conditions.
- **O-3 — Image retention default.** Opt-in (recommended, privacy-preserving) vs opt-out. Confirms PHI posture.
- **O-4 — Experiment trigger detection.** How automatically should experiment triggers fire (e.g., "ride > 60 min")? Fully automatic from `WorkoutSession`, or user-confirmed each iteration? Recommendation: auto-detect, user-confirm capture.
- **O-5 — Supplement clinical depth.** How far do we model supplement interactions/ingredients? Recommendation: v2 models supplements at parity with meds for tracking/adherence/experiments, but defers ingredient-level interaction modeling to a later phase.
- **O-6 — FHIR demand.** Is physician FHIR export actually wanted, or is printable PDF sufficient for v2? Defer FHIR unless validated.
- **O-7 — `IntakeSchedule` soft-delete.** Promote to `SoftDeleteModel` to fix cascade asymmetry, or leave as-is? Low priority; decide during Phase 3.

---

## 19. Recommended Phase Order

Phase 1 (this document) is complete. The remaining phases, in dependency order:

| Phase | Title | Gate / dependency | Promotion trigger |
|-------|-------|-------------------|-------------------|
| **2** | **Stabilize & Gap-Close** | Fix D1, D2, D5; confirm O-1/O-2 ownership; full gap analysis vs this spec | Defects fixed + ownership decided |
| **3** | **Data Model Evolution** | `MedicationEvent` ledger (+ backfill), structured `Intake` fields, `Provider`/`Pharmacy`/`Prescription`/`TreatmentPlan`/`SideEffectReport`; state-contract `treatment` section | Phase 2 green; migrations additive & reversible |
| **4** | **Image-First Ingestion** | `MedicationScanDraft` + review/confirm workflow; pharmacy-doc parsing; consent for image retention | Phase 3 canonical model stable |
| **5** | **Beth Intelligence** | Extended `_contract` (observations, momentum, monitoring); safety classifier; visibility blind-spots closed | Phases 3–4 feeding real data |
| **6** | **Experiment Engine** | `IntakeExperiment`/`ExperimentObservation`; deterministic summarizer; trigger detection | Phase 5 narration proven safe |
| **7** | **Physician Mode** | PDF (add WeasyPrint), structured export extension; optional FHIR | Phases 3–6 producing exportable evidence |
| **8** | **Advanced Cross-Domain Intelligence** | New CDCE detectors, PRIE forecasts, predictive observations, treatment-learning | All prior phases stable; sufficient longitudinal data |

**Sequencing principle:** correctness before capability (Phase 2 first), canonical truth before intelligence (Phase 3 before 5), and safety proven before autonomy (Phase 5 before 6/8). Each phase is independently shippable, additive-compatible, and reversible. No phase is "maybe someday" — each has an explicit promotion trigger per WLJ planning law.

---

*End of specification. Phase 1 complete. No implementation performed. Awaiting explicit instruction to proceed to Phase 2.*
