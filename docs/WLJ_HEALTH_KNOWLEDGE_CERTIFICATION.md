# WLJ Health Knowledge Certification

**Status:** Living document. Established 2026-07-29.
**Governing question (NOT "what tables exist?"):** *If Danny asked any reasonable question about this health domain, is the deterministic truth already available to the Chief of Staff?*

Glucose is the **gold-standard reference implementation**. Every other health domain is
certified against the same dimensions. This milestone certified the domains that reusable
platform capabilities + cheap truth-exposure could reach, and **phased** the domains that
require new per-metric truth producers (with explicit promotion triggers).

---

## The 9 certification dimensions

1. **Current Context** — can questions about the current page be answered without retrieval?
2. **Current Truth** — can the current value be retrieved? (`get_domain_state` / `current()`)
3. **Historical Truth** — per-day series over a period? (`get_history`)
4. **Reading Series** — intra-day / high-frequency readings? (`get_readings`) — *only where applicable.*
5. **Trends** — a deterministic change/direction? (**platform**, on every history series)
6. **Comparisons** — period A vs period B? (**platform**, `get_comparison`)
7. **Analysis Inputs** — a composed evidence bundle to reason over? (`get_analysis`)
8. **Adherence** — actual vs the user's target/limit? (**platform**, `get_adherence`) — *where a target exists.*
9. **Missing / Duplicate** — what truth should exist but doesn't; any duplicate producers.

---

## Reusable platform capabilities (built this milestone — ONE each, never per-domain)

Per the mandate ("build ONE comparison capability, not nutrition/weight/glucose comparisons"):

| Capability | Surface | Reuse | Applies to |
|---|---|---|---|
| **Trend** | `HistorySeries.change()` → flows through `get_history` + every `get_analysis` window | endpoints + least-squares slope; direction is arithmetic (rising/falling/flat), never a verdict | **every** history metric, free |
| **Comparison** | `get_comparison(domain, metric, period_a, period_b)` (`domain_comparison.py`) | composes two `get_domain_history` reads | **every** history metric |
| **Adherence** | `get_adherence(domain, metric, period)` (`domain_adherence.py`) + target registry (`core/truth/targets.py`) | composes history (actual) vs a registered target | any metric with a registered target |
| **Reading series** | `get_readings` (prior Glucose milestone) | `reading_window` + `windows` | high-frequency metrics (glucose; HR/SpO2 phased) |

These are advertised in the capability index (`truth_comparison`, `truth_adherence`) so the
model discovers them, and they are catalog/registry-driven — a metric participates the moment
it declares a history series or registers a target.

---

## Certification matrix (post-milestone)

Legend: ✅ present · ➖ n/a · ⬜ gap (phased). Trend/Comparison are ✅ for every history metric by construction.

| Domain | Current Ctx | Current | History | Series | Trend | Compare | Analysis | Adherence | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Glucose** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | **Certified** (gold standard) |
| **Weight** | ✅ | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ⬜(goal) | **Certified** |
| **Nutrition (macros)** | ✅ | via state | ✅ (6 macros) | ➖ | ✅ | ✅ | ✅ (+aliases) | ✅ (new) | **Certified** |
| **Body composition** | ✅ (Body Intelligence) | ⬜ | ✅ (25 metrics) | ➖ | ✅ | ✅ | ✅ (new) | ➖ | **Certified** |
| **Steps** | ⬜ blind page | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ✅ (new) | **Needs Current Context** |
| **Sleep** | ⬜ blind page | ✅ | ✅ | ➖ | ✅ | ✅ | ✅ | ➖ | **Needs Current Context** |
| **Workouts** | ⬜ blind page | ➖ | ✅ | ➖ | ✅ | ✅ | ✅ | ➖ | **Needs Current Context** |
| **Blood pressure** | ⬜ blind page | ⬜ | ✅ (sys/dia/pulse) | ⬜(phase) | ✅ | ✅ | ✅ (new) | ➖ | **Needs Current Context + Current** |
| **Heart rate** | ⬜ blind page | ⬜ | ⬜ | ⬜ | — | — | ⬜ | ➖ | **Needs New Truth** |
| **Water** | ⬜ blind page | ⬜ | ⬜ | ➖ | — | — | ⬜ | ⬜(goal) | **Needs New Truth** |
| **SpO2 (blood oxygen)** | ⬜ blind page | ⬜ | ⬜ | ⬜ | — | — | ⬜ | ➖ | **Needs New Truth** |
| **Body temperature** | ⬜ (no page) | ⬜ | ⬜ | ➖ | — | — | ⬜ | ➖ | **Needs New Truth** |

Certification statuses used: **Certified · Needs Current Context · Needs Retrieval · Needs Truth Exposure · Needs New Truth · Needs Platform Capability**.

---

## Shipped this milestone

- **Platform:** Trend (`HistorySeries.change`), Comparison (`get_comparison`), Adherence (`get_adherence` + `core/truth/targets.py` registry). All catalog/registry-driven and advertised in the capability index.
- **Nutrition (the reported failure — "do I need more carbs or are they in line?"):**
  - Adherence targets registered for calories/protein/carbs/fat/fiber (targets) + sugar/sodium (limits); `get_adherence("nutrition","carbs")` now returns target/actual/signed-variance/%.
  - Analysis-subject aliases added: `macronutrients`, `macronutrient_intake`, `macronutrient`, `macro`, `carbohydrates`, `fiber`, `sugar` (the "macronutrient intake" routing miss).
- **Analysis-blind gaps closed:** `blood_pressure`/`bp` and `body_composition`/`waist`/`body_fat` are now analysis subjects.
- **Steps:** step-goal adherence registered.

## Phased backlog (deferred = phased, with promotion triggers)

- **Phase 2a — Blind-page Current Context** (steps, sleep, blood pressure, heart rate, water, fitness): add `PageSummaryMixin` + a `@register_page_summary` provider that reuses each page's existing summary builder (mirror `health.glucose`/`health.weight`). **Trigger:** the next time one of these pages is touched, or a reported "look at this page" miss.
- **Phase 2b — New-truth metric surfaces** (heart rate, water, SpO2, temperature): models exist but expose no DomainTruth surfaces. Add `current` + `history` providers (mirror `HealthHistory.glucose`/`steps`), an analysis subject, and — for HR/SpO2 — a `reading_metrics` intra-day series (mirror `glucose_reading_window`). **Trigger:** the user asks about any of these, or a wearable begins syncing them at volume.
- **Phase 3 — Adherence targets:** water goal, weight goal. **Trigger:** confirm the canonical storage location for each goal, then register a provider.

## Invariants (do not regress)
- WLJ exposes **facts** (target, actual, variance, direction) — the model renders the verdict ("in line", "improving"). Trend direction is arithmetic, never "better/worse".
- ONE producer per truth; comparison/adherence **compose** existing surfaces and add no parallel retrieval.
- A missing target returns `no_target` (never treated as zero); an empty window returns `empty` (never "the metric is unavailable").
