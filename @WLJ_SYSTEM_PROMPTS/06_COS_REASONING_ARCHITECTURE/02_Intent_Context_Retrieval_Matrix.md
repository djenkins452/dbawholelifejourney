# Document 2 — Intent → Context Retrieval Matrix

**Purpose:** Define the categories of questions a holistic CoS faces, and for each: the evidence it requires, the retrieval strategy, and the deterministic surfaces/tools it should route to. Includes the **Dynamic Tool Catalog** with each tool's *truth-backing status* carried forward from the Readiness Audit.

This is the lookup the reasoning loop (Doc 1, Stages 1–4) consults.

---

## 1. The Seven Reasoning Categories

Each maps to a reasoning *speed* (Doc 1 §4) and, where one exists, to an **already-deterministic WLJ surface** the CoS should consume rather than re-derive.

| Category | Canonical example | Speed | Routes to existing deterministic surface? |
|----------|-------------------|-------|-------------------------------------------|
| **Scalar** | "What is my weight?" | Fast | SAE metric (`get_metric`) — direct read |
| **Status** | "How am I doing?" | Fast/Deliberate | Executive summary + situation verdict (`build_executive_context`, `compute_situation_for_user`) |
| **Execution / Planning** | "What should I focus on today?" | Fast | **Execution decision mode** (`cos_mode_router` → `/api/cos/decision/`) |
| **Risk** | "What's most at risk right now?" | Fast | **Risk decision mode** (same router) |
| **Fix** | "What's behind / what should I clean up first?" | Fast | **Fix decision mode** (same router) |
| **Diagnostic / Cross-Domain** | "Why has my weight loss slowed?" / "Why am I less productive?" | Deliberate | Root-cause composer where one exists (`_render_structured_assessment`) + multi-provider synthesis |
| **Historical** | "When have I struggled like this before? What worked?" | Deliberate | History/memory providers (Doc 5) |
| **Predictive** | "What happens if I continue this pattern?" | Deliberate | PRIE predictions + trajectory state |
| **Coaching** | "I'm discouraged." | Deliberate | Synthesis over state + history + goals + faith (Doc 5) |

> Note: Execution / Risk / Fix are listed as one row in the prompt but are **three distinct deterministic modes in code** (priority FIX > RISK > EXECUTION, `cos_mode_router.py:114`). The CoS must respect that routing, not collapse them.

---

## 2. Intent → Evidence Requirements Matrix

"Required evidence" = the deterministic providers whose output the category's answer must rest on. "Standing" = already in the always-loaded package (Doc 4); "On-demand" = retrieved in Stage 5.

| Category | Required evidence | From standing context? | Retrieval strategy |
|----------|-------------------|------------------------|--------------------|
| **Scalar** | One metric | Sometimes (vitals are standing) | Single direct read; stop immediately |
| **Status** | Executive summary, top signals, situation verdict | Yes (all standing) | No retrieval; narrate standing context |
| **Execution** | Today's execution state, next action | Yes (execution truth is standing) | Read Execution-mode decision; narrate |
| **Risk** | At-risk items, biggest risk | Partly standing | Read Risk-mode decision |
| **Fix** | Behind/overdue items, fix priority | Partly standing | Read Fix-mode decision |
| **Diagnostic** | The *focal* domain's full state + *candidate contributing* domains' state + recent history | Focal partly standing | **Iterative widening** (Doc 3): focal → adjacent → distal, stop when cause is supported or evidence exhausts |
| **Historical** | Time-series for the focal domain + prior insights/briefings + prior interventions + conversation memory | No | Sequenced history search: recent → older; specific metric → thematic |
| **Predictive** | Current trajectory state + PRIE prediction for the domain + historical analog | Trajectory partly standing | Read prediction provider; corroborate with historical analog |
| **Coaching** | Emotional/journal state + execution state + active goals + faith state + relevant history + prior successful interventions | Some standing | Breadth-first light read across the person's "whole self," then synthesize tone (Doc 5) |

---

## 3. Dynamic Tool Catalog

Tools are **behavioral roles**, not API designs. Each is a named act of retrieving deterministic truth. The critical column is **Truth Backing** — the audited reality of whether a real deterministic provider stands behind the tool *today*:

- **BACKED** — a deterministic provider exists and returns the data.
- **STRANDED** — the deterministic state is *computed* but not assembled/serialized for consumption (Audit Doc 2 §1/§3).
- **UNWIRED** — a complete provider exists but has no caller/endpoint (Audit Doc 2 §2: dead code).
- **ABSENT** — no deterministic provider; the data is raw-only or not computed.

| Tool (behavioral role) | When used | Trigger conditions | Expected output | Truth backing (today) | Confidence implication |
|------------------------|-----------|--------------------|-----------------|----------------------|------------------------|
| **get_dashboard_context** | Status, opening of most Deliberate turns | Any "how am I" / holistic framing | Executive summary, risk flags, momentum, focus | **BACKED** (`build_executive_context:9079`) | High — composed deterministic state |
| **get_calendar_context** | Execution, Planning, overload diagnostics | Time/schedule references | Upcoming, active block, density, conflicts, execution state | **BACKED** (`build_calendar_state:3833` + APIs) | High |
| **get_health_context** | Scalar vitals, health diagnostics | Weight/glucose/sleep/recovery refs | Vitals, trends, signals (4 modules) | **BACKED, partial fields** (no "recent changes"/unified risk) | High for present fields; "need more" for deltas |
| **get_goal_context** | Planning, motivation, coaching | Goal/habit/momentum refs | Active goals, momentum, habits, streaks | **BACKED, partial** (no stalled/discipline-trend) | Medium–high |
| **get_faith_context** | Coaching, faith-drift diagnostics | Faith/prayer/scripture refs | Prayer, scripture engagement, streak | **BACKED, partial** (no trends/saved verses/learning) | Medium |
| **get_journal_context** | Stress/emotion diagnostics, coaching | Mood/stress/"feeling" refs | mood_trend, stress_score, anxiety mentions | **BACKED for trends; ABSENT for text/themes** | High for trend; "suspect" for themes |
| **get_relationship_context** | Relationship-stress diagnostics, coaching | People/family/social refs | People, neglect/engagement gaps, signals | **BACKED, partial** (no family aggregate/interaction log) | Medium |
| **get_decision (Execution/Risk/Fix)** | Execution, Risk, Fix questions | Mode keywords | The deterministic one-line decision | **BACKED** (`/api/cos/decision/`) | High — canonical |
| **get_root_cause_assessment** | Diagnostic (weight & physical-health) | "why has X slowed/changed" | Facts/Evidence/Assessment/Confidence/Recommendation | **BACKED but 5-domain aperture** (`deterministic_router:6279`) | High *within* aperture; misses 6 factors |
| **get_module_state(domain)** | Any domain not covered by a named tool | Diagnostic widening | That domain's SAE state dict | **STRANDED** (computed, not serialized externally) | Backing exists; reach is the gap |
| **search_history** | Historical questions | "when before / used to / last time" | Time-based events across health/journal/faith | **BACKED for time-based; ABSENT for keyword** | Good for dates; "need more" for thematic |
| **search_capture** | Recall of meetings/sermons/ideas | "what did I capture / that talk about" | Transcripts, summaries, signals | **UNWIRED** (engine exists, no caller; live search skips transcripts) | "Need more evidence" until reachable |
| **search_notes** | Knowledge/SOP recall | "my note on / how do I" | Ranked notes (FTS+embeddings) | **UNWIRED** (`search_notes_cos` dead code) | Same |
| **get_document** | Fetch a specific item by reference | User names a doc/note/capture/lab | The item's content | **PARTIAL** (HTML detail views; no JSON contract) | Retrievable by id; not by query |
| **get_screen_context** | Screen-aware turns | In-app context present | Current page + extracted fields | **BACKED in-app only** (`personal_assistant.py:166`); not external | High when present; absent for external CoS |
| **get_predictions** | Predictive questions | "what happens if / will I" | PRIE trajectory + confidence | **BACKED** (PRIE) | Medium — model-based, carries own confidence |

**Two honest catalog facts (from the audit, not re-derived):**
1. The richest cross-domain tools (`get_module_state` for the 6 stranded domains, `search_capture`, `search_notes`) are **not reachable today** — their backing is computed-but-unexposed or built-but-unwired. The reasoning architecture treats them as first-class tools, but the confidence framework (Doc 6) must downgrade any conclusion that *would* have depended on them to "I suspect / I need more evidence."
2. The deterministic decision modes and the dashboard/calendar/health composers are genuinely BACKED — so Scalar, Status, Execution, Risk, Fix, and physical-health Diagnostic questions are fully serviceable from real truth today.

---

## 4. Retrieval Strategy Rules (per category)

- **Scalar / Status / Execution / Risk / Fix** → *single deterministic read, no loop.* These have canonical providers; ChatGPT narrates, never re-computes (Law 4, Law 14).
- **Diagnostic** → *iterative widening with a stopping gate* (Doc 3). Start at the focal domain's BACKED tool; if it explains the change at acceptable confidence, stop; else widen to adjacent then distal domains via `get_module_state`, degrading confidence where backing is STRANDED/UNWIRED.
- **Historical** → *sequenced, recent-first, specific-before-thematic*; combine `search_history` (time-based, BACKED) with prior insights/briefings (BACKED as lists) and conversation memory; flag the keyword-search gap.
- **Predictive** → *prediction-provider-first, then historical analog* for corroboration.
- **Coaching** → *breadth-first light scan of the whole self* (state across health/journal/goals/faith/execution/relationships) then tone synthesis (Doc 5); never deep-dive one domain before seeing the person whole.

---

## 5. The Matrix as a Decision Aid (summary)

```
Scalar / Status / Execution / Risk / Fix → BACKED single-read → narrate (high confidence)
Diagnostic (physical health)             → root-cause composer (BACKED, narrow) + widen → label aperture
Diagnostic (life/cross-domain)           → multi get_module_state synthesis → STRANDED reach → "I suspect"
Historical                               → search_history (time) + inboxes + memory → keyword gap → partial
Predictive                               → PRIE + analog → model confidence
Coaching                                 → whole-self scan → synthesize tone over truth
```

The matrix's guiding rule: **route to the most-canonical BACKED surface first; only widen into STRANDED/UNWIRED territory when the question demands it, and carry the reduced confidence forward honestly.**

---

*Document 2 of 6. Evidence-ordering and stopping criteria are specified in Document 3.*
