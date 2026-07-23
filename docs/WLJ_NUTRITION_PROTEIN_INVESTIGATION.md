# Nutrition "protein yesterday" — Runtime Investigation & Fix

**Date:** 2026-07-22
**Class:** Truth Retrieval Certification — shadow authority, **incomplete-key-set variant**
**Status:** INVESTIGATION COMPLETE → IMPLEMENTED — AWAITING PRODUCTION VALIDATION
**Method:** Hypothesis → Runtime Proof → Architectural Decision → Implementation
**Predecessor:** `docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md` (weight; prod-validated)

---

## 0. The report

While viewing the Nutrition page for **Tuesday, July 21, 2026**, which displayed
Calories 1270 · **Protein 79 g** · Carbs 109 g · Fat 60 g:

> **User:** What was my protein yesterday?
> **CoS:** Your protein intake for yesterday was not recorded.

Contradicting the deterministic truth on screen.

---

## 1. Runtime method

Identical to the weight investigation: `CoSGateway.respond(surface="chat")` →
`ModelInterfaceRuntime` (`use_model_interface=True`) → real gpt-4o → `ToolCallLog`,
with `page_context` set to the Nutrition page for July 21 (the reported situation).

`wlj_dev` was seeded to reproduce the page exactly — verified before drawing any
conclusion: `build_nutrition_summary` returned `1270.00 / 79.00 / 109.00 / 60.00`.

> **Method note.** A first probe run reported doubled values (158 g protein). That was
> **my own test-data contamination** — a census run had left its seeded rows behind —
> not a product defect. Rows were purged and every number below is from a clean re-run.

---

## 2. Runtime trace — the defect, reproduced 2/2

```
Q "What was my protein yesterday?"   (page context: Nutrition, 2026-07-21)
CoS: "Your protein intake for yesterday was not recorded."
  TOOL get_foundational_health_facts  args={"keys": ["protein_today"]}
    -> protein_today: status=not_recorded,
       reason="No protein observation recorded on 2026-07-22",
       authority=get_domain_history:nutrition.protein
```

The model asked for **`protein_today`** to answer a **yesterday** question, received a
correct "not recorded **for today**", and reported it as **yesterday's** answer.

Second rep, same result — and revealing:

```
  TOOL get_foundational_health_facts  args={"keys": ["protein_today", "protein_yesterday"]}
```

The model *tried* `protein_yesterday`. **That key does not exist.**

```
get_foundational_health_facts(["protein_yesterday"])
  -> {"status": "unsupported_fact", "supported": [ ...18 keys, no protein_yesterday... ]}
```

### The contrast that identifies the cause

| Question | Curated key exists? | Result |
|---|---|---|
| "What was my protein **yesterday**?" | `protein_today` only | ❌ 2/2 — wrong day reported |
| "What was my protein **on July 21, 2026**?" | (no key matches) → `get_history` | ✅ 2/2 — **79 g** |
| "How many **carbs** yesterday?" | **no carb keys at all** → `get_history` | ✅ 2/2 — **109 g** |

**The metrics with NO curated key answered correctly. The metric WITH an incomplete
curated key answered falsely.** The curated surface was not merely redundant — its
*incompleteness* was the defect.

---

## 3. Authority census — answers to the numbered questions

Every surface, against identical seeded data:

| # | Authority | protein, 2026-07-21 |
|---|---|---|
| A1 | Page producer `build_nutrition_summary` | **79.0 g** |
| A2 | Current Context page summary `health.nutrition` | **79.00 g protein** |
| A3 | `NutritionQueries.get_daily_totals` | **79.00** |
| A4 | `get_history(nutrition, protein, yesterday)` | **79.0**, confidence high |
| A5 | `metric_date.metric_on_date(nutrition, protein, …)` | **79.0**, `exact_date` |
| A6 | `get_foundational_health_facts(protein_yesterday)` | **`unsupported_fact`** |
| A7 | `get_domain_state("nutrition")` SAE `daily_protein_g` | **0.0** (false zero; `rolling_7d_protein_avg` = 79.0) |

1. **Which tool answered?** `get_foundational_health_facts`, with key `protein_today`.
2. **Did it call the canonical metric-date authority?** Yes — and correctly. It answered
   `not_recorded` **for 2026-07-22**, which is true. The wrong *date* was requested.
3. **What authority answered?** The canonical one, for the wrong day.
4. **Is `protein_yesterday` still a parallel path?** No — it **did not exist**. That is
   the defect: the curated enum offered `protein_today` and nothing else, so the model
   substituted the only protein key on offer.
5. **Does Nutrition history hold the value while another authority says "not recorded"?**
   Yes — A1–A5 all held 79 g; only the curated key set could not express the question.
6. **Another member of the shadow-authority class?** Yes — the **incomplete-key-set**
   variant. Weight's variant was *contradictory values*; this is *false absence*.
7. **Do page / Current Context / Domain Truth / retrieval agree?** **Yes — all four
   agree at 79 g.** The truth layer was never wrong. Only the retrieval *vocabulary* was.
8. **Enumeration & delegation:** A1–A5 all resolve through `NutritionQueries` (the page
   via `get_daily_totals`, the tools via `macro_series`) — one producer, no divergence.
   A7 (`get_domain_state`) remains an unconverted SAE projection (§6 residual).

---

## 4. Root cause

> **A hand-maintained key list stood between the question and the systematic authority.
> When the list lacked the exact (metric, date) pair, the model substituted the nearest
> key it was offered and reported another day's answer as this day's.**

This was **systemic, not nutrition-specific**. Measured across the capability index:

```
domain.metric        today key        yesterday key      verdict
health.steps         steps_today      steps_yesterday    symmetric
nutrition.calories   calories_today   calories_yesterday symmetric
health.glucose       —                glucose_yesterday  *** ASYMMETRIC ***
health.weight        —                weight_yesterday   *** ASYMMETRIC ***
nutrition.protein    protein_today    —                  *** ASYMMETRIC ***
(44 other metrics)   —                —                  no key → get_history (SAFE)
```

**3 of 5 curated metrics were asymmetric**; the curated set covered **7 of 50**
(domain, metric) pairs. The same asymmetry was hand-coded in the legacy classifier:
`_refine_to_day` refined `calories_today` → `calories_yesterday` but had **no protein
branch**, so "protein yesterday" stayed on `protein_today` there too.

---

## 5. Architectural decision & implementation

**Remove the hand-maintained list from the path** — two coordinated changes:

**(a) The key set is DERIVED, never hand-listed.** `_date_scoped_index()` generates
`<metric>_today` / `<metric>_yesterday` for **every** metric in
`history_capability_index()`. Coverage went **7 → 101** keys, symmetric by
construction. A metric can never again be offered for one date but not the other.

**(b) The model is offered ONE door for "metric X on date D".** The date-scoped keys
were removed from the **model-facing enum** (`model_facing_facts()`, 18 → 11 keys);
`get_history` owns date-scoped questions and answers every metric for every date. The
keys remain **serveable** for the legacy deterministic classifier, which names them
directly. The tool description now says so explicitly.

**(c) The legacy `_refine_to_day` is generic** — any `<metric>_today` refines to
`<metric>_yesterday` against the derived set, instead of a per-metric branch.

**(d) A bare call returns the model-facing set,** not all 101 keys (which would have
produced a ~48 KB payload for a tool whose purpose is a tiny one). Envelopes dropped
`schema_version`/`lookback_days` — internal bookkeeping the model cannot act on.

### Runtime verification (real gpt-4o, 2 reps each — 14/14)

| Question | Result | Tool |
|---|---|---|
| **PROD-VALIDATED** "weight yesterday" | ✅ 281.5 lb | `get_history` |
| **PROD-VALIDATED** "weight on July 21, 2026" | ✅ 281.5 lb | `get_history` |
| **PROD-VALIDATED** "most recently known weight" | ✅ 280.4 lb, recorded today | `get_foundational_health_facts` |
| **THE DEFECT** "protein yesterday" | ✅ **79 g** | `get_history` |
| "carbs yesterday" | ✅ 109 g | `get_history` |
| "calories yesterday" | ✅ 1,270 | `get_history` |
| "steps yesterday" | ✅ 6,200 | `get_history` |

The three questions validated in production were re-probed specifically because
removing enum keys risked regressing them. **No regression.**

### Certification gates

`apps/ai/tests/test_metric_date_authority.py` — day-key coverage is **symmetric for
every metric in the capability index** (the generic gate that makes this class
impossible); all six nutrition macros answerable for both days; the model is not
offered a second door for a date question; derived keys still serveable for legacy;
generic legacy day-refinement.

---

## 6. Residuals (logged, not fixed)

1. **`get_domain_state("nutrition")` still projects the SAE snapshot** (`daily_protein_g`
   = 0.0 while the live authority holds 79 g for the prior day). It is a *broad overview*
   tool, not a date-scoped one, so it is not part of this class — but it is the remaining
   Class-A work in `docs/WLJ_TRUTH_RETRIEVAL_CERTIFICATION_PROGRAM.md`.
2. **Non-date-scoped SAE-backed keys** (`last_glucose_reading`, `average_glucose_yesterday`,
   `sleep_*`, `steps_recent`, `last_blood_pressure_reading`, `weight_30_day_change`) are
   unconverted.
3. **`sleep_last_night`** keeps its `latest_sleep` authority (night-of vs wake-date
   attribution needs its own runtime proof); now discloses `semantics`.
4. **Self-consistency reasoning miss** from the weight investigation §10.3 is unchanged.

## 7. Test-suite honesty

Running the legacy suites surfaced 6 failures. Baselined in a clean worktree at
`f7cad624` (before any of this work):

* **4 were caused by my previous commit** (`140e6c3c`) — `current_weight`/macro facts
  moved from the mocked SAE snapshot to live reads, and I had not run those suites.
  Fixed by giving the tests real records (the same migration already applied to
  medications).
* **2 pre-dated all of this work** (`test_full_facts_payload_under_2000_chars`,
  `test_medications_from_canonical_state`) — fixed here as well.
* **3 further failures** in `test_chatgpt_cos_clean` / `test_p29_morning_and_precedence`
  were confirmed pre-existing at `f7cad624` and are **untouched / out of scope**.
