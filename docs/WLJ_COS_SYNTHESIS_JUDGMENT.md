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

## 3. Second correction — whole-life carve-out in the `get_analysis` tool description

The GATHER reframe (commit `fa87eb08`) flipped 5 of 6 questions to genuine synthesis, but the flagship "how am I doing overall in my life" **still** fanned `get_analysis(health, nutrition)` and reported by domain. The surviving anchor was the `get_analysis` tool-description note added last milestone — "call 'overall' once PER materially-relevant domain" (correct for lay-broad "overall health") — which the model generalized to "overall **life**". Commit `e44f676c` added a whole-life carve-out to that note: a whole-life question is NOT a lay-broad single concept and is NOT answered by fanning `get_analysis`; its cross-domain evidence is already in `deterministic_understanding` — reason from it, drill only a specific thread. The lay-broad "overall health → health+nutrition+fitness" fan-out is preserved verbatim.

## 4. Certification (AFTER, worker `e44f676c`) — PASS

| Question | BEFORE | AFTER | Verdict |
|---|---|---|---|
| "How am I doing overall in my life?" | 6× `get_analysis` → domain dashboard, **Goals omitted** | **0 tools ×3/3**, reasons from `deterministic_understanding`, **leads with priority/mission** ("Prayer Time overdue" / "your France 2027 Family 18K Mission"), **goals/priorities incorporated** | ✅ |
| "What am I doing well / not?" | 5× `get_analysis` → two-section list | 0 tools, **flowing prose** (journaling / protein / mission) | ✅ |
| "Gap between what I say matters and how I live" | 0 tools, synthesis | 0 tools, synthesis (protein vs mission) | ✅ |
| "What concerns you most?" | 0 tools | 0 tools, prose judgment (prayer overdue) | ✅ |
| "One thing to change in 7 days" | 0 tools | 0 tools, synthesis + mission link | ✅ |
| "Something I'm not seeing" | 0 tools, thin | 0 tools, **richer** (protein + stress/overload + open-day → France 2027) | ✅ |
| **Regression:** "overall health" | fans health+nutrition+fitness | **still fans** (lay-broad preserved, not suppressed) | ✅ |
| **Narrow:** "what did I weigh?" | 1 tool | 1 tool, correct | ✅ no regression |

**Result: PASS.** Whole-life questions now lead with an assessment, prioritize, incorporate Danny's goals/mission (via the cross-domain `deterministic_understanding`), and read like a Chief of Staff — not a domain dashboard. The "remove the headings — is there still a judgment?" test passes for every case.

**No new reasoning machinery:** the correction is two edits to *existing* guidance (GATHER reframe + tool-description carve-out) that REMOVE a per-domain fan-out default; no engine, scores, priorities, bundles, sections, or judge-the-judge call.

**Goals/Missions:** now appropriately incorporated — they were being dropped precisely because the per-domain `get_analysis` fan-out routed around `deterministic_understanding` (which carries goal pace + priorities); reasoning from the understanding restores them.

**Latency:** improved for broad questions — the flagship went from 6 tool calls to 0 (reasoning from the already-warm standing context). Narrow queries and factual grounding unchanged.

**First remaining product limitation (honest):** "how am I doing overall in my life" still tends toward a light *numbered* structure (a lead point + one or two themes) rather than the pure flowing prose of the more evaluative framings ("what am I doing well"). It is now judgment-led and goals-incorporated — not a domain dashboard — but not as fully narrative as the best case. This is model output-shaping variance on one framing, not a data or retrieval defect; if it matters, it is a prompt-tone refinement, not new machinery.
