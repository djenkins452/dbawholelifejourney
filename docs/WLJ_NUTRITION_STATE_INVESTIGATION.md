# Nutrition SAE Projection — Runtime Investigation & Fix

**Date:** 2026-07-23
**Class:** Truth Retrieval Certification — Class A (snapshot projection vs canonical authority)
**Status:** INVESTIGATION COMPLETE → IMPLEMENTED — AWAITING PRODUCTION VALIDATION
**Method:** Hypothesis → Runtime Proof → Architectural Decision → Implementation
**Predecessors:** `WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md`, `WLJ_NUTRITION_PROTEIN_INVESTIGATION.md` (`5b4bd722`)

---

## 0. Premise correction (stated first, because it changes the diagnosis)

The residual was carried forward as *"`daily_protein_g = 0.0` while the canonical
authority holds 79 g."* **Runtime proof shows that framing was wrong — and the error
was mine**, written into my own changelog residual note.

`daily_protein_g` describes **today**. The 79 g was **yesterday's**. Comparing them
compares two different questions. With data logged today and the snapshot fresh, every
surface agrees exactly:

```
snapshot daily_*   : 1270.0 / 79.0 / 109.0 / 60.0
get_daily_totals   : 1270.00 / 79.00 / 109.00 / 60.00
metric_on_date     : 1270.0 / 79.0 / 109.0 / 60.0
-> agree: True
```

**But the investigation did find a real, provable contradiction** — a different and
more dangerous one than the reported symptom.

---

## 1. The real defect — date-rollover staleness (runtime-proven)

`daily_*` is a claim **about a calendar day**, but the snapshot carried **no record of
which day**, and the freshness guard detects staleness by looking for a **newer raw
write**. At a date rollover there *is no write to detect* — so the guard structurally
cannot fire:

```
B. Clock advances one day — NO new food entry
   snapshot daily_* (still says 'today'): {'daily_protein_g': 79.0, ...}
   canonical get_daily_totals(new today): {'protein_g': '0', ...}
   metric_on_date(protein, new today)   : not_recorded
   get_history(protein, new today)      : empty
   *** CONTRADICTION: snapshot says 79.0 g 'today' while canonical says not_recorded
   ensure_fresh cannot fire: no FoodEntry write is newer than the snapshot.
```

Every morning before the first log, `get_domain_state("nutrition")` reported **yesterday's
macros as today's**, while `metric_on_date`/`get_history` correctly said not-recorded.
That is exactly the parallel-truth condition the milestone exists to remove.

### Supporting findings

| # | Question | Finding |
|---|---|---|
| 1 | Which handler serves it | `get_domain_state` → `DOMAIN_REGISTRY["nutrition"]="nutrition"` |
| 2 | Which store | SAE `UserState.state_data["nutrition"]`, read `allow_rebuild=False` |
| 3 | Which builder | `build_nutrition_state` |
| 4 | When it runs | background SAME cycle + write-triggered `deferred_sae_refresh` + read-path `ensure_fresh` |
| 5 | Failure mode | **stale by date rollover** + **independently calculated** + **no freshness envelope** |
| 6 | Page vs Current Context | **same** producer (`build_nutrition_summary` → `get_daily_totals`) — never in conflict |
| 7 | Readers of the projection | `get_domain_state` (model-callable), dashboard/mission composers, insight rules, `signal_trust` |
| 8 | Other disagreeing fields | `rolling_7d_*` uses a **different denominator** than `get_history(...).average` (days-with-data, excludes today) — same-sounding, different contract |

**Independent calculation (3):** `build_nutrition_state` ran its own
`today_entries.aggregate(Sum(...))` instead of calling `NutritionQueries.get_daily_totals`
— a second calculation of one deterministic question, and it silently omitted sugar.

---

## 2. Fix — the snapshot may cache canonical truth, never produce it

1. **Delegate.** `build_nutrition_state` now calls `NutritionQueries.get_daily_totals(user, today)`
   — the same producer behind the page, Current Context, `get_history` and `metric_date`.
   Sugar added; no aggregation of its own remains.
2. **Date-stamp.** The snapshot records `daily_totals_date` — the user-local day its
   `daily_*` fields describe. An undated day-claim is what made rollover invisible.
3. **Detect rollover.** `state_freshness._DATE_BOUND_MODULES` registers nutrition's date
   field; `ensure_fresh` checks it **before** the raw-write check. One dict read, no
   query. Repair is the same bounded single-module rebuild already approved for
   nutrition (~10 queries) — **never** a full SAE rebuild on the request path.
4. **Disclose.** `get_domain_state` now returns `day_freshness` (`current`/`stale`/`unknown`),
   `state_date`, `user_local_date`, and on stale a `day_freshness_reason`. **The stale
   values are still returned — disclosed, never hidden or suppressed.**
5. **Name the different contract.** `rolling_7d_basis` states the window, denominator
   (`days_with_data`) and `excludes_today: true`, so it cannot be mistaken for the daily
   value or for `get_history`'s average.

### After the fix (same probe)

```
B. Clock advances one day — NO new food entry
   snapshot daily_*: {'daily_protein_g': 0.0, ...}   <- self-healed
   metric_on_date  : not_recorded
   *** CONTRADICTION: False
   envelope: day_freshness=current, state_date=<today>, user_local_date=<today>
```

---

## 3. Certification (Phases 3 & 4) — `apps/ai/tests/test_nutrition_truth_agreement.py` (17 gates)

**Agreement matrix** — for calories/protein/carbs/fat on one user-local day, asserting a
single value set across: rendered page · Current Context summary · `NutritionQueries` ·
`get_history` · `metric_date` · `get_foundational_health_facts` day keys ·
`get_domain_state`. Plus exact-date semantics, `observed_on`, and authority provenance.

**Snapshot-is-not-a-producer gate:** stubbing `NutritionQueries.get_daily_totals` changes
the snapshot — proving it has no second calculation path.

**Lifecycle:** a new record refreshes; date rollover repairs with no write; a failed
repair is **disclosed as `stale`** with the real `state_date` (not silently current);
an unstamped pre-upgrade snapshot reads `unknown`, not current; the repair is a bounded
single-module rebuild (asserts `rebuild_user_state` is **not** called); disclosure never
breaks the read.

## 4. Phase 5 — real model-interface verification

`CoSGateway.respond(surface="chat")` → model_interface → real gpt-4o → `ToolCallLog`,
on the Nutrition page for the seeded day, 2 reps.

| Prompt | Result |
|---|---|
| "How much protein did I get yesterday?" | ✅ 2/2 — **79 g** (`get_history`) |
| "What were my calories, protein, carbs, and fat yesterday?" | ✅ 2/2 — 1,270 / 79 / 109 / 60 |
| "How did I do nutritionally yesterday?" | ✅ correct facts (per-meal + totals; phrasing varies) |
| "What does my Nutrition overview show for yesterday?" | ✅ correct facts (see residual) |
| follow-up "And protein?" | ✅ 2/2 — no contradictory fact |
| follow-up "Why does the overview say something different?" | ✅ **2/2 — no disagreement exists to explain** |

**Regression set (all ✅):** current weight 280.4 "recorded today" · weight yesterday
281.5 · explicit-date weight 281.5 · protein yesterday 79 · carbs 109 · calories 1,270.

## 5. Phase 6 — Class-A audit (read-only; nothing implemented)

49 day/current-shaped snapshot fields scanned across every registered domain.
**Nutrition is now LOW risk on every field** (day-stamped + disclosed + delegated).

Ranked residuals for the next milestone — corrected for honesty (`last_*_entry` fields
are provenance **timestamps**, not day-value claims, so they are lower risk than a naive
name match suggests):

| Rank | Domain.field | Canonical authority | Delegates? | Envelope? | Risk |
|---|---|---|---|---|---|
| 1 | `tasks.completed_today` / `life.completed_today` | `get_history:tasks.completed` | No | No | **HIGH** — day-value claim, background-only refresh, undated |
| 2 | `calendar.today_events` / `current_event` | `get_history:calendar.events` | No | No | **HIGH** — day-value claim, undated |
| 3 | `journal.last_mood` | `get_history:journal.mood` | No | No | MED — write-only refresh (no rollover hole; not a day claim) |
| 4 | `health.last_*_entry` (weight/glucose/bmi/bmr/waist/lean_mass/fat_mass) | corresponding `get_history` | No | No | LOW–MED — provenance timestamps, can lag but do not claim "today's value" |
| 5 | `fitness.today_*`, `medicine.today_*`, `routine.today_*` | none | n/a | No | LOW — no overlapping history authority to contradict |

**Recommended next slice:** apply this milestone's exact pattern (delegate → date-stamp →
rollover detection → disclosure) to `tasks/life.completed_today` and `calendar.today_events`.
The mechanism is now generic: `_DATE_BOUND_MODULES` + `day_bound_field()` + `_day_freshness()`.

## 6. Residuals (logged, not fixed)

1. **`get_entity` with an invented `entity_type`** (`nutrition_overview`): WLJ answered
   correctly — `status: unsupported` with the valid list and an honest reason — and the
   model narrated it as *"not recorded"*. A **Layer-2 reasoning miss over an honest
   envelope**, not a truth defect. No detector added.
2. **"And protein?" after an ENTITY retrieval** is not anchored to a metric (the subject
   is the meal record). No contradictory fact resulted; a metric-shaped follow-up after an
   entity retrieval is a distinct anchoring case from the one closed in `140e6c3c`.
3. **Pre-existing, unrelated, NOT absorbed:** `test_nutrition_entity_truth.test_nutrition_is_now_entity_capable`
   (asserts `entity_types == ('food',)`; the domain legitimately grew to
   `('food','meal','frequent_food')`) — confirmed failing with this milestone's changes
   stashed. Also still out of scope: `test_chatgpt_cos_clean`, `test_p29_morning_and_precedence`.

## 7. Durable principle

None added to the startup package. This milestone is an *instance* of principles already
recorded — *one authority per truth domain*, *snapshots project canonical truth rather
than independently producing it*. The one non-obvious mechanism, worth reusing verbatim:

> **A snapshot field that describes a calendar DAY must record WHICH day.** Staleness
> detection based on "is there a newer write?" is structurally blind to a date rollover,
> because the passage of midnight writes nothing.
