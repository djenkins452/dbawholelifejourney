# Document 1 — Day 1 ChatGPT Tool Catalog

**Purpose:** The smallest read/search tool catalog that lets ChatGPT function as Danny's full-time holistic Chief of Staff on Day 1. Action/write tools are in Document 3.

**Anti-overengineering thesis (the central recommendation):** The candidate list proposes ~20 read/search tools, many one-per-domain (`get_health_context`, `get_faith_context`, …). Building 12 near-identical domain readers is exactly the overengineering the mandate forbids. WLJ already exposes **one parameterized state accessor** — `get_module_state(user, module)` (`apps/core/ai_state/state_engine.py:74`) over the `MODULE_BUILDERS` registry (`state_builder.py:5576`) covering **every domain**. So the Day-1 read surface collapses to a handful of tools, most of which are *serialization wrappers over functions that already exist*.

---

## 1. The Day 1 Read Catalog — 4 Tools, Not 12

| Day-1 tool (behavioral role) | Replaces these candidates | Backed by (existing) | Day-1 work |
|------------------------------|---------------------------|----------------------|------------|
| **get_standing_context** (implicit — always loaded) | — | `build_cos_context` / `build_executive_context` (`cos_context.py:3555/9079`) | Serialize 1 object (Doc 2) |
| **get_domain_state(domain)** | `get_health_context`, `get_faith_context`, `get_journal_context`, `get_goal_context`, `get_relationship_context`, `get_calendar_context`, `get_execution_context`, `get_finance_context`, `get_sports_context`, `get_user_preferences` | `get_module_state` over `MODULE_BUILDERS` (all domains) | Serialize 1 generic accessor |
| **get_dashboard_context** | `get_dashboard_context` | `build_executive_context` (`cos_context.py:9079`) | Already in standing context; expose for explicit deep reads |
| **get_decision(mode)** | (new — but already an endpoint) | `cos_mode_router` → `/assistant/api/cos/decision/` (`apps/ai/views.py:2221`) | **Already exposed** — reuse as-is |

**That's the entire Day-1 read surface: one always-loaded bundle + one parameterized domain reader + one composed dashboard read + one already-built decision endpoint.** Everything the per-domain candidates would have returned is reachable through `get_domain_state(domain)` because the underlying builder already exists for every domain.

---

## 2. The Day 1 Search Catalog — 1 Tool

| Day-1 tool | Replaces | Backed by | Status |
|-----------|----------|-----------|--------|
| **search_history(domain, time_range)** | `search_history`, `search_journal` (time-based) | `query_event_history` → `EventResolver` (16 domains) (`apps/ai/action_handlers.py:6626`, `ai_events/resolver.py:24`) | **EXISTS & wired** — time/date lookups across health/journal/faith |

**Deferred search (Phase 2), with reason:** `search_capture`, `search_notes`, `search_documents`, `search_conversations`, and *keyword* (thematic) history all depend on providers that are **built but unwired** (`SearchService` `apps/ai/search_service.py:30`; `search_notes_cos` `apps/notes/services.py:419`) — dead code with zero callers (Audit Doc 2 §2). They are cheap to enable later (the logic exists), but **not required for a usable Day-1 CoS**, which reasons from current state + time-based history. Including them Day-1 adds wiring surface for marginal Day-1 value.

---

## 3. Full Candidate Tool Classification

| Candidate tool | Classification | Existing provider | Existing UI/API? | Notes |
|----------------|----------------|-------------------|------------------|-------|
| `get_health_context()` | **DAY 1** (via `get_domain_state("health")`) | `build_health_state:321` | No JSON | Foundational; also in standing context |
| `get_goal_context()` | **DAY 1** (via `get_domain_state`) | `build_goal_state:1424` | No JSON | Needed for coaching/accountability |
| `get_calendar_context()` | **DAY 1** (via `get_domain_state`) | `build_calendar_state:3833` | **Yes** (`calendar_engine` APIs) | Only domain already serialized |
| `get_execution_context()` | **DAY 1** (via `get_domain_state("execution")`) | `build_today_execution:34` | Partial | Core "what to do" |
| `get_dashboard_context()` | **DAY 1** | `build_executive_context:9079` | No JSON | In standing context |
| `get_journal_context()` | **DAY 1** (via `get_domain_state`) | `build_journal_state:1731` | No JSON | Trends present; text/themes absent |
| `get_faith_context()` | **DAY 1** (via `get_domain_state`) | `build_faith_state:1622` | No JSON | Prayer/scripture present |
| `get_relationship_context()` | **DAY 1** (via `get_domain_state`) | `build_relationships_state:4671` | No JSON | Engagement gaps present |
| `get_user_preferences()` | **DAY 1** (folded into standing context) | `UserPreferences` | Partial | Personalization |
| `get_finance_context()` | **PHASE 2** (via `get_domain_state`) | `build_finance_state:4521` | No JSON | Same accessor; not core to daily CoS |
| `get_sports_context()` | **PHASE 2** (via `get_domain_state`) | `build_sports_state:5099` | No JSON | Context-modifier domain |
| `search_history()` | **DAY 1** | `query_event_history:6626` | Intent-wired | Time-based only |
| `search_journal()` | **DAY 1** (time) / **PHASE 2** (keyword) | EventResolver / `SearchService` (unwired) | — | Time-based via search_history |
| `get_document()` | **PHASE 2** | detail views (HTML) | Per-domain HTML | No JSON contract; by-id only |
| `search_capture()` | **PHASE 2** | `SearchService.search_capture` (unwired) | — | Engine exists, needs wiring |
| `search_notes()` | **PHASE 2** | `search_notes_cos` (unwired) | — | Engine exists, needs wiring |
| `search_documents()` | **PHASE 2** | (partial) | — | Overlaps get_document |
| `search_conversations()` | **PHASE 2** | conversation memory (recall) | — | Semantic recall exists in-loop |
| `get_screen_context()` | **PHASE 2** (in-app only) | `_build_page_awareness_instruction:166` | In-app only | Not reachable by external CoS |
| `get_travel_context()` | **FUTURE** | none (`TravelActiveRule` only) | — | Domain unbuilt |

---

## 4. Why This Is the Minimum (not less, not more)

- **Not less:** drop `get_domain_state` and ChatGPT can't see faith/journal/goals/relationships beyond the headline in standing context — it can't coach or diagnose holistically. Drop `search_history` and it loses "have I been here before." These two are the floor for a *holistic* CoS.
- **Not more:** the keyword-search engines, document fetch, and screen context are deferrable because a Day-1 CoS reasons from **current deterministic state + time-based history**, which the 4 read tools + 1 search tool fully deliver. Adding the unwired search layer Day-1 buys little and costs wiring/testing.
- **Mostly reuse:** of the Day-1 read+search surface, only the serialization wrappers are new; the *intelligence* (every builder, the decision router, the event resolver) already exists and runs in production.

---

## 5. Day 1 Read/Search Catalog — Final

```
ALWAYS-LOADED:   get_standing_context        (serialize build_cos_context)        [EXISTS → serialize]
READ:            get_domain_state(domain)    (serialize get_module_state)         [EXISTS → serialize]
READ:            get_dashboard_context       (serialize build_executive_context)  [EXISTS → serialize]
READ:            get_decision(mode)          (Execution/Risk/Fix)                 [EXISTS → reuse endpoint]
SEARCH:          search_history(domain,range)(query_event_history)                [EXISTS → reuse]
```

**Five tool roles. Four are serialization/reuse of existing deterministic providers; one (decision) is already a live endpoint.** This is the holistic read surface for a full-time CoS, with essentially no new intelligence built.

---

*Document 1 of 6. Write/action tools — where the reuse story is even stronger — are in Document 3.*
