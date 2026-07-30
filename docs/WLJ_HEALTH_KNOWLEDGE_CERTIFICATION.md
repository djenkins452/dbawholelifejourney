# WLJ Health Knowledge Certification

**Status:** Living document. Established 2026-07-29.
**We certify QUESTIONS, not domains.** The customer never asks "is Heart Rate certified?" — they ask "has my resting heart rate improved?" A metric is certified when the reasonable customer questions about it are answerable from deterministic truth. The dimensions below are the *means*; the **Question Certification matrix** is the *measure*.

Glucose is the gold-standard reference. This milestone closed the "Needs New Truth" and "Needs Current Context" rows for heart rate, water, SpO2, temperature, blood pressure, steps, and sleep — via the reusable spine (a metric with current+history inherits trend/comparison/analysis; a reading series adds intra-day + time-of-day; a registered target adds adherence).

## THE CERTIFICATION IS DATA-DRIVEN — the Question Catalog is the standard

Certification is no longer produced by architectural reasoning; it is a **permanent, machine-checked artifact**. Each domain declares its real customer questions in a **Question Catalog** (`apps/health/health_question_catalog.py` for Health); each question declares the deterministic truth it REQUIRES; and the reusable framework (`apps/core/truth/question_catalog.py`) **computes** `certified` by checking those requirements against the LIVE capability registries. A question auto-certifies the day its required surface ships.

- **Run it:** `python manage.py certify_questions health` (add `--gaps` for only the failures).
- **Enforced:** `apps/core/truth/tests/test_question_catalog.py` ratchets the certified set — if a certified question regresses (a surface broke) or a gap closes, the test fails until the catalog lock is reviewed.
- **Extend, don't reinvent:** future Health work = add a `Question` to the catalog. Certification becomes "can the CoS answer every question in the catalog?", never "can someone think of more questions?"
- **Reusable framework:** the framework is domain-agnostic (Requirement = `(capability, domain, target)` checked against the wired registries). Finance / Faith / Relationships / Journal / Goals / Medical / Travel each add a catalog module and register in `question_catalog._DOMAIN_MODULES`. **Health is the reference catalog** — the first proven implementation; other domains adopt the same pattern with zero new framework code.

**Current live status: 74 / 80 Health questions certified (92.5%).** The 6 gaps below each need a NEW platform capability or a page that does not exist — genuine future milestones, not oversights.

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

## Question Certification matrix

✅ = answerable from deterministic truth now · ◑ = answerable but requires the model to reason over multiple deterministic reads (no single-call surface) · ⬜ = not yet answerable (see "Still impossible").

| Domain | Representative customer questions | Verdict | Truth path |
|---|---|---|---|
| **Glucose** | overnight lows? time below 70? what time of night? last urgent low? | ✅ | `get_readings` (below_low, urgent, by_hour, low_excursions) |
| | are overnight lows getting *more frequent*? | ◑ | two `get_readings` windows, model compares counts (no excursion-frequency series) |
| **Nutrition** | enough carbs/protein/calories? over sugar limit? | ✅ | `get_adherence` (target/actual/variance) |
| | which macros am I consistently missing? | ✅ | `get_adherence` per macro |
| | which meals have the most carbs? | ◑ | `get_entity('meal')` detail, model ranks (no ranked-by-macro surface) |
| **Weight** | losing too quickly? loss accelerating? vs last month? | ✅ | `get_history` change/slope · `get_comparison` |
| | when did my trend change? | ⬜ | no change-point capability |
| **Sleep** | sleeping enough? improved? worst nights? | ✅ | `get_history` (avg, trend, per-day points) |
| | how consistent is my schedule? | ⬜ | no bedtime-variance/consistency metric |
| **Heart rate** | resting HR improved? trend? | ✅ | `get_history('resting_heart_rate')` + trend |
| | intra-day HR? recovery improving? | ◑/⬜ | readings ✅; HRV/recovery metric ⬜ (fields on SleepEntry unexposed) |
| **Blood pressure** | improving? time of day highest? how often above range? | ✅ | `get_analysis`/trend · `get_readings` by_hour + above_high |
| **Body composition** | gaining muscle? losing fat? body-fat trend? | ✅ | `get_history('lean_mass'/'body_fat_pct')` + trend |
| **Steps** | hitting my goal? trend? vs last week? | ✅ | `get_adherence` · `get_history` · `get_comparison` |
| **SpO2** | trend? any dips? current? | ✅ | `get_history('spo2')` · `get_readings` |
| **Body temperature** | trend? any fever readings? | ✅ | `get_history('body_temperature')` · `get_readings` (urgent_high 100.4) |
| **Workouts** | how many? what did I do? trend? | ✅ | `get_history('workouts')` · `get_entity('workout')` · `get_analysis` |

**Current Context (answer "look at this page" without retrieval):** now declared on home, weight, nutrition, glucose, body-intelligence, **steps, sleep, heart rate, blood pressure, water** (10 pages). Remaining blind: fitness, health-intelligence, blood-oxygen, temperature (no dedicated page) — Phase 2c.

---

## Shipped (milestone 1 — platform)

- Trend (`HistorySeries.change`), Comparison (`get_comparison`), Adherence (`get_adherence` + `core/truth/targets.py`). Nutrition macro-adherence + aliases; BP/body-comp analysis subjects.

## Shipped (milestone 2 — question closure)

- **New-truth metric surfaces (closed "Needs New Truth"):** heart rate, resting heart rate, water, SpO2, body temperature now have per-day **history** (`HealthHistory.*`) → inherit trend/comparison/analysis; **entity** detail (`health_entities`); and — for the high-frequency vitals — an intra-day **reading series** (`vitals_readings.py`: heart_rate, blood_pressure, spo2, body_temperature) with the new **hour-of-day distribution**.
- **Hour-of-day distribution** (`reading_window.by_hour`, reusable): peak/lowest hour + per-hour count/avg/min/max — answers "what time of day is X highest" / "what time of night do my lows occur" (glucose enables it too).
- **Current Context (closed "Needs Current Context"):** page summaries for steps, sleep, heart rate, blood pressure, water via a reusable `_metric_page_summary` (reuses history+trend+adherence). Mixin added to the five blind views.
- **Adherence targets:** water (64 oz app default). Steps already registered.

## Questions still impossible (and exactly why)

1. **"Are my overnight lows becoming more frequent?"** — comparison compares history *averages/totals*, not reading-window *excursion counts* across windows. Needs an excursion-frequency series or a comparison mode over reading-window stats. (◑ today: model compares two `get_readings` windows.)
2. **"When did my weight trend change?"** — no deterministic change-point detection. Trend gives one slope over the window, not the inflection date.
3. **"How consistent is my sleep schedule?"** — no bedtime-variance/consistency metric (a variance/regularity platform capability).
4. **"Is my recovery / HRV improving?"** — `SleepEntry.heart_rate_avg/min/max` + `respiratory_rate` exist but are not exposed as history metrics; no recovery composite.
5. **"Which meals have the most carbs?"** — meal record detail exists (`get_entity('meal')`) but there is no ranked-by-macro surface; the model must rank the returned records.
6. **"Did exercise change my HR baseline?"** — cross-domain correlation; answerable by the model reasoning over two deterministic reads, not a single surface.

## Phased backlog (deferred = phased, with promotion triggers)

- **Phase 2c — Remaining Current Context:** fitness, health-intelligence, blood-oxygen pages (no temperature page exists). **Trigger:** page touch or a "look at this page" miss.
- **Phase 3a — Variance/consistency platform capability** → sleep schedule consistency, glucose variability (generalize the glucose-specific CV). **Trigger:** a consistency/variability question.
- **Phase 3b — Excursion-frequency trend** (reusable comparison over reading-window stats) → "lows getting more frequent". **Trigger:** the glucose-frequency question recurs.
- **Phase 3c — Recovery/HRV exposure** (SleepEntry cardiac fields → history) + change-point detection. **Trigger:** a recovery or "when did it change" question.

## Invariants (do not regress)
- WLJ exposes **facts** (target, actual, variance, direction) — the model renders the verdict ("in line", "improving"). Trend direction is arithmetic, never "better/worse".
- ONE producer per truth; comparison/adherence **compose** existing surfaces and add no parallel retrieval.
- A missing target returns `no_target` (never treated as zero); an empty window returns `empty` (never "the metric is unavailable").
