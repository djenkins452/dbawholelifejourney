# WLJ Chief of Staff — Current Evidence Before Executive Judgment

**Type:** Investigate → smallest reusable correction (clarify existing guidance) → production certification. No Executive Reasoning Engine, no sufficiency score, no required domain list, no whole-life bundle, no fan-out.
**Date:** 2026-08-13
**Governing rule:** *WLJ knows who Danny is and what has actually happened. OpenAI uses the first to understand what matters and retrieves the second to determine how things are going — then thinks.* Invariant: **the minimum sufficient CURRENT authoritative evidence necessary to support the judgment asked for.**

---

## 1. Root cause — the Synthesis fix overcorrected (proven at runtime)

The prior (Synthesis & Judgment) milestone stopped the domain dashboard, but its GATHER text said the whole-life answer's *"PRIMARY evidence is ALREADY in your standing context … REASON FROM THESE: that is the judgment."* Runtime (2-turn `cos-run`) shows the consequence:

- **"How am I doing overall in my life?" → 0 tool calls.** Leans on standing context.
- **"What specific information did you use, and how current is each piece?" → 0 tool calls.** Cites only STANDING facts — execution priority (Prayer Time), active goals/missions (France 2027, Avoiding Sweets). No current behavioural/outcome evidence.
- Contrast: **"How is my overall health?" → 3 tools** with real current evidence (−9.2 lb/30d, A1C 6.2, glucose in range 95.7%).

So the model treated `deterministic_understanding` as *sufficient evidence* rather than *orientation*. Two problems compounded:

1. **Freshness/substance:** standing facts (missions, targets, medications, one execution item) say WHO Danny is and WHAT matters — not HOW he is currently doing. An evaluative claim ("doing well", "drifting in X") needs current behaviour/outcomes.
2. **Ownership boundary (Constitution I.3→I.4, per `WLJ_EXECUTIVE_TRUTH_OWNERSHIP_BLUEPRINT.md`):** `deterministic_understanding` is a **"Mixed"** surface — it forwards deterministic facts AND legacy heuristic **verdicts** (`biggest_risk`, `primary_challenge`, `patterns`/`opportunity`/`wins` prose, `priority_action`) that the Constitution assigns to **OpenAI**. Telling the model to "reason FROM" it made WLJ's legacy heuristic verdict substitute for the model's own judgment over current facts — exactly what the blueprint forbids.

## 2. Smallest correction — orientation ≠ evidence (clarify existing guidance)

`apps/ai/model_interface/constitution.py`, two edits, both clarifications of the guidance the prior milestone added (no new machinery):

- **GATHER (whole-life paragraph):** standing context (`deterministic_understanding`, `missions`, `personal_truth`, `current_action`) **ORIENTS** — it is not, by itself, evidence; its interpretive fields (biggest risk, primary challenge, patterns-as-meaning) are WLJ's **heuristic READ, not the model's judgment and not certified current evidence**. An evaluative claim about CURRENT behaviour/outcomes **REQUIRES current authoritative evidence**: orient → decide which recent evidence is materially necessary (examples, never a fixed set, never a domain because it exists) → **SELECTIVELY retrieve the MINIMUM current truth** → confirm sufficiency → judge. Both failure modes are forbidden: a **zero-retrieval** standing-only answer AND a **fan across every domain**. Retrieval structure is never answer structure.
- **`get_analysis` tool-description carve-out:** replaced "its cross-domain evidence is ALREADY assessed in `deterministic_understanding`; reason FROM that" with "understanding ORIENTS you but is not your current evidence — neither fan nor zero-retrieve; selectively retrieve the minimum current truth."

The model still decides what is material; nothing is prescribed.

## 3. Certification

_Filled in after deploy + AFTER run._
