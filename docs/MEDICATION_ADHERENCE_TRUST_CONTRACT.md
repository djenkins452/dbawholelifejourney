# Medication Adherence — Trust Contract

> **Origin:** 2026-06-30 production review. **Medication Adherence must refer to
> prescription medications only.** It must never include supplements, vitamins, or
> wellness products. This is a trust issue, not a reporting issue.

## The three categories (canonical classification)

Single source of truth: `apps/health/medicine_classification.py :: classify_intake` /
`classification_q`. Driven by `Intake.category` (+ insulin via `intake_subtype`).

| Bucket | `Intake.category` values | Counts toward |
|---|---|---|
| **Prescription Medication** | `prescription` + any insulin (`intake_subtype`) | **Medication Adherence** |
| **Supplement** | `vitamin`, `mineral`, `amino_acid`, `herbal`, `probiotic`, `hormonal` | Supplement Adherence |
| **Wellness / Nutrition** | `otc`, `performance`, `other` | Health Routine Adherence only |

**Strict by design:** an uncategorized medication (`category='other'`) is **Wellness**, not
Medication — so a supplement can never leak into the medication number. Consequence: a real
prescription that is **not tagged `category='prescription'` will not count** toward Medication
Adherence. Tag prescriptions correctly. (Insulin is always prescription regardless of category.)

## The three metrics — never merged, never mislabeled

| Metric | Scope | Where |
|---|---|---|
| **Medication Adherence** (`adherence_7d`) | prescription only | SAE, CoS context, dashboard, physician summary, Beth |
| **Supplement Adherence** (`supplement_adherence_7d`) | supplements only | SAE, dashboard, physician summary |
| **Health Routine Adherence** (`health_routine_adherence_7d`) | ALL ingestibles, **explicitly named** | SAE, dashboard, Beth |

A mixed (all-ingestibles) number is **never** labeled "Medication Adherence" — it is
"Health Routine Adherence".

## Calculation

`calculate_medicine_adherence(user, start, end, classification=...)` /
`calculate_medicine_adherence_rate(..., classification=...)` apply the trust-contract
filter (`'prescription' | 'supplement' | 'wellness' | None`). `classification` is the
canonical filter; the legacy `intake_type` param remains for back-compat but
medication-labeled surfaces now pass `classification='prescription'`.

## Surfaces corrected (every place "Medication Adherence" is computed/shown)

`apps/core/ai_state/state_builder.py` · `apps/ai/dashboard_ai.py` · `apps/ai/services.py`
(Beth wording: "Medication adherence at X%" + separate "Health routine adherence") ·
`apps/dashboard/cache.py` · `apps/health/physician_summary.py` · `apps/health/views.py` ·
`apps/ai/situational_awareness.py`. The CoS chain (`cos_context.medication_adherence_state`
→ `standing_context.medication_adherence` → Beth) reads the prescription-scoped SAE.

## Permanent protection

`apps/health/tests/test_medication_classification.py` — the classifier buckets every
category correctly, supplements are never prescription, and prescription vs supplement
adherence are **disjoint** (prescription 100% taken + supplement 0% taken → the two metrics
differ, and the mixed routine number sits between them and is never the medication number).
