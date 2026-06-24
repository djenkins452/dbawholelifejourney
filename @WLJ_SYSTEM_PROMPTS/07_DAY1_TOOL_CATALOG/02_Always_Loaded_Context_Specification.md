# Document 2 — Always-Loaded Context Specification

**Purpose:** Specify the smallest context package that accompanies **every** chat request — the standing awareness ChatGPT carries before any tool call. Maximum awareness, minimum tokens.

**Core finding:** This package is **not new work**. It is essentially the output of one existing function — `build_cos_context` (`apps/core/ai_orchestrator/cos_context.py:3555`), wrapped by `build_executive_context` (`:9079`) — which WLJ already assembles for the current CoS on every turn. The only Day-1 task is **serializing that existing object** for an external consumer (it is internal-only today; Readiness Audit Doc 2 §1). No new computation, no new engine.

---

## 1. The Standing Package — Exact Fields

| # | Field | Why it belongs (every turn) | Provider | Status |
|---|-------|------------------------------|----------|--------|
| 1 | **Identity & personalization** — display name (assistant + user), enabled feature flags, key preferences | Scopes every answer; sets which domains exist for this user; sets the CoS's own name | `UserPreferences`, `get_cos_name()` (`apps/users/models.py:694/701`), `context_processors.py:203` | **EXISTS** |
| 2 | **Time anchor** — now, active block, day phase | Nearly every CoS judgment is time-relative (overdue vs today vs future) | `get_active_block` (`apps/core/execution/active_block.py:145`), today services | **EXISTS** |
| 3 | **Execution state summary** — done/overdue/recoverable counts, next action, biggest risk, fix priority | The single most-used CoS function: "what should I do / where do I stand" | `get_execution_truth` (`execution_truth_engine.py:81`), `build_execution_state` (`execution_state.py:46`), selectors | **EXISTS** |
| 4 | **Executive summary** — strategic state, top risk flags, momentum, recommended focus | The holistic 30,000-ft view the CoS reasons from | `build_executive_context` (`cos_context.py:9079`), `build_cos_intelligence` (`cos_intelligence.py:253`) | **EXISTS** |
| 5 | **Top signals** — prioritized, deduped, foundational+important | What's notable now without raw queries | unified feed (`ai_signals/unified_feed.py`) + `signal_renderer.py` | **EXISTS** |
| 6 | **Current health summary** — weight+trend, glucose, sleep, recovery | Foundational-tier domain; contextualizes most life reasoning | `build_health_state` (`state_builder.py:321`) | **EXISTS** (partial fields; see §3) |
| 7 | **Situation verdict** — day mode (normal/recovery/behind), right-now focus | Sets the CoS's posture before it speaks | `compute_situation_for_user` (`situation_computer.py:23`), `compute_right_now_focus` (`right_now.py:133`) | **EXISTS** |
| 8 | **Active goals (compact)** — active goal titles + momentum direction | Lets the CoS coach toward *Danny's* goals without a fetch; cheap and high-value | `build_goal_state` (`state_builder.py:1424`) | **EXISTS** (no stalled/discipline-trend field) |
| 9 | **Trust framing** — which fields are canonical vs advisory | Stops the LLM converting rollups into per-item claims (Law 16) | narration-contract tiers (`narration_contract.py:51`) | **EXISTS** |

---

## 2. Deliberately *Excluded* from Standing Context (anti-overengineering)

These were in the candidate list but do **not** belong in always-loaded context. Each is on-demand:

| Candidate | Why excluded | Where it lives instead |
|-----------|--------------|------------------------|
| **Current screen** | In-app only, per-page DOM-scraped, not reachable by an external CoS (Audit Doc 1); also high-churn/low-value most turns | On-demand `get_screen_context` only when an in-app client supplies it |
| **Travel state** | Travel is an **unbuilt domain** — only a transient insight rule exists (Audit Doc 2 §3.4). Putting it in standing context implies state that isn't computed | Not loaded; ABSENT |
| Full faith / journal / relationship / finance state | Domain-specific; needed only when the conversation turns there | On-demand `get_domain_state(domain)` (Doc 1) |
| Recent captures / notes / documents | Retrieval targets, not standing awareness | On-demand search tools |
| History / trends | Pulled when a historical question is asked | On-demand `search_history` |

**Principle:** standing context answers *who, when, what's due, the big picture, what's notable, core health, the day's posture, my goals, what's trustworthy.* Everything else is a tool call. Bloating the standing package with domain detail burns tokens every turn for value needed on few turns.

---

## 3. Token-Cost Posture

- Standing context must be **summaries, not records.** Every field above is already an aggregate/verdict (SAE stores meaning, not raw rows — Audit Doc 2 §3.1), so the package is naturally compact.
- The package is **one composed object** (`build_cos_context`), not nine fetches — assembled once, cached per the existing CoS cadence.
- Field 6 (health) and 8 (goals) carry only the *headline* metrics; full domain state is on-demand. This keeps the always-on cost bounded while preserving foundational awareness.

---

## 4. Readiness Classification (summary)

| Status | Fields | Meaning |
|--------|--------|---------|
| **EXISTS** | 1, 2, 3, 4, 5, 7, 9 | Computed and composed today; needs serialization only |
| **PARTIAL** | 6 (health — no "recent changes" delta), 8 (goals — no stalled/discipline-trend) | Present and usable; missing fields are non-blocking for standing context |
| **MISSING** | none in the recommended package | (Travel/screen were excluded precisely because they're MISSING/unreachable) |

**Bottom line:** the entire recommended standing package is **EXISTS or PARTIAL** — zero MISSING. Day-1 work is one serialization of an object WLJ already builds every turn. This is the cheapest, highest-leverage item in the whole launch.

---

*Document 2 of 6. The read/search tools that operate on top of this standing context are specified in Document 1; write tools in Document 3.*
