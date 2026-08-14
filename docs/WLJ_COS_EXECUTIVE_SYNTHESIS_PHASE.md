# WLJ Chief of Staff — Bounded Executive Synthesis Phase

**Type:** Authorized architecture — two phases of ONE CoS task (investigate → synthesize) + evidence-payload slimming. No new authority, engine, second assistant, aggregator, whole-life bundle, deterministic verdict, judge-the-judge, or phrase-list classifier.
**Date:** 2026-08-13
**Governing:** *OpenAI investigates. WLJ supplies truth. OpenAI decides when it has enough. The same Chief of Staff then steps back from the evidence, thinks across it, and gives Danny the executive read.*

---

## 1. Two-phase runtime design (insertion point)

The whole change lives at ONE seam — `ModelInterfaceService.generate()` — reusing the existing tool loop, dispatch, standing context, persistence, audit, and model config:

- **Phase 1 — Investigation (unchanged, already certified):** `_call_api_with_tools` runs the agentic tool loop. The model decides what the question means, which truth to retrieve, and when it has enough. As each truth read returns, `dispatch` now **captures the substantive results** (`turn_capture["evidence"]`) — the evidence the model *chose* to gather. Phase 1 still produces a final answer.
- **Eligibility (runtime signal, no classifier):** after the loop, `synthesis_eligible(evidence)` is true only when the investigation drew on **≥2 independent substantive truth surfaces** (distinct tool+domain+subject that returned real data). A narrow lookup (0–1 surfaces) stays single-phase.
- **Phase 2 — Executive Synthesis (`synthesis.py`):** for an eligible turn, the SAME model runs ONE bounded completion, **no tools**, over the gathered evidence + standing orientation, with a dedicated synthesis system prompt. Its answer replaces Phase 1's (which is discarded — Phase 2 never sees Phase 1's prose, so it is **not** judge-the-judge). On failure/empty, the grounded Phase-1 answer is kept (justified safe fallback; the durable turn is never lost; logged + audited via `synthesis_used`).

No new authority: WLJ still owns truth; both phases are the same configured OpenAI reasoning authority; the synthesis phase retrieves nothing and computes no deterministic verdict.

## 2. Eligibility rule

`≥2 distinct substantive truth surfaces gathered in Phase 1`. Pure behaviour signal — reuses the tools the model actually called and whether they returned data (`holds_data`/`ready`/`ok`/`rich`). No phrase list, no fixed domain set, no requirement to inspect every domain. Whole-life (3–5 surfaces) and "overall health" (2–3 surfaces) are eligible; "what did I weigh", "what did I spend at Costco", "what should I do next", "how much protein yesterday" (0–1 surface) stay single-phase.

## 3. Phase 2 input shape

- **System:** `SYNTHESIS_SYSTEM` — same Chief of Staff, second phase; you have ALREADY gathered the evidence; lead with the verdict, prioritise, connect to goals/missions, name progress/drift, explain why, challenge, advise; **ground every important claim in the provided evidence, never invent a Danny-specific fact, surface genuine insufficiency**; the standing orientation's interpretive fields are WLJ's heuristic read, NOT current evidence; **one synthesized judgment, never a domain tour**.
- **User content:** the question + **standing orientation** (missions, personal_truth, current_action, deterministic_understanding as orientation only) + the **gathered deterministic evidence**, consolidated into ONE pooled block (scaffolding stripped — `render_evidence`/`_strip`), not re-partitioned per tool. Plus conversation history (continuity). No tools.

## 4. Evidence-payload slimming (generic, safe)

`domain_analysis.py::_envelope`: the ~275-token `scope` prose repeated in **every** `get_analysis` result is reduced to the one rule not already in the model contract (the `all_time` pairing rule — `holds_data` meaning and "consider-all/present-the-vital-few/not-a-checklist" already live once in the tool description); pure metadata (`schema_version`/`generated_at`/`granularity`) dropped. Facts (`subjects`/`concepts`/`state`/`window`/`holds_data`) and provenance untouched. Phase 2's `_strip` removes the remaining scaffolding for the handoff. Not optimised to a number — only safe redundancy removed.

## 5. Failure & continuity

Phase 2 failure → keep the grounded Phase-1 answer (logged; `synthesis_used=false`). The final answer persists as the normal assistant turn via the existing durable turn lifecycle; follow-ups ("why do you think that?", "what should I do about it?", "what evidence did you use?") continue from it and can retrieve deeper truth in a fresh Phase-1. One Chief of Staff, one conversation — no separate Phase-2 identity.

## 6. Certification

_Filled in after deploy + real-runtime run._
