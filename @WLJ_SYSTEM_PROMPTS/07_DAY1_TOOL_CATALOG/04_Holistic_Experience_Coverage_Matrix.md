# Document 4 — Holistic Experience Coverage Matrix

**Purpose:** Determine which real user experiences become possible with the proposed Day-1 catalog (Docs 1–3): standing context + `get_domain_state` + `get_dashboard_context` + `get_decision` + `search_history` + the Day-1 action set.

**Legend:** FULLY SUPPORTED = answerable from Day-1 deterministic providers at high confidence · PARTIALLY = answerable but bounded by a known gap (degrades to "I suspect" / "I need more") · NOT SUPPORTED = required provider is deferred/absent Day-1.

---

## 1. Coverage Matrix

| User experience | Coverage | Why |
|-----------------|----------|-----|
| **"What is my weight?"** | **FULLY** | Standing context / `get_domain_state("health")` → `weight_current` (`state_builder.py:358`). Scalar, BACKED. |
| **"How am I doing?"** | **FULLY** | Standing context = `build_executive_context` (strategic state, risks, momentum, focus). Composed, BACKED. |
| **"What should I focus on?"** | **FULLY** | `get_decision("execution")` — the live deterministic Execution mode (`/api/cos/decision/`). Canonical. |
| **"What's most at risk right now?"** | **FULLY** | `get_decision("risk")` — deterministic Risk mode. |
| **"What should I clean up first?"** | **FULLY** | `get_decision("fix")` — deterministic Fix mode. |
| **"What goals am I neglecting?"** | **FULLY** | `get_domain_state("goals")` → overdue/active + momentum (`build_goal_state:1424`). (No "stalled" label, but overdue covers the ask.) |
| **"What should I pray about?"** | **FULLY** | `get_domain_state("faith")` → unanswered/urgent prayers (`build_faith_state:1655`). |
| **"Why has my weight loss slowed?"** | **PARTIALLY** | `get_root_cause_assessment` (if exposed) is BACKED but 5-domain aperture; widening to stress/routine/calendar uses `get_domain_state` (STRANDED→now reachable Day-1!) → CoS synthesizes correlation, labeled "I suspect" (Reasoning Doc 4). Holistic *reach* improves Day-1 because `get_domain_state` exposes the previously-stranded domains — but causality stays synthesized, not certified. |
| **"What happened last month?"** | **PARTIALLY** | `search_history` gives time-based events across health/journal/faith (BACKED); daily briefings exist but aren't search-exposed Day-1. Good factual recall; thematic recall limited. |
| **"Have I struggled like this before?"** | **PARTIALLY** | Time-based episode matching via `search_history` works; "what *worked* before" needs conversation/intervention recall (PHASE 2 keyword search). Pattern-by-metric: yes; pattern-by-theme: limited. |
| **"How have I changed this year?"** | **PARTIALLY** | Time-series via `search_history` supports metric deltas; lifetime/thematic narrative needs keyword history (Phase 2). |
| **"What patterns do you see?"** | **PARTIALLY** | Standing signals + CDCE correlations (BACKED, 7 fixed detectors) + multi-domain `get_domain_state` synthesis. Real patterns surface; novel cross-domain ones are CoS-synthesized ("I suspect"). |
| **"Log my prayer / I finished X / put Y on my calendar."** | **FULLY** | Day-1 action set (`log_prayer`, `complete_task`, `schedule_event`) — deterministic handlers. |
| **"I'm discouraged." (coaching)** | **PARTIALLY → FULLY** | Breadth-first scan via `get_domain_state` across health/goals/faith/journal/execution (all BACKED Day-1) + situation verdict → genuine whole-person coaching. Limited only by absent journal *text/themes* (uses mood/stress trends instead). Strong Day-1. |
| **"Show me my note/capture about Z."** | **NOT SUPPORTED** | `search_notes`/`search_capture` are PHASE 2 (unwired engines). Day-1 CoS can't retrieve knowledge content. |
| **"What's on my screen / this page?"** | **NOT SUPPORTED** (external) | `get_screen_context` is in-app-only, PHASE 2. |

---

## 2. Coverage Summary

| Coverage | Count | Experiences |
|----------|-------|-------------|
| **FULLY SUPPORTED** | 8 | weight, how-am-I, focus, risk, fix, neglected goals, pray-about, all Day-1 actions, (coaching near-full) |
| **PARTIALLY SUPPORTED** | 6 | why-weight-slowed, last-month, struggled-before, changed-this-year, patterns, deep coaching |
| **NOT SUPPORTED** | 2 | knowledge/note/capture retrieval, external screen awareness |

---

## 3. The Important Insight

**Every "current state," "what-should-I-do," "how-am-I," and "do-this-for-me" experience is FULLY supported Day-1** — because those rest on standing context, the decision modes, domain state, and the action handlers, all of which already exist and are BACKED. That is the *daily* Chief-of-Staff loop, and it works on Day 1.

**The PARTIAL experiences are all diagnostic/historical depth** — and they degrade *gracefully*, not falsely: the reasoning architecture (Reasoning Doc 6) forces them to "I suspect / I need more evidence" rather than fabrication. Crucially, Day-1's `get_domain_state` already **un-strands** the 6 cross-domain factors (stress, routine, calendar, relationship, faith, execution) for *retrieval and synthesis*, so holistic reasoning is materially better Day-1 than the current weight composer's 5-domain aperture — it just remains synthesized correlation, never certified cause.

**The only NOT-SUPPORTED experiences are knowledge retrieval (notes/captures) and external screen awareness** — both deferrable without crippling the daily CoS, and both cheap to add later (the engines exist; they need wiring).

---

## 4. Verdict

The Day-1 catalog delivers a **genuinely holistic daily Chief of Staff**: it knows where Danny stands, what he should do, how he's trending across every domain, can recall his history by time, can coach from the whole person, and can act on his behalf. It is *bounded* only in deep thematic recall and knowledge-document search — which it discloses honestly rather than faking.

---

*Document 4 of 6. Whether this is enough to actually switch over is assessed in Document 5.*
