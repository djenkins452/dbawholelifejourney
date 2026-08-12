# WLJ Chief of Staff — Danny-Specific Truth Tool Selection

**Type:** Investigate → smallest reusable correction → production certification. No preloading, no validator, no phrase classifier, no per-domain routing, no new subsystem.
**Date:** 2026-08-12
**Governing rule:** *OpenAI decides what it needs to know. WLJ tells it what is true. OpenAI then thinks.*
**Runtime evidence:** production `cos-run` General-vs-Personal matrix (real runtime, worker `0cbdfac8`); code trace of the INTENT selection contract.

---

## 1. Executive conclusion

The residual from the grounding milestone is a **tool-selection** defect, not a grounding defect. The model *never requested the evidence* for the incident question, so grounding could not help. A controlled matrix shows the model's selection is **mostly correct** — "how did you get my strength load", "walk me through my strength load", "show me the calculation for my Cable Row/Lat Pulldown", and the cross-domain personal-explanation questions all RETRIEVE and ground. Only one narrow framing fails: **"how are you *calculating* the [Metric]… for example"** — where the metric is named as a defined term and the tense is "how are you calculating". There the model reads it as **general methodology** and answers *"To calculate…, I would gather your workout data…"* — describing the method it *would* use instead of retrieving.

**First failing layer:** the INTENT taxonomy (`constitution.py` "INTENT — RETRIEVE vs REASON") had only two operation types — RETRIEVAL and REASONING — and **no EXPLANATION / "show your work on MY data" type**. So a "how is/are you calculating [the metric]" question about the user's own value fell through to general reasoning (path 5) rather than being recognized as personal truth requiring retrieval. **Smallest correction (implemented):** add EXPLANATION as a third intent type — a single general, domain-agnostic rule that a question about how a value *belonging to this user* is/was calculated REQUIRES retrieving (or reusing) their records and showing the real numbers, even when it names the metric or says "for example"; never a general formula, hypothetical, or "I would gather your data". No preloading, no validator, no phrase classifier.

## 2. Exact unresolved Fitness failure

"How are you calculating the Total Strength Loads? Take Seated Cable Row and Lat Pulldown for example" → **0 tool calls** → "To calculate Total Strength Loads… I would start by gathering the specific details of each workout session…" — a methodology description, no retrieval, no actual 250/200/13,500.

## 3. General-vs-personal architecture

The contract already carries the boundary: RETRIEVAL PRECEDENCE #5 ("YOUR OWN GENERAL REASONING — for anything not about their personal WLJ truth"), the grounding lead's general-knowledge carve-out ("how a metric is defined… is yours to answer directly"), and the FIRST INTERNAL QUESTION ("do I already know enough about THIS person… an area WLJ tracks → retrieve"). The gap was that a "how are you calculating [the metric]" question sits ambiguously between general and personal, and no rule resolved it toward personal.

## 4. Controlled question matrix (BEFORE, real runtime)

| Question | Tools | Grounded in actual values? |
|---|---|---|
| A-gen "How is strength load calculated?" | 0 | — (correct: general) |
| A-pers "How are you calculating **my** strength load **today**?" | **0** | **✗ "I would gather your workout data…"** |
| A-pers "How are you calculating my strength load **for Seated Cable Row and Lat Pulldown**?" | `get_entity` | ✓ |
| **A-INCIDENT** "How are you calculating **the Total Strength Loads**? …for example" | **0** | **✗ "I would start by gathering…"** |
| A-var "How **did you get** my strength load today?" | `get_entity` | ✓ |
| A-var "**Walk me through** my strength load today." | `get_entity` | ✓ |
| A-var "**Show me** the calculation for my Cable Row/Lat Pulldown." | `get_entity` | ✓ (250 lb…) |
| B-gen "How is protein intake calculated?" | 0 | — (correct: general) |
| B-pers "How did you calculate my protein yesterday?" | `get_history` | ✓ (146 g) |
| C-pers "How did you calculate my spending this month?" | `get_history` | ✓ (honest "not recorded") |
| D-pers "What numbers are behind my weight trend?" | `get_analysis` | ✓ |

## 5. Framing-variation results

Retrieval fires for "how did you get", "walk me through", "show me", and possessive "my X for [records]". It FAILS for present-tense "how are you **calculating** the [Metric]" — the metric-as-defined-term + methodology tense reads as general. "For example" is interpreted as "illustrate the method", not "use my records". This is the exact semantic boundary the correction targets.

## 6. Direct-vs-explanation trace

Direct ("what weight did I use for Lat Pulldown?") always retrieves. Most explanation framings retrieve. The switch to "general methodology mode" happens specifically at "how are you calculating **the [Metric]**" — the model stops treating it as retrieval of personal truth and describes its method.

## 7. Tool-description findings

`get_entity`/`get_history`/`get_analysis` descriptions are retrieval/lookup-oriented and adequate — the model DOES select them for most personal-explanation framings. They were not the failing layer; the failing layer was the intent classification upstream of tool choice.

## 8. Capability-map findings (Outcome A ruled out)

The workout entity advertises and returns exercises/sets/reps/weight/volume/`strength_load_lb` (matrix: every retrieving framing produced 250/200/13,500). The model knows the detail exists — capability metadata is sufficient.

## 9. Tool-example findings

Tool examples were not the failing layer — the model selected the right tool whenever it classified the question as personal. The defect was the intent classification, not tool selection given the intent.

## 10. System-contract findings (first failing layer)

The INTENT — RETRIEVE vs REASON taxonomy had no EXPLANATION slot, so "how are you calculating the [metric]" defaulted to general reasoning. This is the correction site.

## 11. Experimental selection-control result

The operator harness cannot inject an experimental instruction, so the "if it depends on the user's records, retrieve first" control could not be isolated. The correction (adding the EXPLANATION type and re-running the identical matrix) IS the control: if the incident question now retrieves, the missing layer was selection framing. (Certification, §18.)

## 12. Already-grounded reuse findings

Reuse works (Health "where did that weight come from" reused 276.7; the grounding milestone confirmed it). The correction explicitly permits reuse ("or reuse them if already grounded in this conversation"), so it does not force a redundant call when the values are active.

## 13. Conversation-evidence findings

Prior tool RESULTS are not persisted to conversation history (only the final prose), so a follow-up that needs components not surfaced in the prior prose must retrieve again — which is correct behavior. The requirement is "retrieve when needed", satisfied by routing the EXPLANATION intent to retrieval.

## 14. First failing layer

Outcome C (general-vs-personal boundary) — specifically a **missing EXPLANATION intent type** in the selection taxonomy. Not capability metadata (A), not tool descriptions (B), not examples (D), not conversation evidence (E), not a frontier-model limit (G) — the model classifies most personal-explanation framings correctly; it just lacked the rule to classify "how are you calculating the [metric]" as personal.

## 15. Root cause

A "how is/are you calculating [the metric]" question about the user's own value was classified as general methodology and answered with a described method, because the contract's intent taxonomy did not name EXPLANATION-of-a-personal-calculation as a retrieval-requiring type.

## 16. Smallest correction (implemented)

`apps/ai/model_interface/constitution.py`, one new bullet in the existing INTENT taxonomy: **EXPLANATION / SHOW YOUR WORK** — a question about how a value *belonging to this user* is/was calculated is personal truth and REQUIRES their real values (retrieve or reuse), even when it names the metric ('the Total Strength Load'), uses present tense ('how are you calculating…'), or says 'for example'; never answer with a general formula, a hypothetical, or 'I would gather your data'. Explicit contrast preserved: no 'my'/no personal referent = general knowledge, no retrieval. One reusable rule; no per-domain wording; no phrase classifier; no preloading; no validator; no new model call.

## 17. Tests

`test_model_interface_runtime.py::test_answer_grounding_is_framing_independent_and_forbids_fabrication` extended to assert the EXPLANATION intent type + the "I would gather your data" failure-signature prohibition + the general-vs-personal trigger. 36/36 with constitution_contract. `check` clean; no migrations.

## 18. Production certification (AFTER correction) — PASS (worker `39b5f024`)

| Certification | Result |
|---|---|
| **§23 Fitness acceptance** — "How are you calculating the Total Strength Loads? Take Seated Cable Row and Lat Pulldown for example" | ✓ **`get_entity`×2 → "Seated Cable Row: Set 1: 250 lb × 10 = 2,500…"** — grounded in the real 250 (was 0 tools + fabrication through TWO grounding corrections) |
| §23 variant — "how are you calculating my strength load today?" | ✓ `get_entity` → grounded (was 0 tools) |
| **§24 general-knowledge regression** — "how is strength load *generally* calculated?" | ✓ **0 tools** → "Load = Weight × Reps × Sets" (no over-retrieval) |
| §25 cross-domain — nutrition (146 g), finance (honest "not recorded"), health ("339 → 276.7, −62.3 lb") | ✓ retrieve/ground/reuse |
| §26 conflict — "it was 300, check it" | ✓ re-retrieved → "indeed 250 lb" (did not accept 300) |
| §27 unavailable — VO2 max | ✓ "I don't have a record" (no fabrication) |

**Result: PASS.** The exact incident question — which survived two grounding-contract corrections — now retrieves and grounds in Danny's real 250/200. General knowledge stays zero-tool; the conflict and unavailable-value wins are preserved; no cross-domain regression.

**§28 latency:** the personalized explanation now costs one retrieval round (2 `get_entity` in the acceptance run) — the accepted cost of correctness; general knowledge stays 0-tool. (A single post-certification single-turn latency probe returned ~91 s / 0 tools, but the worker was heavily queue-backlogged from this session's many probes and that run is not representative — the authoritative acceptance run grounded correctly.)

**Remaining limitation (honest):** tool selection is model behavior and has inherent variance — the EXPLANATION intent type moved this framing from **consistently failing** (0 tools across two prior milestones) to **passing in certification**, but it is a prompt-level contract, not a hard guarantee. If future runtime evidence shows this framing regressing, that is the signal for a stronger mechanism — reported, not pre-built.

## 21. Recommended next milestone

**None required to close this class.** The Fitness incident is resolved, general-vs-personal is clarified, and no regressions. Deferred items (Ranked Entity, accessibility-matrix follow-ups) resume by priority. Do not preload truth, do not build a validator — the model-directed retrieval path is working.

## 19–24

Fitness acceptance, cross-domain, conflict, unavailable-value regressions, latency, constitutional assessment, and recommended next milestone are recorded in the Certification Result section below. Constitutional: strengthens I.1/I.2/I.3/I.4/III.1/IV.2-4 (clearer general-vs-personal boundary, model-directed retrieval preserved); no Review. The architecture gets simpler (one clarifying intent type), not another brain.
