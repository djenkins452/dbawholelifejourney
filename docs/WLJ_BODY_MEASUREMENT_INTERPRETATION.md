# WLJ Body Measurement Interpretation

**Canonical module:** `apps/health/services/measurement_interpretation.py`
**Consumed by:** `apps/health/services/body_intelligence.py` (`_measurement_rows`) → the
Body Intelligence "Body measurements" cards (`templates/health/_bi_measure_table.html`).
**Tests:** `apps/health/tests/test_measurement_interpretation.py`

---

## The question each card answers

> **"What is this change most likely telling me?"**

Every measurement card communicates three *separate* things:

| Concept | Where it shows |
|---|---|
| The **literal** measurement change | the arrow (▲ up / ▼ down / → none) + the signed number |
| Whether that change is a **healthy** direction | the colour + status word |
| The current **status** | Improving · Needs attention · No change |

The arrow is *always* the literal movement. The **colour and label are the judgment** — so
the user never has to remember whether "up" or "down" is good for a given metric.

Three visual states (and only three):

| State | Colour | Meaning |
|---|---|---|
| 🟢 **Improving** | green | movement in the healthy direction |
| 🔴 **Needs attention** | red | movement away from the goal |
| ⚪ **Inconclusive** | gray | the deterministic signals don't support a confident conclusion (or nothing meaningful has moved yet) |

We deliberately **never** say "No change" when the truth is "we cannot confidently determine
what this means" — that is **Inconclusive**, and we say so ("keep tracking over the next few
check-ins"). We never present an uncertain inference as certain; medium-confidence limb reads
are hedged ("Likely improving").

Every card also surfaces the **evidence** it was built from + a one-line **conclusion**, so the
user understands *why* WLJ reached the verdict — e.g. `Body fat ↓ · Lean mass ↑` →
"Likely muscle gain while losing fat."

---

## Core principle: never judge a circumference in isolation

WLJ always has the whole picture — daily body weight, body-fat %, lean mass, fat mass, and
the precomputed body-composition signals. A limb (arm/forearm/thigh/calf) getting bigger or
smaller can be muscle **or** fat, so we do **not** hard-code "arms bigger = good". Instead we
infer the **body's direction** and read the limb change through it.

---

## Category map (`MEASUREMENT_CATEGORY`)

Every measurement is one of four categories. New measurements inherit behaviour by being
added here (anything unlisted defaults to `neutral` — we never fabricate a verdict).

### `decrease_good` — direct fat / risk measures; smaller is healthier
`waist`, `hips`, `neck`, `body_fat_pct`, `fat_mass`, `visceral_fat`, `bmi`, `metabolic_age`

*(These directly measure the target — waist ↓ **is** less fat — so they're judged by their
own literal direction, high confidence, no inference.)*

### `increase_good` — direct lean / structural mass; larger is healthier
`lean_mass`, `skeletal_muscle_mass`, `bone_mass`

### `inferred` — limb circumferences; judged by the body's inferred direction
`arm_left`, `arm_right`, `forearm_left`, `forearm_right`, `thigh_left`, `thigh_right`,
`calf_left`, `calf_right`

### `neutral` — no directional health goal (tracked, never judged)
`chest`, `shoulders`, `body_water_pct`, `bmr`

---

## Body-direction inference (`infer_body_direction`)

Deterministic, from the `DailyHealthSummary` body-comp panel (all computed in the background
cycle — no request-path queries). Inputs: 14-day `fat_mass`/`lean_mass` deltas +
`recomposition_flag_14d`, `muscle_loss_risk_level`, `muscle_preservation_status`. Meaningful
move = ±0.5 lb over 14 days.

Rules, in priority order (matching the agreed Scenarios A–D):

| # | Condition | Verdict | Status | Confidence |
|---|---|---|---|---|
| 1 | `muscle_loss_risk_level ∈ {high, elevated}` **or** lean ↓ ≥0.5 lb | `muscle_loss` | 🔴 Needs attention | high if both, else medium |
| 2 | `recomposition_flag_14d` **or** (fat ↓ **and** lean ↑) | `recomposition` | 🟢 Improving | high |
| 3 | fat ↓ **and** lean not down | `fat_loss_preserving` | 🟢 Improving | high if muscle preserved, else medium |
| 4 | fat ↑ **and** lean ↑ (or no clear pattern) | `mixed`/`unclear` | ⚪ No change | low |
| — | missing fat or lean delta | `insufficient` | ⚪ No change | low |

**Worked scenarios**

- **A** — waist ↓, fat ↓, lean ↑, strength ↑, arm ↑ → *recomposition* → **Improving**.
- **B** — waist ↓, fat ↓, lean stable, arm ↓ slightly → *fat loss preserving muscle* →
  **Improving** (a **down** arrow shown **green** — smaller limb = fat loss).
- **C** — weight ↓ fast, lean ↓, strength ↓, arms ↓ → *muscle loss* → **Needs attention**.
- **D** — signals conflict → *unclear* → **No change** ("Not enough evidence").

A limb card then takes the body verdict's status (with its own literal arrow). Low
confidence → gray "Not enough evidence"; medium → "Likely …".

---

## Per-measurement interpretation (`interpret_measurement`)

```
if |delta| < epsilon(unit):            → Inconclusive ("no meaningful change yet")  (flat arrow)
elif category == neutral:              → Inconclusive ("no established healthy direction")
elif category in {decrease_good, increase_good}:
        healthy = literal direction matches the good direction
        → Improving | Needs attention  (high confidence, with a one-line reason)
elif category == inferred:
        use infer_body_direction() (carries evidence + summary):
          low confidence  → Inconclusive ("keep tracking over the next few check-ins")
          medium          → "Likely improving" / "Likely needs attention" (+ evidence)
          high            → Improving | Needs attention (+ evidence)
```

Each result carries `evidence` (the signals, e.g. `["Body fat ↓", "Lean mass ↑"]`) and a
`reason` (the conclusion) — both rendered beneath the status word on the card.

`epsilon(unit)`: 5.0 for `kcal/day`, else 0.05 (only a genuine ~0 reads as "No change").

---

## Adding a new measurement

1. Add it to `MEASUREMENT_CATEGORY` in the correct category. That's it — the cards, colours,
   legend, and (for limbs) the inference all inherit automatically.
2. If it's a limb-like circumference that could be muscle or fat → `inferred`.
3. If it has no accepted directional health goal → `neutral` (never guess).
4. Add a case to `test_measurement_interpretation.py`.

**Do not** hard-code "up good / down good" for anything a limb-style circumference —
route it through the body-direction inference so the judgment stays honest across phases
(cut vs bulk vs recomposition).
