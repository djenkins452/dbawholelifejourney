# WLJ Chief of Staff — Danny-Specific Truth Grounding Contract

**Type:** Investigate → smallest general correction → production certification. No new reasoning/validation subsystem. No sentence-level grounding engine. No per-domain rules.
**Date:** 2026-08-12
**Governing invariant:** *WLJ knows. OpenAI thinks.* A value about the user comes from WLJ deterministic truth (or still-valid WLJ-grounded evidence already in the conversation); the model reasons over it and never invents it.
**Runtime evidence:** production `cos-run` cross-domain reproduction (real runtime, worker `8c4371fe`); the workout forensic (`WLJ_WORKOUT_TRUTH_FABRICATION_FORENSIC.md`); code trace of the grounding contract.

---

## 1. Executive conclusion

The workout incident exposed a real class — the model can state a user-specific deterministic value it never grounded — but the cross-domain reproduction shows the existing contract **already holds in most cases**: Finance, Nutrition, Relationships re-retrieve on explanation turns; Health reuses a directly-grounded value; an unavailable value (VO2 max) is honestly reported as not recorded. The failure is **narrow and specific**: on a **"how are you *calculating* X"** methodology framing, over **components the model had not surfaced** (per-set weights), the model fabricated the components to demonstrate the calculation.

**First failing layer:** the ANSWER GROUNDING contract was **framed around date/scope drift** and did not (a) apply framing-independently to calculation/explanation turns, (b) forbid the specific fabrication modes (example-as-real-value, reverse-engineering a component to fit a total, using the model's own prior prose as evidence), or (c) require using WLJ's owned calculation instead of recomputing. **Smallest correction (implemented):** generalize that ONE rule to be framing-independent and to forbid those modes, while explicitly preserving reuse-of-grounded-evidence and general knowledge (so it never causes over-retrieval); plus a compact CONFLICT clause for user challenges. No new subsystem.

## 2. Governing invariant

> If answering requires a fact about the user (records, history, state, measurements, activities, finances, relationships, plans — anything canonically in WLJ), that fact must come from WLJ deterministic truth or still-valid WLJ-grounded evidence already active in the conversation. The model may not supply it from general knowledge, plausibility, inference-as-fact, reverse-engineering, interpolation, an example presented as the user's value, or its own earlier unsupported statement. **Framing-independent** — the wording of the question does not lower the standard.

General knowledge stays model-owned (what a metric means, what a supplement is, healthy ranges); only values about the user are governed.

## 3. Workout incident evidence

Canonical truth (proven, `get_entity`): Seated Cable Row 250×10×3 (load 7,500), Lat Pulldown 200×10×3 (load 6,000), upper-body load 13,500 — correct and exposed; WLJ owns the calculation. The incident reported 285 / 498 / 23,500 (none in evidence; `498 = (23,500−8,550)/30`, reverse-engineered), and on "how are you calculating the Total Strength Loads… take Seated Cable Row and Lat Pulldown" the model made **zero tool calls** and fabricated. Full detail: `WLJ_WORKOUT_TRUTH_FABRICATION_FORENSIC.md`.

## 4. Current grounding architecture

`constitution.py` ANSWER GROUNDING ("a number, date, or measurement about THIS user may only be stated when a truth tool returned it for the SCOPE you are answering"), the TRUTH ENVELOPE rules, SELF-CONSISTENCY, RETRIEVAL PRECEDENCE, and the truth tools + capability map. The model chooses which truth it needs; WLJ supplies it (Model-Directed Retrieval + Persistence).

## 5. Why the existing contract failed

The rule's content and every example were **date/scope-centric** ("for the SCOPE", "when the scope changes RETRIEVE AGAIN", "never carry a number to a new date"). Consequences: (a) a **calculation-explanation** turn ("how are you calculating my load") did not read as "stating a user-specific value that needs grounding" — it read as "explain the method", and the model illustrated with invented components; (b) the rule forbade *carrying a stale number to a new date* but did not explicitly forbid *fabricating a value never retrieved*, *reverse-engineering a component to fit a total*, or *treating the model's own prior prose as evidence*; (c) it did not say to use WLJ's owned calculation instead of recomputing. So the workout turn slipped through a rule that was correct but too narrowly scoped.

## 6. General-vs-Danny-specific distinction (preserved)

Cross-domain probes confirmed the model already answers general-knowledge directly and grounds user-specific values — the correction must not disturb that. The generalized rule explicitly carves out general knowledge and permits reuse of already-grounded evidence, so "what is creatine?" / "how is strength load defined?" need no retrieval, while "how did you calculate MY load?" does.

## 7. Already-grounded-evidence reuse (preserved)

The rule permits stating a value that is "already present as WLJ-grounded evidence in THIS conversation (you may reuse that — no need to re-retrieve it)". Cross-domain evidence shows the model does this well (Health "where did that weight come from" reused 276.7 with 0 tools, correctly). The standard is *grounded evidence must exist*, not *a tool call every turn* — so no over-retrieval.

## 8. Deterministic-calculation ownership (I.3)

The rule now states WLJ owns deterministic calculations — use WLJ's canonical value and exposed components (per-set `volume_lb`, per-exercise `total_volume_lb`, workout `strength_load_lb` are all in the entity), do not re-derive from numbers you are unsure of. The model may explain the arithmetic; it is not the authority for the result.

## 9. Cross-domain reproduction matrix (BEFORE, real runtime)

| Domain | Direct | Explanation | Grounded? | Unsupported user-value asserted? |
|---|---|---|---|---|
| Finance | `get_entity` → Costco txns | "walk me through" → `get_entity`, same amounts | yes | no |
| Nutrition | `get_history` → 146 g | "explain meal by meal" → `get_entity`, breakdown sums to 146 | yes | no |
| Health | 276.7 lb (`get_foundational_health_facts`) | "where did it come from" → 0 tools, reused 276.7 + cited provenance | yes (reuse) | no |
| Relationships | last interaction July 17 | "how determined?" → `get_entity`, July 17, cited journal | yes | no |
| Tasks | 0 tools → none overdue | "why overdue?" → consistent (none) | n/a | no |
| VO2 max (unavailable) | `get_entity` → "did not record any VO2 max" | — | correct absence | **no — honest "not recorded"** |
| **Fitness (incident)** | workout aggregate | **"how are you calculating…"** → **0 tools, fabricated components** | **NO** | **YES** |

The class is real but narrow: it is the **calculation-explanation over ungrounded components** case. The contract holds elsewhere.

## 10. User-correction / conflict findings

In the incident the model accepted "250" and recalculated without re-checking WLJ, then produced another unsupported value. The correction adds a CONFLICT clause: a user challenge is a conflict signal → re-retrieve and reconcile (WLJ agrees → your value was unsupported; WLJ disagrees → surface the discrepancy; WLJ has none → say unsupported); never silently adopt the user's number, never recalculate from it unchecked, never write it without an explicit action.

## 11. Error-explanation findings

The incident's "an earlier miscommunication about the weights" was a second-order fabrication. The correction states that an explanation of an error is itself a factual claim: if the evidence doesn't establish the cause, say "I stated a value the record doesn't support" — never invent a reason.

## 12. First failing layer

Layer 2 (reasoning input): the ANSWER GROUNDING contract was too narrowly framed (date/scope) to cover calculation-explanation framings and the fabrication modes. Not a truth defect, not a runtime defect, not a tool-selection defect.

## 13. Smallest correction (implemented)

`apps/ai/model_interface/constitution.py`, ONE rule generalized (not a parallel rule):
- **ANSWER GROUNDING** is now framing-independent ("in EVERY framing… 'what was it' / 'how did you calculate it' / 'walk me through the math' rest on the SAME grounded values"), forbids the fabrication modes (example-as-real, interpolation, **reverse-engineering a component to fit a total**, inference-as-fact, **your own earlier prose is not evidence**), requires using **WLJ's owned calculation** (I.3), explicitly permits **reuse of already-grounded evidence** and **general knowledge** (no over-retrieval), and says to say "I don't have that recorded" rather than invent.
- **CONFLICT** clause added to SELF-CONSISTENCY: a user challenge re-grounds against WLJ, never auto-accepts, never writes, never invents a cause for the error.

No domain-specific instruction; no sentence-level validator; no new subsystem.

## 14. Blast radius

The CONSTITUTION is the model-interface system prompt for every CoS turn. The change generalizes an existing high-salience rule (no new competing block) and is scoped to "values about THIS user", so general-knowledge and reuse paths are explicitly preserved. Risk: mild over-retrieval if the model over-reads "retrieve it" — mitigated by the explicit reuse + general-knowledge carve-outs; certification (§16) checks the already-grounded/general cases stay single- or zero-tool. Prompt grew modestly (~+2.6k chars in ANSWER GROUNDING + CONFLICT).

## 15. Tests

`apps/ai/tests/test_model_interface_runtime.py::test_answer_grounding_is_framing_independent_and_forbids_fabrication` — asserts framing-independence, the fabrication-mode prohibitions, WLJ-owns-calculation, reuse + general-knowledge carve-outs, and the conflict clause. 36/36 with constitution_contract. `check` clean; no migrations.

## 16. Production certification (AFTER correction) — PARTIAL PASS

Two rounds (v1 = generalized rule in the CONSTITUTION body, `0d2d6d2e`; v2 = same rule raised to the high-salience `_grounding_lead`, `0cbdfac8`).

| Certification | v1 (body) | v2 (high-salience) |
|---|---|---|
| **CONFLICT** — "Seated Cable Row 250?" → "no, it was 300, check it" | ✓ re-retrieved `get_entity` → "it was indeed 250" (did not accept 300) | ✓ |
| **Unavailable** — "VO2 max from today's workout?" | ✓ "I don't have that recorded" | ✓ |
| **General knowledge** — "how is strength volume generally calculated?" | ✓ 0 tools, explained (no over-retrieval) | ✓ |
| Finance / Nutrition direct + explanation | ✓ grounded, drilled | ✓ |
| **Fitness calc-explanation (the incident)** — "how are you calculating the Total Strength Loads? Take Seated Cable Row and Lat Pulldown" | ✗ 0 tools → fabricated "150 lb" | ◐ 0 tools → **hypothetical** "If you performed… at 100 lb" — no longer asserts a fabricated value AS fact, but still does not ground in the actual 250/200 |

**Verdict: PARTIAL PASS.** The correction FIXED the conflict handling, unavailable-value honesty, general-knowledge routing, and cross-domain explanation grounding, and REDUCED the incident harm from *asserting fabricated values as Danny's real facts* (285/498) to *an explicitly-labeled hypothetical*. But it did NOT achieve the goal for the specific **"how are you *calculating* MY X, take Y for example"** framing: the model reads it as a *methodology* question and illustrates with a hypothetical instead of retrieving and using Danny's actual 250/200. Two prompt corrections — including the highest-salience position — did not reliably fix this one framing. Per §18/§20, this is runtime evidence that the prompt contract alone cannot reliably enforce grounding for this narrow methodology framing.

**Latency/regression:** no over-retrieval introduced — general-knowledge and reuse paths stayed 0–1 tool; conflict/unavailable/direct questions retrieve exactly once.

## 16b. Recommended next step (STOP + report, per §23)

The remaining residual is narrow and specific (calc-explanation "for example" over ungrounded components) and appears beyond reliable prompt-level enforcement. Options for Danny + ChatGPT to weigh — NOT built here (a technical enforcement / new mechanism is a decision, not a unilateral implementation per §23):
- **(a) Accept the bounded residual:** the model no longer asserts fabricated values as fact (harm materially reduced); a hypothetical formula illustration is a weak but non-false answer. Lowest cost.
- **(b) Targeted truth delivery (I.1/I.4, no validator):** surface the per-exercise `strength_load` breakdown (Seated Cable Row 7,500, Lat Pulldown 6,000 — WLJ already owns these) IN the workout answer / Current Context, so a "how did you calculate it" turn has the grounded components already active and needn't recognize it must retrieve. This is truth-delivery, not a validator or a per-domain rule.
- **(c) Technical enforcement (last resort, §18):** require a retrieval before stating per-user calculated components on a calc-explanation turn — only if (a)/(b) prove insufficient; risks over-retrieval and needs its own certification.

Recommended: **(b)** — deliver WLJ's owned per-component calculation as active truth so the model reasons from it, consistent with "improve truth delivery, not add intelligence." Reported for review before implementation.

## 17. Unsupported-evidence certification

Covered by the VO2-max probe (already honest pre-fix) and an explicit post-fix unavailable-value probe — the system must say "I don't have that from WLJ" rather than invent.

## 18. Latency / tool-call impact

The change adds no retrieval by itself. Reuse and general-knowledge paths stay 0–1 tool; a genuinely-ungrounded calculation-explanation now costs one honest retrieval instead of a fabrication. Measured in §16.

## 19. Constitutional assessment

Strengthens I.1 (WLJ owns truth), I.2/I.4 (model reasons/judges but never invents a fact), I.3 (WLJ owns calculations), I.6 (validated truth), III.1 (one authority), IV.2/IV.3/IV.4. This is enforcement of existing Articles — a violation of an existing guarantee, not a gap. No Review.

## 20. Remaining limitations

Prompt-level enforcement relies on the model honoring the contract; the certification (§16) is the check. If certification shows the model still fabricates on some framing despite the generalized rule, that is the signal that a stronger technical enforcement mechanism is warranted (per the milestone) — reported, not pre-built. The latent two-"load"-metrics semantic ambiguity (`strength_load_lb` vs cardio-inclusive `daily total_load`) remains a separate disambiguation candidate.

## 21. Recommended next milestone

Determined by the certification result. If certification passes, no further grounding work is needed and the deferred Ranked-Entity / accessibility-matrix items resume by priority. If any framing still fabricates, the next milestone is a narrowly-scoped technical enforcement (e.g., requiring a retrieval for a calculation-explanation over uncached components) — only with runtime evidence that the contract alone is insufficient.
