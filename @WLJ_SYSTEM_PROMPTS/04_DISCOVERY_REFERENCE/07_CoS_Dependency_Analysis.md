# WLJ Chief of Staff (Beth) Dependency Analysis

**Date:** 2026-06-23
**Scope:** READ-ONLY knowledge extraction. Classifies what the current "Beth" conversational implementation depends on, in service of moving the conversational layer to ChatGPT WHILE PRESERVING the WLJ platform (data, engines, signals, state, dashboards, integrations unchanged).
**Method:** Traced `apps/ai/`, `apps/cos/`, `apps/core/ai_orchestrator/`, `apps/core/ai_state/`, `apps/core/signals/`, `apps/core/execution/`, `apps/core/ai_persona/`. Cross-referenced against `@WLJ_SYSTEM_PROMPTS/03_CANON_REFERENCE/WLJ ARCHITECTURE LAWS.md` (Laws 1, 2, 9, 13, 14, 15, 16) and `docs/ENGINE_COS_REFERENCE.md`.

> This is **objective classification only** — no recommendations, no redesign, no implementation plan for the ChatGPT integration.

---

## Classification buckets (definitions)

| Bucket | Meaning |
|--------|---------|
| **DETERMINISTIC TRUTH PROVIDER** | Crown jewels. Canonical state/signal/computation sources. JSON-able output, **no LLM call**. The truth layer of Laws 1, 2, 9, 13, 14, 15. |
| **REUSABLE FOR CHATGPT CoS** | Structured-data providers a different conversational layer could consume unchanged (overlaps with the above; broader — includes context builders, enrichers, validators). |
| **TIGHTLY COUPLED TO BETH** | Code specific to the current OpenAI chat orchestration / intent-handler architecture / in-process Python chat loop. Would NOT transfer directly. |
| **CONVERSATIONAL ONLY** | Pure narration / persona / prompt-assembly with no deterministic truth value. |
| **OBSOLETE** | Dead / legacy. (None found in this analysis.) |

---

## The Truth-vs-Narration boundary (Laws 1, 2, 9, 13, 16)

The architecture is explicitly **LLM-LAST** (Law 1) with a fixed truth hierarchy: deterministic data → canonical structured state → signals/engine interpretation → CoS context → **LLM narration last**. The chat loop is the only place an LLM is invoked, at exactly two sites:

- `apps/ai/services.py:424` — `self.client.chat.completions.create(...)` inside `_call_api()` (non-streaming)
- `apps/ai/services.py:562` — streaming variant inside `_call_api_stream()`
- Plus intent extraction LLM calls in `apps/ai/intent_service.py:216` and `:1141`

**Everything upstream of those four call sites is deterministic** and feeds the LLM as authoritative constraints (locked facts, situational awareness injection, executive briefing, narration-contract tiers). Everything downstream (truth validator, contradiction telemetry) checks the LLM output against deterministic truth.

---

## Master classification table

| Component | File(s) | What it does | Classification | Why |
|-----------|---------|--------------|----------------|-----|
| **SAE State engine** | `apps/core/ai_state/state_builder.py` (build_health_state:321, build_goal_state:1424, build_habit_state:1534, build_faith_state:1622, build_nutrition_state:1928, build_fitness_state:2213, build_task_state:3121); `apps/core/ai_state/metric_access.py:46` (`get_metric`→`MetricResult`); `state_engine.py` (`get_state_value`, `get_module_state`) | Canonical per-module state snapshots and scalar metrics. State-first reads (Law 9). | **DETERMINISTIC TRUTH PROVIDER** | JSON-able dicts / frozen `MetricResult` dataclass. No LLM. Single source for "current" scalars. |
| **Signal renderer** | `apps/core/signals/signal_renderer.py` (SIGNAL_RENDER_MAP:130, normalize_signal:220, render_signal:255, select_top_signals:328, resolve_conflicts:401) | Table-driven user-prose rendering of signals; prioritization + conflict resolution (Law 13). | **DETERMINISTIC TRUTH PROVIDER** | Pure lookup tables + selection logic. Producers can't leak prose. No LLM. |
| **Execution state** | `apps/core/execution/execution_state.py:46` (`build_execution_state`) | Builds the full execution-state dict: active block, items, prioritized actions, overdue/now/next/upcoming, expired/deferred, recovery_state, collapsed_blocks. | **DETERMINISTIC TRUTH PROVIDER** | Comprehensive JSON-able dict. All filtering/ranking/recovery bucketing done here (Law 14). No LLM. |
| **Execution selectors** | `apps/core/execution/selectors.py` (get_next_action:145, get_biggest_risk:254, get_fix_priority:326) | Pick the single answer for each of the 3 CoS decision modes from pre-built execution_state. | **DETERMINISTIC TRUTH PROVIDER** | Law 14 pure predicates — no DB, no ranking, no LLM. Read pre-filtered state only. |
| **Recoverability / task classifier** | `apps/core/execution/task_classifier.py:100` (`classify`); `recoverability.py:85` (`is_recoverable`) | Classifies every actionable item HARD_EXPIRED / WINDOWED / SOFT_EXPIRED / FLEXIBLE with grace/reset metadata (Law 15). | **DETERMINISTIC TRUTH PROVIDER** | Pure rule engine on activity_type/domain. No titles, no LLM. |
| **Locked facts** | `apps/ai/cos_fact_statements.py:22` (`build_locked_facts`), `:474` (`build_recovery_brief`), `:530` (`build_locked_next_action`) | System-declared authoritative facts (faith/routine/task/workout/journal summaries + `_raw` booleans) sourced from the Execution Truth Engine. | **DETERMINISTIC TRUTH PROVIDER** | LLM receives these as constraints; never composes them. No LLM call. |
| **CoS truth validator** | `apps/ai/cos_truth_validator.py:94` (`validate_response_truth`), `:387` (`validate_locked_facts`) | Post-response regex validation that the LLM's text didn't fabricate completion/state vs live execution truth; rejects/regenerates. | **DETERMINISTIC TRUTH PROVIDER** (post-LLM gate) | No LLM in the validator itself. Enforces Law 1/16 truth. Reusable as an output gate for any narrator. |
| **Contradiction telemetry** | `apps/core/ai_orchestrator/contradiction_telemetry.py:95` (`detect_contradictions`) | Pre-response detection of rollup-vs-canonical disagreements (Law 16). | **DETERMINISTIC TRUTH PROVIDER** | Pure state comparison → `Contradiction` dataclasses (`as_dict()`). No LLM. |
| **Situational awareness** | `apps/ai/situational_awareness.py:534` (`build_situational_awareness`); `:643` (`format_..._injection`) | 7–14 day behavioral patterns: workout/weight/journal patterns, mood trend, med adherence, fatigue, goal streaks, priority model. | **DETERMINISTIC TRUTH PROVIDER** | "All computations are DB + math — no LLM." `build_*` returns dict (reusable); `format_*_injection` produces prompt text (Beth-coupled). |
| **CoS intelligence** | `apps/ai/cos_intelligence.py:24` (`goal_pace`), `:253` (`build_cos_intelligence`), `:291` (`cos_intelligence_narrative`) | Composes goal-pace + recommendation-effectiveness + overall + briefing into one intelligence dict. | **DETERMINISTIC TRUTH PROVIDER** | Pure math on history. `build_cos_intelligence`→dict (reusable). Narrative fn is deterministic string assembly. No LLM. |
| **Deterministic health summary** | `apps/ai/deterministic_health_summary.py:79` (`is_health_summary_query`), `:130` (`build_health_summary_response`) | Lexical detection + SAE-sourced health summary that **bypasses the LLM** (200ms vs 15–30s). | **DETERMINISTIC TRUTH PROVIDER** | Reads SAE state, returns formatted str. No LLM. Output is prose so reuse value is the data path, not the string. |
| **Executive briefing** | `apps/ai/executive_briefing.py:335` (`build_executive_briefing`) + section builders | Composes deterministic greeting/life-events/health-gate/day-overview/journal-followup sections into a system-prompt injection block. | **REUSABLE FOR CHATGPT CoS** (data) / partly Beth-coupled (output is prompt text) | No LLM (injected, not generated). Underlying section data is reusable; the returned string is shaped for the current prompt. |
| **CoS context builder** | `apps/core/ai_orchestrator/cos_context.py` (`build_cos_context`:3555, `build_executive_context`:9079) | Assembles full operational-state dict via parallel scoped builders (state-first per Law 9 + allowlist). | **REUSABLE FOR CHATGPT CoS** | Returns fully-resolved JSON-able dict. No LLM. The canonical "everything Beth knows" object. |
| **CoS context → prompt injection** | `apps/core/ai_orchestrator/cos_context.py:6136` (`format_cos_system_injection`) | Renders the context dict into the LLM system-prompt block (narration-contract tiers, decision rules). | **TIGHTLY COUPLED TO BETH** | Produces OpenAI system-prompt prose. The narration contract framing is specific to the current chat loop. |
| **Intent engine (categorizer)** | `apps/core/ai_orchestrator/intent_engine.py` (intent sets:15–139, get_intent_module:150, is_time_aware:202, is_context_aware:207) | Static frozensets + lookups mapping intent type → module / time-awareness. | **DETERMINISTIC TRUTH PROVIDER** | Pure data + lookups. But the *taxonomy* is the current intent-handler architecture (see coupling note below). |
| **Signal interpreter** | `apps/core/ai_orchestrator/signal_interpreter.py:50` (`interpret_signals`) | Normalizes signal intents to meaning codes (`_INTENT_SEMANTICS`). | **DETERMINISTIC TRUTH PROVIDER** | Machine-readable output, no narration, no LLM. |
| **Signal insight engine** | `apps/core/ai_orchestrator/signal_insight_engine.py:67` (`generate_signal_insights`) | Rule-driven aggregation of interpreted signals → insight dicts. | **DETERMINISTIC TRUTH PROVIDER** | Static `_INSIGHT_RULES`, JSON-able output, no LLM. |
| **Orchestrator pipeline** | `apps/core/ai_orchestrator/orchestrator.py` (process_user_input:127→`OrchestratorResult`; enrich_and_execute:224) | Runs context→time→semantic resolution; routes & executes actions. | **MIXED** — `process_user_input`/`OrchestratorResult.to_dict()` REUSABLE; `enrich_and_execute` delegates to `execute_action`→`intent_service.execute_intent` = **TIGHTLY COUPLED TO BETH** | Resolution is deterministic; the execute path is the in-process intent/CRUD loop. |
| **Execution engine** | `apps/core/ai_orchestrator/execution_engine.py:39` (`execute_action`); `:176` (`_run_intelligence_chain`) | Action gateway → `intent_service.execute_intent`; then runs PIE/PRIE/SAE chain. | **MIXED** — gateway is **TIGHTLY COUPLED TO BETH** (delegates to intent loop); intelligence chain is deterministic post-execution engines | The write path is bound to the current intent dispatcher. |
| **Context pipeline** | `apps/core/ai_orchestrator/context_pipeline.py:25` (`resolve_context_pipeline`→`MemoryResolution`) | Memory-engine semantic resolution. | **REUSABLE FOR CHATGPT CoS** | Structured `MemoryResolution`. No LLM. |
| **Action router / contracts / policy** | `apps/core/ai_orchestrator/action_router.py:60` (`route_action`→`EnrichedAction`); `action_contracts.py:152` (`build_action_contract`); `action_policy.py` (get_policy:287, requires_confirmation:296, is_destructive:305, get_risk_level:322) | Enriches intents with time/context/tone; builds UX action contracts; governs confirmation/risk/rate-limit. | **REUSABLE FOR CHATGPT CoS** (structured) but **keyed to the current intent taxonomy** | `to_dict()` everywhere, no LLM. Coupling is to intent_type names, not to OpenAI. |
| **Safety engine** | `apps/core/ai_orchestrator/safety_engine.py:53` (`validate_action`→`SafetyResult`) | Destructive-action verification, timestamp bounds, risk gating. | **REUSABLE FOR CHATGPT CoS** | Deterministic `SafetyResult`, no LLM. Reusable guardrail for any executor. |
| **Decision memory** | `apps/core/ai_orchestrator/decision_memory.py` (get_decision_suggestion:23, record_decision:58, compute_context_key:97) | Learns/records user CRUD decision preferences. | **REUSABLE FOR CHATGPT CoS** | Structured dicts, DB-backed, no LLM. |
| **Narration contract** | `apps/core/ai_orchestrator/narration_contract.py` (section_header:69, narration_contract_preamble:83, is_*_tier:138–152) | Tags prompt sections with trust tiers (Law 16); preamble instructs the model. | **TIGHTLY COUPLED TO BETH** (preamble/headers) + DETERMINISTIC helpers | The preamble/header strings are OpenAI-prompt instructions specific to the current narrator. Tier predicates are reusable logic. |
| **CoS purity guard / read allowlist** | `apps/core/ai_orchestrator/cos_purity_guard.py` (classify_violation:77, log_..._violation:89); `cos_read_allowlist.py` (COS_READ_ALLOWLIST:50) | Enforces state-first reads (Law 9) — observability/CI guards. | **DETERMINISTIC TRUTH PROVIDER** | Pure classification + logging. No LLM. Architectural guardrails. |
| **Persona engine** | `apps/core/ai_persona/persona_engine.py` (`render_with_persona`); persona_profiles.py; persona_registry.py (8 profiles); persona_renderer.py (`render`); persona_adaptation.py (`calculate_tone_intensity`) | Applies a user-selected coaching-style tone (supportive/direct/drill_sergeant/etc.) to a base message via templates; intensity derived from GLOE/ICQG/severity/priority signals. **Applied POST-LLM.** | **CONVERSATIONAL ONLY** | Pure narration styling. No truth value. `ai_coaching_style` is the persona; "Beth" is just a display name. No LLM (intensity calc is deterministic signal-read). |
| **Personal assistant chat loop** | `apps/ai/personal_assistant.py` (send_message:1142, send_message_stream:6008, `_build_system_prompt`, `_generate_response`) | The in-process Python orchestration of a chat turn: idempotency, message persistence, mode shortcut, intent recognition, prompt assembly, the OpenAI call, post-processing. ~388 KB. | **TIGHTLY COUPLED TO BETH** | This IS the current OpenAI chat loop. Glue between deterministic providers and `services._call_api`. Does not transfer to an external narrator. |
| **AI service (OpenAI client)** | `apps/ai/services.py:327` (`_call_api`), `:424` (`chat.completions.create`), `:511`/`:562` (streaming) | The single OpenAI chat-completion call site. | **TIGHTLY COUPLED TO BETH** | The literal in-process LLM invocation. |
| **Intent service** | `apps/ai/intent_service.py` (`execute_intent`, `_build_intent_system_prompt`, OpenAI calls at :216, :1141) | Recognizes intents (LLM function-calling) and dispatches to handlers. | **TIGHTLY COUPLED TO BETH** | OpenAI function-calling + dispatcher tied to the current intent architecture. |
| **Action handlers** | `apps/ai/action_handlers.py` (`handle_<intent>()` methods; ~287 KB) | Executes each recognized intent against domain models (the actual writes). | **TIGHTLY COUPLED TO BETH** (interface) — but the underlying domain writes are platform | The *dispatch surface* is intent-architecture-specific; the *domain services* they call are the preserved platform. |
| **Deterministic router** | `apps/ai/deterministic_router.py` (`classify_and_route`→`RouteResult`) | Shared LLM-last routing: answers deterministically where possible, else falls through to the LLM pipeline. ~335 KB. | **MIXED** — routing logic is deterministic and reusable; it is *wired into* `send_message`/`send_message_stream` | Classifications are deterministic; the fallthrough target is the Beth chat loop. |
| **cos_mode_router** | `apps/ai/cos_mode_router.py` | Keyword resolver → "execution"/"risk"/"fix" mode (Law 14). "NO LLM is involved." | **DETERMINISTIC TRUTH PROVIDER** | Single source for "is this a deterministic mode query?" Consumed by both chat shortcut and the JSON API. |
| **narration_contract_validator** | `apps/ai/narration_contract_validator.py` | Soft post-response validator flagging state claims not traceable to `canonical_item_truth` (Law 16). | **DETERMINISTIC TRUTH PROVIDER** (post-LLM gate) | No LLM. Reusable output governance. |
| **Beth renderers** | `apps/ai/beth_day_renderer.py`, `beth_status_renderer.py`, `beth_checkin_renderer.py` (`render_morning_checkin`, `build_cos_structured_output`) | Thin deterministic formatters over the Today Engine — day agenda, status ("what's left?"), morning/midday/evening check-ins. Explicitly "LLM is NOT involved." | **DETERMINISTIC TRUTH PROVIDER** (data via `build_cos_structured_output`) / output is prose | `build_cos_structured_output()` returns a structured dict (reusable); the render functions emit fixed prose. No LLM. |
| **greeting / response governor / response optimizer** | `apps/ai/greeting_service.py`, `response_governor.py`, `response_optimizer.py` | Greeting assembly (deterministic, from CoS structured output); response-type routing (REFLECTIVE/EXECUTION/BRIEFING/ALERT); trait analysis + feedback learning. | **CONVERSATIONAL ONLY** (governor/optimizer) / greeting is deterministic-data-backed | No LLM. Governor/optimizer shape *which narration fires* — narration-governance, not truth. |
| **TTS service** | `apps/ai/tts_service.py:70` (`from openai import OpenAI`, `client.audio.speech.create`) | Converts CoS text to audio via OpenAI TTS. | **CONVERSATIONAL ONLY** | Calls OpenAI **audio**, not chat. Pure output rendering. |
| **apps/cos/ — action contracts** | `apps/cos/contracts.py` (CosActionContract, ActionResult, DuplicateCheck, ConflictCheck); `registry.py` (cos_registry); `actions/calendar_actions.py`, `actions/journal_actions.py` | CoS v2 module-action framework: dedup/conflict-aware create/retrieve/summarise contracts per module. **ACTIVE** (installed `apps.cos` settings.py:184; calendar/journal contracts wired). | **REUSABLE FOR CHATGPT CoS** | Structured `ActionResult` dataclasses; deterministic dedup/conflict logic. No LLM. A different narrator could drive these contracts. |
| **apps/cos/ — context builders** | `apps/cos/context/diagnostic_context.py`, `signal_prioritizer.py`, `temporal_matcher.py`, `specificity_block.py` | Compute single most-urgent signal, task↔free-window matches, top-N specificity, WHY-question causal injection. Injected into every CoS message via `cos_context.py`. **ACTIVE.** | **DETERMINISTIC TRUTH PROVIDER** | Deterministic scoring/matching, JSON-able outputs, no LLM. |
| **apps/cos/ — intelligence** | `apps/cos/intelligence/behavior_forecast.py`, `goal_gap_analyzer.py` | Completion-probability forecast (8-week history) and declared-vs-actual goal-gap analysis. **ACTIVE** (via cos_context). | **DETERMINISTIC TRUTH PROVIDER** | Historical math, structured output, no LLM. |
| **apps/cos/ — services & models** | `apps/cos/models.py` (CosReflection, CosPromptSchedule, CosGoalSuggestion, CosAutoShiftLog + migrations 0001–0004); `services/*` (reflection, prompt, pattern, tone, auto_shift, completion, goal_suggestion, cos_prompt_scheduler, persona_service) | Reflection capture, pre/post proactive prompt lifecycle, pattern detection, tone selection, priority-aware auto-shift, completion routing. **ACTIVE** across orchestrator/scheduler/personal_assistant. | **REUSABLE FOR CHATGPT CoS** (data/lifecycle) — `tone_service`/`persona_service` are **CONVERSATIONAL ONLY** | Models + lifecycle services are deterministic platform infrastructure. Tone/persona services are narration styling. |
| **state_assessment** | `apps/ai/state_assessment.py:36` (`assess_current_state`) | Comprehensive assessment: deterministic SAE metrics + a cached AI synthesis refreshed ~every 2h. | **MIXED** | Metric layer deterministic/reusable; the cached AI-assessment regeneration **may call the LLM**. |

---

## Per-bucket detail

### DETERMINISTIC TRUTH PROVIDERS (crown jewels)

These are the canonical sources a ChatGPT-based CoS would consume. All are JSON-able and contain **no LLM call**. They already encode the verdict (Law 16 `canonical_item_truth`) — a different narrator narrates *over* them, it does not recompute them.

1. **SAE state** — `apps/core/ai_state/state_builder.py` + `metric_access.py:46`. Single source for all "current" scalars (Law 9).
2. **Signals** — `apps/core/signals/signal_renderer.py` (render/select/resolve, Law 13).
3. **Execution state + selectors** — `apps/core/execution/execution_state.py:46`, `selectors.py:145/254/326` (Law 14). The 3 CoS decision modes resolve here with zero LLM.
4. **Recoverability** — `task_classifier.py:100`, `recoverability.py:85` (Law 15).
5. **Locked facts** — `apps/ai/cos_fact_statements.py:22` (Execution Truth Engine).
6. **Truth/contradiction/narration validators** — `cos_truth_validator.py:94`, `contradiction_telemetry.py:95`, `narration_contract_validator.py`. Post-/pre-response gates with no LLM.
7. **Situational awareness** — `situational_awareness.py:534`.
8. **CoS intelligence** — `cos_intelligence.py:253`.
9. **cos_mode_router** — `apps/ai/cos_mode_router.py` (keyword mode resolution).
10. **Signal interpreter / insight engine / purity guards** in `ai_orchestrator/`.
11. **apps/cos context & intelligence** — `diagnostic_context`, `signal_prioritizer`, `temporal_matcher`, `specificity_block`, `behavior_forecast`, `goal_gap_analyzer`.
12. **Beth check-in structured output** — `beth_checkin_renderer.build_cos_structured_output()` (the dict, not the prose).

### REUSABLE FOR CHATGPT CoS (structured, broader)

`cos_context.build_cos_context`/`build_executive_context` (the full state dict), `context_pipeline.resolve_context_pipeline`, `action_router`/`action_contracts`/`action_policy`/`safety_engine`/`decision_memory` (structured, no LLM — but keyed to the current intent taxonomy), `executive_briefing` (section *data*), and the entire `apps/cos` action-contract + lifecycle-service layer (calendar/journal contracts, reflection/prompt/pattern/auto-shift/completion services and models).

### TIGHTLY COUPLED TO BETH

The in-process OpenAI chat loop and its dispatch surface:
- `apps/ai/personal_assistant.py` (`send_message`, `send_message_stream`, `_build_system_prompt`, `_generate_response`)
- `apps/ai/services.py` (`_call_api`/`_call_api_stream` — the OpenAI call sites)
- `apps/ai/intent_service.py` (OpenAI function-calling + dispatcher)
- `apps/ai/action_handlers.py` (intent-architecture dispatch surface; underlying domain services are platform)
- `cos_context.format_cos_system_injection` and `narration_contract` preamble/headers (OpenAI system-prompt prose)
- The execute/enrich paths of `orchestrator.enrich_and_execute` / `execution_engine.execute_action`

### CONVERSATIONAL ONLY

`apps/core/ai_persona/*` (coaching-style tone, applied post-LLM), `apps/ai/greeting_service.py`, `response_governor.py`, `response_optimizer.py`, `tts_service.py`, `apps/cos/services/tone_service.py` + `persona_service.py`. No deterministic truth value.

### OBSOLETE

**None identified.** `apps/cos/` is fully active (installed at `config/settings.py:184`, wired into `cos_context.py`, scheduler, and `personal_assistant.py`). No dead modules surfaced in the traced areas.

---

## Endpoints: structured-state vs in-process-chat-only

Endpoints registered in `apps/ai/urls.py`, classified by whether they already emit clean JSON state an external consumer (e.g. ChatGPT) could consume vs whether they only wrap the in-process LLM narration. (View classes in `apps/ai/views.py`.)

### Already emit clean structured state (no narration wrapping)

| Endpoint | View (file:line) | Returns |
|----------|------------------|---------|
| `GET /assistant/api/cos/decision/?mode=` | `CosDecisionView` (views.py:2221) | **Fully deterministic** `{mode, primary_action, reason, follow_on, message}`. Explicit comment: "NO LLM is called" (views.py:2230). Backed by execution_state + selectors. |
| `GET /assistant/api/drift/` | `DriftDetectionView` (views.py:1703) | `{drift_areas:[...]}` from trend tracker. No LLM. |
| `GET /assistant/api/priorities/` | `DailyPrioritiesView` (views.py:1445) | `{priorities:[{priority_type,title,description,why_important}]}`. Structured list. |
| `GET /assistant/api/analysis/weekly/` · `/monthly/` | `WeeklyAnalysisView` (1619) · `MonthlyAnalysisView` (1661) | `{analysis:{period_start,period_end,summary,patterns,recommendations,comparison,metrics}}`. Structured dict (some narrative fields). |
| `GET /assistant/api/analysis/goals/` | `GoalProgressView` (1726) | `{report:{...}}` structured progress. |
| `GET /assistant/api/state/` | `StateAssessmentView` (1590) | `{state:{...}}` — deterministic SAE metrics, but **may include a cached AI-synthesized narrative** (MIXED). |

### In-process LLM chat loop only (narration-wrapped)

| Endpoint | View (file:line) | Why |
|----------|------------------|-----|
| `POST /assistant/api/chat/` | `AssistantChatView` (views.py:732) | Wraps `personal_assistant.send_message()` → `services._call_api()`. Returns LLM `response` text + structured `actions_taken`/`options`/`navigation` sidecar. |
| `POST /assistant/api/chat/stream/` | `AssistantChatStreamView` (views.py:1058) | SSE token stream from a Celery `run_chat_generation` task via `chat_stream_bus`. |
| `GET /assistant/api/chat/stream/resume/<job_id>/` | `AssistantChatResumeView` (views.py:1160) | Reconnect relay of an in-flight stream (no new LLM call, but bound to the chat-job machinery). |
| `POST /assistant/api/briefing/` | `ProactiveBriefingView` (views.py:337) | LLM-narrated proactive briefing via `_generate_response()`. |

> Note: the chat endpoints already return a **structured sidecar** (`actions_taken`, `options`, `navigation`, `request_id`) alongside the narration — the action/UX contract layer is JSON even though the prose is LLM-generated.

---

## Notable gaps / observations (objective)

1. **The truth layer is cleanly separable from the narrator at exactly 4 LLM call sites** (`services.py:424/562`, `intent_service.py:216/1141`). All deterministic providers sit upstream and feed the prompt; validators sit downstream and check the output. The boundary is enforced by Law 9 (`cos_read_allowlist.py`) and the CI purity test (`apps/core/ai_state/tests_metric_access.py`).

2. **Most deterministic providers expose a structured dict internally but only a prose string at the chat boundary.** Examples: `executive_briefing.build_executive_briefing` returns a prompt-injection *string*; `situational_awareness` has both `build_*` (dict) and `format_*_injection` (string); the `beth_*` renderers emit prose but `build_cos_structured_output()` exposes the dict. The reusable asset is the dict-producing function in each pair; the `format_*_injection` / render-to-prose functions are Beth-prompt-shaped.

3. **The `CosDecisionView` JSON API is the clearest existing example of a fully-deterministic, externally-consumable CoS surface** — it shares the exact execution_state + selectors pipeline used by the chat shortcut and Action Center, with no LLM (views.py:2230; `cos_mode_router.py` is the shared resolver).

4. **The intent/execution write path is the deepest Beth coupling.** `intent_service` (OpenAI function-calling) → `execution_engine.execute_action` → `action_handlers.handle_<intent>()` is structured around the current intent taxonomy and OpenAI tool schemas (Law 11 schema-parity chain). The *domain services* these handlers ultimately call are platform (preserved); the *dispatch surface* is Beth-specific.

5. **Persona ("Beth") is post-LLM tone styling, not truth.** The assistant name is a user-configurable `cos_display_name`; the persona is `user.preferences.ai_coaching_style` (8 profiles). `render_with_persona` is applied after generation. No truth value; entirely in the CONVERSATIONAL ONLY bucket.

6. **`apps/cos/` (CoS v2 action framework) is active platform infrastructure, not legacy.** Its action contracts, context builders, intelligence modules, models, and lifecycle services are deterministic and reusable; only its `tone_service`/`persona_service` are narration.

7. **`state_assessment.assess_current_state` is the one MIXED truth provider** — deterministic SAE metrics plus a cached LLM synthesis. An external consumer reading it would inherit a (cached) LLM narrative unless it reads the metric layer directly.
