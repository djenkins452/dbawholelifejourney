# CoS Phase III Execution Plan

**Project:** Whole Life Journey
**Goal:** Transform CoS into a conversational, adaptive, trust-based partner
**Author:** Claude Code (automated engineering plan)
**Created:** 2026-02-18

---

## Table of Contents

1. [Phase 0 — Codebase Audit Results](#phase-0--codebase-audit-results)
2. [Reuse Decisions](#reuse-decisions)
3. [Phase 1 — Adaptive Authority Framework](#phase-1--adaptive-authority-framework)
4. [Phase 2 — Post-Event Reflection Loops](#phase-2--post-event-reflection-loops)
5. [Phase 3 — Relationship & Significance Intelligence](#phase-3--relationship--significance-intelligence)
6. [Migration Plan](#migration-plan)
7. [Risks & Mitigations](#risks--mitigations)

---

## Phase 0 — Codebase Audit Results

### A) CoS Chat Entry Points & Routing

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/ai/views.py` — `AssistantChatView` | POST `/ai/api/chat/` — primary chat endpoint | **Reuse** — all CoS conversation flows through here |
| `apps/ai/views.py` — `AssistantDashboardView` | GET `/ai/` — full chat dashboard page | **Reuse** — assistant UI |
| `apps/ai/personal_assistant.py` — `send_message()` | Core message handler: intent recognition → orchestrator → response | **Reuse** — all new features hook into this flow |
| `apps/ai/personal_assistant.py` — `_generate_response()` | Builds system prompt, injects CoS context, calls OpenAI | **Reuse** — governance layer hooks in here |
| `apps/ai/personal_assistant.py` — `_build_system_prompt()` | Assembles base prompt + coaching style + time + faith + profile | **Extend** — add governance instructions |
| `apps/core/ai_orchestrator/orchestrator.py` | UAIO pipeline: context → time → semantic → enrich → execute | **Reuse** — no modification needed |
| `apps/core/ai_orchestrator/cos_context.py` | `build_cos_context()` + `format_cos_system_injection()` | **Extend** — add governance profile to context |
| `apps/core/ai_orchestrator/execution_engine.py` | Post-execution intelligence chain (SAE → PIE → PRIE) | **Extend** — add reflection queue trigger |

### B) Command Mode / Arrival Experience

| File | What It Does | Reuse? |
|------|-------------|--------|
| `templates/components/cos_command_mode.html` | Primary login: greeting, moves, protections, input, timeline, weekly | **Reuse** — already built in Phase 4 Live Build Loop |
| `templates/dashboard/home.html` | Renders Command Mode primary, dashboard secondary | **Reuse** — no changes needed |
| `apps/dashboard/views.py` — `_get_command_mode()` | Builds command mode context with human language | **Reuse** — working as designed |
| `apps/core/blueprint/human_language.py` | Metric→language translation (sole authority) | **Reuse** — no raw metrics exposed |
| `apps/core/blueprint/weekly_pressure.py` | 7-day pressure forecast engine | **Reuse** — feeds weekly glance |

### C) Calendar / Tasks / Organize

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/life/models.py` — `LifeEvent` | Calendar events (9 types, recurrence, external sync) | **Reuse** — create events from conversation |
| `apps/life/models.py` — `Task` | To-do items (priority, effort, due date, recurring) | **Reuse** — create tasks from conversation |
| `apps/life/models.py` — `SignificantEvent` | Birthdays, anniversaries, memorials with SMS reminders | **Reuse for Phase 3** — relationship milestones |
| `apps/life/models.py` — `GoogleCalendarCredential` | Encrypted OAuth credentials, sync settings | **Reuse** — push events to GCal |
| `apps/life/services/google_calendar.py` | `GoogleCalendarService` + `CalendarSyncService` | **Reuse** — create/update/sync events |
| `apps/ai/action_handlers.py` — `handle_create_event()` | Creates LifeEvent + CoS post-scheduling chain | **Reuse** — already has conflict detection + GCal sync |
| `apps/ai/action_handlers.py` — `handle_create_task()` | Creates Task from conversation | **Reuse** — for reflection action items |
| `apps/core/blueprint/architecture_engine.py` | Daily plan generation + curveball re-optimization | **Reuse** — `handle_curveball()` for schedule changes |
| `apps/core/blueprint/priority_engine.py` | Tier-based conflict resolution | **Reuse** — conflict detection in scheduling |

### D) Journal & Semantic Extraction

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/journal/models.py` — `JournalEntry` | Journal entries with mood, categories, tags, emotions | **Reuse for Phase 3** — extract people mentions |
| `apps/core/ai_semantics/semantic_engine.py` | SUE: `interpret()` → SemanticResult (intent, entities, confidence) | **Reuse** — extract people, activities from text |
| `apps/core/ai_semantics/semantic_parser.py` | Rule-based intent/entity extraction | **Extend for Phase 3** — add people extraction patterns |

### E) Preferences & Persona System

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/users/models.py` — `UserPreferences` | Comprehensive preferences (AI, notifications, modules, persona) | **Extend** — add governance fields |
| `apps/ai/models.py` — `CoachingStyle` | DB-stored persona prompt instructions | **Reuse** — persona drives tone |
| `apps/core/ai_persona/persona_registry.py` | 8 persona profiles with tone templates | **Reuse** — persona rendering |
| `apps/core/ai_persona/persona_profiles.py` | PersonaProfile dataclass | **Reuse** — tone patterns |
| `apps/core/blueprint/models.py` — `PersonalOperatingBlueprint` | Blueprint with `operating_style`, `interruption_tolerance`, `persona_id` | **Extend** — add governance profile fields |

### F) Existing Significant Events

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/life/models.py` — `SignificantEvent` | Birthdays/anniversaries with person_name, recurrence, SMS reminders | **Reuse for Phase 3** — DO NOT create new milestone system |
| `apps/life/views.py` — CRUD views | Full CRUD for significant events | **Reuse** — extend for CoS-initiated creation |

### G) Relationship/Contact/Person Models

| Status | Finding |
|--------|---------|
| **NO Person model exists** | Only `SignificantEvent.person_name` (text field) |
| **NO Contact model exists** | No contact database |
| **NO Relationship model exists** | No relationship tracking |
| **NO Interaction tracking exists** | No interaction signals or cadence |
| **NO Journal people extraction** | SUE does not extract people from journal entries |

**Decision:** Phase 3 will create minimal new models (`Person`, `Relationship`, `InteractionSignal`) in a new `apps/core/ai_relationships/` module, following the engine pattern. `SignificantEvent` will be extended with an optional FK to Person (nullable, backward-compatible).

### H) Intervention Engine

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/core/blueprint/intervention_engine.py` | Escalation levels (0-4), trigger-based, persona-rendered | **Extend** — governance layer wraps this |
| `apps/core/blueprint/assistant_triggers.py` | Deadline, drift, architecture triggers | **Extend** — add reflection triggers |
| `apps/core/blueprint/models.py` — `InterventionLog` | Logs interventions with user response tracking | **Reuse** — track governance decisions |

### I) Intelligence Pipeline

| File | What It Does | Reuse? |
|------|-------------|--------|
| `apps/core/ai_memory/memory_engine.py` | SLCME: resolve context, learned mappings, confidence | **Extend** — store governance preferences |
| `apps/core/ai_memory/models.py` — `LearnedMapping` | Phrase → meaning with confidence scores | **Reuse** — governance preference learning |
| `apps/core/ai_insights/insight_engine.py` | PIE: `run_insights()` with dedupe + confidence | **Reuse** — reflection signals |
| `apps/core/ai_guidance/guidance_engine.py` | PGE: generate ranked guidance items | **Reuse** — relationship suggestions |
| `apps/core/ai_delivery/delivery_engine.py` | DNE: channel routing with throttling + policies | **Reuse** — deliver reflections/suggestions |
| `apps/core/ai_scheduler/scheduler_registry.py` | ISE: 11 registered tasks | **Extend** — add reflection scheduler |

---

## Reuse Decisions

### REUSE (Do NOT rebuild)
- Chat pipeline (`send_message` → orchestrator → action handlers)
- Command Mode template and dashboard integration
- LifeEvent/Task/SignificantEvent models and CRUD
- Google Calendar service and sync
- Architecture engine (plan generation, curveball handling)
- Priority engine (conflict detection)
- Persona system (persona_registry, CoachingStyle)
- Intervention engine (escalation logic)
- SLCME memory engine (preference learning)
- DNE delivery engine (notifications)
- All intelligence engines (PIE, PRIE, PGE, SAE, DBE, WIRE)

### EXTEND (Add fields/methods to existing)
- `PersonalOperatingBlueprint` — add governance profile fields
- `UserPreferences` — add CoS governance toggle fields (5 simple toggles)
- `cos_context.py` — inject governance profile into system prompt
- `_build_system_prompt()` — append governance instructions
- `intervention_engine.py` — governance layer consultation before escalation
- `assistant_triggers.py` — add reflection triggers
- `scheduler_registry.py` — register reflection check task
- `semantic_parser.py` — add people extraction patterns (Phase 3)

### CREATE NEW (justified)
- `apps/core/blueprint/cos_governance.py` — Governance decision layer (new logic, no existing equivalent)
- `apps/core/blueprint/reflection_engine.py` — Post-event reflection queue + question generation (new concept)
- `apps/core/ai_relationships/` — Relationship intelligence module (no existing Person/Relationship models)
- `templates/components/cos_settings.html` — Simple CoS settings page (no existing governance UI)
- Migration files for new model fields

### DO NOT CREATE
- New calendar system (LifeEvent exists)
- New task system (Task exists)
- New assistant brain (PersonalAssistant exists)
- New scheduling logic (handle_create_event + handle_curveball exist)
- New milestone system (SignificantEvent exists)
- New notification system (DNE exists)

---

## Phase 1 — Adaptive Authority Framework

### Objective
Give CoS a configurable, persona-driven, learnable governance framework that adapts through conversation — not through a giant preferences screen.

### Tasks

#### 1.1 Add Governance Fields to Blueprint
**File:** `apps/core/blueprint/models.py`

Add fields to `PersonalOperatingBlueprint`:
```python
# Governance Profile
accountability_style = CharField(choices=['light','standard','firm'], default='standard')
question_frequency = CharField(choices=['low','medium','high'], default='medium')
relationship_suggestions_enabled = BooleanField(default=False)
event_reflections_enabled = BooleanField(default=True)
sensitivity_tags = JSONField(default=list)  # ['medicine','relationships','faith']
calibration_day = PositiveSmallIntegerField(default=0)  # Day counter (0-14)
calibration_complete = BooleanField(default=False)
governance_overrides = JSONField(default=dict)  # User override history
```

**Migration:** `0015_blueprint_governance_fields.py` (or next available number)

#### 1.2 Create Governance Decision Layer
**File:** `apps/core/blueprint/cos_governance.py` (NEW)

Functions:
- `evaluate_governance(user, action_type, context)` → `GovernanceDecision`
  - Consults blueprint governance profile
  - Consults intervention engine escalation level
  - Applies persona tone modifiers
  - Returns: ask/skip, tone_intensity, delivery_channel, explanation
- `should_ask_question(user, question_category)` → bool
  - Checks daily question count vs frequency tolerance
  - Checks if topic is in sensitivity_tags (gentler approach)
  - Checks calibration status
- `record_governance_interaction(user, question_category, user_response)` → None
  - Updates SLCME learned mapping for preference
  - Updates governance_overrides if user declined/modified
- `get_calibration_question(user)` → dict or None
  - Returns next calibration question (1-2/day during first 14 days)
  - Categories: core_people, non_negotiables, preferred_activities, negotiables
  - Returns None if calibration complete or daily cap met
- `build_governance_instructions(user)` → str
  - Produces system prompt instructions for governance compliance
  - "Your accountability style is [firm]. Ask questions [rarely]. Be sensitive about [medicine]."

#### 1.3 Wire Governance into System Prompt
**File:** `apps/core/ai_orchestrator/cos_context.py`

Extend `build_cos_context()`:
- Add `governance` key with accountability_style, question_frequency, sensitivity_tags, calibration_status

Extend `format_cos_system_injection()`:
- Add `--- GOVERNANCE PROFILE ---` section with human-readable instructions

#### 1.4 Wire Governance into Response Generation
**File:** `apps/ai/personal_assistant.py`

In `_generate_response()`, after CoS injection:
- Call `build_governance_instructions(user)` and append to system prompt
- This tells the LLM how to modulate tone, when to ask vs. skip, what to be sensitive about

#### 1.5 Add "Why Are You Asking?" Handler
**File:** `apps/ai/personal_assistant.py`

In intent recognition or response generation:
- Detect "why are you asking" / "why do you need to know" patterns
- Respond with standard trust message: "The more I understand what matters to you, the better I can protect it—share only what you're comfortable with."
- Log the interaction via SLCME (user asked "why" about category X)

#### 1.6 Add CoS Settings View
**Files:**
- `templates/components/cos_settings.html` (NEW)
- `apps/dashboard/views.py` or `apps/ai/views.py` — add settings view
- `apps/ai/urls.py` or `apps/dashboard/urls.py` — add URL route

Simple view with 5 controls:
1. "How firm should I be?" → accountability_style slider (light/standard/firm)
2. "How often should I ask questions?" → question_frequency (low/medium/high)
3. "Relationship suggestions?" → relationship_suggestions_enabled toggle
4. "Event reflections?" → event_reflections_enabled toggle
5. "Preferred notifications" → intelligence channel selection (in-app/email/SMS)

All other preferences learned through conversation and visible/editable in a "Learned Preferences" expandable section.

#### 1.7 Add Calibration Mode Logic
**File:** `apps/core/blueprint/cos_governance.py`

During first 14 days (calibration_day < 14, calibration_complete = False):
- `get_calibration_question()` returns 1-2 high-leverage questions per day
- Question categories:
  - Day 1-3: Core people ("Who matters most in your daily life?")
  - Day 4-6: Non-negotiables ("What activities are sacred to you?")
  - Day 7-10: Preferred activities ("What do you enjoy doing in free time?")
  - Day 11-14: Negotiables ("What can be moved or dropped when things get busy?")
- Answers stored via SLCME `LearnedMapping` with category-based meaning_type
- `calibration_day` incremented daily via ISE or on first daily interaction
- After day 14 or if user says "skip calibration": `calibration_complete = True`

### File Touchpoints
| File | Change |
|------|--------|
| `apps/core/blueprint/models.py` | Add governance fields to PersonalOperatingBlueprint |
| `apps/core/blueprint/cos_governance.py` | **NEW** — Governance decision layer |
| `apps/core/ai_orchestrator/cos_context.py` | Extend context with governance profile |
| `apps/ai/personal_assistant.py` | Inject governance instructions into system prompt |
| `templates/components/cos_settings.html` | **NEW** — Simple CoS settings view |
| `apps/ai/views.py` or `apps/dashboard/views.py` | Add CoS settings view |
| `apps/ai/urls.py` or `apps/dashboard/urls.py` | Add URL route |
| Migration file | New governance fields |

### Phase 1 Tests
1. Governance profile creation with defaults
2. `accountability_style` modifies tone instructions in system prompt
3. `sensitivity_tags` produce "be sensitive about medicine" instruction
4. `should_ask_question()` returns False when daily cap exceeded
5. `should_ask_question()` returns False for declined category
6. "Why are you asking?" detection and standard response
7. Calibration question returns appropriate category for day range
8. Calibration completes after day 14
9. `record_governance_interaction()` creates SLCME learned mapping
10. GovernanceDecision respects intervention engine levels
11. Settings view renders with correct current values
12. Settings view saves accountability_style and question_frequency

---

## Phase 2 — Post-Event Reflection Loops

### Objective
Make CoS a partner that follows up after meaningful events, extracting action items, injuries, follow-ups — and turning them into WLJ tasks/events.

### Tasks

#### 2.1 Create Reflection Engine
**File:** `apps/core/blueprint/reflection_engine.py` (NEW)

Models (in blueprint/models.py):
```python
class EventReflection(UserOwnedModel):
    """A pending or completed post-event reflection check-in."""
    source_type = CharField(choices=['calendar','workout','social','health'])
    source_id = CharField(max_length=100)  # LifeEvent.id, WorkoutSession.id, etc.
    source_title = CharField(max_length=200)
    event_date = DateField()
    status = CharField(choices=['pending','delivered','completed','skipped','expired'], default='pending')
    scheduled_for = DateTimeField()  # When to deliver (12-24h after event)
    questions = JSONField(default=list)  # Pre-generated reflection questions
    answers = JSONField(default=dict)  # User responses
    action_items_created = JSONField(default=list)  # Task/event IDs created from answers
    delivered_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
```

Functions:
- `detect_reflectable_events(user, date=None)` → list of event dicts
  - Scans completed LifeEvents tagged as meeting/social or duration > 60min
  - Scans completed WorkoutSessions (if fitness module enabled)
  - Skips events already in reflection queue
  - Respects `event_reflections_enabled` governance flag
  - Caps daily reflections (max 2 per day)
- `generate_reflection_questions(event_dict, persona)` → list of question strings
  - Meeting: "Any action items from [title]?" / "Anything to follow up on?"
  - Workout: "How did [title] go? Any injuries or adjustments needed?"
  - Social: "How was [title]? Anyone you want to follow up with?"
  - Health anomaly: "Your [metric] was unusual yesterday — want to adjust today?"
- `queue_reflection(user, event_dict)` → EventReflection
  - Creates reflection with `scheduled_for` = event end + 12-24h (morning preferred)
  - Pre-generates questions using persona
- `deliver_pending_reflections(user)` → list of delivered reflections
  - Called when user opens Command Mode or assistant
  - Returns reflections where `scheduled_for <= now` and `status == 'pending'`
  - Marks as `delivered`
- `process_reflection_answer(user, reflection_id, answer_text)` → dict
  - Parse via SUE + HTIE for action items, follow-up events, injury notes
  - Create Tasks for action items (`handle_create_task`)
  - Create LifeEvents for follow-ups (`handle_create_event`)
  - Store answers and created item IDs
  - Mark reflection as `completed`

#### 2.2 Add Reflection Triggers to Assistant Triggers
**File:** `apps/core/blueprint/assistant_triggers.py`

Add:
- `check_pending_reflections(user)` → TriggerResult
  - Returns `should_fire=True` if pending reflections exist past scheduled time
  - Includes reflection questions in message

#### 2.3 Register Reflection Scheduler
**File:** `apps/core/ai_scheduler/scheduler_registry.py`

Register: `queue_event_reflections` task (86400s / 24h)
- Scans previous day's events for all users
- Queues reflections via `detect_reflectable_events` + `queue_reflection`

**File:** `apps/core/ai_scheduler/scheduler_runner.py`
- Add `run_reflection_queue()` function

#### 2.4 Wire Reflections into Command Mode
**File:** `apps/dashboard/views.py` — `_get_command_mode()`

Add `reflections_pending` list to command_mode context:
- Call `deliver_pending_reflections(user)`
- Include as "Quick check-ins" section (non-intrusive)

**File:** `templates/components/cos_command_mode.html`

Add section between protections and input:
```html
{% if command_mode.reflections_pending %}
<div class="cos-cm-reflections">
    <div class="cos-cm-section-label">Quick check-ins</div>
    {% for r in command_mode.reflections_pending %}
    <div class="cos-cm-reflection">{{ r.question }}</div>
    {% endfor %}
</div>
{% endif %}
```

#### 2.5 Wire Reflection Responses via Chat
**File:** `apps/ai/personal_assistant.py`

In `send_message()`, before intent recognition:
- Check if user has pending delivered reflections
- If message appears to be answering a reflection (contextual detection via SLCME):
  - Call `process_reflection_answer()`
  - Include created action items in response

#### 2.6 Integration with Daily Briefing
**File:** `apps/core/ai_briefing/briefing_engine.py`

In `generate_daily_briefing()`:
- Include pending reflections in briefing snapshot
- Surface as "Check-ins" in briefing output

### File Touchpoints
| File | Change |
|------|--------|
| `apps/core/blueprint/models.py` | Add EventReflection model |
| `apps/core/blueprint/reflection_engine.py` | **NEW** — Reflection detection, queuing, processing |
| `apps/core/blueprint/assistant_triggers.py` | Add reflection trigger |
| `apps/core/ai_scheduler/scheduler_registry.py` | Register reflection task |
| `apps/core/ai_scheduler/scheduler_runner.py` | Add runner function |
| `apps/dashboard/views.py` | Add reflections to command mode |
| `templates/components/cos_command_mode.html` | Add check-ins section |
| `apps/ai/personal_assistant.py` | Wire reflection answer processing |
| `static/css/assistant-panel.css` | CSS for check-ins section |
| Migration file | EventReflection model |

### Phase 2 Tests
1. `detect_reflectable_events` finds meetings > 60min
2. `detect_reflectable_events` finds completed workouts (fitness enabled)
3. `detect_reflectable_events` respects `event_reflections_enabled` flag
4. `detect_reflectable_events` caps at 2 reflections per day
5. `generate_reflection_questions` varies by event type (meeting/workout/social)
6. `queue_reflection` creates EventReflection with correct scheduled_for
7. `deliver_pending_reflections` only returns past-due pending reflections
8. `process_reflection_answer` creates Task from action item
9. `process_reflection_answer` marks reflection completed
10. Reflection skipped for disabled modules (fitness module off → no workout reflections)
11. Command mode includes reflections_pending when available
12. Scheduler runner processes all users without crash

---

## Phase 3 — Relationship & Significance Intelligence

### Objective
Remember what matters — people and milestones — and protect them proactively. Make WLJ emotionally resonant.

### Tasks

#### 3.1 Create Relationship Models
**File:** `apps/core/ai_relationships/models.py` (NEW module)

```python
class Person(UserOwnedModel):
    """A person in the user's life."""
    display_name = CharField(max_length=200)
    person_type = CharField(choices=['family','friend','colleague','mentor','other'], default='other')
    notes = TextField(blank=True)
    is_active = BooleanField(default=True)

class Relationship(models.Model):
    """User's relationship with a person."""
    user = ForeignKey(User, on_delete=CASCADE)
    person = ForeignKey(Person, on_delete=CASCADE, related_name='relationships')
    relationship_type = CharField(max_length=50)  # 'spouse','child','parent','friend','boss'
    importance_tier = PositiveSmallIntegerField(default=3)  # 1=innermost, 3=outer
    cadence_target = CharField(choices=['daily','weekly','biweekly','monthly','quarterly'], blank=True)
    last_interaction = DateField(null=True)

class InteractionSignal(models.Model):
    """Extracted signal of interaction with a person."""
    user = ForeignKey(User, on_delete=CASCADE)
    person = ForeignKey(Person, on_delete=CASCADE, related_name='interactions')
    signal_date = DateField()
    signal_type = CharField(max_length=50)  # 'mention','event','call','message'
    confidence = FloatField(default=0.8)
    source_type = CharField(max_length=50)  # 'journal','calendar','reflection','manual'
    source_id = CharField(max_length=100, blank=True)  # FK to source record
```

#### 3.2 Link SignificantEvent to Person
**File:** `apps/life/models.py`

Add nullable FK to Person on SignificantEvent:
```python
person = ForeignKey('core_ai_relationships.Person', null=True, blank=True, on_delete=SET_NULL)
```

This is backward-compatible (existing events keep working via `person_name`).

#### 3.3 Create Relationship Engine
**File:** `apps/core/ai_relationships/relationship_engine.py` (NEW)

Functions:
- `extract_people_from_text(user, text, source_type, source_id)` → list of InteractionSignal
  - Uses SUE to identify people mentions
  - Matches against existing Person records (fuzzy by name)
  - Creates InteractionSignal for each match
  - Returns list of created signals
- `compute_interaction_baselines(user)` → dict of person_id → baseline_days
  - Compute 30/60/90d interaction frequency per person
  - Returns expected cadence
- `detect_relational_drift(user)` → list of drift alerts
  - Compare last_interaction vs cadence_target
  - Flag people with gaps > 1.5x cadence target
  - Return sorted by importance_tier (most important first)
- `generate_relationship_suggestion(user, drift_alert)` → suggestion dict
  - Persona-aware suggestion (respects sensitivity_tags)
  - Options: "schedule time", "send a note", "call", "plan an outing"
  - Respects `relationship_suggestions_enabled` governance flag
- `suggest_opportunity_windows(user, person)` → list of time slots
  - Uses weekly pressure engine to find light windows
  - Proposes 1-3 scheduling options
  - If user approves: create LifeEvent + push to Google Calendar

#### 3.4 Wire People Extraction into Journal Save
**File:** `apps/journal/models.py` or `apps/journal/signals.py`

Post-save signal on JournalEntry:
- Call `extract_people_from_text()` if AI enabled and consent given
- Only extract, never store raw journal content

#### 3.5 Wire Extraction into Reflection Answers
**File:** `apps/core/blueprint/reflection_engine.py`

In `process_reflection_answer()`:
- Call `extract_people_from_text()` on answer text
- Create InteractionSignal for mentioned people

#### 3.6 Register Relational Drift Detector in ISE
**File:** `apps/core/ai_scheduler/scheduler_registry.py`

Register: `detect_relational_drift` task (86400s / 24h)
- Runs `detect_relational_drift()` for all users with `relationship_suggestions_enabled`
- Generates GuidanceItem via PGE for each drift alert

#### 3.7 Wire Suggestions into PGE
**File:** `apps/core/ai_guidance/guidance_engine.py`

In `generate_guidance()`:
- Add relational drift as a guidance source
- GuidanceItem with `guidance_type='relational_drift'`, `source='composite'`

#### 3.8 Add Relationship Settings to CoS Settings
**File:** `templates/components/cos_settings.html`

Already has "Relationship suggestions?" toggle from Phase 1.

Add "Learned People" expandable section:
- Lists known Person records
- User can edit, merge, or remove
- Visible but not primary

### File Touchpoints
| File | Change |
|------|--------|
| `apps/core/ai_relationships/__init__.py` | **NEW** module |
| `apps/core/ai_relationships/models.py` | **NEW** — Person, Relationship, InteractionSignal |
| `apps/core/ai_relationships/relationship_engine.py` | **NEW** — Extraction, drift, suggestions |
| `apps/core/ai_relationships/admin.py` | **NEW** — Admin registration |
| `apps/life/models.py` | Add optional FK on SignificantEvent |
| `apps/journal/signals.py` or `apps/journal/models.py` | People extraction on journal save |
| `apps/core/blueprint/reflection_engine.py` | People extraction in reflection answers |
| `apps/core/ai_scheduler/scheduler_registry.py` | Register drift detector |
| `apps/core/ai_scheduler/scheduler_runner.py` | Add runner function |
| `apps/core/ai_guidance/guidance_engine.py` | Add relational guidance source |
| `apps/core/ai_semantics/semantic_parser.py` | Add people extraction patterns |
| `settings.py` | Add `core.ai_relationships` to INSTALLED_APPS |
| Migration files | Person, Relationship, InteractionSignal, SignificantEvent FK |

### Phase 3 Tests
1. Person model creation and soft delete
2. InteractionSignal creation with confidence
3. `extract_people_from_text` matches existing Person by name
4. `extract_people_from_text` creates InteractionSignal
5. `compute_interaction_baselines` returns correct cadence
6. `detect_relational_drift` flags gap > 1.5x target
7. `detect_relational_drift` skips users with feature disabled
8. `generate_relationship_suggestion` respects persona
9. `suggest_opportunity_windows` uses weekly pressure light windows
10. SignificantEvent.person FK is nullable and backward-compatible
11. Journal save triggers people extraction (when enabled)
12. Relational drift creates GuidanceItem via PGE

---

## Migration Plan

### Phase 1 Migrations
1. `apps/core/blueprint/migrations/0015_blueprint_governance_fields.py`
   - Add governance fields to PersonalOperatingBlueprint
   - All fields have defaults — safe for existing data

### Phase 2 Migrations
2. `apps/core/blueprint/migrations/0016_eventreflection.py`
   - Create EventReflection model
   - New table, no existing data affected

### Phase 3 Migrations
3. `apps/core/ai_relationships/migrations/0001_initial.py`
   - Create Person, Relationship, InteractionSignal
4. `apps/life/migrations/XXXX_significantevent_person_fk.py`
   - Add nullable FK to Person on SignificantEvent
   - Nullable = backward-compatible

### Rollback Strategy
- All new fields have defaults or are nullable — safe to roll back migrations
- New modules (`ai_relationships`) can be removed from INSTALLED_APPS
- Feature flags (`event_reflections_enabled`, `relationship_suggestions_enabled`) default to safe states
- No existing model structure is altered destructively

---

## Risks & Mitigations

### Risk 1: Governance instructions bloat system prompt
**Mitigation:** Governance instructions are a compact paragraph (3-5 sentences), not a detailed spec. The LLM gets behavioral guidance, not engine internals.

### Risk 2: Reflection queue creates notification fatigue
**Mitigation:** Hard cap of 2 reflections/day. Governance `question_frequency` further limits. "Skip" always available. Calibration mode asks 1-2 questions max.

### Risk 3: People extraction creates false positives
**Mitigation:** Confidence scoring on InteractionSignal. Only high-confidence matches auto-link. Medium confidence asks user to confirm. All people are user-editable and deletable.

### Risk 4: Google Calendar sync failures
**Mitigation:** Already handled — `_run_cos_post_scheduling` wraps sync in try/except. Sync failures are logged but never block event creation.

### Risk 5: Privacy concerns with relationship intelligence
**Mitigation:** Triple-gated: (1) `personal_assistant_enabled` must be True, (2) `relationship_suggestions_enabled` must be True (default False), (3) `ai_data_consent` must be True. No raw journal content stored — only extracted signals with references.

### Risk 6: Migration complexity
**Mitigation:** All migrations are additive (new fields with defaults, new tables, nullable FKs). No destructive changes. No data transformation needed.

---

*Plan ready for review. Implementation begins after confirmation.*
