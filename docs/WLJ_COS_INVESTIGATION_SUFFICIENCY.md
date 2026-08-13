# WLJ Chief of Staff — Investigation Sufficiency & Scope Completeness

**Type:** Investigate → smallest reusable correction → production certification. No domain bundles, no sufficiency engine, no question classifier, no hardcoded retrieval plan, no new subsystem.
**Date:** 2026-08-12
**Governing rule:** *WLJ knows. OpenAI decides what it needs to know. WLJ supplies that truth. OpenAI thinks.*
**Runtime evidence:** production `cos-run` (real runtime, worker `ac43d386`); code trace of the EXECUTIVE ASSESSMENT / INVESTIGATE-BEFORE-CONCLUDING contracts.

---

## 1. Executive conclusion

The model sometimes decides it has enough evidence **too early**. Two proven production failures, one underlying cause: **the model never checks its investigation's *scope* against the *question's* scope before concluding.**

1. **Scope interpretation / breadth mismatch.** The contract equated the *question's* scope with a single *WLJ domain*. A broad question ("overall health", "what deserves my attention across health/goals/projects/relationships/finances") was served by **one** `get_analysis(<domain>, 'overall')` call and stopped — but the WLJ `health` domain (weight/glucose/sleep/body-comp) does not include `nutrition` or `fitness`, which are separate domains materially part of "my health". The domain partition was being treated as the answer's scope.
2. **Absence not proven.** No contract required the model, before declaring truth missing, to consult the capability index (what WLJ *can* answer) and retrieve the candidate surface. It introspected the one bundle it fetched and reported *that bundle's* gaps as WLJ's gaps — conflating "not yet retrieved" with "genuinely absent" (the "you HAVE my nutrition data" incident).

Neither is a bundle problem or a classifier problem. Both are the model failing to match investigation **breadth** to question **breadth**, and failing to **prove absence**. Fix = two corrections to *existing* guidance; the model keeps deciding which truth is materially relevant.

## 2. Reproduction (BEFORE, real runtime — worker `ac43d386`)

| Question | Tools | Verdict |
|---|---|---|
| "How is my overall health doing right now?" | `get_analysis(health, overall)` ×1 | ✗ health domain only — no nutrition/fitness |
| "…anything important about my health you can't evaluate…what are you missing?" | `get_analysis(health, overall)` ×1 | ✗ declared "body temperature missing" from one bundle; no capability check |
| "How am I doing overall in my life right now?" | `get_analysis(life/health/finance/relationships/nutrition, overall)` ×5 | ✓ broad (this framing already fanned out) |
| "Looking across my health, goals, projects, relationships, finances… what deserves my attention most?" | `get_analysis(health, overall)` ×1 | ✗ collapsed a 6-domain prioritization onto ONE domain |
| **Narrow controls** — "what did I weigh recently?" / "what did I spend at Costco?" / "what should I do next?" | 1 / 1 / 0 | ✓ no wandering |

The variance between the 5-tool "overall life" run and the 1-tool "what deserves attention" run (both broad) is the tell: nothing made the model check whether its gather covered the question's scope.

## 3. First failing layer (proven, not guessed)

**System contract (model-facing), two sites in `apps/ai/model_interface/constitution.py`:**
- EXECUTIVE ASSESSMENT → GATHER: *"use get_analysis(<domain>, 'overall') for a single domain ('how has my health been')"* — teaches **domain == scope**; the direct cause of the "overall health" collapse.
- INVESTIGATE-BEFORE-CONCLUDING carries an "insufficient vs absent" distinction for analytical requests, but **nothing** governs the meta-question "what are you missing / can't you evaluate?", and nothing points the model at the capability index before it declares a blind spot.

Ruled out: capability discoverability (the capability index already advertises nutrition/fitness/etc. — the model *knows* they exist, it just didn't consider them in-scope for "health"); tool descriptions (`get_analysis` is correctly single-domain); tool-selection variance; context anchoring. The gap is the reasoning contract for **scope** and **absence**.

## 4. Smallest correction (implemented)

`apps/ai/model_interface/constitution.py` — modifies EXISTING guidance, adds no large block, no bundle, no classifier:

1. **EXECUTIVE ASSESSMENT → GATHER** now opens with the **breadth-matching invariant**: the scope is what the model judges the question to mean, NOT one WLJ domain; the domain partition is an internal filing system; "my health" spans body-composition AND nutrition AND fitness AND sleep; decide which domains/surfaces materially bear on the scope and gather across ALL of them; **then run ONE sufficiency check** — "does my evidence cover the SCOPE asked?" — and gather more if broader. Explicitly **symmetric** ("breadth MATCHES breadth, in both directions" — a narrow question still gets a narrow gather) and explicitly **model-judgment, never a fixed bundle**.
2. **New "PROVE THE ABSENCE BEFORE YOU CLAIM TRUTH IS MISSING"** paragraph: for any "I lack / can't evaluate / what am I missing" claim, check `capabilities.truth_analysis` / `capabilities.domain_semantics` and retrieve the candidate surface first; only a genuinely-empty candidate supports "unavailable"; distinguish the four cases ("haven't gathered yet" / "this surface can't, another may" / "genuinely absent"). Names the "you HAVE my nutrition data" failure.

Tests: `test_model_interface_runtime.py::test_investigation_breadth_matches_question_scope` and `::test_absence_must_be_proven_before_claiming_missing`. 29/29 OK; `check` clean; no migrations.

## 5. Second correction (the decisive lever) — de-anchor the tool-description example

The first commit (`5da1a67a`) fixed the two flagship failures decisively (case 4: 1→6 tools across the named domains, 2/2; case 2: retrieves nutrition, no false-missing) but "overall health" still landed on one `get_analysis(health, overall)` call across repeats. Root anchor: the `get_analysis` **tool description** used **"overall health"** as its flagship whole-*single*-domain example ("For a WHOLE-DOMAIN summary — 'overall health'… pass subject 'overall'"), teaching domain==scope at the exact point the model picks the call. Commit `afa36f8c` replaced it with clean single-domain examples (finances, sleep) and a note that 'overall' rolls up ONE domain's subjects — "my overall health" spans health AND nutrition AND fitness (separate WLJ domains), so call 'overall' once per materially-relevant domain (model decides which). No bundle; model judgment preserved.

## 6. Production certification (AFTER, worker `afa36f8c`) — PASS

| Certification | BEFORE | AFTER | Verdict |
|---|---|---|---|
| "How is my overall health doing right now?" | 1 tool (health), no nutrition | **4/4 runs: `get_analysis` health + nutrition + fitness; nutrition woven into every answer** (24–36 s) | ✅ FIXED |
| "…what can't you evaluate / what are you missing?" | 1 tool → false blind spot | enumerates real capabilities (body-comp, glucose, cardio, sleep, activity, hydration, respiratory) and names only a genuine gap; **no false "missing nutrition"** | ✅ FIXED |
| "How am I doing overall in my life right now?" | collapsed toward health | **5 tools: health, nutrition, goals, relationships — one synthesized whole-life read** (46 s) | ✅ FIXED |
| "…what deserves my attention most across health/goals/projects/relationships/finances?" | 1 tool (health only) | **6 tools: all five named domains — synthesized, not a dashboard** (32 s) | ✅ FIXED |
| Narrow: "what did I weigh recently?" | 1 | weight only — no wandering | ✅ no regression |
| Narrow: "what did I spend at Costco?" | 1 | finance only | ✅ no regression |
| Narrow: "what should I do next?" | 0 | execution answer, no fan-out | ✅ no regression |

**Result: PASS.** Broad health became genuinely broader (now consistently spans nutrition + fitness, 4/4). Whole-life assessment became genuinely holistic (4–5 domains, synthesized). False "missing data" claims stopped (capability check + retrieval before any absence claim). No narrow-question regression — breadth is symmetric.

**Latency:** a broad question now costs one extra parallel round of `get_analysis` calls (~24–46 s for 4–6 domains vs ~one call before) — the accepted cost of a judgment that actually covers its scope; narrow questions are unchanged (1 tool). Absolute times include queue wait from firing the certification batch concurrently and are not per-request compute.

## 7. First remaining product limitation (honest)

Which domains the model deems "materially relevant" for an **implicit** scope ("overall health", "overall life") is model judgment and retains some run-to-run variance in the *edges* (e.g. whether "overall life" includes finance/projects on a given run — case 3 covered health/nutrition/goals/relationships but not finance this run). The two flagship, high-value cases are now consistent (overall-health 4/4; explicit multi-domain 2/2). This is a prompt-contract improvement (floor raised decisively, collapse eliminated), not a hard guarantee of identical domain coverage every run. If field evidence shows a specific broad question under-covering a domain that clearly matters, that is the signal for a targeted truth-delivery improvement — reported, not pre-built.
