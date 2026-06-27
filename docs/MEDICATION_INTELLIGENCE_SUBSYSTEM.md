# Medication Intelligence — Subsystem Reference

**Status:** Version 1 feature-complete and production-hardened (Sprint 9).
**Last updated:** 2026-06-27.
**Canon:** governed by `docs/MEDICATION_INTELLIGENCE_CANON.md` (philosophy) + the v2 planning docs (`MEDICATION_SUPPLEMENT_INTELLIGENCE_V2_*`).

This is the developer/operator reference for the Medication Intelligence subsystem. It is a mature WLJ subsystem: deterministic end-to-end, safety-gated, observable, and cached on the request path.

---

## 1. The deterministic pipeline

```
Acquisition (scan / manual)         apps/health/medication_acquisition.py
   → MedicationScanDraft (staging)  apps/health/models.py
   → Confidence Engine              apps/health/medication_confidence.py
   → Duplicate detection + Confirm  medication_acquisition.confirm_draft
   → Intake (current state) + Prescription/Pharmacy/MedicalProvider links
   → MedicationEvent (append-only ledger)   record_medication_change (one writer)
        ↓
Treatment Timeline + Summaries       apps/health/treatment_timeline.py
        ↓
Observation Engine (deterministic)   apps/health/observations/rules.py + engine.py
   → Safety Classifier               apps/health/observations/core.py
   → Prioritization + Grouping       apps/health/observations/prioritization.py
   → Narration boundary              apps/health/observations/narration.py
        ↓  (one cached bundle — apps/health/observations/bundle.py)
Canonical medicine state (_contract) apps/core/ai_state/state_builder.py::build_medicine_state
        ↓
Chief of Staff (Beth)  ·  "What We've Noticed" UI  ·  Physician Mode
```

**Invariants (every layer):** LLM-last (Beth narrates, never reasons over raw); one history writer (`record_medication_change`); one adherence author (`medicine_utils._enumerate_expected_doses`); OCR never truth (confirm-gated); append-only history (no fabrication); deterministic observations (no causation, no advice); narration adds no facts.

---

## 2. Key files

| Concern | File |
|--------|------|
| Models (Intake, IntakeSchedule, IntakeLog, MedicationEvent, Pharmacy, Prescription, MedicationScanDraft, MedicalProvider) | `apps/health/models.py` |
| History writer + timeline reader | `apps/health/medication_events.py` |
| Acquisition pipeline (draft / duplicate / confirm / scan bridge / structured linking) | `apps/health/medication_acquisition.py` |
| Confidence engine | `apps/health/medication_confidence.py` |
| Treatment timeline + summaries + cross-domain | `apps/health/treatment_timeline.py` |
| Observation layer (rules / safety / prioritization / narration / cached bundle / telemetry) | `apps/health/observations/` |
| Physician Mode service | `apps/health/physician_summary.py` |
| Beth-facing canonical state | `apps/core/ai_state/state_builder.py::build_medicine_state` (`_contract`) |
| UI (acquire/review, timeline, noticed, physician) | `apps/health/views_acquisition.py` + `templates/health/{acquisition,intake}/` |

**`_contract` sections Beth reads:** `summary`, `today`, `upcoming`, `alerts`, `treatment` (incl. `history`), `acquisition`, `observations`, `prioritized_observations`, `observation_groups`, `narrations` (Beth's surface), `narration_groups`.

---

## 3. Performance (Sprint 9A)

The observation → prioritization → narration computation is consolidated into **one cached bundle** (`apps/health/observations/bundle.py`), keyed `wlj:med:obs:<user_id>`, TTL 300s. Read by both `build_medicine_state` and `physician_summary` — no double computation. Freshness is **event-driven**: a `post_save` on `MedicationEvent` busts the bundle (`apps/health/signals.py`). Fail-open: a bundle failure returns a neutral empty bundle, never an exception.

Adherence and timeline reads use the canonical utilities/services (no duplicate math, bounded per-user queries).

---

## 4. Observability (Sprint 9B)

`apps/health/observations/telemetry.py` — Ops Wall convention (`wlj:ops:*`):
- `compute_medication_intelligence_ops()` (background-intended) writes `wlj:ops:med_intelligence`: acquisition counts by status, confirmation rate, duplicate resolutions, confidence distribution, by-source, physician-summaries-generated.
- `get_medication_intelligence_ops()` reads the snapshot only (returns `None` when unpopulated — never live-computes on the request path).
- `record_physician_summary_generated()` increments `wlj:ops:med_physician_summaries`.

**Wiring TODO (acceptable debt):** register `compute_medication_intelligence_ops` in the SAME cycle / ISE registry (6h tier) so the snapshot self-populates; today it must be invoked (e.g., by an ops view or task).

---

## 5. Reliability (Sprint 9C)

Fail-safe throughout: observation bundle (fail-open empty), every `build_medicine_state` section guarded, cross-domain timeline/observation rules defensive per-source, acquisition structured-linking best-effort, lifecycle event recording best-effort (never blocks a lifecycle action), physician summary guards per-med rows + the view degrades to a friendly redirect. Missing data → "Not recorded" / `insufficient_data`, never a fabricated value.

---

## 6. Safety model

OCR/extraction is never canonical without confirmation. Observations state chronology/association only (no causation), pass the deterministic safety classifier (suppress weak/low-confidence/contradictory; route biomarker associations to physician-discussion), and narration adds no facts/causal claims/recommendations (`assert_safe` + banned-language tests). Physician Mode surfaces approved observations + facts only, with a "not a medical record / not medical advice" disclaimer. Beth never diagnoses, prescribes, or recommends dose changes.

---

## 7. Tech-debt classification (Sprint 9G)

**Must address before Treatment Intelligence:**
- *(none blocking)* — the foundation is treatment-shaped (TreatmentPlan/MedicalCondition deferred but anticipated; `_contract` is composition-ready).

**Acceptable technical debt (track, not blocking):**
- Telemetry snapshot not yet wired into the SAME cycle / ISE registry (§4).
- Legacy `vision._build_actions` medicine/supplement branches remain (functionally retired in 3.5; view overrides them).
- Provider matching is exact-name (no fuzzy / NPI).
- `Intake.strength`, `Prescription.refills_authorized`, `filled_date` not persisted losslessly (carried in draft `extracted_values`).
- `IntakeSchedule` cascade asymmetry (no soft-delete) — edge-case hygiene only.

**Future enhancement (post-V1):**
- PDF export for Physician Mode (WeasyPrint/reportlab — not in requirements; print-friendly HTML ships today).
- Richer cross-domain observation detectors (BP, sleep-after-change, lab trends).
- Multi-item label acquisition (currently `items[0]`); consented image retention (`MedicationImage`).
- DrugClass catalog (deferred to its own initiative); FHIR export.

---

## 8. Tests

`apps/health/tests/`: `test_medicine*.py`, `test_expected_dose_single_author.py`, `test_medication_events.py`, `test_medication_acquisition.py` (+ `acquisition_fixtures.py`), `test_treatment_timeline.py`, `test_observations.py`, `test_observation_prioritization.py`, `test_narration.py`, `test_physician_summary.py`, `test_medication_hardening.py`. Run scoped per the WLJ testing policy — never the full suite.
