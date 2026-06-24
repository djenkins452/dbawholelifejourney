# WLJ Context & Intelligence Pipeline

**Scope:** How conversational context is assembled and reaches the LLM — the full Context & Intelligence Pipeline the Chief of Staff (CoS / "Beth") narrates over, plus Historical Intelligence (storage + retrieval of history/memory/trends).

**Method:** Traced from inbound chat message to final LLM call, proven with `file:line`. Framing docs (`docs/cos_context_architecture.md`, `docs/INTELLIGENCE_ARCHITECTURE.md`) were read for framing and verified against code. Documentation only — no recommendations.

> **Architectural law (verified):** The narration layer "is NOT a new decision engine — it is a narration-governance layer that sits on top of the existing deterministic engines (build_today_execution, build_execution_state, signal renderer, selectors)." — `apps/core/ai_orchestrator/narration_contract.py:8`. Beth **consumes** composed deterministic state; she does not reason from atomic signals.

---

## A. Ordered Call Chain — Inbound Message → LLM

```
HTTP POST /ai/chat/  (AssistantChatView.post)                 apps/ai/views.py:732
  ├─ parse body / images, length guard (≤2000 chars)          apps/ai/views.py:806-827
  ├─ handle_day_start(user)  (idempotent day-start)           apps/ai/views.py:830  → apps/ai/executive_briefing.py
  ├─ assistant = get_assistant(); get_or_create_conversation  apps/ai/views.py:833-834
  └─ assistant.send_message(message, conversation, ...)        apps/ai/views.py:836
        │
        ▼  PersonalAssistant.send_message()                    apps/ai/personal_assistant.py:1142
        ├─ idempotency guard (check_duplicate)                 :1199
        ├─ ★ DETERMINISTIC CoS-MODE SHORTCUT (LLM BYPASS)      :1213 → _cos_mode_shortcut() :819
        │     resolve_cos_mode(message) → "execution"|"risk"|"fix"   apps/ai/cos_mode_router.py:99
        │     build_execution_state(user)                       apps/core/execution/execution_state.py:46
        │     select(mode, state) → deterministic message       apps/core/execution/selectors.py:441
        │     (LLM NEVER called on this path)
        ├─ persist user AssistantMessage (+ images)            :1225
        ├─ comprehensive vision analysis (if images)           :1259
        ├─ ECC pre-check: build/reuse cos_context, tier        :1311-1364
        │     build_cos_context(user)                           apps/core/ai_orchestrator/cos_context.py:3555
        │     (cached into _cos_context_cache for reuse)        :1357
        ├─ intent recognition  intent_service.recognize_intents apps/ai/intent_service.py:160
        │     _build_intent_system_prompt(user, page_context)   apps/ai/intent_service.py:377
        │     intent categories sourced from *_INTENTS sets     apps/core/ai_orchestrator/intent_engine.py:15-129
        │     → if actionable: execute_intent()                 apps/ai/intent_service.py:1403
        └─ ★ _generate_response(message, cos_context_cache=…)   apps/ai/personal_assistant.py:3307 (called :1557/1753/2150)
              │
              ▼  CONTEXT ASSEMBLY (prompt construction)
              ├─ base system prompt  _build_system_prompt()     :3371 (calls :761)
              │     └─ build_personal_facts_prompt(user)        injected at :701 (PersonalFact memory)
              ├─ priority_layers = []  /  append_layers = []    :3468-3469
              ├─ priority layers (PREPENDED): calibration :3508, recalibration :3527,
              │     alignment :3540, governance :3553, learned profile :3565
              │     get_profile_system_prompt(user)             apps/core/ai_learning/learning_extractor.py
              ├─ Layer 6 — operational context:
              │     • learning-mode? build_learning_mode_context :3586
              │     • check-in? FORCE fresh build_cos_context   :3592
              │     • else reuse cos_context_cache              :3597-3599
              │     • else readiness cache (layered→flat)→build :3601-3656
              │       build_cos_context(user, scoped_builders)  apps/core/ai_orchestrator/cos_context.py:3555
              │     • trajectory signals + activation tier      :3659-3667
              │     • ECC detection/closure (DB commitments)    :3676-3760
              │     • affirmed completions / event followups    :3762-3784
              ├─ format_cos_system_injection(cos_context, msg)  :3786 → cos_context.py:6136
              │     (emits [TIER:…]-tagged sections; FINAL EXECUTION STATUS anchor verified :3795)
              ├─ append cos_injection                           :3814
              ├─ LOCKED CoS STATE block (build_cos_structured_output) :3820-3845
              ├─ ANTI-FABRICATION RULES (absolute)              :3858-3886
              ├─ assembled = priority_layers + [system_prompt] + append_layers  :3954-3955
              ├─ executive briefing / checkin briefing          :3973-3994 (apps/ai/executive_briefing.py)
              ├─ conversation memory (rolling summary)          :4000-4003
              ├─ health-briefing narration addendum             :4012
              └─ → LLM call (ai_service) → response text
              │
              ▼  POST-LLM NARRATION GOVERNANCE (soft, non-blocking)
              ├─ validate_narration_contract(response, canonical_blob, rollup_blob)  :2247
              │     apps/ai/narration_contract_validator.py:1   (flags claims not traceable to canonical)
              ├─ detect_contradictions(exec_state, fresh_med_schedule)  :2279
              │     apps/core/ai_orchestrator/contradiction_telemetry.py:1
              └─ dump_chat_snapshot(build_snapshot_payload(...))       :2302
                    apps/ai/observability/chat_snapshot.py:1  (flag WLJ_CHAT_SNAPSHOTS_ENABLED)
        │
        ▼  back in view: spawn bg thread _post_response_intelligence  apps/ai/views.py:854-902
              learning extraction, correction detect, pattern detect,
              extract_life_facts_from_message → PersonalFact  apps/ai/views.py:892-898
```

**Streaming path** (`/ai/chat/stream/`, SSE): `AssistantChatStreamView` `apps/ai/views.py:1058` → `_generate_response_stream()` `apps/ai/personal_assistant.py:5785` (docstring: "Streaming version of _generate_response", falls back to full `_generate_response` pipeline at :5800/:5844). Both paths funnel through the **same** context-assembly + `format_cos_system_injection` machinery — Streaming-vs-Non-Streaming parity is structurally enforced by sharing `_generate_response`.

---

## B. Context Builders Table

| Builder | Entry (file:line) | Inputs | Output | Truth sources | Consumers |
|---|---|---|---|---|---|
| **CoS context (master)** | `build_cos_context(user, scoped_builders=None)` `cos_context.py:3555` | user, optional scoped builder tags | comprehensive dict (blueprint, pressure, health, calendar, signals, `cos_intelligence`, etc.) | Pre-loads SAE snapshot `get_user_state` (:3589); runs ~30 tagged `_build_*` builders in parallel via ThreadPoolExecutor | `_generate_response` :3592/3639; ECC pre-check :1321 |
| **CoS prompt formatter** | `format_cos_system_injection(context, user_message)` `cos_context.py:6136` | cos_context dict, message | tiered prompt string with `[TIER:…]` sections + FINAL EXECUTION STATUS anchor | `build_cos_context` output; `DailyProgressService.get_today()` for canonical TODAY block (:8355) | `_generate_response` :3786 |
| **Unified CoS intelligence** | `build_cos_intelligence(user)` `apps/ai/cos_intelligence.py:253` | user | dict: overall, goal_pace, recommendation_effectiveness, briefing, events | `goal_pace`, `evaluate_active_recommendations`, `build_executive_summary` (cos_briefing), `recent_cos_events` | Injected into `cos_context['cos_intelligence']` `cos_context.py:3978-3979` |
| **SAE state** | `get_module_state(user, module)` `ai_state/state_engine.py:74`; `get_user_state` :19; `rebuild_user_state` :95 | user, module | state dict per module; `get_state_value(user, path)` :142 dot-path reads | ~23 `build_*_state` builders `state_builder.py` (`MODULE_BUILDERS` :5576): health :321, goal :1424, execution :5610 (wraps `build_today_execution`) | `build_cos_context` :3589; briefing engine; persona adaptation |
| **Situation state** | `compute_situation_for_user(user)` `ai_state/situation_computer.py:23` | user | `CoSSituationState` (situation_mode, dominant_concern, opening_sentence) — pre-computed every 15 min | SAE + engine outputs (pure logic, no LLM) | CoS awareness / opening |
| **Right-now focus** | `compute_right_now_focus(trust_reports, completed_today)` `ai_state/right_now.py:133` | domain trust reports | dict (status, domain, priority, confidence, reason) — single-item focus selector | domain trust reports | situational awareness |
| **Briefing (DBE)** | `generate_daily_briefing(user)` `ai_briefing/briefing_engine.py:26`; retrieve `get_todays_briefing` :106 | user | `DailyBriefing` (summary + state/guidance/insight/prediction snapshots) | SAE `get_user_state`, `Insight`, `Prediction`, `GuidanceItem`; ranked via `briefing_selector.py:22`/`briefing_ranker.py:13`; stored via `briefing_logger.store_briefing` :18 | daily-briefing mgmt cmd, Celery, executive briefing |
| **Memory (SLCME)** | `resolve_context(user, phrase, hint)` `ai_memory/memory_engine.py:63` | user, phrase | `MemoryResolution` (resolved, source, confidence, needs_confirmation) | `ContextSnapshot` (current view) → `LearnedMapping` (learned) priority order | orchestrator context_pipeline, entity_resolver, learning_pipeline |
| **Life facts** | `build_personal_facts_prompt(user)` `ai_memory/life_fact_extractor.py:258`; extract `extract_life_facts_from_message` :69 | user / message | prompt block of permanent facts | `PersonalFact` (permanent) | `_build_system_prompt` injects at `personal_assistant.py:701`; bg extraction `views.py:896` |
| **Persona (PIL)** | `render_with_persona(user, base_message, message_type, …)` `ai_persona/persona_engine.py:22` | user, message, type, priority/severity | persona-rendered string (fail-safe → base on error) | `user.preferences.ai_coaching_style` → `get_persona_profile` (registry.py:355); tone via `calculate_tone_intensity` (adaptation.py:33, reads GLOE/ICQG/SAE) | briefing engine :349, weekly report engine |
| **Narration contract preamble** | `narration_contract_preamble()` `ai_orchestrator/narration_contract.py:83`; `section_header(tier,title)` :69 | — | prompt preamble declaring strict tier authority | static contract text | top of CoS prompt; every `[TIER:…]` section |

**Builder safety contract:** all COS-CX modules are fail-safe — return empty string on any error, never break the chat pipeline (`docs/cos_context_architecture.md:20,163`; mirrored by `except … pass` guards throughout `_generate_response`).

---

## Trust Tiers (declared & enforced)

Declared in `apps/core/ai_orchestrator/narration_contract.py:51-56`:

| Tier | Constant | Authority |
|---|---|---|
| **canonical_item_truth** | `TIER_CANONICAL` :51 | ONLY authority for done / overdue / recoverable / at-risk / "next". LLM must quote verbatim. |
| **rollup_summary** | `TIER_ROLLUP` :52 | Domain/window aggregates; MUST NOT become per-item completion claims. |
| **advisory** | `TIER_ADVISORY` :53 | Recommendations; MUST NOT determine state/urgency/selection. |
| **contextual** | `TIER_CONTEXTUAL` :54 | Background (signals, goals, time-of-day); default for untagged sections; never overrides canonical. |

- **Preamble** (read-first contract): `narration_contract_preamble()` :83, inserted at top of prompt.
- **Section tagging:** `section_header(tier, title)` :69 emits `[TIER:<tier>] <title>` (used throughout `cos_context.py`, e.g. :4699, :6585).
- **State-determining check:** `is_state_determining_tier()` :146 — only canonical qualifies.
- **Post-LLM validator:** `validate_narration_contract()` `apps/ai/narration_contract_validator.py:1` — soft-warn, flags claims traceable only to rollup/advisory/contextual; does NOT block (`:9-12`).
- **Contradiction telemetry:** `detect_contradictions()` `apps/core/ai_orchestrator/contradiction_telemetry.py:1` — pre/post detection of rollup-says-DONE vs canonical-child-pending (PRAYER/BIBLE/MEDICATION/WORKOUT/JOURNAL codes :8-18).
- **Snapshot artifact:** `chat_snapshot.py:1` — per-request JSON tying prompt sections (with tier), execution snapshot, selector outputs, contradictions, validations, LLM response; flag `WLJ_CHAT_SNAPSHOTS_ENABLED`.

---

## C. Current-State Computation — Canonical Methods

| "Current X" | Canonical method | file:line |
|---|---|---|
| **Current execution state** | `build_execution_state(user, now, execution_contract)` | `apps/core/execution/execution_state.py:46` |
| **Today (authoritative contract)** | `build_today_execution(user)` | `apps/core/execution/today_execution.py:34` |
| **Daily status / completion truth** | `get_execution_truth(user, target_date)` ("THE single source of completion truth") | `apps/core/execution/execution_truth_engine.py:81` |
| **Today's per-domain prompt block** | `DailyProgressService(user).get_today()` (CANONICAL block in CoS prompt) | `apps/dashboard_v2/services/daily_progress_service.py`; injected `cos_context.py:8355` |
| **Next action** | `get_next_action(state)` — EXECUTION mode | `apps/core/execution/selectors.py:145` |
| **Biggest risk** | `get_biggest_risk(state)` — RISK mode | `apps/core/execution/selectors.py:254` |
| **Fix priority (fix first)** | `get_fix_priority(state)` — FIX mode | `apps/core/execution/selectors.py:326` |
| **Selector dispatcher** | `select(mode, state)` | `apps/core/execution/selectors.py:441` |
| **Chat-mode routing (which of the 3)** | `resolve_cos_mode(user_input)` (FIX > RISK > EXECUTION) | `apps/ai/cos_mode_router.py:99` |
| **Active block (current window)** | `get_active_block(user, now, execution_items)` | `apps/core/execution/active_block.py:145` |
| **Recoverable / past-window** | `is_recoverable(item, now)` | `apps/core/execution/recoverability.py:85` |
| **Right-now focus (single item)** | `compute_right_now_focus(trust_reports, completed_today)` | `apps/core/ai_state/right_now.py:133` |
| **Current situation/awareness** | `compute_situation_for_user(user)` → `CoSSituationState` | `apps/core/ai_state/situation_computer.py:23` |
| **Current health** | `build_health_state(user)` (SAE) | `apps/core/ai_state/state_builder.py:321` |
| **Standing CoS read (overall/pace/rec)** | `build_cos_intelligence(user)` | `apps/ai/cos_intelligence.py:253` |
| **Locked structured day state** | `build_cos_structured_output(user)` (do_now / sequence / completed) | `apps/ai/beth_checkin_renderer.py`; injected `personal_assistant.py:3824` |

**Key property:** The deterministic CoS-mode shortcut (`_cos_mode_shortcut` `personal_assistant.py:819`) and the Action Center share the **same** `build_execution_state` + `selectors` contract — execution/risk/fix answers are 100% deterministic and bypass the LLM (`personal_assistant.py:1207-1216`).

---

## D. Historical Intelligence — Storage & Retrieval

### Persistent state / memory models

| Model | file:line | Key fields | Retention | Retrieval |
|---|---|---|---|---|
| **UserState** (SAE snapshot) | `apps/core/ai_state/models.py:18` | `state_data` (JSON keyed by module), `schedule_instability_score` (rolling 7-day), `last_updated`, `created_at` | One-to-one per user; overwritten incrementally after each action; `last_updated` indexed | `get_user_state` / `get_module_state` `state_engine.py:19/74`; `get_state_value` dot-path :142 |
| **CoSSituationState** | `apps/core/ai_state/models.py` (after UserState) | situation_mode, dominant_concern, opening_sentence; recomputed every 15 min (pure logic) | persistent awareness snapshot; enables delta tracking | `compute_situation_for_user` `situation_computer.py:23` |
| **DailyBriefing** | `apps/core/ai_briefing/models.py:12` | `briefing_date`, `summary`, `state_snapshot`, `guidance_snapshot`, `insight_snapshot`, `prediction_snapshot` | unique (user, briefing_date) = one/day; permanent (no documented prune); ordered `-briefing_date` | `get_todays_briefing(user)` `briefing_engine.py:106`; stored by `store_briefing` `briefing_logger.py:18` |
| **Insight** | `apps/core/ai_insights/models.py:11` | severity :45, status :65, created_at :81 | indexed (user, status, -created_at); ordering `-created_at` :98 | briefing engine reads last-24h non-dismissed (≤20) |
| **Prediction** | `apps/core/ai_predictions/models.py:11` | confidence_score :35, status :38, created_at :42 | indexed (user, status), (user, created_at) | briefing engine reads status=active ordered `-confidence_score` (≤15) |
| **GuidanceItem** | `apps/core/ai_guidance/models.py` | active/dismissed/expired status | active + not-dismissed | `get_active_guidance(user, limit)` |
| **PersonalFact** (life facts) | `apps/core/ai_memory/models.py:15` | fact_type (8 categories), subject_name, relationship, fact_text, confidence, source, is_active | **PERMANENT** — never auto-pruned; indexed (user, fact_type, is_active) | `build_personal_facts_prompt(user)` `life_fact_extractor.py:258` → injected `personal_assistant.py:701` |
| **LearnedMapping** (phrase→meaning) | `apps/core/ai_memory/models.py:112` | phrase, meaning_type/identifier, confidence_score, usage_count, last_used_at, is_active | soft-deactivatable, kept for history; confidence grows +0.05/reuse (cap 1.0) | `find_learned_mapping(user, phrase)` `retrieval_engine.py:13` (auto-use ≥0.75) |
| **ContextSnapshot** (current view) | `apps/core/ai_memory/models.py:177` | context_type, context_identifier, metadata, created_at | all kept; latest-per-type used | `get_current_context(user, context_type)` `context_resolver.py:35` |
| **ClarificationLog** (audit) | `apps/core/ai_memory/models.py:222` | original_input, clarification_question, user_response, resolved_meaning | write-only audit, never deleted | by user, `-created_at` |

### Memory resolution order (SLCME)
`resolve_context()` `memory_engine.py:63` resolves a phrase in priority order:
1. **Current context snapshot** (`get_current_context` :35) — high confidence (matches user's current page).
2. **Learned mappings** (`find_learned_mapping` :13) — auto-use if `is_safe_to_use()` (≥0.75); request confirmation if 0.5–0.75.
3. **None** — caller falls back to DB lookup or asks the user.

### Trends / behavioral history
- **Rolling conversation summary** ("memory") injected via `get_conversation_memory(conversation)` `personal_assistant.py:4001` (skipped for check-in/task queries to avoid stale-task contamination).
- **Schedule instability:** rolling 7-day score on `UserState` (`models.py` schedule_instability fields).
- **Behavioral forecast (CX6):** 8-week lookback computed live per request (`apps/cos/intelligence/behavior_forecast.py`, per `docs/cos_context_architecture.md:145-157`) — derived, not stored.
- **Decision/learning history:** `apps/core/ai_orchestrator/decision_memory.py`, `learning_pipeline.py` (writes `LearnedMapping`).

---

## Notable Gaps / Observations (factual, not recommendations)

1. **Doc drift — COS-CX file paths:** `docs/cos_context_architecture.md` references `apps/cos/context/*` and `apps/cos/intelligence/*` (CX1–CX6). The wiring lives in `apps/core/ai_orchestrator/cos_context.py` and `apps/ai/personal_assistant.py` as the doc states, but the standalone `apps/cos/...` module paths were not separately verified in this pass — they are cited from the doc, not from a direct read.
2. **Narration enforcement is soft (v1):** `validate_narration_contract` logs/flags but does **not** block responses (`narration_contract_validator.py:9-12`). The hard guardrails are upstream (deterministic selectors + ANTI-FABRICATION + LOCKED CoS STATE prompt blocks), not the post-LLM validator.
3. **Snapshot artifact is flag-gated:** `dump_chat_snapshot` is a no-op unless `WLJ_CHAT_SNAPSHOTS_ENABLED` is set (`chat_snapshot.py:8-11`), so per-request prompt/response divergence forensics are off by default.
4. **`time_pipeline.py` canonical "now/today":** grep for `def get_user_now`/`def today` in `apps/core/ai_orchestrator/time_pipeline.py` returned no matches under those exact names — the canonical TODAY surface used in the prompt is `DailyProgressService.get_today()` + `build_today_execution` / `get_execution_truth(target_date=user-today default)`, not a single named time helper in `time_pipeline.py`.
5. **Two redundant `build_execution_state` calls per turn:** once for the prompt's canonical block (via `format_cos_system_injection`) and again post-LLM for narration telemetry (`personal_assistant.py:2219`). Both read the same contract; this is for validation, not divergence.
