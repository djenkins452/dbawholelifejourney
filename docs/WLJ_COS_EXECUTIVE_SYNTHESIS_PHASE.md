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

## 6. Two deployment defects found + fixed during certification

1. **Fatal startup crash (unrelated to synthesis):** the temporary A/B experiment module was deleted but a prior `git add` aborted on the removed pathspec, so its `urls.py` URL path and `apps.py` `ready()` import survived in the committed tree. Django loaded the URLconf/`ready()` at startup, hit `__import__` of the deleted module, and crashed web (URLconf) + worker/beat (`ready()`). Fixed in `2814322b`; full-site recovery confirmed on the fix SHA. No rollback of synthesis.
2. **Phase-2 latency/hang:** two bugs — (a) the `model_interface_synthesis` endpoint was absent from `ENDPOINT_TIMEOUTS`, inheriting the 8s utility timeout (`80ac1155`); (b) routing Phase 2 through `_call_api`'s 2×45s retry loop + rate-limit circuit breaker made a triggered broad turn **hang >260s** (proven: 0-tool turns finished in ~12s, retrieving turns hung). Fixed by compact evidence rendering (`9583b51b`, ~9× smaller handoff) and by making Phase 2 a **single hard-bounded client call** — one attempt, strict 35s timeout, no retry loop, self-contained prompt (`61fad3bc`); on any error/timeout it returns "" and the grounded Phase-1 answer is kept.

## 7. Production certification (worker `61fad3bc`) — PASS

**Flagship "How am I doing overall in my life right now?"** (3+ runs, 18–25s): retrieves **4–6 domains** of current evidence, Phase 2 triggers, **0 domain sections**, judgment-led — e.g. "you're in a state of **drift** … particularly serving others", "progress is **steady, but protein needs immediate attention** … your highest-leverage move", "**solid but uneven**, relationship with God has the most momentum". Grounded + Chief-of-Staff, not a dashboard.

| Certification | Result |
|---|---|
| Flagship — Truth + Chief-of-Staff | ✅ grounded (4–6 surfaces), leads with judgment, prioritizes, mission-connected, **no domain tour** |
| "What evidence & how current?" | ✅ identifies each piece + freshness (protein 6 days/57%, God-mission 50%, workload "as of today") |
| Continuity: "why" / "what should I do" | ✅ continue naturally from the synthesized turn, grounded |
| "biggest gap" | ✅ 10s, 4 surfaces, Phase 2, judgment-led ("the gap is your 'Serve Others' mission") |
| "one thing to change" | ✅ 9s, single-phase, focused recommendation |
| **Narrow:** weigh / Costco / next / protein | ✅ single-phase (Phase 2 NOT activated), 9–19s, correct |
| "overall health" | ✅ 9s, 2 surfaces, Phase 2, synthesized ("stable, but protein a concern") — documented: it DOES use synthesis and reads as a judgment, not a dashboard |

**New authority introduced:** none — both phases are the same configured OpenAI reasoning authority; Phase 2 retrieves nothing and computes no deterministic verdict.
**Evidence slimming:** `get_analysis('overall')` `_envelope` scope-prose/metadata removed; Phase-2 handoff rendered as compact flat facts (~472 tokens for 4 domains vs ~6,200 full).
**Phase-1 evidence selected (certification):** health, nutrition, finance, relationships, journal, tasks, goals, faith — selectively, varying by run (no fixed set).
**Phase-2 input:** the question + capped standing orientation + the pooled compact facts; no tools, no history (self-contained).
**Latency:** flagship ~18–25s (conversational — comparable to or faster than the pre-synthesis broad turns at 24–46s, thanks to the payload slimming that offsets the added call); narrow queries 9–19s, single-phase.
**Failure behavior:** Phase-2 error/timeout → grounded Phase-1 answer kept (bounded ≤35s; the durable turn is never lost).

**First remaining limitation (honest):** eligibility depends on Phase 1 actually retrieving ≥2 surfaces; the flagship's Phase-1 retrieval still has run-to-run variance (occasionally 0 tools → single-phase, answering judgment-led from standing context — acceptable, but not synthesis-grounded that run). When Phase 1 does retrieve (the common case in certification), Phase 2 delivers grounded judgment reliably.
