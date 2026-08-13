# WLJ Chief of Staff — Synthesis & Judgment (whole-life assessment)

**Type:** Investigate → smallest reusable correction (simplify existing guidance) → production certification. No Executive Reasoning Engine, no life scores, no deterministic priorities/bundles, no hardcoded sections, no judge-the-judge call.
**Date:** 2026-08-13
**Governing rule:** *WLJ knows Danny's truth. OpenAI determines what that truth means. The Chief of Staff communicates the judgment, not the dashboard.*
**Runtime evidence:** production `cos-run`, full answers + tool traces (worker `2d093779`).

---

## 1. Root cause — proven by runtime, not guessed

For a WHOLE-LIFE assessment the model produced a domain-by-domain **report** and omitted Goals, even after being told "I want your assessment, not a report." The reproduction makes the cause unambiguous — it is a **retrieval-structure-becomes-answer-structure** failure, driven by the GATHER guidance added in the previous (Investigation-Sufficiency) milestone:

| Question | Tools | Output shape |
|---|---|---|
| "How am I doing overall in my life?" | **6× `get_analysis`** (health, nutrition, fitness, journal, faith, finance) | **domain report** — "• Health & Fitness … • Nutrition … • Finance … • Faith & Journaling … Overall …"; **Goals omitted** |
| "What am I doing well / not?" | **5× `get_analysis`** | two-section domain list; Goals omitted |
| "Gap between what I say matters and how I live" | **0 tools** (reasoned from `deterministic_understanding`) | **genuine synthesis** — "the gap is faith practices overdue — a disconnect between intentions and execution" |
| "What concerns you most" | 0 tools | judgment (prayer overdue) |
| "One thing to change in 7 days" | 0 tools | synthesis **with mission link** — "protein… supports your France 2027 Family 18K Mission" |
| "Something I'm not seeing" | 0 tools | judgment (protein below target) |

**The causal link is direct: when the model fans `get_analysis` per domain, each returns a domain-labelled bundle and the model mirrors that structure as domain sections; when it reasons from the single cross-domain `deterministic_understanding` it synthesizes AND naturally includes goals/missions.** The prior milestone's GATHER text ("use `get_analysis(<domain>,'overall')` for EACH domain the scope spans") made the per-domain fan-out the *default* for cross-domain questions — which both fragments the evidence into a report and routes *around* the goal/mission/priority signals `deterministic_understanding` already holds (why Goals kept dropping).

`deterministic_understanding` is the **assessment tier** (`understanding.py`): primary challenge, biggest risk, cross-domain patterns, wins, opportunity, **goal pace and priorities**, material changes — exactly the synthesized cross-domain evidence a whole-life judgment needs.

## 2. Smallest correction — simplify the GATHER step (remove the fan-out default)

`apps/ai/model_interface/constitution.py`, EXECUTIVE ASSESSMENT → GATHER, reframed (not enlarged with new scaffolding):

- **Whole-life / cross-domain assessment → reason FROM `deterministic_understanding`** (+ `missions` / `personal_truth` / `current_action`) as the PRIMARY evidence — it already spans every domain and carries goals/mission/priorities; the judgment is "is their behaviour moving toward or away from what they say matters?". **Do NOT rebuild the whole-life picture by fanning `get_analysis` per domain** (that fragments evidence into a dashboard and routes around the goal signals). Drill a single `get_analysis` only when a specific thread needs depth.
- **Preserved** (no regression to the prior milestone): a LAY-BROAD single concept ("overall health" → health AND nutrition AND fitness) and an EXPLICITLY-NAMED set still gather those specific named domains; a single-domain question is one `get_analysis`.
- **New anti-mirroring rule:** "HOW you gather is never HOW you answer … the number of bundles you gather is NEVER the number of sections you write."

No new reasoning machinery. The correction removes a dashboard-inducing instruction and points the model at the cross-domain assessment it already had.

## 3. Certification

_Filled in after deploy + AFTER run._
