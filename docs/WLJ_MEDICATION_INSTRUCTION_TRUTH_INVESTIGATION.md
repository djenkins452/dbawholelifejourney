# WLJ — Medication Instruction Truth: Investigation

**Status:** INVESTIGATION COMPLETE · **NO CODE CHANGED** · awaiting Danny's architecture decision
**Date:** 2026-08-21 · **Origin:** the successful own-record-grounding smoke (`a4995dcd`)
**Governing:** `02_WLJ_CONSTITUTION.md` (I.1, I.2, I.4, IV.2, IV.4) · `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`

---

## 1. The defect

The smoke that proved own-record grounding also exposed a new trust defect. The CoS correctly retrieved Danny's
Mounjaro record and correctly resolved his next dose — then said:

> *"…it has a **60-minute grace period for a late dose**. … Generally, if you miss a dose, it's advised to take it
> **as soon as possible within the same day**, unless it is very close to your next scheduled dose."*

Two separate errors in one sentence pair:
1. a WLJ **adherence-bookkeeping** number was narrated as if it were **administration guidance**;
2. the drug-specific missed-dose rule was **improvised from general model knowledge** and is not the established
   guidance for this product (per Danny: a ~4-day / 96-hour window, then skip and resume).

**The class:** *personal regimen truth and medication-product instructions are different kinds of evidence.* The CoS
must not retrieve the schedule correctly and then fill the product-instruction gap from improvised knowledge.

---

## 2. PROVEN: what `grace_period_minutes` actually is

**It is adherence-status bookkeeping. It carries zero prescribing meaning.**

| Evidence | Finding |
|---|---|
| `apps/health/models.py:2497` | Declared under the comment `# Grace Period for Missed Doses`, `default=60`, help_text **"Minutes after scheduled time before marking as overdue"** |
| Consumers (only two, non-test) | `IntakeLog.was_taken_on_time` and `IntakeLog.mark_taken` — both do exactly one thing: classify a log as `STATUS_TAKEN` vs `STATUS_LATE` |
| `apps/health/models.py:6018` | **The identical field, identical `default=60`, identical semantics exists on the WORKOUT PLAN model** ("Minutes after preferred_time before marking late") — proving it is a platform-wide lateness-tolerance concept, not a clinical one |
| Clinical use | **None.** No consumer anywhere treats it as dosing guidance |

**The `60` is the untouched platform default** — nobody prescribed it, and it says nothing about Mounjaro.

### Why the model read it as guidance — the exposure defect
`MedicineQueries.describe_one` emits it as a **bare, unitless, unlabelled integer inside a block named `plan`**,
adjacent to `schedule`, `start_date` and `instructions`. Verified by dumping the real serialization
(transaction-rolled-back, dev DB untouched):

```json
"plan": {
  "schedule": ["7:00 AM"],
  "schedule_detail": [{"time": "7:00 AM", "days_of_week": "0", ...}],
  "grace_period_minutes": 60,          ← adherence bookkeeping, presented as part of the PLAN
  "start_date": "2026-01-01",
  "instructions": null,                ← no product instruction truth at all
  "monitoring": null
}
```

Nothing in that payload tells the model the number is bookkeeping. **Mea culpa:** the domain-semantics line added
yesterday (`apps/core/truth/semantics.py:109`) describes it as *"the grace period for a late dose"* — ambiguous
phrasing that made this more likely, not less.

---

## 3. PROVEN: what instruction truth exists today

**None that is authoritative for product administration.**

| Candidate | What it actually is | Verdict |
|---|---|---|
| `Intake.instructions` | Free text, help_text *"Special instructions (e.g., 'take with food', 'avoid grapefruit')"* — **user/prescription-entered regimen notes** | Personal regimen truth. Would never contain a manufacturer missed-dose window. **`null` in the verified serialization** |
| `Intake.monitoring_requirements` | Free-text monitoring notes | Not administration guidance |
| `apps/scan/services/medicine_lookup.py` | RxNav + openFDA **NDC directory** + OpenAI fallback → identity, strength, form, purpose, warnings | **Scan-time IDENTIFICATION only.** Consumed solely by `apps/scan/views.py` for barcode prefill; **not** in the truth catalog, **not** a CoS tool, persists nothing, request-path outbound HTTP |
| DailyMed / package insert / monograph / label endpoint | — | **Does not exist anywhere in the repo** |

**Conclusion: WLJ owns no authoritative drug-product administration instructions.** The model was structurally
forced to improvise. That is not a reasoning defect — there was nothing to reason from.

---

## 4. First failing layer

**Layer 1 (Truth) — two distinct defects.** Reasoning did its job: it retrieved, and it resolved the branch from
real truth. It then hit a hole and filled it.

- **Defect A — semantic mislabelling (no architecture needed).** An adherence-bookkeeping integer is exposed inside
  `plan` with no semantics, inviting the category error. *This is a defect regardless of what we decide about B.*
- **Defect B — missing authority (architecture decision required).** No deterministic source of product
  administration/missed-dose instructions exists.

---

## 5. Options for Defect B (NOT implemented — Danny's call)

| # | Option | Assessment |
|---|---|---|
| 1 | Instruct the model to attribute/hedge product instructions | Cheapest, but only makes wrong drug facts better-labelled. **Does not fix the defect.** |
| 2 | WLJ answers regimen truth; the CoS bounds the *specific* missed-dose rule back to the labelling/pharmacist | Honest and safe, needs no new authority — but partially re-opens the deflection class just closed. A **narrow, bounded** escalation, not the old blanket punt. |
| 3 | **Expose an authoritative product-label surface** (openFDA `/drug/label.json` → `dosage_and_administration`), cached + background-refreshed + attributed, read-only | The only option that actually fixes it. **But it is NOT "expose what exists":** `Intake` stores only a free-text `name` (no NDC, no rxcui), and the wired client calls the **NDC directory**, not the label endpoint. Needs name→product resolution, a new endpoint, and a **new KIND of truth: impersonal REFERENCE truth** (about a product, not a user) — every surface today is user-scoped. **Architecture decision.** |
| 4 | Let the model web-search | Non-deterministic and unattributed; conflicts with the constitution's authoritative-attribution requirement. Not recommended. |

**Constitutional read on Option 3:** WLJ would own *retrieval, caching, provenance and verbatim exposure* of an
authoritative external document; the model still interprets. That is consistent with I.1/I.2/I.4 — provided WLJ
**never paraphrases or summarizes** a label (that would be WLJ generating clinical content). Must be
background/cached — **never request-path outbound HTTP** (`docs/WLJ_REQUEST_PATH_SAFETY.md`).

---

## 6. Recommendation

1. **Fix Defect A now** (small, no decision needed): stop presenting adherence bookkeeping as plan/administration
   truth — move `grace_period_minutes` out of `plan` into the adherence/standing context where it belongs, label it
   for what it is, and correct the ambiguous semantics line. Add a contract test that WLJ never exposes an
   adherence-tolerance field as prescribing guidance.
2. **Decide Defect B.** Recommended sequence: **Option 2 as the immediate safety floor** (bounded, honest, ships
   today), then **Option 3** if Danny wants the CoS to genuinely own this class — opened as its own architecture
   review, since it introduces impersonal reference truth.

**STOPPED here per instruction. No code changed, no real-model call spent.**

---

## 7. Open item for Danny (one glance)

The verified serialization shows `instructions: null` for a blank record, and the smoke quoted no instruction text —
so Danny's Mounjaro record almost certainly has empty `instructions`. **Not proven:** the audit ledger stores
envelope metadata only (by design), so the stored value cannot be read from it. Confirm in the app if it matters —
though the class holds either way, since that field is regimen notes, not manufacturer labelling.
