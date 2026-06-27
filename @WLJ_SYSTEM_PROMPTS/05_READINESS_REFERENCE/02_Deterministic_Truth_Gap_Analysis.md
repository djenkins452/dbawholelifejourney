# Document 2 — Deterministic Truth Gap Analysis

**Purpose:** Identify every missing deterministic truth provider required for holistic Chief-of-Staff reasoning. This document does **not** propose implementations — it names the gaps and proves them with `file:line`.

A "gap" here is one of three kinds:
- **TRUTH GAP** — the deterministic metric/signal is *not computed at all*.
- **WIRING GAP** — the deterministic truth *is computed* but is unreachable by a consumer (no caller, no endpoint, dead code).
- **SERIALIZATION GAP** — the deterministic truth is computed and used internally but *not exposed* over HTTP/contract for an external consumer.

Distinguishing these matters: WLJ's gaps are overwhelmingly **wiring and serialization**, not absent truth. The intelligence largely exists; the access surface does not.

---

## 1. SERIALIZATION GAPS — computed truth that has no external contract

This is the single largest category. SAE computes a deterministic state dict for every domain (`build_*_state`, `apps/core/ai_state/state_builder.py`), reachable via `get_module_state` (`state_engine.py:74`), but **no HTTP endpoint serializes the raw module dicts**.

| Computed truth | Internal provider (file:line) | External contract today |
|---|---|---|
| Per-domain module state (health, faith, journal, goals, relationships, etc.) | `get_module_state` `state_engine.py:74`; builders at `state_builder.py:321/1424/1534/1622/1731/4671/...` | **None** — only consumed inside `build_cos_context` in the chat loop |
| Composed executive/dashboard state | `build_executive_context` `cos_context.py:9079`; `build_cos_intelligence` `cos_intelligence.py:253` | **None** — internal-only; dashboard_v3 renders it server-side |
| Full CoS context object | `build_cos_context` `cos_context.py:3555` | **None** as JSON — assembled into the LLM prompt, not returned |

Exposed exceptions (the only deterministic state already serialized): `GET /calendar/api/*` (`calendar_engine/urls.py:16-19`), `POST /ai/api/cos/decision/` (`views.py:2221`), `GET /ai/api/state/` (summarized only, `views.py:1590`).

---

## 2. WIRING GAPS — fully-built deterministic logic with zero production callers

These are implemented, deterministic, and **dead** from the CoS's perspective (verified: callers exist only in tests).

| Capability | Provider (file:line) | Evidence it's unwired |
|---|---|---|
| **Cross-module keyword search** (journal, health, goals, faith, organize, finance, capture, + `search_all`) | `SearchService` `apps/ai/search_service.py:30`; `search_all` `:1449` | `SearchService(` appears only in `apps/ai/tests/test_search_service.py`; not an intent, not a handler, no endpoint |
| **Hybrid notes search** (FTS + embeddings + 6-factor memory ranking) | `search_notes_cos` `apps/notes/services.py:419` | Only references are its own definition + a docstring in `notes/embeddings.py:11`; no production caller, no endpoint |
| **Capture transcript search** | `SearchService.search_capture` `apps/ai/search_service.py:1383` (searches title/transcript/summary) | Unreachable (part of the dead `SearchService`); the live `CaptureListView` `apps/capture/views.py:313` searches only title+summary, **not** transcript |

> Net effect: WLJ already contains the deterministic search engines a holistic CoS needs (keyword + semantic, per-domain + unified), but they are invisible to the conversational layer today.

---

## 3. TRUTH GAPS — deterministic metrics/signals that are not computed at all

These do not exist as deterministic derived truth anywhere in the codebase.

### 3.1 Content/text retrieval from state
SAE stores aggregates, counts, and verdicts — never raw text. The following content is absent from deterministic state (it lives only in raw models, with no derived provider feeding the CoS):
- Journal **entry bodies / recent reflections / major themes** — `build_journal_state:1731` has no text or theme field (no `theme` reference in `state_builder.py`).
- **Gratitude trends** — no `GratitudeEntry` model exists in `apps/journal/models.py` (confirmed absent); declared in `capabilities.py` but unbuilt.
- Faith **saved verses** — not in `build_faith_state:1622`.
- Relationship **interaction log** — only days-since recency (`state_builder.py:4703`), no event feed.
- Capture **action items** — no `action_item`/`ActionItem` model/field in `apps/capture/models.py`; action items, if any, live unstructured inside `summary` text.

### 3.2 Aggregated "recent changes" / deltas
No domain produces a consolidated "what changed recently" object. Piecemeal deltas exist (`weight_change_30d` `state_builder.py:373`, trend strings) but there is no changelog/delta array in any builder audited.

### 3.3 Trend/derived fields missing within otherwise-present domains
- Faith: **spiritual trends**, **faith learning** — point-in-time streaks only, no trend.
- Goals: explicit **stalled** classification and directional **discipline-trend** — only overdue counts and point-in-time completion rates.
- Relationships: **family-state aggregate**, relationship **stress** metric (only neglect/attention-gap exists).

### 3.4 Domains with weak or no signal emission
- **Travel** — no domain, model, state, or UI. Only a transient `TravelActiveRule` PIE insight (`apps/core/ai_insights/rules_context.py:503`). No `build_travel_state`. Routine-disruption-from-travel is detected only as an info-severity insight, not persistent state.
- **Sports** — emits awareness signals but does **not** modify routine interpretation (registry implies it does; unimplemented).
- **Brain Training** — emits no signals, no logging (pull-only).

### 3.5 Capture full-text indexing
No `SearchVector`/`GinIndex`/trigram index in `apps/capture/` — transcript search (where wired at all) is `icontains` scan only.

---

## 4. UI/SCREEN-AWARENESS GAPS

A working in-app `page_context` pipeline exists (`assistant_panel.html:686` → `views.py:766/1091` → `personal_assistant.py:166`), but:
- **No authoritative widget serialization** — `page_content` is client-side DOM scraping (`extractPageContent`, `chat_widget.html:1276`), hand-coded per page type, not generated from the dashboard_v3 composer state.
- **No external screen-context endpoint** — the mechanism only works because the in-app widget pushes context per turn; an external ChatGPT has no `get_screen_context()` to call.

---

## 5. HISTORICAL SEARCH GAPS

- **No keyword search over history** — `query_event_history` (`action_handlers.py:6626` via `EventResolver` `ai_events/resolver.py:24`) does date/count lookups across 16 health/journal/faith domains, but not free-text.
- **No unified history search** — `SearchService.search_all` would be it, but it's dead code (§2).
- **No CoS-facing search** for: insights (`ai_insights/views.py:13` list-only), guidance (`ai_guidance/views.py:26` list-only), briefings (`ai_briefing/admin.py:22` admin-only), predictions (no view), recommendations (no view).
- Goals history has no resolver adapter (not in `_DOMAIN_ADAPTERS`).

---

## 6. Consolidated Gap Register

| Gap | Type | Anchor |
|---|---|---|
| No HTTP serialization of per-domain SAE state | SERIALIZATION | `state_engine.py:74` |
| No HTTP serialization of executive/CoS context | SERIALIZATION | `cos_context.py:9079/3555` |
| `SearchService` (unified + per-domain keyword search) unwired | WIRING | `search_service.py:30/1449` |
| `search_notes_cos` (hybrid notes search) unwired | WIRING | `notes/services.py:419` |
| Capture transcript search unwired; live search excludes transcripts | WIRING | `search_service.py:1383`; `capture/views.py:313` |
| Journal entry text / themes / reflections not in state | TRUTH | `state_builder.py:1731` |
| Gratitude trends — no model | TRUTH | `apps/journal/models.py` (absent) |
| Faith saved verses / spiritual trends / faith learning | TRUTH | `state_builder.py:1622` |
| Relationship family-state / interaction log / stress metric | TRUTH | `state_builder.py:4671` |
| Capture action-items entity | TRUTH | `apps/capture/models.py` (absent) |
| Aggregated "recent changes" delta object (all domains) | TRUTH | `state_builder.py` (absent) |
| Goal stalled-classification / discipline-trend | TRUTH | `state_builder.py:1424` |
| Health unified "medical risks" object | TRUTH | `state_builder.py:4911` (only lab flags) |
| Travel domain/state | TRUTH | only `rules_context.py:503` insight |
| Capture full-text index | TRUTH | `apps/capture/` (absent) |
| Keyword/unified history search; insights/guidance/briefings/predictions search surfaces | WIRING/TRUTH | §5 anchors |
| Screen widget serialization / external screen endpoint | TRUTH/SERIALIZATION | `chat_widget.html:1276` |

**Summary:** The deterministic *truth substrate* is far more complete than the *access surface*. Of the gaps above, the majority are WIRING (dead but built) or SERIALIZATION (built and used, but internal). Genuine TRUTH gaps cluster in: raw-text/content retrieval, "recent changes" deltas, a few missing trend fields, the unbuilt Travel domain, and capture full-text indexing/action-items.
