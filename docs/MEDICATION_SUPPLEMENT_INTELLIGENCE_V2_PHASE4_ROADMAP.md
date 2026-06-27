# Medication & Supplement Intelligence v2 — Phase 4: Product Backlog & Implementation Roadmap

**Status:** Phase 4 — PLANNING ONLY. No code, no implementation, no migrations. Does not redesign Phase 1–3.
**Date:** 2026-06-27.
**Role:** Lead Product Manager / Technical Program Manager.
**Inputs:** Phase 1 (architecture), Phase 2 (gap analysis + migration), Phase 3 (product/UX). This is the master execution plan that sequences those into shippable increments.

> **Governing constraint:** the user must experience value long before the system is complete. Every increment leaves WLJ better, is independently shippable, reversible, feature-flagged, and reuses existing systems. No big-bang releases. All WLJ laws from Phases 1–3 carry forward unchanged (Visual Truth, LLM-last, Beth-never-prescribes, OCR-never-truth, forward-only history, single source of truth, modify-before-add).

---

## 1. Executive Summary

This roadmap converts the Medication Intelligence v2 vision into ~9 epics, ~70 implementation-sized stories, and a 12-sprint sequence that delivers daily-use value from Sprint 1 and compounds toward the flagship "is your treatment working?" experience.

**The shape of the plan:**
- **Stabilize first (Sprint 0/1).** D3, D5 (and a decision on D4) are pure-correctness prerequisites — the only code work that touches *existing* behavior. They unblock everything and carry the lowest risk.
- **Daily value before depth.** The Dashboard + one-tap logging + Detail ship on *existing* data (Sprints 1–2) — users get a better experience before a single new model lands.
- **Capture is the acquisition moment (Sprints 3–4).** Guided Capture + Confidence Review turn "adding meds" from a chore into a delight and is where the staging model + history ledger first appear.
- **Intelligence is the differentiation (Sprints 5–8).** Treatment Dashboard, Cross-Domain Timeline, and Beth's evolving awareness are what no competitor can match — but they *depend on* the history ledger and the unified adherence denominator, so they come after foundation.
- **Clinical value + delight last (Sprints 9–12).** Physician Mode, Learning Plans, and the Medicine Cabinet convert tracking into outcomes and stickiness.

**Two cross-cutting recommendations:**
1. **Evidence as a lightweight contract, not a heavyweight platform (Part 9).** WLJ already has evidence/provenance fields in ~8 models but no shared shape. Standardize an **Evidence envelope** convention scoped to Medication Intelligence first; defer a universal `Evidence` table until proven necessary. This respects modify-before-add and keeps increments small.
2. **Beth evolves in 6 independently-valuable versions (Part 8)** — each shippable, each adding one layer of awareness, never a big-bang "smart Beth."

**The Minimum Lovable Product (Part 5)** = Dashboard + one-tap logging + Guided Capture/Confidence Review + Treatment timeline (read) + Beth medication+adherence awareness + a basic Physician PDF. The daily-use core is delightful by **~Sprint 7**; the basic Physician PDF is the **final MLP element and lands at Sprint 9** (E9-S1/S2), so the full MLP completes at **~Sprint 9**. (C7: timing reconciled — see §6.)

**Recommended immediate next sprint (Part 12):** **Sprint 1 — Stabilization & Dashboard Foundation** (finish D3/D5, decide D4, ship the read-only medication dashboard on existing data). Highest leverage, lowest risk, immediately visible.

---

## 2. Master Feature Inventory

Consolidated from Phases 1–3, de-duplicated, grouped. Status: **Exists** (ship-as-is/reuse) · **Partial** (extend) · **New**.

| # | Feature | Source phase | Status | Epic |
|---|---------|-------------|--------|------|
| F1 | Unified med+supplement record (`Intake`) | P1/P2 | Exists | Foundation |
| F2 | Dose schedule + dose-event logging | P1/P2 | Exists | Foundation |
| F3 | Single adherence authority (`medicine_utils`) | P2 | Partial (D5) | Foundation/Debt |
| F4 | `intake_subtype` insulin UI | P2 | Partial (D3) | Foundation/Debt |
| F5 | Medication Dashboard (today, momentum, attention) | P3 | New | Dashboard |
| F6 | Medication Detail (timeline, outcomes, Q-for-doctor) | P3 | New | Dashboard/Timeline |
| F7 | One-tap logging (dashboard/widget/watch/Beth) | P3 | Partial | Dashboard |
| F8 | Intake Wizard (multi-source add) | P3 | Partial | Capture |
| F9 | Guided Capture (confidence-driven camera) | P1/P3 | Partial (scan exists) | Capture |
| F10 | Confidence Review + staging (`MedicationScanDraft`) | P1/P2/P3 | New | Capture |
| F11 | Barcode/QR → NDC fast path (reuse `medicine_lookup`) | P2/P3 | Partial | Capture |
| F12 | Pharmacy-doc / med-list ingestion (reuse `pdfplumber`/OCR) | P2/P3 | Partial | Capture |
| F13 | Duplicate / old-bottle-vs-current detection | P3 | New | Capture |
| F14 | Structured fields: NDC, strength, SIG, route, expiration | P1/P2 | New | Foundation |
| F15 | Append-only change ledger (`MedicationEvent`) | P1/P2 | New | Timeline |
| F16 | Dose/treatment timeline (per-med) | P1/P3 | New | Timeline |
| F17 | Provider/Pharmacy structured (reuse `MedicalProvider` + new `Pharmacy`) | P2 | Partial/New | Foundation |
| F18 | Prescription record | P2 | New | Foundation |
| F19 | Medical condition / problem list | P2 | New | Treatment |
| F20 | Drug allergy | P2 | New | Treatment |
| F21 | Side-effect reports | P2 | New | Treatment |
| F22 | Treatment plans (group by goal/condition) | P1/P2/P3 | New | Treatment |
| F23 | Treatment Dashboard (momentum, improving/stalled) | P3 | New | Treatment |
| F24 | Cross-Domain Timeline (meds ↔ glucose/weight/labs/…) | P1/P3 | New | Cross-Domain |
| F25 | EAE medicine signals (trend, momentum, refill_risk, instability, monitoring_gap) | P1/P2 | Partial (2 exist) | Signals |
| F26 | PIE medicine insight rules (`rules_medicine.py`) | P2 | New | Signals/Beth |
| F27 | PRIE medicine forecasts (refill/adherence) | P2 | New | Signals/Beth |
| F28 | CDCE med↔biomarker correlation detectors | P1/P2 | New | Cross-Domain |
| F29 | Extended `build_medicine_state._contract` (treatment/observations/monitoring/experiments) | P1/P2 | Partial | State/Beth |
| F30 | Beth medication+adherence narration | P3 | Partial | Beth |
| F31 | Beth cross-domain observations | P3 | New | Beth |
| F32 | Beth treatment reviews (weekly/monthly) | P3 | New | Beth |
| F33 | Beth physician preparation | P3 | New | Beth/Physician |
| F34 | Inventory estimate + refills | P3 | Partial | Inventory |
| F35 | Medicine Cabinet (expiry, duplicates, health score) | P3 | New | Cabinet |
| F36 | Physician Mode export (PDF + print, trends, questions) | P1/P2/P3 | New | Physician |
| F37 | Learning Plans (`IntakeExperiment`/`ExperimentObservation`) | P1/P2/P3 | New | Learning |
| F38 | AI medication CRUD (confirmed-write intents) | P2 (D4) | New | AI CRUD |
| F39 | Notifications (tiered, anti-fatigue) | P3 | Partial | X-cutting |
| F40 | Mobile: widgets, watch, lock-screen, offline | P3 | New | X-cutting |
| F41 | Accessibility baseline | P3 | Partial | X-cutting |
| F42 | Empty/error states | P3 | New | X-cutting |
| F43 | Observability (`wlj:ops:med_*` keys + panel) | P1/P2 | New | Telemetry |
| F44 | Evidence envelope convention | P4 | New | Evidence (X-cutting) |
| F45 | Optional image retention (`MedicationImage`, consented) | P1/P2/P3 | New | Capture |
| F46 | Optional `DrugClass` catalog | P2 | Deferred | Cross-Domain |

---

## 3. Epics

Complexity: **S/M/L/XL**. Each epic notes purpose, business value, user value, dependencies, complexity, risk.

**E1 — Medication Foundation & Stabilization.** *Purpose:* a trustworthy, structured canonical base. *Business value:* unblocks every downstream feature; removes data-integrity risk. *User value:* correct adherence numbers; insulin users can set subtype. *Deps:* none. *Complexity:* M. *Risk:* Low (mostly correctness). Features: F1–F4, F14, F17, F18, F43.

**E2 — Medication Dashboard & Detail.** *Purpose:* the daily-use surface. *Business value:* engagement, retention. *User value:* glance + one-tap log + understand one med. *Deps:* E1. *Complexity:* L. *Risk:* Low-Med (Visual-Truth correctness). Features: F5–F7.

**E3 — Guided Capture & Image Intelligence.** *Purpose:* effortless, trustworthy add. *Business value:* acquisition + data quality. *User value:* snap a bottle, confirm, done. *Deps:* E1 (history ledger for "started" event), scan app. *Complexity:* XL. *Risk:* Med (OCR-truth safety). Features: F8–F13, F45.

**E4 — Medication Timeline.** *Purpose:* longitudinal treatment history. *Business value:* the differentiator's spine. *User value:* "see how treatment changed." *Deps:* E1 (`MedicationEvent`). *Complexity:* L. *Risk:* Med (forward-only honesty). Features: F15, F16.

**E5 — Treatment Intelligence.** *Purpose:* "is treatment working?" at goal level. *Business value:* flagship narrative. *User value:* momentum, improving/stalled, monitor. *Deps:* E1, E4, conditions/plans (F19, F22). *Complexity:* L. *Risk:* Med. Features: F19–F23, F29.

**E6 — Cross-Domain Intelligence.** *Purpose:* meds ↔ life observations. *Business value:* unmatched moat. *User value:* "fasting glucose runs higher after short sleep." *Deps:* E1, E4, CDCE/EAE, cross-domain data (all exist). *Complexity:* XL. *Risk:* Med-High (false causation). Features: F24, F25, F28.

**E7 — Beth Intelligence.** *Purpose:* narration over rich state. *Business value:* the companion no tracker has. *User value:* reviews, prep, observations. *Deps:* E1–E6 incrementally (see Part 8). *Complexity:* L. *Risk:* Med (safety boundaries). Features: F26, F27, F29–F33.

**E8 — Inventory & Medicine Cabinet.** *Purpose:* never run out; whole-cabinet hygiene. *Business value:* practical stickiness. *User value:* refills, expiry, duplicates, cabinet health. *Deps:* E1 (supply fields exist). *Complexity:* M. *Risk:* Low. Features: F34, F35.

**E9 — Physician Mode.** *Purpose:* tracking → clinical value. *Business value:* retention, word-of-mouth. *User value:* one-tap clinician summary. *Deps:* E1, E4, E5, adherence. *Complexity:* M (PDF dep). *Risk:* Low-Med. Features: F36.

**E10 — Learning Plans.** *Purpose:* personal n-of-1 discovery. *Business value:* flagship delight, engagement. *User value:* "does X help my body?" *Deps:* E1, E6 (canonical metric capture), CDCE/PRIE primitives. *Complexity:* L. *Risk:* Med (must stay non-prescriptive). Features: F37.

**E11 — AI Medication CRUD.** *Purpose:* Beth-assisted, confirmed med entry/edit. *Business value:* convenience. *User value:* "add my new prescription" by voice/chat. *Deps:* E1, safety classifier. *Complexity:* M. *Risk:* Med (write authority). Features: F38.

**Cross-cutting (woven through all): Notifications (F39), Mobile/Widgets/Watch/Offline (F40), Accessibility (F41), Empty/Error (F42), Telemetry (F43), Evidence envelope (F44).**

---

## 4. User Stories

Story format: **ID — Title** · *value* · acceptance criteria · deps · effort (1/2/3/5/8) · risk · user-visible outcome. Stories are kept small (≤ one focused effort). Foundational epics are fully enumerated; later epics give the representative implementation set (a backlog seed, not an exhaustive list).

### E1 — Foundation & Stabilization
- **E1-S1 — Render `intake_subtype` in the medicine form (D3).** *value: unlocks insulin intelligence.* AC: subtype field renders, conditional on insulin meds; basal/bolus selectable; saved + shown on detail. Deps: none. Effort: 2. Risk: Low. Outcome: insulin users can set basal/bolus in the UI.
- **E1-S2 — Unify the expected-dose denominator (D5).** AC (single-author, not mere parity): the independent expected-dose enumerators in EAE `signal_aggregation` and **both** `dashboard_v2` paths (`dashboard_service.py`, `compliance/adapters/medication.py`) are **deleted** and replaced by calls into `medicine_utils._enumerate_expected_doses` — exactly one implementation survives; a static check/test asserts no other enumerator exists; golden-master parity holds as a regression guard (parity is necessary but **not** sufficient — single authorship is the acceptance bar). Deps: none. Effort: 5. Risk: Med (touch points). Outcome: adherence has exactly one author (Canon §5), proof against re-divergence when insulin basal/bolus (D3) changes what an expected dose means.
- **E1-S3 — Decision spike: AI med-CRUD (D4) scope.** AC: documented go/no-go + scope for E11; no code. Deps: none. Effort: 1. Risk: Low.
- **E1-S4 — `MedicationEvent` model + single "started" backfill.** AC: immutable model; idempotent reversible data migration creates one "started" event per active med; admin read view. Deps: none. Effort: 5. Risk: Med. Outcome: history begins (invisible until E4).
- **E1-S5 — Structured `Intake` fields (nullable): NDC, strength, sig_text, route/form, expiration, monitoring.** AC: additive migration; form + admin expose them; free-text retained as fallback; schema-parity gate green. Deps: none. Effort: 3. Risk: Low.
- **E1-S6 — `Intake.provider` FK → existing `MedicalProvider` + optional `Pharmacy` model.** AC: nullable FK; opportunistic link prompt; free-text retained. Deps: none. Effort: 3. Risk: Low.
- **E1-S7 — `Prescription` model.** AC: Rx fields distinct from regimen; linked to Intake + provider + pharmacy. Deps: E1-S6. Effort: 3. Risk: Low.
- **E1-S8 — `wlj:ops:adherence_calc` telemetry + D2 regression guard.** AC: background metric; zero-data≠100% asserted. Deps: none. Effort: 2. Risk: Low.

### E2 — Dashboard & Detail
- **E2-S1 — Read-only medication dashboard (today, up-next, groups).** AC: meds/supplements separated; status chips Visual-Truth-correct; renders on existing data. Effort: 5. Risk: Low-Med.
- **E2-S2 — One-tap Take/Skip with undo.** AC: routes through adherence authority; optimistic UI + snackbar undo; PRN handled. Effort: 3. Risk: Low.
- **E2-S3 — "Needs attention" card (low/refill/duplicate/missed-streak/monitoring).** AC: renders only if non-empty; calm styling; each item actionable. Deps: E1, E8 partial. Effort: 3.
- **E2-S4 — Treatment momentum strip (verdict + sparkline).** AC: reads composed verdict; "insufficient_data" honest. Deps: E5/E7 partial. Effort: 3.
- **E2-S5 — Medication Detail: at-a-glance + schedule + adherence.** AC: top-third 90% case; PRN marked. Effort: 5.
- **E2-S6 — Detail: dose/treatment timeline section (reads ledger).** AC: forward-only label; reasons shown. Deps: E1-S4, E4. Effort: 3.
- **E2-S7 — Detail: observed outcomes + questions-to-discuss.** AC: evidence-linked; observational language; add-to-export. Deps: E6, E9. Effort: 5.

### E3 — Guided Capture & Image Intelligence
- **E3-S1 — `MedicationScanDraft` staging model.** AC: per-field confidence; non-canonical; auto-expire. Effort: 3.
- **E3-S2 — Vision medicine/supplement extraction → draft (not prefill URL).** AC: extracts name/strength/SIG/dose/freq/qty/expiration + confidence. Deps: E3-S1, scan app. Effort: 5. Risk: Med.
- **E3-S3 — Confidence Review screen.** AC: low-confidence fields blank+highlighted; forced Rx-vs-supplement toggle; **duplicate / old-bottle-vs-current detection runs here and the confirm-write is gated behind it (E3-S6 is part of this workflow)**; confirm writes Intake + `MedicationEvent`. Deps: E3-S2, E3-S6, E1-S4. Effort: 5. Risk: Med.
- **E3-S4 — Guided Capture decision tree (front → label → conditional more).** AC: confidence-driven stopping; why-this-photo microcopy; pen flow → insulin subtype. Deps: E3-S2, E1-S1. Effort: 5.
- **E3-S5 — Barcode/QR → NDC fast path.** AC: reuse `medicine_lookup`; prefill + confirm. Effort: 3.
- **E3-S6 — Duplicate / old-bottle-vs-current detection at review (C3: ships WITH E3-S3, in the same sprint, before any canonical write can occur).** AC: same-or-different banner; routes to update (dose-change event) vs new; no confirm-write proceeds until this check has run. Deps: E3-S2. Effort: 3. Risk: Med.
- **E3-S7 — Pharmacy-doc / med-list ingestion (PDF/photo → multi-draft).** AC: reuse `pdfplumber`/OCR; checklist review. Effort: 5.
- **E3-S8 — Optional consented image retention (`MedicationImage`).** AC: separate consent; encrypted; default off. Deps: E3-S3. Effort: 3. Risk: High (PHI) — gated.

### E4 — Timeline
- **E4-S1 — Ledger writes on every change (create/edit/pause/discontinue/dose-change).** AC: each canonical change emits an immutable event with reason. **Single-writer rule (C10b, Canon §5 "history has one writer"):** the `Intake`-mutation + `MedicationEvent`-append dual-write happens through ONE service authority (e.g. `record_medication_change()`) that updates head and ledger atomically; **both** the scan-confirm path (E3-S3) and the manual-edit/CRUD paths (E2/E11) call it — no path writes the dual-record invariant independently; asserted by test. Deps: E1-S4. Effort: 5.
- **E4-S2 — Per-med timeline UI.** AC: forward-only honest label; ↑/↓/stop/provider markers; reasons. Effort: 3.
- **E4-S3 — "Reason for change" capture prompt.** AC: provider-directed/side-effect/cost/user-choice; Beth may ask. Effort: 2.

### E5 — Treatment Intelligence
- **E5-S1 — `MedicalCondition` + `TreatmentPlan` models (conditions before plans).** AC: explicit creation only (no auto-infer). Effort: 5. Risk: Med.
- **E5-S2 — `_contract.treatment` section (momentum verdict, recent changes).** AC: verdict-inside; deterministic. Deps: E4, signals. Effort: 5.
- **E5-S3 — Treatment Dashboard UI (goals/therapies/improving-stalled/monitor).** AC: evidence-linked; neutral "stalled." Deps: E5-S2. Effort: 5.
- **E5-S4 — `SideEffectReport` + "report a side effect."** AC: user-reported only. Effort: 3.

### E6 — Cross-Domain Intelligence
- **E6-S1 — EAE signal types: adherence_trend, treatment_momentum, refill_risk, treatment_instability, monitoring_gap.** AC: no-zero-fill; confidence ladder; built on unified denominator. **Calculation-reuse rule (C10a, Canon §5):** `treatment_momentum` (and all composites) **read** adherence from `medicine_utils` and biomarker direction from the existing EAE/CDCE signals — they compute **no** adherence or biomarker math inline; asserted by test. Deps: E1-S2, E4. Effort: 8. Risk: Med.
- **E6-S2 — CDCE med↔biomarker detectors (dose-change↔weight, adherence↔glucose, supplement↔outcome).** AC: strength thresholds; min co-occurrence; correlation-not-causation. Deps: E1, E4. Effort: 8. Risk: Med-High.
- **E6-S3 — `_contract.observations` + cross-domain `_DETECTORS` entries.** AC: rendered verdicts with evidence + discuss-flag. Effort: 5.
- **E6-S4 — Cross-Domain Timeline UI (layered, zoomable).** AC: meds + glucose/weight/labs/nutrition/exercise/sleep/appointments; observational "moments that line up." Deps: E6-S2. Effort: 8.

### E7 — Beth Intelligence (see Part 8 for version gating)
- **E7-S1 — PIE `rules_medicine.py` (adherence drop, missed streak, side-effect onset, monitoring gap).** AC: real insights from the now-live subscriber. Effort: 5.
- **E7-S2 — PRIE `rules_medicine.py` (refill exhaustion, adherence trajectory).** AC: forecasts with confidence. Effort: 5.
- **E7-S3 — Per-med dose/frequency/side-effects surfaced to Beth.** AC: closes the visibility blind spot. Effort: 3.
- **E7-S4 — Safety classifier (pre-narration diagnose/prescribe screen).** AC: decline+redirect template; blocks dose-advice. Effort: 5. Risk: Med.
- **E7-S5 — Weekly/monthly treatment review narration.** AC: calm rollup; improving/watch/discuss. Effort: 3.

### E8 — Inventory & Cabinet
- **E8-S1 — Inventory estimate + run-out projection.** AC: derived from schedule+logs; labeled estimate; user-correctable. Effort: 3.
- **E8-S2 — Refill status + request/mark-refilled.** AC: one-tap supply adjust. Effort: 3.
- **E8-S3 — Medicine Cabinet UI (shelves, expiry, dormant, duplicates).** AC: calm tone; pharmacist as escalation. Effort: 5.
- **E8-S4 — Cabinet health score.** AC: gentle indicator; non-scolding breakdown. Effort: 3.

### E9 — Physician Mode
- **E9-S1 — Add WeasyPrint dependency + export service skeleton.** AC: template→PDF; "not a medical record" framing. Effort: 3.
- **E9-S2 — Export content assembly (meds/supplements/changes/adherence/trends/questions).** AC: all deterministic; adherence via the one util. Deps: E4, E5. Effort: 5.
- **E9-S3 — Print-friendly on-screen view + calendar-aware prompt.** AC: pre-appointment "want to prep?". Effort: 3.

### E10 — Learning Plans
- **E10-S1 — `IntakeExperiment` + `ExperimentObservation` models.** AC: protocol/metrics/target_n; captured metrics from canonical sources. Effort: 5.
- **E10-S2 — Trigger detection + auto-capture.** AC: fires on workout/calendar; prompts only subjective note. Deps: E6. Effort: 5.
- **E10-S3 — Deterministic finding summarizer + UI.** AC: finding computed (not LLM); Beth narrates; non-prescriptive close. Effort: 5. Risk: Med.

### E11 — AI Medication CRUD
- **E11-S1 — Confirmed `add_medication`/`update_medication` intents (5-point registration).** AC: write only after explicit confirm; schema parity; registration-gate test green. Deps: E1, E7-S4. Effort: 5. Risk: Med.

### Cross-cutting stories (sampled; recur per epic)
- **X-S1 — Tiered notification engine + quiet hours + anti-fatigue grouping.** Effort: 5.
- **X-S2 — Home-screen widget (next dose + progress, Visual-Truth-correct).** Effort: 3.
- **X-S3 — Apple Watch glance + tap-to-log + complications.** Effort: 5.
- **X-S4 — Offline log/capture queue + sync.** Effort: 5.
- **X-S5 — Accessibility audit gate (type scaling, contrast, color-independent status, voice log).** Effort: 3 (recurring).
- **X-S6 — Empty/error state pass per surface.** Effort: 2 (recurring).
- **X-S7 — `wlj:ops:med_*` keys + Medicine Ops panel.** Effort: 3.
- **X-S8 — Evidence envelope schema + render (Part 9).** AC (C10c, Canon §5 "evidence has no second copy): the envelope **normalizes the existing `evidence` JSON fields in place** (`Insight.evidence`, `Prediction.evidence`, `DomainCorrelation.evidence`, medicine `_contract.observations`) to one shared shape and renders a "why this?" affordance; it introduces **no** parallel/medication-specific evidence record that duplicates source data. Effort: 5.

---

## 5. Sprint Plan

Twelve themed sprints. Each ships behind a flag, is independently valuable, and leaves WLJ better. "Why before next" explains the ordering.

| Sprint | Theme | Stories | Ships | Why it precedes the next |
|--------|-------|---------|-------|--------------------------|
| **1** | **Stabilization & Dashboard Foundation** | E1-S1,2,3,8; E2-S1,2 | Correct adherence everywhere; insulin subtype UI; read-only dashboard + one-tap log on *existing* data | Everything downstream trusts the adherence number and the dashboard shell; correctness first |
| **2** | **Foundation Data Model** | E1-S4,5,6,7; X-S7 | History ledger (+backfill), structured fields, provider/pharmacy/prescription, ops panel | Capture, timeline, treatment all need the ledger + structured fields to write into |
| **3** | **Capture I — Staging & Review** | E3-S1,2,**3,6**; X-S6 | Vision → draft → Confidence Review **with duplicate detection** → confirmed write | The acquisition moment; needs the ledger (S2) to record "started". **C3: dedup (E3-S6) ships WITH the review screen so the first confirmed write can never create a silent duplicate** |
| **4** | **Capture II — Guided & Smart** | E3-S4,5,7; E3-S8(gated) | Guided decision tree, barcode/QR, doc ingestion | Completes trustworthy add before we ask users to rely on the data for intelligence |
| **5** | **Timeline** | E4-S1,2,3; E2-S6 | Ledger-on-every-change; per-med timeline UI | Treatment & cross-domain reasoning need change events with reasons |
| **6** | **Treatment Intelligence** | E5-S1,2,3,4; E2-S4 | Conditions/plans, treatment momentum verdict + dashboard | "Is it working?" at goal level; needs timeline + unified signals |
| **7** | **Beth I+II — Medication & Adherence Awareness** | E7-S1,3,5; E7-S4; X-S8 | PIE insights, per-med visibility, safety classifier, weekly review, Evidence envelope | Beth narrates the now-rich state; safety classifier must precede deeper autonomy |
| **8** | **Cross-Domain Intelligence** | E6-S1,2,3,4; E7-S2 | EAE signal types, CDCE detectors, observations, Cross-Domain Timeline, PRIE forecasts | The moat; depends on ledger + unified denominator + treatment state |
| **9** | **Physician Mode** | E9-S1,2,3 | One-tap clinician PDF + print + pre-appointment prep | Converts the accumulated intelligence into clinical value |
| **10** | **Inventory & Cabinet** | E8-S1,2,3,4; E2-S3 | Refills, run-out, Medicine Cabinet, health score | High practical value; can slot earlier if refill pain dominates feedback |
| **11** | **Learning Plans** | E10-S1,2,3 | n-of-1 experiments, deterministic findings | Flagship delight; needs cross-domain capture (Sprint 8) |
| **12** | **Mobile Polish & AI CRUD** | X-S2,3,4; E11-S1; X-S1 | Widgets, watch, offline, confirmed AI med-CRUD, notification engine | Hardening + convenience once the core experience is proven |

*Accessibility (X-S5) and empty/error (X-S6) are release gates inside every sprint, not a standalone sprint.* Sprints 10 and 11 can swap based on user feedback (inventory pain vs experiment appetite).

---

## 6. Minimum Lovable Product (MLP)

**Not MVP — the smallest version that genuinely delights Danny (P1).** The daily-use core (dashboard, logging, capture, timeline, Beth awareness) is reachable by **~Sprint 7**; the MLP's one remaining element — the basic Physician PDF — lands at **Sprint 9**, so the **complete MLP is reached at ~Sprint 9**. (C7 reconciliation: this corrects the earlier "~Sprint 6–7" which omitted that the Physician PDF, listed below, is Sprint 9.)

**Core capabilities:** medication dashboard with one-tap logging (Visual-Truth-correct); correct adherence; Guided Capture → Confidence Review → confirmed add (bottles, pens, supplements); per-med Detail with a forward-only treatment timeline.

**Beth capabilities:** knows his current meds/supplements, doses, frequencies; speaks to adherence; gives a calm weekly review; stays strictly within safe boundaries (no dose advice).

**Capture capabilities:** snap a prescription bottle or pen, confidence-reviewed, confirmed in seconds; barcode fast path; duplicate detection.

**Reporting:** treatment momentum strip + adherence trends.

**Physician export (Sprint 9 — the final MLP element):** a basic but real PDF — current meds/supplements with dose/frequency, recent changes, adherence summary, and a questions list. (Trends/graphs can be the next increment.)

**Intentionally deferred from MLP:** full cross-domain correlation timeline, Learning Plans, Medicine Cabinet, AI CRUD, FHIR, image retention, Apple Watch. Each lands later without rework because the foundation is additive.

**Why this is *lovable*, not minimal:** it already does the one thing no competitor does — turns Danny's bottles into an understood, physician-ready treatment story — while feeling calm and effortless.

---

## 7. Technical Debt Priorities

Ranked; must be addressed before the dependent feature work.

| Rank | Item | Status (verified Phase 2) | Blocks | Action |
|------|------|---------------------------|--------|--------|
| 1 | **D5 — divergent expected-dose enumerations** | Partial (util internal-canonical; EAE + 2 dashboards independent) | All new EAE signals (Sprint 8) build on the denominator | Unify in **Sprint 1** (E1-S2) |
| 2 | **D3 — `intake_subtype` not rendered** | Open (template drops the field) | Insulin capture (Sprint 4), insulin intelligence | Render in **Sprint 1** (E1-S1) |
| 3 | **D4 — no AI med-CRUD intent** | Open (by design) | E11 only | Decide scope Sprint 1; build Sprint 12 |
| 4 | **No append-only history** | Open (architectural) | Timeline, treatment, cross-domain | `MedicationEvent` in **Sprint 2** |
| 5 | **Free-text provider/pharmacy/rx (no structure)** | Open | Physician Mode, provider FK | Structured fields Sprint 2 |
| 6 | **WeasyPrint not in requirements** | Open | Physician PDF | Add in Sprint 9 |
| 7 | **`IntakeSchedule` cascade asymmetry (no soft-delete)** | Open (low) | Edge-case data hygiene | Optional, Sprint 2/3 |
| 8 | **Scattered evidence/provenance, no shared shape** | Open (latent) | Beth traceability, physician trust | Evidence envelope Sprint 7 (Part 9) |
| 9 | **No medicine telemetry/ops panel** | Open | Observability of all above | Sprint 1–2 (X-S7) |

*D1 (dead PIE subscriber) and D2 (chart drift) are already FIXED and deployed — not listed as open debt.*

---

## 8. Cross-Domain Dependency Map

What can be built independently vs what must wait.

**Build independently (no external-domain blocker):** Foundation (E1), Dashboard/Detail (E2), Capture (E3), Timeline (E4), Inventory/Cabinet (E8), Physician PDF skeleton (E9-S1). These touch only `apps/health` + `apps/scan` + existing provider models.

**Depend on existing-but-stable read sources (reuse, no changes to those domains):**
| Medication feature | Depends on (read-only) | Status |
|---|---|---|
| Cross-domain observations (E6) | Glucose, Weight, Sleep, Labs, Nutrition, Workouts, `DailyHealthSummary` | All exist; **read-only** — no changes required to those domains |
| Treatment momentum (E5) | Weight, Labs, Glucose | Exist |
| Learning Plans capture (E10) | Workouts, Glucose, Nutrition, Calendar | Exist |
| Physician trends (E9) | Glucose, Weight, Labs | Exist |
| Reason-for-change prompts (E4) | Calendar (appointments) | Exists |

**Depend on intelligence infrastructure (extend existing seams, not rebuild):**
| Feature | Seam | Note |
|---|---|---|
| EAE signals (E6) | `signal_aggregation` `signal_computers` | 2 med types exist; add more |
| Cross-domain detectors (E6) | CDCE `CORRELATION_DETECTORS` | none for meds yet — add |
| Narrative signals (E6) | `ai_signals._DETECTORS` | `medication_adherence_risk` exists |
| State (E5/E7) | SAE `build_medicine_state._contract` | extend, one medicine domain |
| Insights/forecasts (E7) | PIE/PRIE `rules_medicine.py` | new rule files |
| Beth narration (E7) | `build_cos_intelligence` injection | composed verdict only |

**Hard ordering constraints:**
- Cross-domain (E6) and Treatment (E5) **must wait** for the history ledger (E4) and the unified denominator (D5/E1-S2).
- Beth deeper autonomy (E7 narration of observations) **must wait** for the safety classifier (E7-S4).
- Learning Plans (E10) **must wait** for canonical metric capture proven in E6.
- AI CRUD (E11) **must wait** for the safety classifier and confirmed-write path.

**Critically: this initiative requires NO schema or behavior changes to other domains** — it only reads them. That keeps blast radius inside `apps/health`/`apps/scan` and de-risks the whole program.

---

## 9. Beth Evolution Roadmap

Six independently-valuable versions; each ships in/after the noted sprint.

| Ver | Capability | Ships | Independently valuable because… | Safety |
|-----|-----------|-------|-------------------------------|--------|
| **B1 — Medication awareness** | Knows current meds/supplements, dose, frequency, SIG; answers "what am I on?" | Sprint 7 | Replaces the current names-only blind spot | Read-only |
| **B2 — Adherence awareness** | Speaks to 7/30/90-day adherence, streaks, missed patterns; weekly review | Sprint 7 | Useful even with no cross-domain data | Neutral, non-judgmental |
| **B3 — Cross-domain observations** | Narrates meds ↔ glucose/weight/sleep/labs/exercise (observational) | Sprint 8 | The moat; "fasting glucose runs higher after short sleep" | Correlation-not-causation; discuss-with-doctor |
| **B4 — Treatment reviews** | Goal-level "is it working?"; monthly summaries; improving/stalled | Sprint 8 | Reframes from pills to treatment | Verdict-inside, no advice |
| **B5 — Learning plan facilitation** | Proposes/runs/reports n-of-1 plans | Sprint 11 | Active discovery, high delight | Non-prescriptive close |
| **B6 — Physician preparation** | Assembles questions + export before appointments | Sprint 9 | Converts everything into a better visit | "Not a medical record" framing |

Each version gates on the prior one's data being real; **the safety classifier (E7-S4) ships with B1/B2** so every later version inherits it. No "smart Beth" big bang.

---

## 10. Evidence Framework Recommendation (challenged)

**The proposal:** make **Evidence** a first-class architectural concept — every conclusion Beth presents is traceable to its sources (bottle photo, OCR extraction, user confirmation, timeline event, weight/glucose/lab/meal/journal datum).

**Verdict: YES to evidence as a first-class *contract/convention* — NO to a heavyweight universal `Evidence` table in v2.**

**Why the instinct is right.** WLJ *already* has evidence/provenance fields in ~8 places — `Insight.evidence` (JSON), `Prediction.evidence`, `DomainCorrelation.evidence`, `SignalSnapshot.source_signals`, EAE `ExtractedFact`, `IntakeLog.source` (10-value provenance enum), `MedicalDocument.extraction_method`, `ScanLog`, `MedicalAuditLog`. Evidence is *de facto* everywhere; what's missing is a **shared shape** and a consistent way to render "why." Beth's credibility ("why do you say that?") and physician trust both depend on traceability. So the *concept* is sound and overdue.

**Why a universal Evidence *table* is the wrong move now.** Three reasons, each a WLJ law:
1. **Modify before adding.** The `evidence` JSON fields already exist. A new table that every domain must FK into is *adding* where *extending the convention* suffices.
2. **Small, reversible increments.** A platform-wide Evidence model is a cross-cutting migration touching every engine — the definition of a big-bang, high-coordination, high-rollback-risk change this roadmap is built to avoid.
3. **Beth consumes briefings, not atoms.** A separate queryable evidence store invites the anti-pattern of Beth reasoning over raw evidence rows. Evidence belongs *inside* the composed verdict she narrates, not beside it as a new atomic source.

**Recommended path — the Evidence Envelope (a typed convention):**
- Define one shared schema, `EvidenceRef = { source_type, source_id, captured_at, confidence, excerpt/summary, link }`, and a small `EvidenceBundle` (a list + an overall confidence).
- **Standardize the already-existing `evidence` JSON fields** to this shape across `Insight`/`Prediction`/`DomainCorrelation`/medicine `_contract.observations`, and render it as a consistent "Why this?" affordance (tap any Beth conclusion → see its sources).
- **Scope it to Medication Intelligence first** (Sprint 7, X-S8) — the domain where OCR + confidence + clinical stakes make provenance most acute and most valuable. Prove the convention end-to-end (capture → draft → confirm → observation → Beth → physician export).
- **Promotion trigger (per WLJ "deferred = phased"):** if, after Medication Intelligence ships, (a) multiple domains need to *query* evidence across conclusions, or (b) physician export demands durable, immutable evidence rows for audit, **then** promote the envelope to a dedicated `Evidence` model + cross-domain pattern in a separate, properly-scoped initiative. Not before.

**Could it become a broader pattern?** Yes — and it likely should, eventually. The envelope is deliberately domain-agnostic so the same "every conclusion is traceable" guarantee can extend to faith, goals, finance, etc. But that promotion is earned by evidence of need, not assumed up front. Designing the *convention* now makes the future *platform* cheap; building the platform now makes the present *slow and risky*.

**One-line recommendation:** adopt Evidence as a **standardized envelope convention, prove it in Medication Intelligence, and let demonstrated cross-domain demand — not ambition — trigger its promotion to a first-class model.**

---

## 11. Success Metrics

How we'll know it worked. Targets are directional, to be calibrated after baseline.

**Adoption & engagement**
- Med-dashboard DAU/WAU; % of active WLJ users with ≥1 tracked med
- Daily logging rate; one-tap-log usage share
- Beth medication-conversation rate (queries/user/week)

**Capture quality (the OCR-never-truth promise, measured)**
- Capture success rate (draft created without manual fallback)
- Mean per-field extraction confidence; % fields auto-filled vs hand-corrected
- **Confirm rate** (drafts confirmed) and **edit rate** (fields changed at review) — high edit rate flags extraction quality
- Reduction in fully-manual med entry vs baseline

**Clinical value**
- Physician-export generations/user; pre-appointment prep usage
- Adherence trend at cohort level (improvement is a *health* outcome, framed carefully — never claimed as causation)
- Questions-for-physician items created and carried into a visit

**Intelligence value**
- Cross-domain observations surfaced/user; dismiss rate (low dismiss = relevant)
- Learning Plans started → completed (completion rate)
- Treatment-review opens

**Safety & trust (guardrail metrics — must stay green)**
- Zero diagnose/prescribe leakage past the safety classifier (audited)
- "Why this?" evidence-affordance usage (traceability adoption)
- No silent canonical writes from unconfirmed OCR (must be 0)

**Delivery health**
- Sprint throughput; flag-gated rollout success; reverse-migration tested per schema sprint
- Defect escape rate; `wlj:ops:med_*` panel green

**North-star:** *% of tracked medications that have a confirmed source + a forward treatment story + at least one cross-domain observation Beth can discuss* — i.e., the share of the regimen that is genuinely "understood," not just listed.

---

## 12. Recommended Immediate Next Sprint

**Sprint 1 — Stabilization & Dashboard Foundation.**

**Theme:** make the existing data trustworthy and put a daily-use surface in front of the user — zero new clinical models, immediate visible value.

**Scope (stories):** E1-S1 (render `intake_subtype`/D3), E1-S2 (unify dose denominator/D5), E1-S3 (D4 decision spike), E1-S8 (adherence telemetry + D2 guard), E2-S1 (read-only dashboard), E2-S2 (one-tap log + undo).

**Why this first:**
- It is the **only** work that touches existing behavior — doing it now removes data-integrity risk (D5) before any intelligence is built on the denominator, and unblocks insulin capture (D3).
- It ships a surface users **open every day** on data that **already exists** — value before any migration.
- It is the **lowest-risk, highest-leverage** entry point: mostly correctness + read UI, fully reversible, behind a flag.

**Exit criteria:** adherence numbers agree across dashboard/EAE/reports; insulin users can set basal/bolus; medication dashboard live with one-tap logging (Visual-Truth-correct); `wlj:ops:adherence_calc` green; D4 go/no-go documented.

**This is the recommended place to start the moment implementation is authorized.**

---

*End of Phase 4. Planning only — no code, no implementation, no migrations, no architecture/UX redesign. This roadmap operationalizes Phases 1–3 into shippable increments.*
