# Beth Conversational Behavior — Diagnostic Report

**Date:** 2026-03-12
**Investigator:** Claude (automated architectural investigation)
**Status:** Investigation complete — no code modified

---

## Table of Contents

1. [Conversation Architecture Diagram](#1-conversation-architecture-diagram)
2. [Context Assembly Analysis](#2-context-assembly-analysis)
3. [Memory & Topic Persistence Findings](#3-memory--topic-persistence-findings)
4. [Proactive Check-in Trigger Map](#4-proactive-check-in-trigger-map)
5. [Data Confidence Handling](#5-data-confidence-handling-or-lack-thereof)
6. [Engine Integration Analysis](#6-engine-integration-analysis)
7. [Root Causes of the Three Observed Behaviors](#7-root-causes)
8. [Architectural Recommendations](#8-architectural-recommendations)

---

## 1. Conversation Architecture Diagram

### Normal Message Flow (Non-Streaming)

```
User sends message
│
├─ send_message() [personal_assistant.py:2088]
│   │
│   ├─ 1. ECC check (Explicit Commitment Contract) [line 2209]
│   │   └─ Builds _cos_context_cache (first CoS build or cache hit)
│   │
│   ├─ 2. Special handlers (image, calendar, data visibility) [line 2410-2435]
│   │   └─ Calibration intents checked here
│   │
│   ├─ 3. Deterministic Router [line 2567]
│   │   └─ classify_and_route(message, user, cos_context_cache)
│   │   └─ Terminal routes → response set, skip everything below
│   │
│   ├─ 4. Check-in Prefilter [line 2589]
│   │   └─ If router says 'checkin_prefilter' → _generate_response()
│   │   └─ Skips intent recognition, goes straight to LLM
│   │
│   ├─ 5. Intent Recognition [line 2616]
│   │   └─ intent_service.recognize_intents() → OpenAI gpt-4o-mini call
│   │   └─ If action intent → execute via action_handlers.py
│   │   └─ ActionResult.message returned directly (no LLM narration)
│   │
│   ├─ 6. Fallthrough to LLM [line 2732-2760]
│   │   └─ _generate_response(message, conversation, ...)
│   │
│   └─ 7. Post-processing [line 2777+]
│       └─ Health response validator, persistence, memory storage
│
└─ _generate_response() [personal_assistant.py:3538]
    │
    ├─ a. Load conversation history (40 messages) [line 3580]
    ├─ b. Build base system prompt [line 3584]
    ├─ c. Check-in detection (CHECKIN_PATTERNS) [line 3597]
    │   └─ ⚠️ If matched → history DROPPED to 0 messages [line 4245]
    ├─ d. Governance instructions [line 3638]
    ├─ e. Learned user profile [line 3651]
    ├─ f. CoS context injection [line 3776-3838]
    │   └─ format_cos_system_injection() — massive system prompt block
    ├─ g. Executive Arbitration / UAL [line 4093-4124]
    ├─ h. Greeting injection [line 4126-4165]
    │   └─ ⚠️ FRESH SESSION → "Do NOT reference previous conversations"
    ├─ i. Task/analysis detection [line 4187-4245]
    │   └─ ⚠️ Broad phrase matching → state data injected, history dropped
    ├─ j. Semantic memory retrieval [line 4026]
    ├─ k. Data State Snapshot injection [line within format_cos_system_injection]
    └─ l. OpenAI API call [LLM invocation]
```

### Streaming Path Divergence

```
send_message_stream() [line 6079]
│
├─ Same router/intent steps as non-streaming
│
└─ _generate_response_stream() [line 5893]
    │
    ├─ Check-in → forces full pipeline path [line 5937]
    │
    ├─ Normal → _build_fast_context() [line 5533]
    │   ├─ History: 20 messages (vs 40 in full path) ← ⚠️ HALF
    │   ├─ CoS: CACHE-ONLY, never rebuilds [line 5586-5612]
    │   │   └─ ⚠️ If no cache → NO CoS injection at all
    │   ├─ No check-in data injection
    │   └─ No task/analysis state injection
    │
    └─ Fallback → _generate_response(..., _return_context_only=True) [line 5952]
```

### Key Files

| File | Role | Lines |
|------|------|-------|
| `apps/ai/personal_assistant.py` | Main orchestrator — send_message, _generate_response | ~7,500 |
| `apps/ai/deterministic_router.py` | LLM-last routing, data queries | ~850 |
| `apps/core/ai_orchestrator/cos_context.py` | CoS context builders, system prompt injection | ~5,900 |
| `apps/ai/memory_service.py` | Semantic memory (embedding-based RAG) | ~530 |
| `apps/ai/proactive_checkins.py` | Proactive check-in generation | ~varies |
| `apps/ai/assistant_intelligence.py` | Check-in intelligence, style templates | ~varies |
| `apps/ai/executive_briefing.py` | Daily briefing generation | ~varies |
| `apps/health/services/cos_health_context.py` | Health intelligence for CoS | ~300 |

---

## 2. Context Assembly Analysis

### Builder Inventory (`_TAGGED_BUILDERS` in cos_context.py:1303)

| Tag | Builder Function | Data Sources | Includes Data Completeness? |
|-----|-----------------|--------------|----------------------------|
| `blueprint` | `_build_blueprint_and_governance` | Blueprint model, governance state | No |
| `plan` | `_build_plan_and_alignment` | Tasks, calendar, alignment engine | No |
| `pressure` | `_build_pressure_and_deadlines` | Deadline model, pressure engine | No |
| `health` | `_build_health_and_vitals` | SAE state, direct DB (meds, fasting) | **NO** — raw averages only |
| `calendar` | `_build_calendar_events` | Calendar events model | N/A |
| `intelligence` | `_build_intelligence_signals` | Insight, Prediction, Guidance models | Predictions have `confidence_score` |
| `people` | `_build_people_and_mood` | Relationship signals | No |
| `loops` | `_build_loops_and_events` | Open loops, life events | No |
| `strategy` | `_build_strategy_and_signals` | Trajectory signals, decision branches | Has `INSUFFICIENT SIGNAL` flags |
| `images` | `_build_recent_image_analyses` | SAE image analysis cache | No |
| `meals` | `_build_meals_context` | SAE state, pantry models | Has `pantry_confidence` but **NOT nutrition logging coverage** |
| `faith` | `_build_faith_context` | SAE faith state | No |
| `finance` | `_build_finance_context` | SAE finance state | No |
| `brain_training` | `_build_brain_training_context` | SAE brain training state | No |
| `capture` | `_build_capture_context` | SAE capture state | No |
| `medical` | `_build_medical_context` | SAE medical state | No |
| `purpose` | `_build_purpose_context` | SAE goals/habits state | No |
| `operating_profile` | `_build_operating_profile` | UserOperatingProfile model | **YES** — has `confidence_gates` and `_confidence_qualifier()` |

### Critical Finding: Health Builder Has No Data Coverage Indicators

The `_build_health_and_vitals()` function (cos_context.py:273-537) exposes:

```python
health_signals = {
    'sleep_avg_7d': get_state_value(user, 'health.sleep_avg_hours_7d'),      # Average only
    'workout_count_7d': get_state_value(user, 'fitness.workouts_7d', 0),     # Count only
    'steps_avg_7d': get_state_value(user, 'health.steps_avg_7d'),            # Average only
    'weight_current': ...,  # Single latest value
    'glucose_avg_7d': ...,  # Average only
    ...
}
```

**What's missing:**
- No `sleep_logged_days_7d` (e.g., "3 of 7 days had sleep data")
- No `nutrition_logged_days_7d` (e.g., "2 of 7 days had meal logs")
- No `weight_entries_this_week`
- No `data_last_updated` timestamps per metric
- No sample sizes for any average

The `health_intelligence` dict from `cos_health_context.py` has `baseline_ready` (bool) and `protein_consistency_pct`, but:
- `baseline_ready` only gates the health score calculation, NOT the raw averages
- `protein_consistency_pct` is protein-specific, not general nutrition coverage
- `nutrition_logged` (line 226) is a per-day boolean in DailyHealthSummary, exposed only for today/yesterday snapshots — NOT as a 7-day coverage metric

### The Data State Snapshot

`_build_data_state_snapshot()` (cos_context.py:1961-2059) provides TOTAL counts:
```
nutrition_entries: 15
weight_entries: 42
```

But these are **lifetime totals**, not logging frequency. The LLM sees "15 nutrition entries" but doesn't know if that's 15 in the last week (good coverage) or 15 over 3 months (sparse).

### What the LLM Actually Sees (Nutrition Example)

If a user logged 2 meals in 7 days, the LLM's system prompt would contain:
```
nutrition_entries: 2                          # ← lifetime total (from Data State)
protein_avg_7d: 85.0                          # ← BUT this is based on 2 days!
protein_target_g: 140                         # ← daily target
protein_consistency_pct: 28.6                 # ← this IS useful but protein-only
```

The LLM sees a `protein_avg_7d` of 85g and a target of 140g. It could reasonably say: "Your protein intake is averaging 85g, well below your 140g target." This sounds authoritative but is based on 2 data points. **The consistency percentage IS there for protein but the LLM has no instruction to weight its language accordingly for the average itself.**

---

## 3. Memory & Topic Persistence Findings

### Conversation History Loading

| Path | Messages Loaded | When Used |
|------|----------------|-----------|
| Full pipeline (`_generate_response`) | **40 messages** | Non-streaming, calibration fallback |
| Fast path (`_build_fast_context`) | **20 messages** | Streaming (normal) |
| Check-in path | **0 messages** | Any check-in detection |

### The Check-in History Drop — Primary Cause of Topic Abandonment

**Location:** `personal_assistant.py:4233-4245`

```python
if is_asking_about_tasks or is_asking_for_analysis or is_requesting_checkin:
    # Drop ALL conversation history for check-in/task queries.
    history = conversation.messages.none()   # ← ZERO messages
```

This is triggered by **three overlapping detectors**:

1. **`CHECKIN_PATTERNS`** (56 frozen patterns, line 54-109) — matches phrases like:
   - `"where should i start"` — could occur in biblical discussion
   - `"what matters most"` — could occur in any reflective conversation
   - `"what should i focus on"` — could occur in spiritual guidance context
   - `"where am i at"` — could occur in progress discussion about faith
   - `"what would improve my life"` — existential/spiritual question
   - `"top priority"` — could occur in values discussion

2. **`is_asking_about_tasks`** (line 4189) — matches:
   - `"focus on"` — extremely broad
   - `"most important"` — extremely broad
   - `"biggest improvement"` — could be spiritual context

3. **`is_asking_for_analysis`** (line 4201) — matches:
   - `"how am i doing"`, `"how have i been"` — could refer to spiritual progress
   - `"my habits"` — could be in faith context
   - `"where should i"` — extremely broad

### Scenario: Biblical Discussion → Topic Drop

```
User: "I've been studying Proverbs and it's really changing how I think about wisdom."
Beth: "That's powerful. Proverbs has profound practical wisdom..."
User: "What should I focus on next in my reading?"
          ↑
          └─ Matches CHECKIN_PATTERNS: "what should i focus on"
             AND is_asking_about_tasks: "focus on"

Result: history = conversation.messages.none()  ← ALL context dropped
        State data injected (tasks, meds, goals)
        LLM sees: tasks, schedule, no conversation history
        LLM responds: "You have 3 tasks today. Let's focus on what matters most."
```

### Additional Topic Reset: FRESH SESSION Greeting Injection

**Location:** `personal_assistant.py:4143-4152`

```python
greeting_injection = (
    "This is a FRESH START. Do NOT reference or continue topics "
    "from previous conversations — the user has moved on."
)
```

This fires when:
1. A greeting is detected ("good morning", "hey", "hello", etc.)
2. AND an executive briefing was generated (first-of-day or 4+ hour gap)

**Effect:** Even if the user says "morning! So about what we were discussing..." the LLM is explicitly instructed to NOT continue the previous topic.

### No Topic Tracking Mechanism

There is **no topic classification or tracking system** in the codebase. Searched for:
- "topic" — only found in semantic memory `topic_tags` (stored after response, not used for continuity)
- "thread" — only found in threading-related imports
- "subject" — not found in conversation context

The system relies entirely on conversation history in the messages array. When history is dropped, all topic context is lost.

---

## 4. Proactive Check-in Trigger Map

### Sources of Proactive Messages

| Source | File | Trigger | Has Full Context? | Can Be Generic? |
|--------|------|---------|-------------------|-----------------|
| **Proactive Check-ins** | `proactive_checkins.py` | Celery Beat schedule, idle detection | Yes (reads state) | Yes — if state is sparse |
| **Assistant Intelligence** | `assistant_intelligence.py` | Called by proactive check-ins | Provides style/framing | Style can be generic |
| **Executive Briefing** | `executive_briefing.py` | First-of-day or 4h+ gap | Yes (full rebuild) | Rarely generic |
| **Opening Message** | `personal_assistant.py:get_opening_message` | Session start | Limited state | Yes — greeting + basic state |
| **FRESH SESSION Injection** | `personal_assistant.py:4143` | Greeting detected + briefing | Forces topic reset | **Yes** — explicitly generic |
| **CoS Prompts** | `cos/services/prompt_service.py` | Pending prompt queue | Depends on prompt creator | Yes |
| **Nudges** | `_build_nudges()` | State assessment | State-dependent | Can be generic |

### Why Danny Sees Both Generic and Contextual Check-ins

**Contextual path:** Proactive check-in generators in `proactive_checkins.py` are data-driven — they check medicine adherence, workout status, journal streaks, etc. They produce specific messages like "Your evening Lisinopril hasn't been marked yet."

**Generic path:** When:
1. The streaming fast path has **no CoS cache** (line 5608-5612: `FAST_CTX_NO_COS_CACHE`), the LLM gets NO operational data → generic response
2. A greeting triggers the **FRESH SESSION injection** which tells the LLM to start fresh → "Let's focus on what matters today"
3. The check-in detection drops history and injects task/schedule data, but if the user has few tasks, the LLM has minimal specifics to work with
4. Multiple injections fire simultaneously — a generic prompt injection can override a contextual CoS injection

### Multiple Systems Can Fire Simultaneously

The system prompt is assembled by **appending** blocks:
```
base_prompt
+ governance_instructions
+ learned_profile
+ cos_system_injection (massive — situation, health, tasks, intelligence)
+ executive_arbitration OR universal_arbitration
+ greeting_injection (forces fresh start)
+ check-in state injection (tasks, calendar, meds)
+ semantic memory
+ data_state_snapshot
+ correction_context
```

If a greeting injection says "FRESH START, don't reference old topics" but the CoS injection contains relevant conversation themes, the LLM must arbitrate between contradictory instructions in the prompt. The most recent/prominent instruction tends to win — and the greeting injection is appended AFTER the CoS context.

---

## 5. Data Confidence Handling (or Lack Thereof)

### Where Data Confidence EXISTS

| Component | Confidence Mechanism | Applied To |
|-----------|---------------------|------------|
| **Operating Profile** | `_confidence_qualifier()` with gates (0.40/0.60/0.80) | Productive windows, deferral patterns, momentum phase |
| **Intelligence Predictions** | `confidence_score` field (0.0-1.0) | Active predictions only |
| **Intelligence Insights** | `confidence_score` field | Logged but not gated |
| **Body Composition** | `phase_confidence`, `INSUFFICIENT_DATA` labels | Fat loss phase, plateau detection |
| **Trajectory Signals** | `INSUFFICIENT SIGNAL` placeholders | Renegotiation, tier1 skips, drift |
| **Pantry Scan** | `overall_pantry_confidence`, drift calculation | Pantry item freshness only |
| **Health Baseline** | `baseline_ready` boolean | Health score calculation |

### Where Data Confidence is MISSING

| Data Domain | What LLM Sees | What's Missing |
|-------------|---------------|----------------|
| **Nutrition averages** | `protein_avg_7d: 85g` | "Based on 2 of 7 days logged" |
| **Sleep averages** | `sleep_avg_7d: 7.2h` | "Based on 3 nights of data" |
| **Weight trend** | `weight_trend: declining` | "Based on 4 entries over 2 weeks" |
| **Steps average** | `steps_avg_7d: 8500` | "Based on HealthKit — all 7 days" vs "manual — 2 days" |
| **Glucose average** | `glucose_avg_7d: 105` | "Based on 1 reading" |
| **Workout count** | `workout_count_7d: 3` | This IS a count, but no context of target |
| **Heart rate** | `heart_rate_avg_7d: 72` | "Based on continuous monitoring" vs "1 manual entry" |

### The Fundamental Gap

The system has **binary data awareness** (Data State Snapshot shows 0 or non-zero totals) but **no graduated data confidence**. There is no concept of:

- **Logging frequency**: "3 of 7 days this week"
- **Data recency**: "Last nutrition log was 4 days ago"
- **Sample adequacy**: "Insufficient data for reliable trend" (exists for body comp, NOT for raw averages)
- **Source quality**: HealthKit continuous monitoring vs manual single entry

The system prompt's "SPARSE DATA BEHAVIOR" section (cos_context.py:2464-2478) instructs the LLM on what to do when data is MISSING (zero records). But it provides no guidance for SPARSE data (some records, but not enough for confident analysis).

The `_confidence_qualifier()` function (cos_context.py:2189-2203) demonstrates the pattern that SHOULD exist everywhere:
```python
def _confidence_qualifier(confidence):
    if confidence >= 0.80:
        return "Your data consistently shows"
    elif confidence >= 0.60:
        return "It looks like"
    else:
        return "Based on limited data"
```

But this function is ONLY used for the Personal Operating Profile, not for health metrics.

---

## 6. Engine Integration Analysis

### Engine Inventory and Data Flow

| Engine | Files | Computes | Consumed By LLM? | Notes |
|--------|-------|----------|-------------------|-------|
| **SAE** (State Aggregation) | `apps/core/ai_state/state_engine.py`, `state_builder.py` | Pre-computed user state per domain | **YES** — via health builder, meals builder, etc. | Primary truth layer |
| **PIE** (Post-Interaction) | `apps/core/ai_insights/` | Insights, event triggers | **YES** — via `_build_intelligence_signals` | `confidence_score` included |
| **PRIE** (Predictive) | `apps/core/ai_insights/predictions/` | Predictions | **YES** — via intelligence builder | `confidence_score` included |
| **PGE** (Proactive Guidance) | `apps/core/ai_guidance/` | Guidance items | **YES** — via intelligence builder | |
| **SAME** (Semantic Memory) | `apps/ai/memory_service.py` | Embedding-based memory retrieval | **YES** — injected into prompt | Similarity threshold 0.35 |
| **CDCE** (Correlation Detection) | `apps/health/services/correlation_service.py` | Cross-domain correlations | **YES** — via health intelligence | |
| **UAL** (Universal Arbitration) | `apps/core/ai_arbitration/` | Dominant scenario, executive narrative | **YES** — narrative injection | Can be overridden by EAE |
| **EAE** (Executive Arbitration) | `apps/core/ai_eae/` | Budgeted intelligence briefing | **YES** — when enabled | Feature-flagged, supersedes UAL |

### Engine Output → Prompt Injection Trace

```
SAE state_engine.get_module_state()
  → _build_health_and_vitals()      → cos_context['health_signals']
  → _build_meals_context()           → cos_context['meals_context']
  → _build_faith_context()           → cos_context['faith_context']
  ... (all domain builders)

PIE insights
  → _build_intelligence_signals()    → cos_context['recent_insights']
  → format_cos_system_injection()    → system_prompt (PROACTIVE INTELLIGENCE)

PRIE predictions
  → _build_intelligence_signals()    → cos_context['active_predictions']
  → format_cos_system_injection()    → system_prompt (with confidence labels)

Health Intelligence Engine
  → build_cos_health_intelligence()  → cos_context['health_intelligence']
  → format_cos_system_injection()    → system_prompt (HEALTH INTELLIGENCE)

Operating Profile
  → _build_operating_profile()       → cos_context['operating_profile']
  → _format_operating_profile_injection() → system_prompt (with confidence qualifiers)

Trajectory Signals
  → _build_trajectory_signals()      → cos_context['trajectory_signals']
  → system_prompt (with INSUFFICIENT SIGNAL flags)
```

### Engines That Compute But May Not Reach the LLM

1. **PIE events**: Events are fired and stored, but only the *recent* insights are injected. Historical events are not surfaced.
2. **PGE guidance**: Guidance items are generated but their surfacing depends on the UAL/EAE arbitration layer. If neither fires (e.g., both fail silently), guidance items sit unused.
3. **CDCE correlations**: Computed by `CorrelationService.compute()` but only top 2 are injected (cos_context.py:519). The rest are discarded.

---

## 7. Root Causes

### Issue 1: Beth Makes Strong Recommendations Based on Incomplete Data

**Root Cause: No data coverage/frequency metadata in the context pipeline.**

**Evidence chain:**
1. `_build_health_and_vitals()` (cos_context.py:273) reads SAE state values like `sleep_avg_7d`, `protein_avg_7d`, etc.
2. These are averages computed by the health rollup — but the rollup computes averages from WHATEVER data exists, even 1 data point.
3. The average is injected into the system prompt without any sample size or coverage indicator.
4. The "SPARSE DATA BEHAVIOR" prompt block (cos_context.py:2464) addresses MISSING data (zero records) but NOT sparse data.
5. The Data State Snapshot (cos_context.py:1961) shows lifetime totals, not weekly frequency.
6. The LLM sees `protein_avg_7d: 85g` and treats it as a reliable 7-day metric, when it might be based on 2 days.
7. The `_confidence_qualifier()` pattern EXISTS in the codebase (for Operating Profile) but was never applied to health metrics.

**Contributing factors:**
- `baseline_ready` gates the health score but not raw averages — sparse averages still appear in the prompt
- `nutrition_logged` is a per-day boolean but never aggregated into a weekly coverage metric
- Protein has `consistency_pct` but other nutrients/metrics have nothing equivalent

### Issue 2: Beth Generates Generic Check-ins Instead of Contextual Ones

**Root Cause: Multiple — streaming fast path cache misses, prompt injection conflicts, and greeting-forced resets.**

**Evidence chain:**

**Path A — Cache miss:**
1. Streaming path calls `_build_fast_context()` (line 5533)
2. This is CACHE-ONLY — it never rebuilds CoS context (line 5586-5612)
3. If no cache exists: `FAST_CTX_NO_COS_CACHE` → NO operational data in the prompt
4. The LLM has base prompt + governance + profile but NO health data, NO tasks, NO schedule
5. With no data, the LLM falls back to generic responses

**Path B — Greeting forces fresh start:**
1. User sends "good morning" after 4+ hour gap
2. Executive briefing fires (line 4139)
3. FRESH SESSION injection appended: "Do NOT reference or continue topics from previous conversations" (line 4147)
4. Even though CoS context contains rich data, the LLM is told to ignore history and "focus on priorities, schedule, and what needs attention RIGHT NOW"
5. If the schedule is light, the response becomes "Let's focus on what's most important today"

**Path C — Competing injections:**
1. Multiple prompt sections append to `system_prompt` sequentially
2. CoS injection may contain rich intelligence signals
3. But if UAL/EAE both fail (silent except), no narrative injection happens
4. The LLM sees raw data but no curated narrative → defaults to generic framing

### Issue 3: Beth Drops Active Conversation Topic and Switches to Generic Prompts

**Root Cause: Overly broad CHECKIN_PATTERNS matching causes aggressive history dropping.**

**Evidence chain:**
1. `CHECKIN_PATTERNS` (line 54-109) contains 56 patterns, many of which are **context-independent** phrases:
   - `"where should i start"` — matches ANY conversation
   - `"what matters most"` — matches reflective/spiritual conversations
   - `"what should i focus on"` — matches ANY advisory question
   - `"where am i at"` — matches progress questions in any domain
   - `"how am i doing"` — matches self-assessment in any context
   - `"what would improve my life"` — existential/spiritual question

2. When ANY of these match (substring check, no word boundary), `_generate_response()` executes:
   ```python
   history = conversation.messages.none()  # ALL history dropped
   ```

3. Task/schedule state data is injected in its place (line 4248+)
4. The LLM now sees: zero conversation context + task/schedule data
5. Result: "You have X tasks today. What should we focus on?"

**Aggravating factors:**
- The matching is `any(phrase in message_lower for phrase in CHECKIN_PATTERNS)` — **substring matching, no word boundaries**
- The phrase `"focus on"` appears in `is_asking_about_tasks` (line 4192) — almost any message containing "focus" triggers the check-in path
- There's no check for **conversation state** before dropping history. The system doesn't consider whether the user is mid-conversation.
- The streaming path only loads 20 messages (vs 40 in full path) — halving the context window even in the non-check-in case

---

## 8. Architectural Recommendations (High-Level)

### For Issue 1: Data Confidence

1. **Add coverage metadata to SAE state**: Each metric should include `{value, sample_days_7d, last_logged, source}` rather than just the raw number.
2. **Build a `_data_coverage_block()` in cos_context.py**: Similar to `_build_data_state_snapshot()` but showing weekly logging frequency per domain.
3. **Extend the confidence qualifier pattern**: Apply `_confidence_qualifier()` to health metrics in `format_cos_system_injection()`, scaling language by coverage.
4. **Add a "SPARSE DATA" prompt section**: Between "MISSING" (zero records) and "SUFFICIENT" (7/7 days), define behavior for 1-3 day coverage.

### For Issue 2: Generic Check-ins

1. **Eliminate the cache-only constraint on the fast path**: When no cache exists, do a lightweight partial build rather than injecting nothing.
2. **Soften the FRESH SESSION greeting injection**: Instead of "Do NOT reference previous conversations," use "Focus on current day, but reference recent threads if the user continues them."
3. **Add a minimum-context gate**: If the assembled prompt contains less than N bytes of operational data, flag it and ensure at least the Data State Snapshot is included.

### For Issue 3: Topic Dropping

1. **Add conversation-state awareness to check-in detection**: If the conversation has 3+ messages in the last 10 minutes, treat it as "mid-conversation" and do NOT drop history.
2. **Narrow CHECKIN_PATTERNS**: Remove context-independent phrases like "focus on", "what matters most", "where should i start". These should only trigger check-in behavior as standalone messages, not within ongoing conversations.
3. **Add word-boundary matching**: Use regex `\b` boundaries or require phrases to be near the START of the message rather than anywhere in it.
4. **Implement a topic continuity signal**: Before dropping history, check if the last 3 messages share a semantic domain (faith, health, etc.) and preserve history if they do.
5. **Equalize history depth**: The streaming fast path (20 messages) should match the full path (40 messages) to prevent context loss.

---

*End of diagnostic report. No code was modified during this investigation.*
