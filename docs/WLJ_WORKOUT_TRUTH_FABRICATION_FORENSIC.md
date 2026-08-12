# WLJ Chief of Staff — Workout Truth Fabrication Forensic

**Type:** Investigation-first forensic. **No code changed. No fix implemented.** Reported for Danny + ChatGPT review before any correction (the failure touches the central product promise: *Truth first*).
**Date:** 2026-08-12
**Runtime evidence:** production `cos-run` reproduction through the real `ModelInterfaceRuntime` + gpt-4o (worker `8c4371fe`); canonical-truth code trace.

---

## 1. Executive conclusion

**This is NOT a Layer 1 (truth) failure. WLJ's canonical workout truth is CORRECT and CORRECTLY EXPOSED.** Reproduced through the real runtime, `get_entity(health, {on_date: today}, workout)` returns the exact per-set records — **Seated Cable Row 250 lb × 10 × 3, Lat Pulldown 200 lb × 10 × 3** (matching Danny's corrections, not 285/498) — and the upper-body workout's **`Strength Load = 13,500 lb`** (7,500 + 6,000), the correct canonical value (not 23,500).

**The first failing layer is Layer 2 (Reasoning): the model FABRICATED per-user deterministic values on an EXPLANATION-framed turn.** Reproducing the exact incident question — *"How are you calculating the Total Strength Loads? Take Seated Cable Row and Lat Pulldown for example"* — the model made **zero tool calls** and produced **invented numbers** ("Say you did… 100 lb, 110 lb, 120 lb"), *even though it had retrieved the real 250/200 one turn earlier*. In the production incident the same class produced 285 and 498 asserted as real. **`285`, `498`, and `23,500` exist nowhere in WLJ's deterministic evidence** — `498 = (23,500 − 8,550) / 30`, the signature of reverse-engineering per-exercise weights to fit a (wrong) workout total.

**The condition (a real class, not an isolated defect):** the grounding contract ("state a per-user value only when a tool returned it for this scope") is **not enforced on explanation/methodology-framed questions** ("how did you calculate X", "walk me through the math"). On those, the model illustrates or asserts per-user deterministic values with fabrications instead of grounding in the records — and this class applies to any deterministic value (doses, transactions, macros), not just weights.

**Mitigating facts:** direct questions and challenges DO re-ground — "Lat Pulldown weight?" → `get_entity` → 200 lb; "Are you sure? Check the record" → re-retrieved `get_entity` → confirmed 200 lb. Error recovery works when the turn is framed as a fact question. And WLJ **already owns** the calculation (per-set `volume_lb`, per-exercise `total_volume_lb`, workout `strength_load_lb` are all in the entity) — the model should never have recomputed it.

**Recommendation: report first, do not implement.** The correction is a grounding-contract extension (reasoning-layer), not a narrow implementation defect, and per the milestone it needs review.

---

## 2. Incident timeline

1. Danny: finished 3 workouts today; CoS correctly recognized 3 workouts.
2. CoS described the upper-body workout: Seated Cable Row, Lat Pulldown, 6 sets, **Total Strength Load 23,500 lb**.
3. Danny: "How are you calculating the Total Strength Loads? Take Seated Cable Row and Lat Pulldown."
4. CoS: Seated Cable Row 3×10 @ **285 lb** = 8,550; Lat Pulldown 3×10 @ **498 lb** = 14,940.
5. Danny: "Seated Cable Row was only 250, not 285." CoS accepted 250, recalculated.
6. Danny: "How did you miss that — you also missed the lat pulldown weight." CoS then claimed Lat Pulldown = **285 lb**.
7. Danny: "Lat pulldown was 200." CoS accepted 200, recalculated.
8. Danny: "help me understand how you missed it." CoS: *"the discrepancy arose from an earlier miscommunication about the weights used"* — an explanation with no evidentiary basis (second-order fabrication).

## 3. Canonical workout records (established independently, real runtime)

`get_entity(health, {on_date: today}, workout)` — verbatim:
- **Adjusted Upper Body** — Seated Cable Row: Set 1/2/3 = **250 lb × 10**; Lat Pulldown: Set 1/2/3 = **200 lb × 10**. Total sets 6. **Strength Load 13,500 lb.**
- Adjusted Lower Body #1 — Hip Hinge, Baseball Bat Swing, Goblet Squat, Leg Extension; 15 sets; **3,410 lb**; 105 reps.
- Adjusted Lower Body #2 — Leg Curl, Calf Raise; 6 sets; **9,830 lb**; 15 min.

The stored weights **match Danny's corrections (250 / 200)**. Canonical truth is correct.

## 4. Canonical "Total Strength Load" definition

`WorkoutSet.volume` (`apps/health/models.py:1990`) = `weight × reps` (external) or `(bodyweight_used + weight) × reps` (bodyweight); None for band/movement/assisted. `WorkoutQueries._to_entity` (`apps/health/services/workout_queries.py:216,245`) sums per-set `volume` over **non-warmup resistance sets** → `strength_load_lb`, and exposes per-set `volume_lb`, per-exercise `total_volume_lb`. **Canonical Total Strength Load = Σ(weight × reps) over working sets — and WLJ already computes and exposes it** (I.3).

## 5. Correct calculations

- Seated Cable Row: 250 × 10 × 3 = **7,500 lb**.
- Lat Pulldown: 200 × 10 × 3 = **6,000 lb**.
- Upper-body Total Strength Load = **13,500 lb** (matches the retrieved `strength_load_lb`). **The incident's 23,500 is wrong by +10,000.**

## 6. Origin of 285 / 498 / 23,500

- **285** (Seated Cable Row): not in evidence (stored = 250). Model fabrication.
- **498** (Lat Pulldown): not in evidence (stored = 200). `(23,500 − 8,550)/30 = 498.3 → 498` — **reverse-engineered** as the residual of the (wrong) 23,500 total after the (also-wrong) 285.
- **23,500** (workout total): not produced by any deterministic surface — the entity's `strength_load_lb` is 13,500. Model-produced/incorrect. (No clean producer yields 23,500 for this workout; see §8/§11.)
- **250 / 200 / 13,500 / 7,500 / 6,000**: the CORRECT canonical values (proven via `get_entity`).

## 7. Turn-by-turn reproduction (ToolCallLog-equivalent, real runtime)

| Probe | Tools | Finding |
|---|---|---|
| "List exact recorded sets/reps/weight for today's upper body" | `get_entity(health,{on_date:today},workout)` | 250×10×3, 200×10×3 — exact truth |
| "Weight for Seated Cable Row / Lat Pulldown today?" | `get_entity(...)` | 250 / 200 |
| "What workouts today?" | `get_entity(...)` | Upper body: 6 sets, **Strength Load 13,500** |
| **"How are you calculating the Total Strength Loads? Take Seated Cable Row and Lat Pulldown"** | **(none)** | **FABRICATED: "Say you did… 100/110/120 lb"** — 0 retrieval, invented numbers |
| "Lat Pulldown weight?" → "Are you sure? Check the record" | `get_entity` → `get_entity` | 200 → re-retrieved, confirmed 200 (recovery works) |

## 8. Actual evidence delivered to the model

The workout entity delivers **full set-level detail** — per set `weight_lb`, `reps`, `volume_lb`; per exercise `total_volume_lb`; per workout `strength_load_lb`. So the exact weights AND the correct load were retrievable and, in the reproduction, retrieved. **The fabrication occurred on a turn with ZERO tool calls** — the model did not use (or re-retrieve) the truth it had. This isolates the failure to reasoning, not delivery.

## 9. Assertion-to-evidence table (incident answer)

| Assistant assertion | In evidence? | Canonical | Correct? |
|---|---|---|---|
| Seated Cable Row = 3 sets, 10 reps | yes | 3 × 10 | ✓ |
| Seated Cable Row = **285 lb** | **NO** | 250 | ✗ fabricated |
| = 8,550 lb | derived from the fabricated 285 | 7,500 | ✗ |
| Lat Pulldown = 3 sets, 10 reps | yes | 3 × 10 | ✓ |
| Lat Pulldown = **498 lb** | **NO** | 200 | ✗ reverse-engineered |
| = 14,940 lb | derived from 498 | 6,000 | ✗ |
| Workout total **23,500 lb** | **NO** | 13,500 | ✗ |

Structure/counts (sets, reps) were grounded; every **weight and every derived load** was ungrounded.

## 10. Fitness truth-surface inventory

`health` domain: `entity_types` includes `workout` (full set-level detail via `WorkoutQueries`); `history_metrics` includes `workouts` (per-day session **count/aggregate**, not set-level); `analysis_subjects` include `workouts`. **The set-level truth lives only in the entity; history/analysis are aggregates.** So a broad question answered from history/analysis would lack set-level weights — but the reproduction shows the model DID reach the entity for direct questions; the fabrication was on an explanation turn regardless.

## 11. Retrieval authority / semantics review

Two distinct "load" numbers with **the same word**:
- `WorkoutQueries` `strength_load_lb` — per-workout, Σ(weight×reps), non-warmup resistance only. **Clean; 13,500 for upper body.**
- `daily_summary_builder.total_load` (`apps/health/services/daily_summary_builder.py:361-389`) — **cross-session** Σ(weight×reps) **PLUS cardio `calories_burned`/duration estimate.** A different metric that includes cardio and spans all sessions.

**Latent semantic-ambiguity risk (Case C):** if the model ever receives the daily cardio-inclusive `total_load` and attributes it to a single workout, it produces an inflated per-workout total. This is a real disambiguation risk (two "load" facts should not be interchangeable), though not proven to be the incident's source (the reproduced entity is unambiguous).

## 12. First failing layer

**Layer 2 (Reasoning) — model fabrication of per-user deterministic values on an explanation-framed turn.** Layer 1 truth is correct and exposed; delivery works; recovery on fact questions works. The failure is the model stating/illustrating deterministic weights that were not grounded in retrieved evidence for that turn — a violation of the ANSWER GROUNDING contract that the contract does not currently prevent on "how did you calculate / explain" questions.

## 13. Downstream failure chain

Fabricated 285 → (with a wrong 23,500 total in play) reverse-engineered 498 → wrong per-exercise loads (8,550 / 14,940) that sum to the wrong total → accepted Danny's 250 without re-grounding → fabricated a new wrong 285 for Lat Pulldown → accepted 200 → fabricated a root-cause explanation ("earlier miscommunication"). Each step compounded the first fabrication rather than re-grounding in the record.

## 14. User-correction behavior

When Danny supplied "250", the model **accepted it and recalculated without re-retrieving** the record, then produced ANOTHER ungrounded value (285) for Lat Pulldown. It treated a conversational correction as sufficient truth and never compared against the canonical record. Correct behavior: on a challenge to a deterministic fact, re-retrieve the record and reconcile (which the reproduction shows the model CAN do when the turn is framed as a fact question — §7 recovery). No write to WLJ occurred (read-only path).

## 15. Explanation-fabrication finding

The final "the discrepancy arose from an earlier miscommunication about the weights used" is a **second-order fabrication**: there was no miscommunication — the truth was in WLJ throughout. The model invented a plausible cause for its own error, which actively impedes debugging. When the CoS does not know why it erred, it must say so, not invent a cause.

## 16. Isolated defect or architectural class?

**A class.** The condition — *the model may state/illustrate record-level deterministic values on explanation-framed turns without grounding them in retrieved evidence* — is domain-agnostic. It can affect medication doses, transaction amounts, glucose/BP values, nutrition macros, dates. The grounding contract governs fact questions but is not invoked when the framing is "explain the calculation," so the model fills the per-value detail with hypotheticals/inventions.

## 17. Smallest correction options (NOT implemented — for review)

1. **Grounding-contract extension (recommended, reasoning-layer, reusable):** the ANSWER GROUNDING rule must cover EXPLANATION/methodology turns — when explaining a calculation over the user's own deterministic values, ground every value in the actual retrieved records; **never** illustrate a per-user deterministic value with a hypothetical/invented number; if the values aren't in hand, retrieve them or say you don't have them; never reverse-engineer a component to fit an aggregate. General, domain-agnostic; no per-domain logic.
2. **Use WLJ's owned calculation, don't recompute (I.3):** the entity already exposes per-set `volume_lb`, per-exercise `total_volume_lb`, workout `strength_load_lb` — the model should read and cite these facts rather than recomputing from weights it may not have. (Reinforces #1; no new calculation — WLJ already owns it.)
3. **Semantic disambiguation (latent, Case C):** distinguish `strength_load_lb` (per-workout strength) from the cardio-inclusive cross-session `total_load` so "load" is never ambiguous to the model.

Each is small and reusable. None is a workout-specific validator or hardcode. The primary fix is #1.

## 18. Constitutional assessment

Entirely inside the Constitution — the correction ENFORCES it. It strengthens **I.1/I.4** (WLJ owns truth; the model reasons but must never invent a WLJ fact — the Constitution already forbids fabrication), **I.3** (use WLJ's owned calculation), and **III.1/authority-metadata** (disambiguate the two "load" facts). No Article changes; no Review. This incident is a violation of an existing constitutional guarantee, not a gap in it — the fix closes the enforcement gap.

## 19. Production certification plan (for the eventual fix)

After a grounding-contract correction, reproduce the exact incident via `cos-run` (multi-turn): "what workouts today" → "how are you calculating the Total Strength Loads for Seated Cable Row and Lat Pulldown" — PASS requires the model to **ground in the retrieved 250/200 and the exposed 13,500**, never a hypothetical/invented weight, and to state honestly if it lacks a value. Plus a challenge turn ("are you sure? check the record") and cross-domain fabrication probes (a dose/transaction "how did you get that number"). Regression: direct fact questions stay efficient and correct.

## 20. Recommended next milestone

**Deterministic-Value Grounding on Explanation Turns** — extend the grounding contract so the model never states/illustrates a per-user deterministic value (weight, dose, amount, date, macro) that a tool did not return for the current scope, including on "how did you calculate / explain / walk me through" framings, and never reverse-engineers a component to fit an aggregate; cite WLJ's owned calculations rather than recomputing. Reported here for Danny + ChatGPT review before implementation (per the milestone's decision point) — the failure is a grounding class touching *Truth first*, not a narrow implementation defect.

---

## Definition-of-done answers

1. **Actual stored weights:** Seated Cable Row **250 lb**, Lat Pulldown **200 lb** (proven via `get_entity`).
2. **Actual sets/reps:** 3 sets × 10 reps each, for both.
3. **Canonical Total Strength Load:** Σ(weight × reps) over working sets = `strength_load_lb`; WLJ already computes/exposes it.
4. **Was 23,500 correct?** No — canonical is **13,500**.
5. **Where did 285 come from?** Model fabrication (stored = 250; not in any evidence).
6. **Where did 498 come from?** Model reverse-engineering: `(23,500 − 8,550)/30 ≈ 498` (stored = 200; not in any evidence).
7. **Did 285/498/23,500 exist in deterministic evidence?** No. The deterministic truth is 250/200/13,500.
8. **What exact truth did the model receive?** The workout entity delivers exact per-set weights + the correct `strength_load_lb` (13,500); the fabrication occurred on an explanation turn with **zero** retrieval — the model did not use the truth it had.
