# WLJ Chief of Staff — Model-Directed Retrieval Persistence

**Type:** Investigation → smallest reusable correction → production certification. No domain-specific fallback routing. No Projects analysis, no Ranked Entity. Execution Decision Authority + the completed surfaces untouched.
**Date:** 2026-08-12
**Governing principle:** *WLJ provides trustworthy evidence; the Chief of Staff decides whether it has enough — and what to investigate next.*
**Runtime evidence:** production `cos-run` traces (real `ModelInterfaceRuntime` + gpt-4o); local semantics introspection; code trace.

---

## 1. Executive conclusion

**The model was stopping after a thin first retrieval not because the runtime, capability discovery, or the truth were missing — but because the `get_analysis` result *semantics* and *description* told it the investigation was over.** For a domain that is entity-capable but not analysis-capable (Projects), `get_analysis` returned `status: insufficient_evidence` with the reason *"assessable measures: (none)"* — which reads as *"no truth exists"* and never mentions that the domain's records are retrievable via `get_entity`. Compounded by the `get_analysis` tool description over-claiming it "performs the whole investigation… you never have to orchestrate get_entity yourself; only status: empty is a genuine absence."

The truth, capability discovery, and tool loop all work: the same domain answers `get_entity('projects')` when the question is direct (positive control), and the runtime supports up to 7 tool rounds with the growing tool conversation preserved. **First failing layer = tool-result semantics (Outcome A) + tool description (Outcome B) — both reusable, platform-level, not domain-specific.**

**Smallest correction (implemented):** (1) an unsupported/insufficient analysis now points the model to the domain's OWN retrievable surfaces (`get_entity`/`get_history`, derived generically from its registered capabilities) — "this analysis surface doesn't cover it, but the records ARE retrievable"; (2) the `get_analysis` description clarifies that an empty/unsupported/thin analysis is NOT proof truth is absent — drill into the records before concluding. **No deterministic fallback call, no per-domain routing, no new judgment.** WLJ only tells the model what else is retrievable; the model decides.

## 2. Proven runtime behavior

- **Projects:** "How are my projects going?" → `get_analysis(projects,overall)` → *insufficient* → **stop** ("not enough data"). But "What tasks are open on my projects?" → `get_entity('projects','project')` → returns projects **with tasks**. The model reaches the truth when the question is direct; it doesn't drill when the analysis dead-ends.
- **Finance:** "What did I spend at Costco?" → `get_entity('finance',{contains:Costco},transaction)` → real transactions. But "Which transactions contributed most?" → `get_analysis(finance,overall)` (holds_data true, but summary-level) → **stops at the summary**, never drilling to the transaction records.

## 3. Projects trace (the smoking gun)

`get_analysis('projects','overall')` model-facing envelope (local reproduction):
```
status : insufficient_evidence
reason : "WLJ tracks these assessable measures for 'projects': (none). Answer from one of
          those (or offer them). Do NOT tell the user that this measure cannot be analyzed…"
```
`(none)` assessable + no mention of the retrievable `project` entity ⇒ the model concludes truth is unavailable and stops. Root: `apps/ai/cos_services/domain_analysis.py` unsupported-subject branch (a domain with `entity_types` but no `analysis_subjects`).

## 4. Finance trace

`get_analysis(finance,overall)` SUCCEEDS (`holds_data` true) but is a spending/income *summary*; it carries no per-transaction detail. For "which transactions contributed most?" the model reasoned over the summary and did not drill to `get_entity('finance','transaction')` — consistent with the description's "get_analysis performs the whole investigation; you never have to orchestrate get_entity yourself."

## 5. Positive control

**Within-domain, same session:** direct entity questions ("what tasks are open", "what did I spend at Costco") reach `get_entity` and return real records. So truth exists, capability discovery works, and the tool loop works — the only thing missing is the model continuing from a thin `get_analysis` into those records. (No cross-domain example of a *natural* analysis→entity drill was observed; the model tends to treat `get_analysis` as terminal, which is exactly the described behavior.)

## 6. Tool-loop architecture

`AIService._call_api_with_tools` (`apps/ai/services.py`): `for _round in range(max_tool_rounds+1)`; model_interface budget = **7 rounds**. Each round: one model call; if it emits tool calls they are executed and appended; `continue` re-calls with results in context. So multiple reasoning rounds ARE supported and the model MAY call another tool after seeing a result. **Not a tool-loop defect (Outcome E ruled out).**

## 7. Multi-round capability

`govern_prompt` runs ONCE at assembly (not per round), so the growing tool conversation within a turn is never truncated; the system prompt (with the capability map) remains `messages[0]` in every round. The capability map is available for fallback reasoning in later rounds. **Not a capability-visibility-loss defect.**

## 8. "Insufficient" result semantics (root cause — Outcome A)

`domain_analysis.py` returned `unsupported` with a reason listing only `analysis_subjects` (here `(none)`), wrapped by `service._wrap_truth` into `insufficient_evidence`. The reason did **not** distinguish *"this analysis surface cannot answer"* from *"no truth exists,"* and did **not** advertise the domain's retrievable records. This is the primary cause of the stop.

## 9. Capability map after a failed retrieval

The capability index (`truth_entities`, etc.) is present every round, so `get_entity('projects')` is discoverable in principle. But the failed `get_analysis` result actively contradicted it ("(none) assessable") and the CONSTITUTION's own "if not analysis-advertised, use get_entity" guidance was not triggered because the result never signaled "not analysis-advertised." Metadata was adequate; the **result semantics** overrode it.

## 10. Tool-description assessment (compounding — Outcome B)

`get_analysis` was described as performing "the whole investigation… you never have to orchestrate get_history + get_entity yourself" and "only status: empty is a genuine absence." That framing invites the model to treat any `get_analysis` result (thin, unsupported, or summary-level) as terminal. Runtime evidence connects this wording to the Finance non-drill, so a minimal clarification is warranted.

## 11. Experimental persistence control

The operator harness (`cos-run`) uses the production system prompt and cannot inject an experimental instruction, so the "seed a persistence instruction" control could not be run in isolation. The **correction itself is the controlled experiment**: fix only the result semantics + description and re-run the identical probes — if the model then drills (`get_analysis → get_entity → grounded answer`), the semantics were the cause; if not, the failing layer is elsewhere. (Certification, §19.)

## 12. Evidence-sufficiency findings

No deterministic sufficiency engine exists or is proposed. The model already decides sufficiency natively (it drills on direct questions, stops on dead-ends). The defect was that a dead-end result *told* it there was nothing more to find; the fix restores accurate signal so the model's own sufficiency judgment can continue.

## 13. Latency decomposition

Recorded post-correction in §19. A second retrieval round adds one model round-trip + one deterministic retrieval (historically ~5–10 s of the whole-life band). The correction does not force a second call — it only removes the false "stop" signal, so simple questions stay single-round.

## 14. Question Certification implications (report only)

Confirmed direction: **some questions the catalog might mark "needs a new deterministic capability" are answerable by model reasoning over already-exposed records.** "How are my projects going?" needs **no** deterministic "project assessment" capability — the model can assess from `get_entity('projects')` (status, tasks, due dates, completion). Certification should keep certifying the *truth foundation* (are the records exposed + discoverable?), not pre-build a reasoning path for every judgment. No catalog change in this milestone.

## 15. First failing layer

**Tool-result semantics (Outcome A), compounded by the tool description (Outcome B).** Not the runtime, not capability discovery, not the exposed truth, not prompt over-scaffolding suppressing retries (the CONSTITUTION already encourages the fall-through — it just wasn't triggered), not a genuine capability gap for these questions.

## 16. Root cause

An unsupported/insufficient `get_analysis` result read as "truth unavailable" and advertised no alternative surface, and the `get_analysis` description framed the tool as terminal — so the model stopped instead of drilling into records it could already retrieve.

## 17. Smallest correction (implemented)

- `apps/ai/cos_services/domain_analysis.py`: the unsupported-subject reason now appends the domain's retrievable surfaces (from its registered `entity_types`/`history_metrics`): *"this analysis surface does not cover it, but the records ARE retrievable — inspect get_entity(domain='…') … then reason from those records. Do NOT conclude the truth is unavailable from a thin analysis."* Generic; no per-domain code; no fallback call.
- `apps/ai/model_interface/constitution.py`: the `get_analysis` description now states an empty/unsupported/thin analysis is NOT proof truth is absent, and to drill into `get_entity`/`get_history` (e.g. when the user asks WHICH records behind a summary) before concluding.
- Tests: `test_truth_exposure_completion.py::AnalysisDrillPointerTests` (unsupported analysis points to the records) — 47/47 with domain_analysis + constitution contract.

## 18. Constitutional assessment

Entirely inside the Constitution. Strengthens I.2/I.4 (the model owns whether to keep investigating and the judgment), IV.4 (expose the alternative truth rather than inventing a capability/router), and IV.3 (reuse existing surfaces). It does **not** move reasoning into WLJ (no fallback call, no per-domain routing, no deterministic sufficiency/judgment), does not touch III.2, and adds no new authority. No Review.

## 19. Production certification (AFTER correction)

*(Recorded after worker deploy — see the Certification Result section appended below.)*

## 20. Recommended next milestone

Determined by the certification result. If the correction makes the model drill, the residual "ranked-entity" question ("my 5 biggest expenses" as one deterministic call) remains a legitimate *calculation* candidate — but only if runtime shows the model cannot reasonably rank a retrievable record set itself. Truth-first; reasoning stays with the model.
