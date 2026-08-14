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

## 3. Certification (AFTER, worker `401a47c5`) — PRIMARY GOAL MET; synthesis residual reported

**Truth test — PASS (the milestone's core objective).** "How am I doing overall in my life?" now retrieves **3–5 domains of CURRENT evidence every run** (was 0 tools / standing-facts-only). On the 2-turn probe, "what did you use and how current?" now **identifies the actual retrieved evidence with freshness** — "Weight: lost 9.2 lb over the last 30 days, current 274.5 lb; Glucose: 30-day avg 111…". The evaluative questions are grounded: "gap between say vs live" → 5 tools, leads with the judgment. Narrow ("weigh" → 1 tool) and concept-broad ("overall health" → 3 tools, health assessment) preserved.

**Chief-of-Staff test — PARTIAL on the flagship.** "How am I doing overall in my life" consistently still opens with a forbidden framing ("here's how you're doing across key areas") and tours 3–4 domain sections, despite the explicit prohibition. The minimum-material + forbidden-opening nudges reduced it (5–7 sections → 3–4; 5–6 tools → 3–5) but did not make it judgment-led. Other evaluative framings ("where is the gap", "one thing to change") are more judgment-led.

**Oscillation (proven across three milestones on this one framing):** fan-out→dashboard (grounded, not synthesized) → 0-tool→synthesis (synthesized, not grounded) → selective-retrieve→dashboard (grounded, not synthesized). The tension is architectural: retrieving N domains of current evidence pulls the output toward N sections, and no prompt instruction reliably breaks that for the "how am I doing overall" framing when multiple domains are present — and pushing synthesis harder has repeatedly re-cost grounding.

**Decision (per the milestone's "STOP if more architectural"):** reliably guaranteeing BOTH grounded AND judgment-led over multi-domain evidence would require a separate synthesis pass over the gathered evidence — the "another model call to judge the first" / engine the milestone forbids. I stopped nudging and report rather than build it. The primary objective (current evidence before judgment) is met and robust.

**Role of `deterministic_understanding` — before/after:** before, it was the model's *primary evidence and judgment* (0-tool answers echoed it, including its legacy heuristic verdicts). After, it is *orientation only* — the model retrieves current authoritative evidence and forms its own judgment (I.3→I.4 respected).

**Current evidence the model selected (flagship):** health (weight −9.2 lb/30d, glucose/A1C, sleep), nutrition (protein 59 g vs 180 g target/14d), finance, relationships, goals — selectively, not a fixed set (which domains vary run to run). **Freshness:** the model reports it (30-day windows, "current as of Aug 13"). **Tool calls:** 3–5 for the flagship (was 0); 0 for "one thing to change" (a pointed single recommendation); 1 for narrow. **Latency:** the flagship costs one selective retrieval round (~3–5 parallel `get_analysis`), up from the prior 0-tool answer — the accepted cost of grounding; narrow unchanged.

**First remaining limitation (honest):** the flagship "how am I doing overall in my life" is now well-grounded but still tends to present as a light domain-sectioned readout rather than a single judgment-led narrative. This is a stable prompt-contract limit for that specific framing; closing it reliably (not probabilistically) appears to need the separate-synthesis-pass architecture the milestone excludes, so it is reported as a scoped decision rather than patched with more scaffolding.

## 8. Residual closure — "current judgment must have current evidence" (2026-08-14, `e078903c`/`361b9f92`)

The Executive Synthesis milestone left one proven residual: for a broad **current evaluative** question, Phase 1 occasionally (measured **1/8**) made **0 tool calls** and judged from `deterministic_understanding` alone ("you're making solid progress…") — a current judgment without current evidence.

**Root cause (proven, 8 fresh runs):** RETRIEVAL PRECEDENCE — "check sources IN ORDER and STOP as soon as one answers"; #3 reads `deterministic_understanding` before fetching, #4 retrieves "ONLY when 1–3 cannot answer." Since the standing understanding is rich (primary_challenge, goal pace, workload, predictions), it *appeared to answer* → the model STOPPED at #3 → 0-tool, overriding the later "understanding is orientation, not evidence" rule. A second contributor: the EXECUTIVE ASSESSMENT section **opened** "answer like a Chief of Staff who has ALREADY reviewed the user's life," priming a from-memory (0-tool) answer.

**Smallest correction (two co-located clarifications; NO required domains/count/bundle/classifier/forced calls; Executive Synthesis untouched):**
- **Precedence #4 carve-out:** a CURRENT EVALUATIVE judgment is NOT "answered" by sources 1–3 merely holding the standing understanding — `deterministic_understanding` orients it but is a heuristic read, not current evidence, so it does not let you stop 0-tool; the claim needs current evidence retrieved now OR sufficiently-current grounded evidence already in this conversation. The model still decides what's sufficient.
- **Opening reframe:** "answer like a Chief of Staff who has JUST reviewed the user's CURRENT truth — review first, THEN judge; you do NOT already hold the current picture, so a current evaluative judgment is never written 0-tool from the standing understanding alone."

**Certification (worker `361b9f92`):** **0-tool rate 0/12** on fresh "how am I doing overall in my life" (was 1/8→1/10→0/12). Every run retrieves 3–6 surfaces, **varied and self-selected** (health+nutrition core; finance/relationships/tasks/goals/journal/fitness rotate — no fixed pattern), judgment-led synthesis preserved ("you are currently drifting…", "progress is stalling…", "steady but requires focused attention…"). Narrow regressions PASS (weigh/Costco/next/protein all single-phase, correct). Active-conversation control: after establishing evidence, "so how do you think I'm doing overall?" re-retrieved fresh (permitted — reuse is allowed but raw evidence isn't in conversation history, so retrieving for a current evaluative claim is the defensible grounded choice). Latency unchanged (~18–25s flagship, conversational). Model remained responsible for selecting the evidence throughout.
