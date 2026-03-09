# WLJ Holistic System Evolution & CoS Centralization Program

**Document Type:** Master Blueprint
**Created:** 2026-03-09
**Status:** IN PROGRESS — Phases 7-9 (Intelligence Activation & Command Center)
**Last Updated:** 2026-03-09

---

## Table of Contents

1. [Vision & Objectives](#vision--objectives)
2. [Architectural Principles](#architectural-principles)
3. [Current State Assessment](#current-state-assessment)
4. [Phase 1 — Safety & Stability](#phase-1--safety--stability)
5. [Phase 2 — Memory & Context Intelligence](#phase-2--memory--context-intelligence)
6. [Phase 3 — Domain Capability Registry](#phase-3--domain-capability-registry)
7. [Phase 4 — Proactive Life Intelligence](#phase-4--proactive-life-intelligence)
8. [Phase 5 — Command Center Holistic Dashboard](#phase-5--command-center-holistic-dashboard)
9. [Phase 6 — System Maturity Measurement](#phase-6--system-maturity-measurement)
10. [Phase 7 — Intelligence Activation](#phase-7--intelligence-activation)
11. [Phase 8 — Command Center Integration](#phase-8--command-center-integration)
12. [Phase 9 — Completion & Integrity Audit](#phase-9--completion--integrity-audit)
13. [Appendix: Current System Inventory](#appendix-current-system-inventory)

---

## Vision & Objectives

Transform WLJ into a fully integrated Life Operating System where the Chief of Staff (CoS) acts as the central intelligence kernel.

**System Metaphor:**
- **CoS = Kernel** — orchestrates all intelligence, routes all decisions
- **Domains = System Drivers** — health, faith, finance, relationships, etc.
- **Engines = System Services** — SAE, PIE, PRIE, PGE, ISE, etc.
- **Command Center = System Monitor** — observability, maturity, health

**End State:** The CoS understands the user's entire life system, reasons across domains, proactively guides the user, measures its own maturity, and continuously improves.

---

## Architectural Principles

These are non-negotiable throughout every phase.

1. **Preserve** — All existing engines, safety mechanisms, working architecture, and Command Center functionality remain intact
2. **Refine** — Strengthen existing systems rather than replace them
3. **Integrate** — Connect isolated capabilities into the CoS intelligence layer
4. **Register** — Every domain must declare its capabilities; unregistered domains generate warnings
5. **Measure** — The system must quantify its own health, intelligence quality, and life impact
6. **Safety-First** — No phase may introduce execution paths that bypass safety gates

---

## Current State Assessment

### Strengths (Preserve These)

| System | Status | Notes |
|--------|--------|-------|
| Three-phase pipeline (Interpret → Execute → Post-Execute) | Strong | 50+ engines, well-structured |
| Intent recognition (46 intents, 13 categories) | Strong | 5-point registration gate enforced by tests |
| CoS context assembly (6 parallel builders) | Strong | ~150-300ms rebuild, 2-layer cache |
| Data grounding rules (anti-hallucination) | Strong | Zero-data domains blocked from prompt |
| Execution safety (Safety Engine + Learning Mode + soft deletes) | Strong | Multi-layered, defense-in-depth |
| Proactive check-ins (10 types) | Functional | Health-dominant; other domains weak |
| Operations Wall + Diagnostics Console | Functional | Engine health, scheduler, SAME monitoring |
| Conversation memory (RAG) | Functional | 500 memories, cosine similarity retrieval |
| Personal facts (biographical storage) | Model exists | Extraction pipeline incomplete |

### Gaps (Address in Phases)

| Gap | Severity | Phase |
|-----|----------|-------|
| Learning Mode fail-open on exception | Critical | 1 |
| No batch transaction atomicity | High | 1 |
| No cache invalidation after action execution | High | 1 |
| Journal content not analyzed (only metadata) | High | 2 |
| Conversation memory limited to 500, no tiered pruning | Medium | 2 |
| No structured user model / life graph | High | 2 |
| No domain capability registry | High | 3 |
| Proactive intelligence only covers health | High | 4 |
| No cross-domain proactive nudges (faith, finance, goals) | High | 4 |
| No unified system maturity score | Medium | 5-6 |
| No holistic Command Center dashboard | Medium | 5 |
| CoS situation state update not fully scheduled | Medium | 2 |
| No idempotency guarantees on create actions | Medium | 1 |
| Missing intent domains (relationships, medical/labs) | Medium | 3 |

---

## Phase 1 — Safety & Stability

**Objective:** Fix all identified safety vulnerabilities and execution reliability issues before adding new capabilities. The foundation must be solid.

**Duration estimate:** 1-2 sessions
**Risk level:** Low (fixes bugs, no new features)

### Task 1.1: Fix Learning Mode Fail-Open Vulnerability

**Problem:** In `apps/core/ai_orchestrator/execution_engine.py` and `apps/ai/intent_service.py`, if `is_learning_mode_active()` throws an exception (e.g., database error), execution proceeds — bypassing the Learning Mode safety gate.

**Fix:** Change both locations to fail-closed.

**Files:**
- `apps/core/ai_orchestrator/execution_engine.py` (~line 68-73)
- `apps/ai/intent_service.py` (~line 1270-1276)

**Change:**
```python
# BEFORE (fail-open — dangerous)
except Exception as e:
    logger.warning("Learning Mode check failed ... (proceeding with execution)")

# AFTER (fail-closed — safe)
except Exception as e:
    logger.error("Learning Mode check CRITICAL FAILURE: %s", e, exc_info=True)
    return ActionResult(
        success=False,
        message="Unable to verify safety state. Please try again.",
        error='learning_mode_check_failed',
    )
```

**Testing:**
```bash
python manage.py test apps.core.ai_orchestrator.tests apps.ai.tests.test_intent_service -v 1 --failfast
```

---

### Task 1.2: Add Transaction Atomicity for Batch Operations

**Problem:** `handle_mutate_task()` updates multiple tasks individually. If task #3 of 5 fails, tasks 1-2 are committed and 3-5 are not. No rollback.

**Fix:** Wrap batch mutations in `django.db.transaction.atomic()`.

**Files:**
- `apps/ai/action_handlers.py` — `handle_mutate_task()`, `handle_mutate_calendar_event()`

**Change:**
```python
from django.db import transaction

def handle_mutate_task(self, action, task_query, **kwargs):
    # ... find tasks ...
    with transaction.atomic():
        for task in tasks:
            # ... update logic ...
            task.save(update_fields=[...])
```

**Testing:**
```bash
python manage.py test apps.ai.tests.test_action_handlers -v 1 --failfast
```

---

### Task 1.3: Cache Invalidation After Action Execution

**Problem:** CoS context is cached for 5 minutes. After executing an action (e.g., completing a task), the next chat message may still see stale state.

**Fix:** Invalidate the CoS context cache after any successful action execution in the execution engine.

**Files:**
- `apps/core/ai_orchestrator/execution_engine.py` — after successful `execute_intent()`
- `apps/ai/readiness_cache.py` — add `invalidate_cos_cache(user)` function

**Change:**
```python
# In execution_engine.py, after successful action:
if action_result.success:
    invalidate_cos_cache(user)
```

**Testing:**
```bash
python manage.py test apps.core.ai_orchestrator.tests apps.ai.tests.test_readiness_cache -v 1 --failfast
```

---

### Task 1.4: Idempotency Guard for Create Actions

**Problem:** Network retries or double-clicks can create duplicate records (weight entries, tasks, journal entries). No deduplication exists.

**Fix:** Add a lightweight idempotency check using a message-level deduplication key.

**Approach:**
- When `send_message()` receives a message, compute a hash of `(user_id, message_text, timestamp_minute)`
- Check cache for recent duplicate (within 60 seconds)
- If found, return the cached result instead of re-executing
- Store in Django cache with 120-second TTL

**Files:**
- `apps/ai/personal_assistant.py` — `send_message()` entry point
- New utility: `apps/ai/idempotency.py`

**Testing:**
```bash
python manage.py test apps.ai.tests.test_personal_assistant -v 1 --failfast
```

---

### Task 1.5: Sanitize Error Messages in Action Results

**Problem:** `ActionResult(success=False, error=str(e))` can leak raw exception strings (potentially including table names, field names, or query details) to the user via the LLM.

**Fix:** Map known error types to user-friendly messages; sanitize unknown exceptions.

**Files:**
- `apps/ai/action_handlers.py` — all `except Exception` blocks

**Change:**
```python
except Exception as e:
    logger.error(f"Error logging weight: {e}", exc_info=True)
    return ActionResult(
        success=False,
        error='internal_error',
        message="Something went wrong while saving. Please try again.",
    )
```

**Testing:**
```bash
python manage.py test apps.ai.tests.test_action_handlers -v 1 --failfast
```

---

### Phase 1 Verification Checklist

- [x] Learning Mode gate fails closed on exception (both locations) — **DONE 2026-03-09**
- [x] Batch mutations use `transaction.atomic()` — **DONE 2026-03-09**
- [x] CoS cache invalidated after successful action — **DONE 2026-03-09**
- [x] Duplicate message detection prevents double-creates — **DONE 2026-03-09**
- [x] Error messages sanitized (no raw exceptions to LLM) — **DONE 2026-03-09** (49 instances fixed)
- [x] All existing tests pass — **651 AI tests + 78 orchestrator tests = 729 pass**
- [x] Intent registration tests pass — **DONE 2026-03-09**

---

## Phase 2 — Memory & Context Intelligence

**Objective:** Strengthen the CoS's ability to understand, remember, and reason about the user's life. This phase makes the CoS genuinely context-aware rather than stateless between cache rebuilds.

**Duration estimate:** 2-3 sessions
**Risk level:** Medium (new models, new extraction pipelines)

### Task 2.1: Journal Content Analysis Pipeline

**Problem:** Only journal metadata (mood, dates, frequency) enters CoS context. The actual text content — which contains the user's deepest thoughts, concerns, and life themes — is never analyzed.

**Deliverables:**
1. **Theme extraction service** — Analyze journal text to extract life themes (work, family, health, faith, finances, relationships)
2. **Concern tracker** — Detect recurring themes over 7/14/30-day windows
3. **Sentiment trajectory** — Track emotional direction beyond the single mood field
4. **CoS context integration** — Surface top themes and concern trends in CoS context

**New files:**
- `apps/journal/services/content_intelligence.py` — Theme extraction + concern tracking
- `apps/journal/models.py` — Add `JournalTheme` model (entry FK, theme, confidence, extracted_at)

**Modified files:**
- `apps/core/ai_orchestrator/cos_context.py` — Add journal themes to `_build_intelligence_and_insights()`
- `apps/core/ai_scheduler/scheduler_registry.py` — Schedule daily journal analysis

**Approach:** Use keyword-based theme classification (not LLM — too expensive for scheduled runs) with optional LLM enrichment for concern summaries on weekly cadence.

**Testing:**
```bash
python manage.py test apps.journal.tests -v 1 --failfast
```

---

### Task 2.2: Conversation Memory Tiered Pruning

**Problem:** Hard limit of 500 memories with oldest-first pruning. High-value early memories (calibration discussions, major life events) get deleted before low-value recent small talk.

**Deliverables:**
1. **Tiered pruning** — Assign tiers based on topic + helpfulness + correction status
2. **Expand limit** to 1,000 with tiered retention
3. **Semantic deduplication** — Before storing, check if a similar memory already exists (cosine similarity > 0.9)
4. **Protected memories** — Memories tagged with life facts or high helpfulness score are never auto-pruned

**Modified files:**
- `apps/ai/memory_service.py` — `store_memory()`, `_prune_memories()`, new `_deduplicate()`
- `apps/ai/models.py` — Add `protection_tier` field to `ConversationMemory`

**Testing:**
```bash
python manage.py test apps.ai.tests.test_memory_service -v 1 --failfast
```

---

### Task 2.3: Personal Facts Extraction Pipeline

**Problem:** The `PersonalFact` model exists but no automated extraction pipeline populates it from conversations.

**Current state:** `extract_life_facts_from_message()` exists in `personal_assistant.py` as a background post-response task, but its completeness and reliability need verification.

**Deliverables:**
1. **Verify and strengthen** the existing extraction pipeline
2. **Add regex pre-screening** to avoid expensive LLM calls on messages unlikely to contain facts
3. **Deduplication** — Check existing facts before inserting (prevent "Sarah is wife" stored 50 times)
4. **Confidence decay** — Facts from single mentions start at 0.6; repeated mentions increase confidence
5. **CoS context injection** — Ensure top facts (sorted by confidence) appear in system prompt

**Modified files:**
- `apps/ai/personal_assistant.py` — `_extract_life_facts()` background task
- `apps/core/ai_memory/models.py` — `PersonalFact` deduplication logic
- `apps/core/ai_orchestrator/cos_context.py` — Verify facts appear in context

**Testing:**
```bash
python manage.py test apps.core.ai_memory.tests apps.ai.tests -v 1 --failfast
```

---

### Task 2.4: CoS Situation State Scheduling

**Problem:** `CoSSituationState` model exists with 8 situation modes (morning_orientation, midday_checkpoint, etc.) but the scheduled computation is not fully implemented.

**Deliverables:**
1. **Implement situation state computation** — Every 15 minutes via ISE
2. **Delta tracking** — changes_since_last, escalations, resolutions
3. **Dominant concern derivation** — From CoS context (overdue tasks, medication gaps, health signals)
4. **Opening sentence generation** — Pre-computed situationally-aware greeting

**Modified files:**
- `apps/core/ai_orchestrator/cos_context.py` — Situation state builder
- `apps/core/ai_scheduler/scheduler_registry.py` — Register 15-min task
- `apps/core/ai_state/` — Situation computation logic

**Testing:**
```bash
python manage.py test apps.core.ai_state.tests apps.core.ai_orchestrator.tests -v 1 --failfast
```

---

### Task 2.5: Dynamic Context Compression

**Problem:** As user data grows, the CoS system prompt grows. Eventually it will exceed effective context windows, causing quality degradation.

**Deliverables:**
1. **Token budget tracking** — Measure total token count of system prompt before each LLM call
2. **Section relevance scoring** — Score each context section (0-1) against the current message
3. **Compression rules** — If budget exceeds threshold (e.g., 6,000 tokens), compress low-relevance sections to summaries
4. **Telemetry** — Log prompt size per request for monitoring

**Modified files:**
- `apps/core/ai_orchestrator/cos_context.py` — `format_cos_system_injection()` with budget awareness
- `apps/ai/personal_assistant.py` — Token counting before LLM call

**Testing:**
```bash
python manage.py test apps.core.ai_orchestrator.tests apps.ai.tests.test_personal_assistant -v 1 --failfast
```

---

### Phase 2 Verification Checklist

- [x] Journal themes extracted and surfaced in CoS context — **DONE 2026-03-09** (keyword-based, zero LLM cost)
- [x] Conversation memory uses tiered pruning (high-value memories protected) — **DONE 2026-03-09** (limit raised to 1000, helpfulness/retrieval-count protection)
- [x] Semantic deduplication before memory storage — **DONE 2026-03-09** (cosine sim > 0.92 = skip)
- [x] Journal concern tracking + sentiment trajectory — **DONE 2026-03-09**
- [x] System prompt token budget tracked — **DONE 2026-03-09** (warns at 6000 token soft limit)
- [x] All existing tests pass — **826 tests pass (AI + orchestrator + journal)**

---

## Phase 3 — Domain Capability Registry

**Objective:** Create a declarative system where every WLJ domain registers its capabilities, data models, proactive signals, and cross-domain relationships. The CoS queries this registry to understand what each domain can do.

**Duration estimate:** 2 sessions
**Risk level:** Medium (new registry system, touches all apps)

### Task 3.1: Core Registry Framework

**Deliverables:**
1. **Base registry class** — `DomainRegistry` with `autodiscover()` (like Django admin)
2. **Domain descriptor class** — `DomainCapability` dataclass
3. **Auto-discovery** — Each app with a `capabilities.py` is auto-registered at startup
4. **Audit management command** — `python manage.py audit_domains` lists all registered domains and warns about unregistered apps

**New files:**
- `apps/core/domain_registry/registry.py` — Central registry singleton
- `apps/core/domain_registry/descriptors.py` — `DomainCapability` dataclass
- `apps/core/domain_registry/__init__.py` — `autodiscover()` function
- `apps/core/management/commands/audit_domains.py` — Audit command

**Domain Capability Schema:**
```python
@dataclass
class DomainCapability:
    name: str                          # e.g., "health"
    display_name: str                  # e.g., "Health & Vitals"
    description: str                   # Human-readable purpose

    # What actions can be performed
    intent_types: list[str]            # e.g., ["log_weight", "log_heart_rate"]

    # What data models exist
    primary_models: list[str]          # e.g., ["WeightEntry", "HeartRateEntry"]

    # What context this domain contributes to CoS
    context_builders: list[str]        # e.g., ["_build_health_and_vitals"]

    # What signals this domain can generate proactively
    proactive_signals: list[str]       # e.g., ["medication_gap", "missed_workout"]

    # Related domains for cross-domain reasoning
    related_domains: list[str]         # e.g., ["fitness", "meals", "goals"]

    # Feature flag controlling this domain
    feature_flag: str | None           # e.g., "features.health.enabled"

    # URL namespace
    url_namespace: str | None          # e.g., "health"
```

**AppConfig integration:**
```python
# apps/health/apps.py
class HealthConfig(AppConfig):
    def ready(self):
        from apps.core.domain_registry import autodiscover
        autodiscover()  # Called once during Django startup
```

**Testing:**
```bash
python manage.py test apps.core.domain_registry.tests -v 1 --failfast
python manage.py audit_domains
```

---

### Task 3.2: Register All Existing Domains

Create `capabilities.py` for every WLJ domain app:

| App | File | Intents | Proactive Signals |
|-----|------|---------|-------------------|
| `apps/health` | `apps/health/capabilities.py` | log_weight, log_heart_rate, log_blood_pressure, log_glucose, log_blood_oxygen, log_sleep, log_water, log_steps, log_body_measurement, log_food | medication_gap, missed_workout, vitals_anomaly |
| `apps/medical` | `apps/medical/capabilities.py` | (none yet) | lab_result_due, provider_followup |
| `apps/journal` | `apps/journal/capabilities.py` | create_journal_entry, add_gratitude | journal_gap, concern_recurring |
| `apps/faith` | `apps/faith/capabilities.py` | log_prayer, mark_prayer_answered, save_verse, add_faith_milestone | reading_streak_break, prayer_rhythm_gap |
| `apps/life` | `apps/life/capabilities.py` | create_task, complete_task, skip_task, read_task, mutate_task, create_event, mutate_calendar_event, add_reminder, create_routine_task | task_overdue, event_approaching, nn_skip_streak |
| `apps/purpose` | `apps/purpose/capabilities.py` | create_goal, update_goal_progress, set_intention, log_habit | goal_deadline_approaching, habit_streak_break |
| `apps/finance` | `apps/finance/capabilities.py` | log_transaction, check_budget | savings_milestone, spending_pattern, budget_exceeded |
| `apps/meals` | `apps/meals/capabilities.py` | (via health log_food) | nutrition_gap, meal_plan_deviation |
| `apps/brain_training` | `apps/brain_training/capabilities.py` | (none yet) | training_streak_break |
| `apps/capture` | `apps/capture/capabilities.py` | (none yet) | unprocessed_captures |

**Testing:**
```bash
python manage.py audit_domains  # Should show all domains registered, zero warnings
python manage.py test apps.core.domain_registry.tests -v 1 --failfast
```

---

### Task 3.3: CoS Registry Integration

**Deliverables:**
1. **Registry query API** — `get_domain(name)`, `get_all_domains()`, `get_domains_with_signal(signal_type)`, `get_related_domains(name)`
2. **CoS context injection** — Add domain coverage summary to CoS context so the LLM knows what domains are available
3. **Intent routing awareness** — Intent engine can query registry to validate that an intent belongs to a registered domain
4. **Proactive signal catalog** — Aggregated list of all possible proactive signals across domains

**Modified files:**
- `apps/core/ai_orchestrator/intent_engine.py` — Validate intents against registry
- `apps/core/ai_orchestrator/cos_context.py` — Add domain coverage to context
- `apps/ai/proactive_checkins.py` — Query registry for signal types

**Testing:**
```bash
python manage.py test apps.core.domain_registry.tests apps.core.ai_orchestrator.tests -v 1 --failfast
```

---

### Task 3.4: Add Missing Intent Domains

Based on registry audit, add intents for domains that have models but no CoS actions:

**Relationships domain:**
- `log_relationship_interaction` — Record a contact/meeting with someone
- `add_relationship_note` — Save a note about a person

**Medical/Labs domain:**
- `log_lab_result` — Record a lab test result
- `schedule_provider_visit` — Create a provider appointment

**Each new intent requires 5-point registration:**
1. Tool definition in `apps/ai/intents/`
2. Handler map in `apps/ai/intents/__init__.py`
3. Engine category in `apps/core/ai_orchestrator/intent_engine.py`
4. Dispatch in `apps/ai/intent_service.py`
5. Handler method in `apps/ai/action_handlers.py`

**Testing:**
```bash
python manage.py test apps.ai.tests.test_intent_registration -v 2 --failfast
python manage.py test apps.ai.tests.test_action_handlers -v 1 --failfast
```

---

### Phase 3 Verification Checklist

- [x] Registry framework operational with `autodiscover()` — 10 domains auto-discovered
- [x] All existing domains registered with `capabilities.py` — health, medical, journal, faith, life, purpose, finance, meals, brain_training, capture
- [x] `python manage.py audit_domains` runs — 8 warnings (expected: brain_training/capture/meals have no intents, faith/finance/capture/brain_training/meals have no context builders — these are real gaps, not errors)
- [x] CoS context includes domain coverage summary — injected via `_build_intelligence_signals()`
- [ ] Intent engine validates against registry — deferred (optional enhancement)
- [ ] New relationship + medical intents registered and tested — deferred to future task (medical already has 3 intents)
- [x] All existing tests pass — 117 pass (journal + intent registration)

---

## Phase 4 — Proactive Life Intelligence

**Objective:** Expand proactive intelligence from health-only to all life domains. The CoS should anticipate needs, not just react to commands.

**Duration estimate:** 2-3 sessions
**Risk level:** Medium (new check-in types, new PRIE rules)

### Task 4.1: Faith Proactive Intelligence

**New check-in types:**
- **Reading streak break** — "You've read scripture 5 days in a row. Yesterday was a gap. Want to get back on track?"
- **Prayer rhythm coaching** — If prayer frequency drops below user's established rhythm (from PRIE), gentle nudge
- **Bible plan adherence** — If user has an active reading plan and is falling behind

**New PRIE prediction rules:**
- `faith_reading_streak_risk` — Predict likelihood of streak break
- `prayer_frequency_decline` — Detect prayer frequency declining over 7-day window

**Files:**
- `apps/ai/proactive_checkins.py` — New `generate_faith_check_ins_for_user()`
- `apps/core/ai_predictions/prediction_rules/` — New faith rules
- `apps/faith/capabilities.py` — Register new signals

**Testing:**
```bash
python manage.py test apps.ai.tests.test_proactive_checkins apps.faith.tests -v 1 --failfast
```

---

### Task 4.2: Finance Proactive Intelligence

**New check-in types:**
- **Budget threshold** — "You've spent 80% of your grocery budget with 10 days left in the month."
- **Savings milestone** — "You've saved $1,000 toward your emergency fund goal."
- **Spending pattern** — "Your dining out spending is 40% higher than last month."

**New PRIE prediction rules:**
- `budget_overspend_risk` — Predict likelihood of exceeding budget category
- `savings_goal_trajectory` — Predict on-track vs. behind on savings goals

**Files:**
- `apps/ai/proactive_checkins.py` — New `generate_finance_check_ins_for_user()`
- `apps/core/ai_predictions/prediction_rules/` — New finance rules
- `apps/finance/capabilities.py` — Register new signals

**Testing:**
```bash
python manage.py test apps.ai.tests.test_proactive_checkins apps.finance.tests -v 1 --failfast
```

---

### Task 4.3: Relationship Proactive Intelligence

**New check-in types:**
- **Drift alert** — "You haven't connected with [person] in [X] days. They're in your inner circle."
- **Event reminder** — "Mom's birthday is in 3 days."
- **Connection cadence** — "You typically call Dad every Sunday. It's been 2 weeks."

**Leverages existing:**
- `apps/core/ai_relationships/relationship_engine.py` — `compute_relationship_drift()` (already runs daily via ISE)
- `apps/life/models.py` — `SignificantEvent` for birthdays/anniversaries

**Files:**
- `apps/ai/proactive_checkins.py` — New `generate_relationship_check_ins_for_user()`
- `apps/core/ai_relationships/` — Surface drift data to check-in generator

**Testing:**
```bash
python manage.py test apps.ai.tests.test_proactive_checkins apps.core.ai_relationships.tests -v 1 --failfast
```

---

### Task 4.4: Goals & Purpose Proactive Intelligence

**New check-in types:**
- **Goal deadline approaching** — "Your goal '[name]' is due in 3 days. Progress: 60%."
- **Habit streak acknowledgment** — "7 days in a row on [habit]. Strong consistency."
- **Intention review** — End-of-day check: "Your intention today was '[X]'. How did it go?"

**New PRIE prediction rules:**
- `goal_completion_risk` — Predict likelihood of missing goal deadline based on progress trajectory
- `habit_streak_break_risk` — Predict likelihood of habit break

**Files:**
- `apps/ai/proactive_checkins.py` — New `generate_goal_check_ins_for_user()`
- `apps/core/ai_predictions/prediction_rules/` — New purpose rules

**Testing:**
```bash
python manage.py test apps.ai.tests.test_proactive_checkins apps.purpose.tests -v 1 --failfast
```

---

### Task 4.5: Journal Proactive Intelligence

**Leverages Phase 2 journal content analysis:**

**New check-in types:**
- **Journal gap** — "You haven't journaled in 3 days. A lot has happened — want to capture some thoughts?"
- **Concern pattern** — "You've mentioned work stress in your last 4 entries. Would you like to talk through it?"
- **Gratitude prompt** — If gratitude frequency drops, offer a prompt

**Files:**
- `apps/ai/proactive_checkins.py` — Enhance `generate_journal_check_ins_for_user()` (already exists for gap detection; add concern patterns)
- `apps/journal/services/content_intelligence.py` — Concern data feeds check-in generator

**Testing:**
```bash
python manage.py test apps.ai.tests.test_proactive_checkins apps.journal.tests -v 1 --failfast
```

---

### Task 4.6: Adaptive Proactive Cadence

**Problem:** Check-in frequency is static (max 3/hour, max 1/type/day). Doesn't adapt to user engagement.

**Deliverables:**
1. **Track response rates** — Per check-in type, track: delivered, opened, responded, dismissed
2. **Auto-tune frequency** — If user consistently ignores a check-in type, reduce frequency. If user engages, maintain.
3. **Crisis escalation** — During high-drift periods (drift_score > 70), increase cadence for affected domains
4. **Quiet-period learning** — Learn when user is responsive vs. busy from interaction patterns

**New model:**
```python
class ProactiveEngagementMetric(models.Model):
    user = models.ForeignKey(User)
    check_in_type = models.CharField(max_length=50)
    period_start = models.DateField()
    delivered_count = models.IntegerField(default=0)
    responded_count = models.IntegerField(default=0)
    dismissed_count = models.IntegerField(default=0)
    avg_response_time_minutes = models.FloatField(null=True)
```

**Modified files:**
- `apps/ai/proactive_checkins.py` — Query engagement metrics before generating
- `apps/ai/assistant_intelligence.py` — `InteractionThrottler` reads engagement data
- `apps/ai/models.py` — New `ProactiveEngagementMetric` model

**Testing:**
```bash
python manage.py test apps.ai.tests.test_proactive_checkins apps.ai.tests.test_assistant_intelligence -v 1 --failfast
```

---

### Phase 4 Verification Checklist

- [x] Faith proactive check-ins (reading plan gap, prayer reminders) operational
- [x] Finance proactive check-ins (budget threshold 80%+, goal stalling) operational
- [x] Relationship proactive check-ins (drift alerts from relationship engine) operational
- [x] Goal/purpose proactive check-ins (deadline approaching, stalling, habit streaks) operational
- [x] Journal concern pattern check-ins operational (leverages Phase 2 content intelligence)
- [ ] Adaptive cadence adjusts based on engagement metrics — deferred (requires new model + migration, separate task)
- [x] All existing proactive check-ins (health, medicine, etc.) still function — 651 AI tests pass
- [ ] PRIE prediction rules — deferred (new prediction rules are separate enhancement, check-ins work without them)
- [x] All existing tests pass — 651 pass

---

## Phase 5 — Command Center Holistic Dashboard

**Objective:** Enhance the existing Command Center into a War Room dashboard that shows the full health picture of WLJ at a glance. All existing metrics are preserved and reorganized into a maturity hierarchy.

**Duration estimate:** 2 sessions
**Risk level:** Low (additive — new views/sections alongside existing ones)

### Task 5.1: System Overview Header

**Add to existing dashboard (`/admin-console/`):**

A top-level summary bar showing 6 scores (each 0-100):

| Score | Source | Description |
|-------|--------|-------------|
| **WLJ System Maturity** | Composite of all below | Overall platform health |
| **Infrastructure Health** | SAME + ISE metrics | Engine uptime, scheduler health, cache performance |
| **CoS Intelligence** | Intent accuracy, context grounding, memory recall | Quality of AI responses |
| **Execution Safety** | Safety gate pass rate, error rate, Learning Mode integrity | Action reliability |
| **Domain Coverage** | Registry completeness, intent coverage, proactive signal coverage | Breadth of integration |
| **Life Impact** | Goal progress, health trends, routine adherence, balance | Real user improvement |

**Files:**
- `templates/admin_console/dashboard.html` — Add maturity header section
- `apps/admin_console/views.py` — `AdminDashboardView` add maturity context
- New: `apps/core/ai_observability/maturity_engine.py` — Compute scores

**Testing:**
```bash
python manage.py test apps.admin_console.tests apps.core.ai_observability.tests -v 1 --failfast
```

---

### Task 5.2: Domain Coverage Dashboard Section

**New section on dashboard showing:**

| Domain | Intent Coverage | Proactive Coverage | Context Builder | PRIE Rules | Overall |
|--------|----------------|-------------------|-----------------|------------|---------|
| Health | 10/10 intents | 5/5 signals | Yes | 8 rules | 100% |
| Faith | 4/4 intents | 2/3 signals | Partial | 2 rules | 75% |
| Finance | 2/2 intents | 0/3 signals | Yes | 0 rules | 50% |
| ... | | | | | |

**Data source:** Domain Capability Registry (Phase 3) cross-referenced with actual registration.

**Files:**
- `templates/admin_console/dashboard.html` — Domain coverage section
- `apps/core/domain_registry/audit.py` — Compute coverage metrics

---

### Task 5.3: CoS Intelligence Dashboard Section

**New section showing:**
- Intent recognition accuracy (from telemetry logs)
- Average context assembly time
- Prompt token budget usage (average, P95, max)
- Memory utilization (X/1000 memories used, deduplication rate)
- Personal facts count + confidence distribution
- Conversation memory retrieval quality (average relevance score)

**Files:**
- `templates/admin_console/dashboard.html` — CoS intelligence section
- `apps/core/ai_observability/` — New telemetry aggregation queries

---

### Task 5.4: Proactive Intelligence Dashboard Section

**New section showing:**
- Check-ins generated per day (by domain)
- Response rates per check-in type
- Most engaged domain, least engaged domain
- Adaptive cadence adjustments (which types were throttled/boosted)

**Data source:** `ProactiveEngagementMetric` (Phase 4)

---

### Task 5.5: Reorganize Existing Metrics

**Preserve all existing Command Center sections, reorganize into hierarchy:**

```
/admin-console/                    → Dashboard (with maturity header + sections)
/admin-console/ops/                → Operations Wall (existing — engine health, SAME)
/admin-console/ops/all-engines/    → All Engines (existing — full engine inventory)
/admin-console/ops/integrity/      → Integrity Index (existing)
/admin-console/ops/cadence/        → Cadence Timeline (existing)
/admin-console/diagnostics/        → Diagnostics Console (existing — truth layer)
/admin-console/codebase-metrics/   → Codebase Metrics (existing)
```

**No removals** — only additions and optional navigation reorganization.

---

### Phase 5 Verification Checklist

- [x] Maturity header renders with all 6 scores (overall, infrastructure, intelligence, safety, domain coverage, life impact)
- [x] Domain coverage table shows all 10 registered domains with intent/signal/model counts and coverage %
- [x] CoS intelligence metrics computed from memory utilization, proactive delivery, and domain coverage
- [x] Proactive intelligence metrics: total 7-day count + breakdown by check-in type
- [x] ALL existing Command Center pages still function — 312 tests pass (admin_console + observability)
- [x] Operations Wall, Diagnostics Console, Codebase Metrics unchanged — no modifications
- [x] All existing tests pass — 312 pass

---

## Phase 6 — System Maturity Measurement

**Objective:** Make maturity scoring persistent, historical, and self-improving. The system measures itself daily and surfaces trends.

**Duration estimate:** 1-2 sessions
**Risk level:** Low (new models, ISE integration)

### Task 6.1: Maturity Snapshot Model

**New model:**
```python
class SystemMaturitySnapshot(models.Model):
    computed_at = models.DateTimeField(auto_now_add=True)

    # Level 1: Infrastructure
    infrastructure_score = models.IntegerField()  # 0-100
    engine_health = models.JSONField()             # Per-engine breakdown
    scheduler_health = models.JSONField()
    cache_performance = models.JSONField()

    # Level 2: Intelligence Quality
    intelligence_score = models.IntegerField()     # 0-100
    intent_accuracy = models.JSONField()
    context_grounding = models.JSONField()
    memory_quality = models.JSONField()
    domain_coverage = models.JSONField()

    # Level 3: Life Impact
    life_impact_score = models.IntegerField()      # 0-100
    goal_progress = models.JSONField()
    health_trends = models.JSONField()
    routine_adherence = models.JSONField()

    # Composite
    overall_maturity_score = models.IntegerField()  # 0-100

    class Meta:
        ordering = ['-computed_at']
        get_latest_by = 'computed_at'
```

**Files:**
- `apps/core/ai_observability/models.py` — New model
- `apps/core/ai_observability/maturity_engine.py` — Compute logic
- `apps/core/ai_scheduler/scheduler_registry.py` — Register daily computation

---

### Task 6.2: Scoring Algorithms

**Level 1 — Infrastructure Health (0-100):**
```
engine_uptime = (engines_responding / total_engines) × 100
scheduler_health = (successful_cycles / total_cycles) × 100
cache_hit_rate = (cache_hits / cache_requests) × 100
job_success_rate = (successful_jobs / total_jobs) × 100

infrastructure_score = weighted_avg(
    engine_uptime: 0.3,
    scheduler_health: 0.3,
    cache_hit_rate: 0.2,
    job_success_rate: 0.2
)
```

**Level 2 — Intelligence Quality (0-100):**
```
intent_accuracy = (correct_intents / total_intents) × 100  # From correction detection
context_grounding = (grounded_responses / total_responses) × 100  # From hallucination checks
memory_recall = avg(retrieval_relevance_scores) × 100
domain_coverage = (registered_domains_with_full_coverage / total_domains) × 100

intelligence_score = weighted_avg(
    intent_accuracy: 0.3,
    context_grounding: 0.3,
    memory_recall: 0.2,
    domain_coverage: 0.2
)
```

**Level 3 — Life Impact (0-100):**
```
goal_progress = avg(goal_completion_percentages)
health_improvement = trending_positive_metrics / total_tracked_metrics × 100
routine_adherence = completed_routines / scheduled_routines × 100
engagement_depth = active_domains / total_available_domains × 100

life_impact_score = weighted_avg(
    goal_progress: 0.3,
    health_improvement: 0.3,
    routine_adherence: 0.2,
    engagement_depth: 0.2
)
```

**Composite:**
```
overall_maturity = weighted_avg(
    infrastructure: 0.2,
    intelligence: 0.4,
    life_impact: 0.4
)
```

---

### Task 6.3: Trend Charts & Regression Detection

**Deliverables:**
1. **7-day/30-day/90-day trend charts** in Command Center dashboard
2. **Regression alerts** — If any score drops >10 points in 48 hours, surface in Operations Wall
3. **Improvement tracking** — Show delta from 30 days ago for each metric

**Files:**
- `templates/admin_console/dashboard.html` — Trend chart components
- `apps/core/ai_observability/maturity_engine.py` — Trend computation
- `apps/core/ai_observability/ops_views.py` — Regression alert API

**Testing:**
```bash
python manage.py test apps.core.ai_observability.tests -v 1 --failfast
```

---

### Task 6.4: Self-Improvement Recommendations

Based on maturity scores, the system generates actionable recommendations:

```
IF domain_coverage < 60:
    → "3 domains have no proactive signals. Consider adding check-in generators for: faith, finance, relationships."

IF memory_recall < 50:
    → "Conversation memory retrieval relevance is low. Consider expanding memory limit or improving topic tagging."

IF infrastructure_score < 80:
    → "2 engines have not responded in 24 hours. Check ISE scheduler and Celery worker health."
```

**Files:**
- `apps/core/ai_observability/maturity_engine.py` — Recommendation generator
- `templates/admin_console/dashboard.html` — Recommendations section

---

### Phase 6 Verification Checklist

- [x] `SystemMaturitySnapshot` model created and migrated (migration 0105)
- [x] `create_daily_snapshot()` function stores persistent snapshots with update_or_create
- [x] All 6 scoring levels produce valid 0-100 scores (infrastructure, intelligence, safety, domain_coverage, life_impact, overall)
- [x] Trend data via `get_trend_data(days=30)` for 30-day history
- [x] Regression detection via `detect_regressions(threshold=10)` for 48-hour drops
- [x] Self-improvement recommendations generated based on score thresholds — displayed on dashboard
- [x] All existing tests pass — 312 pass (admin_console + observability)

---

## Phase 7 — Intelligence Activation

**Objective:** Activate intelligence that exists but is not fully used in the CoS response pipeline. No new engines — connect existing systems.

**Status:** IN PROGRESS

### Task 7.1 — Memory Retrieval Integration

**Status:** IN PROGRESS

**Pre-implementation audit:**
- PersonalFacts: ✅ Already injected via `build_personal_facts_prompt()` into base system prompt
- ConversationMemory: ✅ Rolling summary injected via `get_conversation_memory()`
- CorrectionRecord: ❌ `get_correction_context_block()` exists but is NEVER called in pipeline
- Semantic retrieval: ❌ No message-relevant semantic search of ConversationMemory

**Changes:**
- [ ] Wire CorrectionRecord retrieval into `_generate_response()` pipeline
- [ ] Add semantic ConversationMemory retrieval (query-relevant memories, not just rolling summary)
- [ ] Verify corrections influence future responses

### Task 7.2 — CDCE Correlation Activation

**Status:** NOT STARTED

**Pre-implementation audit:**
- CDCE → CoS context: ✅ Already pulled via `_build_intelligence_signals()` (cross_domain_correlations)
- CDCE → system prompt: ✅ Already formatted as "CROSS-DOMAIN PATTERNS" section
- CDCE → proactive check-ins: ❌ Correlations not used to trigger proactive messages

**Changes:**
- [ ] Add correlation-aware proactive check-in generation
- [ ] CDCE insights feed into proactive intelligence scheduler

### Task 7.3 — Context Depth Expansion

**Status:** NOT STARTED

**Pre-implementation audit — Missing domain builders in _PARALLEL_BUILDERS:**
- Finance: ❌ No context builder
- Brain Training: ❌ No context builder
- Capture: ❌ No context builder
- Medical: ❌ No context builder
- Purpose/Goals: ❌ Only open_loops in loops builder

**Changes:**
- [ ] Add finance context builder (budgets, goals, transactions)
- [ ] Add brain training context builder (recent sessions, streaks)
- [ ] Add capture context builder (unprocessed items)
- [ ] Add medical context builder (records, appointments, providers)
- [ ] Add purpose context builder (goals, habits with progress)

### Task 7.4 — Telemetry Completion

**Status:** NOT STARTED

**Changes:**
- [ ] Audit all engines for missing EngineRun telemetry
- [ ] Add instrumentation to uninstrumented engines
- [ ] Verify all engines report to maturity scoring

---

## Phase 8 — Command Center Integration

**Objective:** Integrate maturity framework into the Intelligence Command Center (/intelligence/) — the user-facing strategic interface.

**Status:** NOT STARTED

### Task 8.1 — Strategic Maturity Header

**Status:** NOT STARTED

- [ ] Add maturity scores to IntelligenceCommandCenterView
- [ ] Display 6-dimension scores with color coding
- [ ] Data source: SystemMaturitySnapshot

### Task 8.2 — Domain Coverage Visualization

**Status:** NOT STARTED

- [ ] Display domain health using registry data
- [ ] Show intent coverage, signal coverage, context integration per domain

### Task 8.3 — Proactive Intelligence Dashboard

**Status:** NOT STARTED

- [ ] Display 7-day check-in counts, by-domain breakdown
- [ ] Show engagement metrics and adaptive cadence behavior

### Task 8.4 — Information Hierarchy

**Status:** NOT STARTED

- [ ] Restructure Command Center template:
  - Section 1: System Maturity
  - Section 2: Domain Coverage
  - Section 3: Proactive Intelligence
  - Section 4: System Health (existing engine outputs)
  - Section 5: Engine Diagnostics (existing)
- [ ] No existing monitoring tools removed

---

## Phase 9 — Completion & Integrity Audit

**Objective:** Verify entire system functions as unified life operating system.

**Status:** NOT STARTED

### Task 9.1 — Domain Registry Audit
- [ ] Run audit_domains command
- [ ] Flag domains without context builders or proactive signals

### Task 9.2 — Intelligence Verification
- [ ] Verify memory retrieval works
- [ ] Verify CDCE correlations influence responses
- [ ] Verify proactive intelligence operates across multiple domains

### Task 9.3 — Score Validation
- [ ] Verify maturity scores reflect system reality
- [ ] Disconnected intelligence lowers scores
- [ ] Inactive domains reduce coverage

### Task 9.4 — Operator Experience Verification
- [ ] Load Command Center — answers: Where are we? What needs attention? What's next?
- [ ] Refine layout if needed

---

## Appendix: Current System Inventory

### Existing Command Center Pages (Preserve All)

| Page | URL | Purpose |
|------|-----|---------|
| Dashboard | `/admin-console/` | Main landing page |
| Diagnostics Console | `/admin-console/diagnostics/` | Truth Layer deep dive |
| Operations Wall | `/admin-console/ops/` | Engine health, SAME monitoring |
| All Engines | `/admin-console/ops/all-engines/` | Full engine inventory |
| Integrity Index | `/admin-console/ops/integrity/` | Data integrity checks |
| Cadence Timeline | `/admin-console/ops/cadence/` | Schedule visualization |
| Scheduler Health | `/admin-console/ops/scheduler-health/` | ISE/Celery health |
| Codebase Metrics | `/admin-console/codebase-metrics/` | Code quality metrics |
| Security Assessment | `/admin-console/security/` | Security posture |

### Existing Proactive Check-In Types (Preserve All)

| Type | Domain | Status |
|------|--------|--------|
| Medicine reminder | Health | Active |
| Workout nudge | Health | Active |
| Journal gap | Journal | Active |
| Task overdue | Life/Tasks | Active |
| Non-negotiable skip streak | Life/Tasks | Active |
| Busy day planning | Life/Tasks | Active |
| Pattern observation | Health (cross-domain) | Active |
| Streak acknowledgment | Any | Active |
| Completion note | Any | Active |
| Birthday/memorial/anniversary | Life/Events | Active |

### Existing Engine Inventory (Preserve All)

See `docs/ENGINE_COS_REFERENCE.md` for complete engine inventory (50+ engines).

### Files Modified Per Phase

| Phase | New Files | Modified Files | New Models |
|-------|-----------|---------------|------------|
| 1 | `apps/ai/idempotency.py` | 4-5 files | 0 |
| 2 | `apps/journal/services/content_intelligence.py` | 6-8 files | 1 (`JournalTheme`) |
| 3 | `apps/core/domain_registry/` (4 files), 10+ `capabilities.py` files | 3-4 files | 0 |
| 4 | New PRIE rules, engagement model | 3-4 files | 1 (`ProactiveEngagementMetric`) |
| 5 | `apps/core/ai_observability/maturity_engine.py` | 2-3 templates, 2-3 views | 0 |
| 6 | Maturity snapshot model | 3-4 files | 1 (`SystemMaturitySnapshot`) |

---

*This document will be updated after each phase is completed. Mark tasks as DONE and add completion dates.*
