# WLJ Body Measurement Interpretation

**Canonical module:** `apps/health/services/measurement_interpretation.py`
**Consumed by:** `apps/health/services/body_intelligence.py` (`_measurement_rows`) → the Body
Intelligence "Body measurements" cards (`templates/health/_bi_measure_table.html`).
**Tests:** `apps/health/tests/test_measurement_interpretation.py`

---

## The question each card answers

> **"What direction has this body part been moving since the start of this journey, and does
> that align with the rest of the body?"**

It reads the **whole journey**, not a single week — so it describes the long-term story like a
body coach and does **not** react to one week's measurement noise. Each card shows:

| Concept | Example |
|---|---|
| **Status** | 🟢 Improving / 🔴 Needs attention / ⚪ Stable / ⚪ Inconclusive |
| **Overall trend** (baseline → now) | "Down 6.2 in" |
| **Recent trend** (rolling ~35 days) | "Down 0.5 in" / "Flat" |
| **Evidence** (limbs) | "Body fat ↓ over your journey · Lean mass ↑ over your journey" |
| **Interpretation** | "Excellent progress — continues moving in the desired direction." |

Five states, four colours:

| State | Colour | Meaning |
|---|---|---|
| 🟢 **Improving** | green | moving the healthy direction **over the journey** |
| 🟡 **Recovering** | amber | still short of the goal **overall**, but recent momentum is **correcting** |
| 🔴 **Needs attention** | red | moving away from the goal **over the journey** |
| ⚪ **Stable** | gray | a *confident* "no meaningful long-term change" |
| ⚪ **Inconclusive** | gray | not enough history / conflicting signals to conclude |

**Status is driven by the OVERALL trend** (noise-resistant); the **narrative reflects recent
momentum**. *Recovering* is the key nuance: e.g. lean mass below baseline overall but rising in
recent readings reads "Still below your starting point, but rebuilding" — **not** muscle loss.

## WLJ Truth architecture: Facts → Assessment → Interpretation

Each card shows **facts first** (Current · Overall trend · Recent trend — deterministic WLJ
truth), then a divided **Interpretation** section. The interpretation *explains* the facts and
must never contradict them.

Before any card renders, `build_body_assessment` builds **one** holistic whole-body verdict from
the complete composition truth. **Every** card's interpretation — and the **Insights** list
(`build_insights`, generated FROM the interpreted rows) — derives from that single assessment, so
no card independently infers a conclusion that conflicts with another. Facts → whole-body
assessment → per-measurement interpretation.

---

## Baseline & trends (`analyze_trajectory`)

* **Baseline** = the **first logged reading** — the start of the journey. (No compelling reason
  to pick another baseline; the DB order is the journey.)
* **Overall** = latest − baseline.
* **Recent** = latest − the earliest reading within the last **35 days** (falls back to the
  prior reading). This is the rolling momentum.
* **< 2 readings** → `None` → the card is *Inconclusive* ("keep logging").

Meaningful-change thresholds are per-unit and **larger for Overall than Recent**, so one week
never sets the long-term story: Overall `in 0.3 · lb 1.0 · pct 0.4 · kcal 30`; Recent is ~half.

---

## Category map (`MEASUREMENT_CATEGORY`)

| Category | Metrics | How it's judged |
|---|---|---|
| `decrease_good` | waist, hips, neck, body_fat_pct, fat_mass, visceral_fat, bmi, metabolic_age | own journey; smaller is healthier |
| `increase_good` | lean_mass, skeletal_muscle_mass, bone_mass | own journey; larger is healthier |
| `inferred` | arm/forearm/thigh/calf, **chest, shoulders** | circumference's journey **against the assessment** |
| `supporting` | bmr, body_water_pct | contextual — lower-confidence supporting evidence, against the assessment |

**Nothing is "neutral / no goal."** Every measurement contributes evidence toward the one goal
(improving the body); some (`supporting`) contribute with lower confidence, but all participate in
the same story. Anything unlisted → `supporting`.

## The executive summary (`build_body_assessment` output)

Computed ONCE, rendered as **"Your Body Assessment"** at the TOP (the cards are its evidence). It
returns, besides `status`/`confidence` (which the cards consume): `grade` (Overall progress —
Excellent / Great / Good / Recovering-grade / Needs attention / …), `headline`, `facts` (journey
highlights: Weight ↓ 27 lb, Waist ↓ 6.2 in, Fat Mass ↓ 14 lb, and a lean-mass sentence),
`overall`, and `opportunity`. The Insights list mirrors the cards, so nothing invents a different
story.

---

## Whole-body assessment (`build_body_assessment`)

The ONE deterministic verdict from the fat / lean / weight trajectories (overall **and** recent).
Used to interpret every limb, and the source the Insights list mirrors.

| Condition | Verdict | Status |
|---|---|---|
| fat ↓ **and** lean ↑ (overall) | recomposition | 🟢 Improving |
| lean ↓ overall **but** lean ↑ recently (≥ 0.5 lb) | recovering | 🟡 Recovering |
| lean ↓ overall **and not** rebuilding | muscle loss | 🔴 Needs attention |
| fat ↓ **and** lean not down | fat loss, muscle preserved | 🟢 Improving |
| fat ↑ **and** lean ↑ (or unclear) | mixed | ⚪ Inconclusive |

*(fat ↓ = fat mass ≤ −1 lb or body-fat ≤ −0.4 pct over the journey.)* A limb inherits the
assessment status (a flat limb → Stable). A shrinking limb reads 🔴 only under genuine
*muscle loss*; under *recovering* it reads 🟡, consistent with the body.

---

## Interpreting a limb

1. Limb **flat** over the journey → ⚪ **Stable** ("no meaningful long-term change").
2. Else read against `classify_body_journey`:
   * body **Improving** → limb Improving. Bigger limb → "muscle development"; smaller limb →
     "fat loss, not muscle loss".
   * body **Needs attention** (losing lean) → a **shrinking** limb → 🔴 "possible muscle loss";
     a growing limb → ⚪ Inconclusive (mixed signal).
   * body **Inconclusive / low confidence** → ⚪ Inconclusive ("keep tracking").

So the same **down** arrow reads 🟢 green during fat loss and 🔴 red during muscle loss — the
user never has to know whether up or down is "good".

---

## Worked examples

- **Waist** — Overall Down 6.2 in, Recent Down 0.5 in → 🟢 "Excellent progress — continues
  moving in the desired direction."
- **Hips** — Overall Down 3 in, Recent Flat → 🟢 "Strong overall progress; plateaued recently."
- **Arm** — Overall Up 0.4 in, body losing fat + gaining lean → 🟢 "Growing while you're losing
  fat and building muscle."
- **Calf** — Overall Flat → ⚪ "Stable — no meaningful long-term change."
- **Calf** — Overall Down 0.6 in, body losing lean → 🔴 "Shrinking while lean mass has fallen —
  possible muscle loss."

---

## Honesty notes

* A dedicated **strength** signal is not yet wired request-path-safe, so evidence is built from
  fat / lean / weight (which directly measure muscle-vs-fat) — never a fabricated "Strength ↑".
  Wiring a precomputed strength-trend (workout/PR progression) into the background cycle is a
  clean follow-up.
* All inputs are deterministic truth already computed (the per-metric history series + weight
  history). This module only INTERPRETS — no new request-path queries.
