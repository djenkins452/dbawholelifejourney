# WLJ — ChatGPT CoS Reasoning Architecture

**Mandate:** Design *how a holistic ChatGPT Chief of Staff should think* — the reasoning, evidence-gathering, retrieval, tool-usage, and synthesis workflows — while WLJ remains the deterministic source of truth. Architecture only: no code, no APIs, no prompts, no infrastructure.

**Builds on:** `../04_DISCOVERY/` (system inventory) and `../05_READINESS_AUDIT/` (deterministic-truth readiness). Those findings are assumed correct and are not repeated.

**Governing principle:**
> **WLJ owns truth. ChatGPT owns wisdom.**
> Every *fact* originates from a deterministic WLJ provider. Every *connection, interpretation, and recommendation* is ChatGPT's labeled synthesis. ChatGPT can reason, hypothesize, and coach — it can never invent a fact.

Fully compliant with the Architecture Laws — LLM Last (1), Raw→Signals→CoS (2), Single Source of Truth (4), State-First Reads (9), Deterministic Decisioning (14), Narration Contract (16).

---

## Deliverables

| # | Document | Covers |
|---|----------|--------|
| 1 | [CoS Reasoning Architecture](01_CoS_Reasoning_Architecture.md) | The complete 11-stage reasoning lifecycle; two-speed pattern; law-compliance map |
| 2 | [Intent → Context Retrieval Matrix](02_Intent_Context_Retrieval_Matrix.md) | 7 reasoning categories; intent→evidence matrix; **Dynamic Tool Catalog with truth-backing status** |
| 3 | [Dynamic Evidence Retrieval Framework](03_Dynamic_Evidence_Retrieval_Framework.md) | Belief-driven retrieval loop; causal-value ranking; widening ladder; stopping criteria; escalation |
| 4 | [Holistic Diagnostic Framework](04_Holistic_Diagnostic_Framework.md) | **Minimal always-loaded context (final)**; evidence ranking; causal confidence; conflict/missing-evidence handling |
| 5 | [Historical & Coaching Framework](05_Historical_and_Coaching_Framework.md) | Memory hierarchy; historical search sequence; pattern rules; 5 coaching modes |
| 6 | [Confidence & Trust Framework](06_Confidence_and_Trust_Framework.md) | The four epistemic states; evidence disclosure; insufficient-evidence behavior; contradiction handling |

---

## The Architecture in One Picture

```
              ┌─ ALWAYS-LOADED STANDING CONTEXT (Doc 4 §0) ─┐
              │ who · when · what's due · big picture ·       │
              │ top signals · vitals · day posture · trust   │
              └──────────────────────┬───────────────────────┘
                                     │
 MESSAGE → classify intent (Doc 2) → scope evidence → inspect known
              → plan + retrieve deterministic evidence (Doc 3, loop)
              → weigh & reconcile (Doc 4) → score confidence (Doc 6)
              → synthesize → explain (sources + epistemic state) → persist wisdom
                                     │
   ChatGPT routes INTO existing deterministic surfaces, never replaces them:
   • Execution/Risk/Fix → cos_mode_router decision modes  • Diagnostic → root-cause composer
   • Scalars/State → SAE get_module_state                 • Big picture → build_executive_context
```

---

## Three Architectural Commitments (and one challenge)

**Commitments:**
1. **ChatGPT sits above the deterministic layer, never beside it.** It *consumes* WLJ's existing decision modes, composers, and state — it does not re-derive truth. This preserves Single Source of Truth and Deterministic Decisioning by construction.
2. **The fact/synthesis seam is explicit and unbreakable.** Provider facts and CoS hypotheses are visibly separated in every answer; synthesized causality is always labeled correlation, never certified cause.
3. **Confidence is derived, not chosen.** The four epistemic states (I know / I suspect / I need more / I cannot determine) are mechanical functions of evidence tier and reachability — the CoS cannot feel more certain than its evidence.

**Challenge carried forward (required by the rules):** the holistic ideal (weigh ~18 factors for "why has weight loss slowed") exceeds today's *reachable* evidence. The Readiness Audit proved 6 cross-domain factors are computed-but-stranded and the weight composer has a 5-domain aperture. This architecture is sound and law-compliant **as designed**, but its evidence *reach* is bounded by which providers are exposed today. Where a factor is STRANDED/UNWIRED, the reasoning loop degrades to "I suspect / I need more evidence" — it never closes the gap with invention. Widening that reach is a separate, later decision; this document set does not design it.

---

*Architecture only. No code, APIs, prompts, or infrastructure were written or proposed. Deterministic truth and WLJ-as-source-of-truth preserved throughout.*
