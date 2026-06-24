# WLJ System Architecture Overview

**Document 1 of 6 — WLJ System Discovery & Architecture Knowledge Extraction**
Purpose: a single high-level model of the entire Whole Life Journey (WLJ) platform, so that an external conversational layer (ChatGPT) can reason holistically over the user's life while the existing WLJ platform is preserved unchanged.
Scope note: This is an objective inventory. Nothing here proposes changes. Every detailed claim is proven with `file:line` references in the companion documents (02a–07).

---

## 1. What WLJ Is

WLJ is a **Django 5.x personal life-operating-system**. It collects data across every major area of a person's life (health, medical, meals, faith, purpose, tasks/calendar, relationships, journal, capture, notes, finance, sports, brain training), interprets that data through a deterministic intelligence pipeline, and exposes the result through dashboards and a conversational **Chief of Staff (CoS)** — currently an in-process OpenAI chat agent the owner personalizes as "Beth."

The platform's defining architectural conviction is **truth before narration**: the LLM never determines what is true. It only narrates over state that deterministic code has already computed.

**Stack (verified):** Django 5.x · PostgreSQL (prod) / SQLite (dev) · Celery + Celery Beat (background intelligence) · Gunicorn/Railway/Nixpacks · OpenAI API (`gpt-4o` family) · django-allauth (email-only auth + MFA) · iOS Swift/SwiftUI wrapper feeding HealthKit data.

**Apps (30+):** domain apps (`health`, `medical`, `meals`, `faith`, `journal`, `purpose`, `life`, `calendar_engine`, `relationships`, `finance`, `capture`, `notes`, `sports`, `brain_training`, `owner_finance`, `scan`) · the intelligence core (`core` with ~28 `ai_*` packages) · the conversational layer (`ai`, `cos`) · UI (`dashboard`, `dashboard_v2`, `dashboard_v3`) · support (`users`, `billing`, `security`, `sms`, `mobile`, `help`, `admin_console`).

---

## 2. The Central Law: Raw Data → Signals/State → CoS → LLM

Every architectural decision in WLJ traces back to one pipeline (codified in `@WLJ_SYSTEM_PROMPTS/03_REFERENCE/WLJ ARCHITECTURE LAWS.md`, Laws 1–2):

```
  RAW DATA            SIGNALS / STATE              CoS CONTEXT             LLM
 (domain models) → (deterministic interpretation) → (composed dict) → (narration only)
```

There is a strict **truth hierarchy** (Law 1): deterministic system data → canonical structured state → signals/engine interpretation → CoS context → LLM narration. The LLM sits at the *bottom*. It may rephrase rendered output; it may not construct factual statements (Law 13).

This is why the system has so much machinery *below* the chat box: the intelligence is in the state layer, not the prompt. The stated direction is that the CoS gets smarter because **state gets richer**, not because prompts get longer.

---

## 3. The Three-Phase Intelligence Pipeline

WLJ separates intelligence into three phases whose boundaries are inviolable (Law 8). Crossing a boundary is treated as a defect.

| Phase | Question | Engines (verified) | Rule |
|-------|----------|--------------------|------|
| **Phase 1 — Interpretation** | "What did the user mean / what happened?" | SUE (semantic), SLCME (memory/context), HTIE (time) | May never execute domain actions |
| **Phase 2 — Execution** | "Do the thing." | UAIO orchestrator cluster (sole write authority), ETE (execution truth), Today Engine | The *only* path to writes |
| **Phase 3 — Post-Execution** | "What does this mean now?" | SAE (state), PIE (insights), PRIE (predictions), PGE (guidance), CDCE (cross-domain), GLOE, E3, DBE, WIRE, ISE, DNE, EAE, + Blueprint suite | Observe and emit only; never execute |

The full engine inventory (50+ engines/services across ~28 `ai_*` packages) is catalogued with cadence and status in **03_Engine_Catalog.md**. Key acronym→code mappings (verified against code, not assumed):

- **SAE** (State Assembly/Engine) → `apps/core/ai_state/` — the canonical "current state" layer. `build_*_state` builders + `get_module_state`/`get_metric`.
- **PIE** (Proactive Insight Engine) → `apps/core/ai_insights/` — single-domain factual pattern rules.
- **PRIE** (Predictive Intelligence Engine) → `apps/core/ai_predictions/` — regression trajectories + confidence.
- **PGE** (Proactive Guidance Engine) → `apps/core/ai_guidance/` — evidence-based recommendations over SAE+PIE+PRIE.
- **CDCE** (Cross-Domain Correlation Engine) → `apps/core/ai_cross_domain/` — statistical cross-domain relationships (6-hour cadence).
- **UAIO** → `apps/core/ai_orchestrator/` — orchestration/intent/execution/safety/action-router cluster; Phase-2 write authority.
- **ETE** (Execution Truth Engine) → `apps/core/execution/execution_truth_engine.py` — single source of completion truth.
- **SAME cycle** → background population loop (~60s) that computes heavy analytics and writes cache + DB snapshots.

> Note on one discrepancy worth carrying forward: code names **EAE = "Executive Arbitration Engine"** (`config/settings.py:187` + docstring), not "Evidence Aggregation Engine" as some reference docs state. Code wins. (See 03_Engine_Catalog.md §gaps.)

---

## 4. Signals — The Interpretation Layer

Domains do not hand raw rows to the CoS. They emit **signals**: deterministic, structured interpretations consolidated into one shape (`UnifiedSignal`) by `apps/core/ai_signals/unified_feed.py`.

- **Canonical shape:** `domain, type, severity, priority_tier, confidence, dedupe_key, source, evidence, explain_why, recency`. Missing required fields → dropped.
- **Priority tiers:** `foundational` (health, medical) > `important` (meals, sleep, habits, faith) > `supporting` (life, tasks, notes). Foundational signals always surface and **suppress** same-domain non-foundational signals (`resolve_conflicts`).
- **Source precedence:** Guidance (PGE) > Insight (PIE) > Prediction (PRIE) > Cross-domain (CDCE) > Correlation > Drift.
- **Deterministic rendering (Law 13):** user-facing prose comes only from the table-driven `apps/core/signals/signal_renderer.py` (`SIGNAL_RENDER_MAP[(domain,type,severity)] → template`). Producer prose is stripped (`normalize_signal`) so it can never leak to the user. Labels are restricted to exactly `{Alert, Trend, Opportunity}`.

Renderer coverage is partial: Health, Medical, Faith, and Life are wired to the canonical renderer; other domains still fall back to bespoke per-surface rendering (Phase 2 of that migration is pending).

---

## 5. Execution & "Today" — How Current State Is Computed

The most load-bearing computation in WLJ is **"what should the user do right now, and where do they stand today."** This is fully deterministic — no LLM touches it (Law 14). Canonical entry points (all in `apps/core/execution/`, proven in 02b & 04):

| "Current X" | Canonical method |
|-------------|------------------|
| Daily completion truth | `get_execution_truth()` — `execution_truth_engine.py:81` ("single source of completion truth") |
| Today's contract | `build_today_execution()` — `today_execution.py:34` |
| Unified execution state | `build_execution_state()` — `execution_state.py:46` |
| Next action / biggest risk / fix priority | `get_next_action` / `get_biggest_risk` / `get_fix_priority` — `selectors.py:145/254/326` |
| Active time block | `get_active_block()` — `active_block.py:145` |
| Is item recoverable | `is_recoverable()` — `recoverability.py:85` |
| Current module state (health, etc.) | `build_*_state()` via SAE — `apps/core/ai_state/state_builder.py` |

Two deterministic contracts govern this layer:

- **Recoverability (Law 15):** every actionable item is classified `HARD_EXPIRED / WINDOWED / SOFT_EXPIRED / FLEXIBLE` (`task_classifier.py:31-34,100`) from activity type / domain rules — never from titles. Recoverability gates whether an item reaches the action pool.
- **Decision modes (Law 14):** the CoS answers in exactly one of three modes — **Execution / Risk / Fix** — chosen by a keyword router (`apps/ai/cos_mode_router.py`), not an LLM. Selectors are pure picks over pre-filtered state; they do not rank, query, or call an LLM. Modes never blend.

The **Visual Truth Contract** (`docs/WLJ_VISUAL_TRUTH_CONTRACT.md`) extends the same principle to the UI: only data-confirmed completion (`item.completed == True`) may use completion-resembling visuals. This is test-enforced.

---

## 6. How Context Reaches the Conversation

When a chat message arrives, WLJ assembles context in a fixed, ordered pipeline (full call-chain in 04):

```
AssistantChatView.post (ai/views.py:732)
  → PersonalAssistant.send_message (ai/personal_assistant.py:1142)
     → deterministic CoS-mode shortcut (execution/risk/fix bypass the LLM entirely)
     → build_cos_context (ai_orchestrator/cos_context.py) — composed structured state
     → intent recognition (ai/intent_service.py:160)
     → _generate_response: layered system prompt assembly
         · base prompt + personal facts
         · CoS context injection (tier-tagged) + canonical TODAY block
         · LOCKED CoS STATE + ANTI-FABRICATION blocks
     → LLM call
  → soft post-LLM governance: narration-contract validator, contradiction telemetry, chat snapshot
  → background thread: learning / fact extraction
```

Every section appended to the prompt declares a **trust tier** (Law 16, `narration_contract.py:51-56`): `canonical_item_truth` > `rollup_summary` > `advisory` > `contextual`. Item-state claims (completed, overdue, at-risk, next action) must trace to a `canonical_item_truth` section; advisory/contextual sections may not override canonical. Enforcement is *soft* (post-response logging/flagging) — the *hard* guarantees come upstream from the deterministic selectors, the LOCKED STATE block, and the anti-fabrication prompt sections.

Streaming (`/api/chat/stream/`) and non-streaming (`/api/chat/`) both route through the same `_generate_response`, giving structural parity (Law 12).

A single composed read, `build_cos_intelligence()` (`cos_intelligence.py:253`), is the "standing" CoS state object — consistent with the architectural rule that **Beth consumes composed briefings, not raw signals.**

---

## 7. Historical Intelligence & Memory

History and memory are first-class, stored in dedicated models (detail in 04):

- **SAE snapshots:** `UserState` (JSON state snapshot, `ai_state/models.py:18`).
- **Situational state:** `CoSSituationState` (recomputed ~15 min).
- **Briefings:** `DailyBriefing` (one per day, snapshotted, `ai_briefing/models.py:12`).
- **Intelligence artifacts:** `Insight`, `Prediction`, `GuidanceItem` (persisted, with inboxes).
- **Memory:** `PersonalFact` (permanent), `LearnedMapping`, `ContextSnapshot`, `ClarificationLog` (`ai_memory/models.py`). Retrieval is ordered through `resolve_context()` (`memory_engine.py:63`).
- **Notes** acts as the long-term knowledge layer (Postgres FTS + OpenAI embeddings + a 6-factor CoS ranker, `apps/notes/services.py:419`).

Signals themselves support multiple time horizons (short/medium/long/lifetime), so the CoS can reason on both immediate coaching windows and long-term trends.

---

## 8. Domains at a Glance

Full per-domain catalog in **02a/02b/02c**. Summary of canonical truth ownership (Law 4 — single source of truth):

| Domain | App | Canonical truth lives in | Emits signals? |
|--------|-----|--------------------------|----------------|
| Health | `apps/health` (largest, ~6,400-line models) | `DailyHealthSummary` + score services; `Intake` is the unified med/supplement model | Yes (foundational) |
| Medical | `apps/medical` | Lab ingestion (`LabResult`, `importer.py`) | Yes (foundational) |
| Meals | `apps/meals` (household-scoped) | Nutrition services; restaurant receipts → `health.FoodEntry` | Yes (important) |
| Faith | `apps/faith` | `faith_queries.py` (Bible-completion truth) | Yes (important) |
| Journal | `apps/journal` | `content_intelligence.analyze_journal_for_cos()` | Partial |
| Purpose | `apps/purpose` | Goals + habits + momentum | Yes |
| Life / Tasks | `apps/life` | Execution pipeline (see §5) | Yes (supporting) |
| Calendar Engine | `apps/calendar_engine` | Projection layer + active-block resolver; primary JSON API | No (consumes upstream) |
| Relationships | `apps/relationships` | `RelationalHealthService.compute_health()` | Yes |
| Finance | `apps/finance` | `FinanceAIService` | Yes |
| Capture | `apps/capture` | Audio→transcript→`CaptureSignal` candidates (cross-domain ingestion) | Yes (blended into snapshots) |
| Notes | `apps/notes` | GFK attachments + FTS + embeddings | Memory layer |
| Sports | `apps/sports` | `GameEvent` → 7 awareness signals | Yes (awareness only) |
| Brain Training | `apps/brain_training` | Puzzle sessions | No (pull-only) |
| Owner Finance | `apps/owner_finance` | LLM-spend telemetry (operator-only) | Operator-only |
| Travel | *(none)* | Planned future domain; only a `TravelActiveRule` insight exists | Not built |

**Cross-domain reality check:** some truth lives in unexpected places — medication adherence and medical providers actually live in `apps/health` (via `Intake` / `MedicalProvider`), not `apps/medical`. Sports is awareness-only (it does *not* yet modify routine interpretation despite the registry implying it does). These attribution facts matter for any consumer reasoning over the data and are flagged in 02a/02c.

---

## 9. User-Facing Surfaces

Three dashboard generations coexist (detail in 05): **`dashboard_v3` is the production default** (gated by `DASHBOARD_V3_DEFAULT`, `config/settings.py:130`), `dashboard_v2` is the preserved rollback at `/dashboard/classic/`, `dashboard` (v1) is legacy. v2's action/HTMX endpoints stay mounted and are reused by v3; the dispatcher only swaps the home view.

Each domain has its own home/list surface following a consistent per-app pattern. The performance-critical rule (CLAUDE.md, "never compute on the request path") is **mostly** honored — the **Ops Wall** (`admin-console/ops/`) is the strict exemplar (cache-only, returns "pending" on miss). Two surfaces still synchronously compute maturity scores on render (Intelligence Command Center and Admin Console Dashboard) — noted objectively in 05 §gaps.

The AI Chat is API-only (`/assistant/api/chat/`, `/stream/`, `/resume/<job_id>/`) rendered in a persistent panel, not a standalone page.

---

## 10. Integrations

Inventory in **06**. Inbound life-data and outbound delivery:

- **Apple Health / HealthKit** — Bearer-token mobile API (`apps/mobile`), 23 metric types routed to per-domain health models, dedup by `sync_id`, audited via `HealthIngestionRun`. This is now the canonical glucose path.
- **Dexcom / CGM** — OAuth code remains but is **deprecated** (glucose now flows via HealthKit; the known ~3h lag is upstream in Dexcom→Apple Health, not a WLJ bug).
- **Google Calendar + Gmail** — OAuth (`GoogleCalendarCredential`, `GmailService`).
- **Email** — outbound SMTP; inbound IMAP "Automate" folder polled 3×/day → `AdminTask`.
- **SMS** — Twilio (`apps/sms`): outbound, inbound webhook, Verify v2 phone verification.
- **Push** — APNs (`ai_delivery/apns_sender.py`); token on `MobileDevice.push_token` (owner device not currently registered, so proactive push no-ops for the owner).
- **Billing** — Stripe (`apps/billing`): entitlements + 5 webhook events + `PaymentAuditLog`.
- **Auth/Security** — allauth email-only + MFA (email code + WebAuthn) + field encryption + audit logs.
- **OpenAI** — chat/vision/embeddings/TTS. Key + models in `config/settings.py:79-88`; the CoS chat binds `COS_MODEL` (default `gpt-4o`). `apps/core/ai_config.py` holds only thresholds, not the key/model.

---

## 11. Personalization

- **User** is a custom email-based model (`apps/users`); **`UserPreferences`** carries settings.
- **Feature flags** live in `apps/core/context_processors.py`: module flags (`journal_enabled`, `health_enabled`, …) and sub-feature flags (`features.health.weight`, …).
- **The assistant name is user-configurable.** It is stored in `UserPreferences.cos_display_name` (`apps/users/models.py:694`) and resolved by `get_cos_name()` → the custom name or the neutral default `"Chief of Staff"`. **"Beth" is one user's personal value, not a system default** — important for any documentation that will be shared.

---

## 12. The CoS Boundary (Why ChatGPT Can Slot In)

The reason an external conversational layer can replace the in-process chat agent *without touching the platform* is the architecture's clean truth/narration split (analysis in **07**):

- The **deterministic truth providers** (SAE state, signals, execution state + selectors, recoverability, locked facts, `build_cos_context`, `build_cos_intelligence`, situational awareness, the truth/contradiction/narration validators) compute everything that matters and contain **no LLM calls**. There are only ~4 OpenAI chat call sites in the whole codebase, all in `apps/ai/services.py` / `intent_service.py`.
- The **Beth-coupled layer** is narrow: the in-process OpenAI chat loop (`personal_assistant.py`, the function-calling intent→execute→handler write path, the persona/tone post-processing, and the system-prompt assembly).
- Several endpoints **already** return clean, externally-consumable structured state with no LLM — most notably `CosDecisionView` (`/api/cos/decision/`, explicitly "NO LLM"), plus drift / daily-priorities / weekly / monthly / goal-progress views.

The crown jewels (state, signals, execution truth) are exactly the half WLJ wants to preserve. The conversational half is the only thing under reconsideration. This separation is what Document 6 (Readiness Assessment) examines in detail.

---

## 13. How To Use This Document Set

| Doc | Read when you need… |
|-----|---------------------|
| **01** (this) | The whole-system mental model |
| **02a/02b/02c** | What data exists, where each domain's truth lives, what signals it emits |
| **03** | The engine inventory — phase, cadence, status, file locations |
| **04** | How context is built and how "current state" is computed; memory/history |
| **05** | Every user-facing surface and its data sources |
| **06** | Integrations + personalization (flags, preferences, assistant name) |
| **07** | What the current Beth implementation depends on, classified for reuse |

All detailed claims in 02–07 carry `file:line` proof. Discrepancies between the existing reference docs and the actual code are called out in each document's "gaps" section rather than silently reconciled.

---

*Generated by read-only architecture discovery. No code, data, engines, signals, state, dashboards, or integrations were modified. Companion reference docs: `@WLJ_SYSTEM_PROMPTS/03_REFERENCE/` (Architecture Laws, Domain Registry, Signal Ontology).*
