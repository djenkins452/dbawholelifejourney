# Document 1 — ChatGPT CoS Reasoning Architecture

**Mandate:** Design *how a holistic ChatGPT Chief of Staff should think* — the reasoning lifecycle — while WLJ remains the deterministic source of truth. Architecture only. No code, no APIs, no prompts.

**Governing split:**
> **WLJ owns truth. ChatGPT owns wisdom.**
> Every *fact* in any answer originates from a deterministic WLJ provider. Every *connection, interpretation, and recommendation* is ChatGPT's synthesis over those facts — and is labeled as synthesis, never written back as system truth.

This document defines the reasoning loop. Documents 2–6 expand each demanding stage.

---

## 1. First Principle — ChatGPT Sits *Above* the Deterministic Layer, Never Beside It

WLJ already contains the deterministic decision surfaces (verified in code):
- A **3-mode decision router** — Execution / Risk / Fix — keyword-resolved, no LLM, exposed at `/assistant/api/cos/decision/` (`apps/ai/cos_mode_router.py:99`, `apps/ai/views.py:2221`).
- A **domain-keyed intent taxonomy** (`HEALTH_INTENTS`, `JOURNAL_INTENTS`, … `intent_engine.py:15+`).
- A **domain-keyed root-cause composer** (`_render_structured_assessment`, `deterministic_router.py:6279`).
- **Per-domain canonical state** via SAE (`get_module_state`, `state_engine.py:74`).

The architecture does **not** replace these. ChatGPT becomes a **router-and-synthesizer that calls these surfaces as evidence providers**. When a deterministic answer already exists (e.g., "biggest risk right now" → Risk mode), ChatGPT *retrieves and narrates it* rather than re-deriving it. This preserves LLM Last, Single Source of Truth, and State-First Reads by construction.

**Architectural law restated for the new layer:** ChatGPT may *gather, rank, connect, and explain* deterministic truth. It may *hypothesize* causes and *recommend* actions. It may **never** assert a fact, a completion, a metric, or a state that no provider returned.

---

## 2. The CoS Reasoning Loop

```
                         ┌──────────────────────────────────────────────┐
                         │  ALWAYS-LOADED STANDING CONTEXT (every turn)  │
                         │  identity · time/today · execution truth ·    │
                         │  executive summary · top signals · vitals ·   │
                         │  situation verdict · trust framing  (Doc 4 §)  │
                         └──────────────────────────────────────────────┘
                                            │
  USER MESSAGE ─▶ (0) GROUND ─▶ (1) CLASSIFY INTENT ─▶ (2) SCOPE EVIDENCE ─▶ (3) INSPECT KNOWN
                                                                                   │
                          ┌────────────────────────────────────────────────────────┘
                          ▼
            (4) PLAN RETRIEVAL ─▶ (5) RETRIEVE DETERMINISTIC EVIDENCE ─▶ (6) ASSESS SUFFICIENCY
                          ▲                                                        │
                          └──────────────── retrieve more (loop) ◀── insufficient ─┤
                                                                                   │ sufficient
                                                                                   ▼
              (7) WEIGH & RECONCILE ─▶ (8) SCORE CONFIDENCE ─▶ (9) SYNTHESIZE ─▶ (10) EXPLAIN
                                                                                   │
                                                                                   ▼
                                                              (11) PERSIST WISDOM (memory write)
```

### Stage definitions

| # | Stage | What ChatGPT does | What it must NOT do |
|---|-------|-------------------|---------------------|
| 0 | **Ground** | Read the always-loaded standing context; note the current screen if supplied | Assume any state not in context or providers |
| 1 | **Classify intent** | Assign the message to one of the 7 reasoning categories (Doc 2) | Pick a deterministic *mode* by guessing — for Execution/Risk/Fix it routes to the existing router |
| 2 | **Scope evidence** | Enumerate the evidence *types* the category requires (Doc 2 matrix) | Decide the answer before scoping |
| 3 | **Inspect known** | Check whether standing context already satisfies the scope | Re-fetch what's already loaded (State-First Reads) |
| 4 | **Plan retrieval** | Order the missing evidence by causal value × cost (Doc 3) | Fetch everything indiscriminately |
| 5 | **Retrieve** | Call deterministic provider tools (Doc 5 catalog) for missing evidence | Fabricate any datum a tool didn't return |
| 6 | **Assess sufficiency** | Decide: enough evidence to answer at acceptable confidence? (Doc 3 stopping criteria) | Continue forever, or stop too early silently |
| 7 | **Weigh & reconcile** | Rank evidence, resolve contradictions, mark gaps (Doc 4) | Average away conflicts or hide missing evidence |
| 8 | **Score confidence** | Assign I-know / I-suspect / need-more / cannot-determine (Doc 6) | Present suspicion as certainty |
| 9 | **Synthesize** | Compose the holistic answer: facts (provider-sourced) + interpretation (labeled) | Blend fact and inference indistinguishably |
| 10 | **Explain** | State the conclusion, the evidence behind it, and the confidence | Assert causality beyond the evidence |
| 11 | **Persist wisdom** | Optionally write durable understanding (pattern, preference, correction) to WLJ memory | Write *facts* back as if WLJ-derived; only labeled CoS-authored memory |

---

## 3. Why These Extra Stages Beyond the Prompt's Draft

The prompt's draft loop (classify → requirements → inspect → identify missing → retrieve → confidence → synthesize → explain) is correct but under-specified at three points. The architecture adds:

- **Stage 0 Ground** — because a holistic CoS must start from standing context (Doc 4 minimal package), not a blank slate. Skipping it causes redundant retrieval and violates State-First Reads.
- **Stage 6 Sufficiency *as an explicit gate with a loop back to Stage 4*** — diagnostic questions need iterative retrieval (gather health → see nothing → widen to stress/calendar → …). Without an explicit loop, the CoS either under-investigates or over-fetches. The loop has hard stopping criteria (Doc 3) so it terminates.
- **Stage 7 Weigh & Reconcile** — separated from synthesis because holistic answers routinely surface *conflicting* deterministic evidence (e.g., nutrition compliant but sleep degraded). Reconciliation is a distinct cognitive step that must happen before confidence scoring.
- **Stage 11 Persist Wisdom** — the CoS improves over time only if confirmed patterns and user corrections become durable memory. This is the one place ChatGPT *writes*, and it writes **understanding**, never **facts**.

---

## 4. The Two-Speed Pattern (Performance-Respecting)

Not every turn runs the full loop. Two speeds, mirroring WLJ's own design:

- **Fast path (Stages 0–1, 9–10):** scalar and status questions whose answer is already in standing context or a single cheap provider. "What's my weight?" → read vital snapshot → answer. No retrieval loop.
- **Deliberate path (full loop):** diagnostic, cross-domain, historical, predictive, coaching questions. These trigger Stage 4–6 iterative retrieval.

Intent classification (Stage 1) chooses the speed. This keeps the common case cheap and reserves multi-provider retrieval for questions that genuinely need it — consistent with WLJ's "never compute heavy on the request path" discipline, now applied to retrieval breadth.

---

## 5. Compliance Map (How the Loop Honors the Architecture Laws)

| Architecture Law | How the reasoning loop preserves it |
|---|---|
| **Law 1 — LLM Last** | Every fact enters at Stage 5 from a deterministic provider; ChatGPT never originates facts |
| **Law 2 — Raw → Signals → CoS** | ChatGPT consumes *state/signal* providers (SAE, signals, composers), never raw models |
| **Law 4 — Single Source of Truth** | Stage 3 inspects-before-fetching; Execution/Risk/Fix route to the *existing* decision router, not a parallel computation |
| **Law 9 — State-First Reads** | Standing context + `get_module_state` provide scalars; ChatGPT does not re-aggregate raw data |
| **Law 13 — Deterministic Rendering** | Provider-rendered prose is narrated; ChatGPT rephrases but does not manufacture factual statements |
| **Law 14 — Deterministic Decisioning** | Execution/Risk/Fix answers come from the keyword-routed decision modes; ChatGPT does not invent a blended mode |
| **Law 16 — Narration Contract** | Stage 8–10 carry each claim's trust tier; synthesized causality is tagged advisory, never canonical |

---

## 6. One Challenge to the Mandate (Required by the Rules)

The example expects the future CoS to weigh ~18 factors for "why has weight loss slowed." The Readiness Audit proved that **6 of those factors (stress, travel, routine, execution-overload, relationship, calendar) are computed as deterministic state but are not assembled into any causal composer**, and that the existing weight composer has a 5-domain aperture.

**Implication for this architecture (stated, not solved):** ChatGPT *can* reason holistically over those 6 factors **only by retrieving each domain's deterministic state via individual provider tools (Stage 5) and synthesizing the connection itself (Stage 9)**. That synthesis is legitimate "wisdom," but it is **correlation, not system-certified causation**, and the confidence framework (Doc 6) must force it to be labeled as such. The architecture is therefore sound, but its *evidence reach* is bounded today by which providers are retrievable — a coverage fact carried forward from Audit Document 2, not re-litigated here. Where a tool's truth backing is "stranded" or "unwired," the reasoning loop must degrade to "I suspect / I need more evidence," never to invention.

---

*Document 1 of 6. Continues in: Intent → Context Retrieval Matrix (2), Dynamic Evidence Retrieval (3), Holistic Diagnostic (4), Historical & Coaching (5), Confidence & Trust (6).*
