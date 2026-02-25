# WLJ Chief of Staff (CoS) — Complete System Report & Gap Analysis

**Generated:** 2026-02-25
**Purpose:** Full inventory of everything CoS can do, every engine it uses, every data source it accesses, and every gap that exists. Intended as input for creating a master prompt to make CoS as capable as Claude Code / ChatGPT.
**Status:** Post-Intelligence Upgrade (all 10 phases complete)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [The Brain: System Prompt & Personality](#3-the-brain-system-prompt--personality)
4. [Intent System: What CoS Can DO](#4-intent-system-what-cos-can-do)
5. [Intelligence Engines (17 Engines)](#5-intelligence-engines-17-engines)
6. [Data Access: What CoS Can SEE](#6-data-access-what-cos-can-see)
7. [Context Assembly: What Goes Into Every Response](#7-context-assembly-what-goes-into-every-response)
8. [Proactive Systems](#8-proactive-systems)
9. [Memory & Learning](#9-memory--learning)
10. [Response Quality Pipeline](#10-response-quality-pipeline)
11. [Frontend Integration](#11-frontend-integration)
12. [Configuration & Personalization](#12-configuration--personalization)
13. [GAP ANALYSIS: What's Missing or Weak](#13-gap-analysis-whats-missing-or-weak)
14. [Comparison: CoS vs Claude Code vs ChatGPT](#14-comparison-cos-vs-claude-code-vs-chatgpt)
15. [Priority Roadmap to Close Gaps](#15-priority-roadmap-to-close-gaps)

---

## 1. Executive Summary

### What CoS IS
The Chief of Staff is the AI orchestration layer of Whole Life Journey. It's a GPT-4o-powered personal executive assistant that sits on top of ALL user data — health, journal, faith, goals, habits, tasks, calendar, finances, relationships — and provides:

- **Natural language interface** to log data, create tasks, manage calendar, track health
- **Contextual awareness** of what page the user is viewing and what they're doing
- **Accountability** via behavioral trajectory monitoring and commitment contracts
- **Executive briefings** (morning summary, gap re-entry, weekly intelligence)
- **Long-term memory** via RAG vector search across past conversations
- **Proactive prompting** — pre/post event check-ins for habits, goals, milestones
- **Pattern detection** — negative streaks, fatigue, consistency drops, positive momentum
- **Faith integration** — scripture context, prayer tracking, reading plan awareness
- **Self-correction** — validates its own responses and regenerates on context mismatch

### What CoS is NOT (Yet)
- Not truly proactive (can't push notifications — only surfaces prompts when user opens chat)
- Not a general knowledge engine (can only answer about WLJ data + weather)
- Can't edit most existing data (primarily creates new records)
- Can't coordinate across users (no family/household awareness)
- Can't speak back (no TTS)
- Can't search the web for general information

---

## 2. Architecture Overview

### Entry Points

| Endpoint | Purpose |
|----------|---------|
| `POST /ai/chat/` | Primary user message processing |
| `GET /ai/opening/` | Daily check-in greeting + snapshot |
| `GET /ai/conversation/<id>/` | Conversation history |
| `GET/POST /ai/cos/settings/` | Governance settings |
| `POST /ai/learning-mode/toggle/` | Enter/exit learning mode |
| `POST /ai/event-reflection/` | Post-event reflection |
| `POST /ai/quick-reply/` | Handle quick reply button clicks |

### Message Processing Pipeline

```
User Message
    │
    ├─> ECC Closure Check (commitment contract — absolute precedence)
    ├─> ECC Detection (new commitment? renegotiation?)
    ├─> Proactive Confirmation (yes/no to check-in?)
    ├─> Calibration Mode (if active — listen only)
    ├─> Learning Mode (if active — suppress execution)
    ├─> Intent Recognition (GPT-4o function calling → 36 intents)
    │   ├─> Safety gate (not during calibration/learning)
    │   ├─> Multi-intent support ("log weight 180 and heart rate 65")
    │   ├─> Orchestrator enrichment (time/context resolution)
    │   └─> Action execution → response built from results
    ├─> Feature Request Detection ("I wish I could...")
    ├─> Bug Report Detection ("Fix this...")
    └─> General Response Generation
            │
            ├─> RAG Memory Retrieval (top-5 similar past conversations)
            ├─> Page Context Injection (what user is viewing)
            ├─> Session Activity (page visit history)
            ├─> Topic Threading (page vs conversation thread)
            ├─> Context-Priority Routing (scripture > routines)
            ├─> Pre-Response Reasoning (chain of thought)
            ├─> Personal Data Query (weight/journal/medication/etc.)
            ├─> Web Search (weather only currently)
            ├─> Response Mode Classification (brief/adaptive/deep)
            ├─> LLM Generation (GPT-4o, temperature 0.4-0.65)
            └─> Response Quality Validation (auto-regenerate on mismatch)
```

### Key Files

| File | Role |
|------|------|
| `apps/ai/personal_assistant.py` | Main brain — system prompt, state assessment, response generation |
| `apps/ai/intent_service.py` | GPT-4o function calling for intent recognition |
| `apps/ai/action_handlers.py` | Executes intents → creates/updates Django models |
| `apps/ai/memory_service.py` | RAG vector memory (embed, store, retrieve) |
| `apps/ai/executive_briefing.py` | Morning briefing, session gap detection |
| `apps/ai/services.py` | OpenAI API wrapper with retry/caching |
| `apps/ai/intents/` | 12 intent modules defining 36 actions |
| `apps/core/ai_orchestrator/` | Context building, commitment contracts, orchestration |
| `apps/core/ai_learning/` | Learning extractor, user profile |
| `apps/core/ai_memory/` | Memory resolution, confidence, learned mappings |
| `apps/core/blueprint/` | Governance, calibration, drift detection |
| `apps/core/ai_governance/` | Recalibration, alignment sessions |
| `apps/cos/` | Prompt scheduling, reflections, patterns, tone |
| `templates/components/chat_widget.html` | Frontend chat interface + page content capture |
| `assistant/` | Personal data query system |

---

## 3. The Brain: System Prompt & Personality

### Identity
- "Trusted partner in their personal journey. Not a generic chatbot — you KNOW this person."
- Has access to goals, health data, habits, faith journey, daily tasks
- "Speaks like a knowledgeable friend who genuinely cares"

### Core Behavior Rules (hardcoded in system prompt)
1. **Trust Principle:** Know their data, remember context, give real answers
2. **Lead with data** — never hedge when you have the information
3. **Conversational intelligence** — thread conversation naturally, read between the lines
4. **Never send to a page when they ask you to THINK** — "where should I focus?" = analyze, not navigate
5. **Answer what was asked, then STOP** — no follow-up questions, no motivational filler
6. **Never fabricate data** — say "I don't see any X logged recently" rather than making it up
7. **Can answer ANYTHING** — not limited to wellness topics
8. **Never cheerleader** — give honest assessment, not empty encouragement

### Coaching Styles (user-configurable)
- **Direct:** Results-focused, concise, no small talk
- **Supportive:** Warm but balanced, encouraging nudges
- **Gentle:** Compassionate, patient, acknowledges emotions

### Faith Integration
When `faith_enabled`, CoS:
- Includes scripture references when naturally relevant
- References spiritual growth and God's faithfulness
- Treats faith as integrated part of the user's journey
- On reading plan pages, prioritizes scripture context over everything else

### Response Modes
| Mode | Trigger | Token Budget | Behavior |
|------|---------|-------------|----------|
| Brief | Short questions, yes/no, confirmations | 400 | 1-3 sentences max |
| Adaptive | Default | 800 | Match depth of user's message |
| Deep | Analysis keywords, data queries | 1200 | Data-driven insights with real numbers |

### Time Awareness
- Calculates hours until bedtime (user-configured or 10pm default)
- 6 urgency buckets: early_morning, morning, midday, afternoon, evening, night
- Adjusts messaging: "You have the whole day ahead" → "Your day is wrapping up"

---

## 4. Intent System: What CoS Can DO

### Complete Intent Inventory (36 intents)

#### Health & Fitness (11 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `log_heart_rate` | Records HR in BPM + context | "my heart rate is 65 resting" |
| `log_blood_pressure` | Records systolic/diastolic | "BP is 128 over 82" |
| `log_weight` | Records weight + unit | "I weigh 185 pounds" |
| `log_glucose` | Records blood sugar + context | "glucose is 95 fasting" |
| `log_blood_oxygen` | Records SpO2 | "oxygen level 97" |
| `log_food` | Records food + calories + meal | "had a salad, about 400 calories for lunch" |
| `log_workout` | Full workout with exercises/sets/reps | "I did 3 sets of bench press 185x8" |
| `log_exercise_set` | Single exercise set | "just did 10 pullups" |
| `log_cardio` | Cardio session | "ran 3 miles in 25 minutes" |
| `start_fast` | Begin fast window | "starting a 16:8 fast" |
| `end_fast` | End current fast | "breaking my fast" |

#### Medicine (1 intent)
| Intent | What it does | Example |
|--------|-------------|---------|
| `take_medicine` | Log medication dose | "took my metformin" |

#### Journal (2 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `create_journal_entry` | Create journal with title/body/mood | "journal entry: feeling grateful today..." |
| `add_gratitude` | Quick gratitude log | "I'm grateful for my family" |

#### Faith (4 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `log_prayer` | Create prayer request | "pray for my wife's surgery" |
| `mark_prayer_answered` | Mark prayer answered | "God answered my prayer about the job" |
| `save_verse` | Save scripture (YouVersion lookup) | "save Romans 8:28" |
| `add_faith_milestone` | Record milestone | "got baptized today" |

#### Purpose (4 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `create_goal` | Create goal with domain/timeframe | "I want to lose 20 pounds by June" |
| `update_goal_progress` | Log progress note | "made progress on my running goal" |
| `set_intention` | Create change intention | "I intend to wake up at 5am every day" |
| `log_habit` | Log habit completion | "did my quiet time today" |

#### Life Management (5 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `create_task` | Create task with priority/effort | "add task: call insurance company" |
| `create_routine_task` | Daily routine with CoS check-ins | "add Quiet Time at 5:30am daily" |
| `complete_task` | Mark task done | "I finished the report" |
| `create_event` | Calendar event | "schedule dentist appointment Friday at 2pm" |
| `add_reminder` | Significant event reminder | "remind me about Mom's birthday March 15" |

#### Calendar (2 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `read_calendar_events` | Query calendar by date/range | "what's on my calendar tomorrow?" |
| `mutate_calendar_event` | Create/update/delete events | "move my 3pm meeting to 4pm" |

#### System (5 intents)
| Intent | What it does | Example |
|--------|-------------|---------|
| `set_cos_name` | Change CoS display name | "call yourself Jarvis" |
| `pause_calibration` | Pause getting-to-know-you | "let's pause the questions" |
| `complete_calibration` | Finish calibration | "I think you know me well enough" |
| `enter_learning_mode` | Listen-only mode | "just listen for a while" |
| `exit_learning_mode` | Resume execution | "you can start taking actions again" |

---

## 5. Intelligence Engines (17 Engines)

### Phase 1: Interpretation (Before Action)

| Engine | Acronym | What It Does |
|--------|---------|-------------|
| Semantic Understanding Engine | SUE | NLP classification of user intent |
| Situational-Lifecycle Context-Mapping Engine | SLCME | Maps user state to lifecycle phase |
| Historical-Temporal Inference Engine | HTIE | Time resolution ("next Tuesday", "every morning") |
| User-Adaptive Interaction Orchestrator | UAIO | Routes to correct action handler |
| Predictive Relevance & Insight Engine | PRIE | Predicts what data/insights are relevant |

### Phase 2: Execution

| Engine | Acronym | What It Does |
|--------|---------|-------------|
| Safety & Anomaly Monitoring Engine | SAME | Detects anomalies in data/behavior |
| Dynamic Nudge Engine | DNE | Delivers nudges at right time/channel |
| Strategic Alignment Engine | SAE | Ensures actions align with user's stated priorities |

### Phase 3: Post-Execution

| Engine | Acronym | What It Does |
|--------|---------|-------------|
| Post-Interaction Enrichment | PIE | Extracts learning after every interaction |
| Continuous Feedback Loop Engine | CFLE | Tracks what worked/didn't for the user |
| Internal Scheduling Engine | ISE | Schedules periodic tasks (prompt generation, cleanup) |

### Additional Engines

| Engine | What It Does |
|--------|-------------|
| Drift Detection Engine | Monitors missed habits/meds/workouts, computes drift score |
| Commitment Contract Engine (ECC) | Deterministic commitment tracking with binary closure |
| Trajectory Activation Engine | Computes CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT state |
| Recalibration Engine | Triggers when miss rate ≥ 60% on non-negotiables |
| Governance Engine | Controls CoS tone, question gating, enforcement level |
| Self-Reliability Index | Admin-only scoring of CoS accuracy (L1/L2/L3 errors) |

---

## 6. Data Access: What CoS Can SEE

### Personal Data Queries (via assistant/data_service.py)
CoS can query ALL of the following user data in real-time when the user asks about it:

| Data Type | What's Available |
|-----------|-----------------|
| **Weight** | Entries, trends, 7/30-day averages, BMI |
| **Blood Pressure** | Readings, averages, position/arm tracking |
| **Heart Rate** | Readings, HR events (high/low/irregular) |
| **Blood Oxygen** | SpO2 readings, trends |
| **Glucose** | Readings, fasting/post-meal context |
| **Sleep** | Duration, quality, trends |
| **Steps** | Daily counts, averages |
| **Workouts** | Sessions, types, exercise details, streaks |
| **Fasting** | Windows, durations, active fast status |
| **Medications** | Schedules, adherence rates, missed doses |
| **Food/Nutrition** | Entries, calories, meal types, nutrient breakdown |
| **Water** | Hydration entries |
| **Mobility** | Mobility data |
| **Audio Exposure** | Noise exposure data |
| **Journal** | Entries, moods, streaks, categories |
| **Tasks** | Active/overdue/completed, due dates, priorities |
| **Goals** | Active goals, progress, milestones, target dates |
| **Habits** | Completion rates, streaks, recovery patterns |
| **Faith** | Prayers (active/answered), reading plans, milestones |
| **Calendar** | Today's events, upcoming events |
| **User Profile** | Name, timezone, preferences |

### State Assessment (comprehensive snapshot, cached 2 hours)
Built by `PersonalAssistant.assess_current_state()`:
- Journal: entry count, streak, dominant mood, recent entries
- Tasks: completed/overdue/due today/upcoming counts
- Purpose: active goals, intentions, annual direction, habit goal recovery patterns
- Faith: prayer counts, reading plan status, milestones
- Health: weight trend, fasting status, workout streak, medication adherence, all vitals

### Executive Context (cos_context.py)
Injected into system prompt for every response:
- Blueprint state (operating style, tiers, override policy)
- Today's plan (blocks, completion, capacity)
- Alignment score, drift score + prediction
- Override frequency (14 days)
- Deadline snapshot
- Strategic summary from PRIE
- Active insights and predictions
- Relationship signals (approaching events, contact gaps)
- Journal mood trends and health signals
- Open loops and feedback profiles
- Transformation metrics

---

## 7. Context Assembly: What Goes Into Every Response

The system prompt is assembled in priority order:

### Layer 1-3: Session Overrides (highest priority)
- **Calibration injection** — if in getting-to-know-you mode
- **Recalibration injection** — if miss rate ≥ 60%
- **Alignment session injection** — if governance alignment needed

### Layer 4: Personality & Governance
- Post-calibration personality instructions
- Operating style, accountability level, sensitivity settings

### Layer 5: Learned User Profile
- Stated values, non-negotiables, identity statements
- Recurring goals, motivational triggers, relationship priorities
- Frustrations, avoidance patterns, health concerns
- Life event mentions, commitments made
- Explanation preferences, time patterns

### Layer 6: Operational Context
- Schedule, calendar, medication gates
- Drift score, trajectory state, activation tier
- Commitment contracts (active/pending)
- Deadline snapshot, tomorrow forecast

### Layer 7: RAG Memory (NEW)
- Top-5 semantically similar past conversations
- Formatted with natural time labels

### Layer 8: Page Context
- Session activity (last 10 page visits with timestamps)
- Current page content (scripture text, journal entry, goal details, etc.)
- Context-priority routing (e.g., scripture > routines)
- Topic threading hint (page vs conversation thread)

### Layer 9: Base Prompt
- Identity, trust principle, conversational intelligence rules
- Coaching style, faith integration, time awareness
- Link directory, response mode rules

### Layer 10: Pre-Response Reasoning
- Chain-of-thought instruction: silently reason about context, intent, relevant data, and what NOT to talk about

---

## 8. Proactive Systems

### Executive Briefing (first-of-day or 4h+ gap)
Sections:
- A: Time-aware greeting + sleep data + session gap humanization
- B: Life events approaching (7-day window)
- C: Health gate (medication status, active fast, workout completion)
- D: Day overview (tasks, goals, habit streaks)
- E: Journal follow-up (mood trends, repeated health keywords)
- F: Gap context (what happened since last visit)

### CoS Prompt Scheduling (apps/cos/)
- **CosPromptScheduler** runs every 6 hours via ISE
- Generates pre/post event prompts for next 24h:
  - Habits (daily check-ins)
  - Goal deadlines (48h window)
  - Milestone deadlines (48h window)
  - Life events (24h window)
  - Manual calendar events (24h window)
- **CosPromptService** delivers prompts with templates + tone
- **CosCompletionService** routes "Yes" responses to mark source complete

### Pattern Detection (CosPatternService)
Detects:
- Negative streaks (consecutive missed days)
- Fatigue patterns (declining performance)
- Consistency drops (sudden decrease)
- Positive momentum (improvement trends)
- Activity gaps (extended periods without activity)
- Generates evidence-based solution suggestions

### Drift Detection
- Monitors: fast breaks, missed meds, skipped workouts, nutrition off-track, faith blocks missed, goal slips, sleep deficits
- Computes daily drift score (0-100) weighted by tier importance
- Predicts 24h/72h drift probability
- Triggers recalibration when miss rate ≥ 60%

### Commitment Contracts (ECC)
- Deterministic detection (no LLM) of commitment intent
- Types: DO, DECIDE, SCHEDULE, STOP
- Time boundaries always required
- Binary closure (success/missed)
- Cross-session persistence
- Tier-aware renegotiation gating

---

## 9. Memory & Learning

### Short-Term: Conversation History
- 40-message context window per conversation
- 20 messages included in user prompt
- Rolling summary generated after 20+ messages via GPT-4o-mini

### Long-Term: RAG Vector Memory (NEW)
- Each conversation turn embedded via `text-embedding-3-small` (1536 dims)
- Stored in `ConversationMemory` model (500 per user, auto-pruned)
- Retrieved via cosine similarity (top-5, threshold 0.35)
- Formatted with natural time labels: "Last Tuesday", "2 weeks ago"
- Topic-tagged: faith, health, goals, tasks, journal, relationships, finance

### Learned User Profile
Regex-based extraction (no AI call) from every conversation:
- Stated values, non-negotiables, identity statements
- Frustrations, recurring goals, relationship priorities
- Motivational triggers, avoidance patterns
- Health concerns, life event mentions, commitments
- Explanation preferences (brief/detailed), time patterns

### Memory Resolution System
Priority chain: current context → high-confidence learned mappings → medium-confidence (suggest + confirm) → ask user

### Calibration System
- 10+ getting-to-know-you questions (core people, non-negotiables, activities, accountability style, faith preferences)
- Data-aware: gathers live snapshot of ALL user data before each question
- User-controlled completion
- Continuous relationship-deepening questions post-calibration

---

## 10. Response Quality Pipeline

### Pre-Generation
1. **Context-priority routing** — per page type disambiguation
2. **Topic threading** — page referent vs conversation continuation detection
3. **Pre-response reasoning** — chain-of-thought "think before speaking"

### During Generation
4. **Response mode classification** — brief / adaptive / deep
5. **Token budget** — 400 / 800 / 1200 based on mode
6. **Temperature** — 0.4 (data-heavy) to 0.65 (conversational)
7. **Style nudge** — concise / balanced / strategic / deep_dive

### Post-Generation
8. **Response quality validation** — keyword-based context mismatch detection
   - Scripture page: detects if response talks about routines instead of scripture
   - Goal/task page: detects if response misses the title entirely
   - Journal page: detects if response ignores the entry content
9. **Auto-regeneration** — on mismatch, regenerates with explicit correction and lower temperature

---

## 11. Frontend Integration

### Chat Widget (templates/components/chat_widget.html)
- Slide-out drawer with text/voice input
- Image attachment (file upload + clipboard paste)
- Voice input via Web Speech API
- Quick reply buttons for proactive messages
- Markdown rendering for responses
- Clear conversation, fullscreen mode
- Context indicator (shows what page CoS can see)

### Page Content Capture
| Page Type | What's Captured |
|-----------|----------------|
| Reading Plan | Day, title, scripture refs, expanded verse text (2000 chars), context summary, commentary, reflection prompts, notes, progress |
| Journal Entry | Title, body (500 chars), mood |
| Task | Title, due date, description |
| Goal | Title, why it matters, progress %, milestones, target date |
| Habit | Title, streak, completion info |
| Prayer | Title, content |
| Fasting | Active fast duration/type, fasting history |
| Health | Current weight, workout info |
| Generic | URL, module name, page title |

### Session Activity Tracking
- Records page visits in `sessionStorage` (last 10 pages)
- Each entry: URL, page title, timestamp
- Sent with every chat message
- Injected into system prompt as "SESSION ACTIVITY"

---

## 12. Configuration & Personalization

### User Preferences (all user-configurable)
| Setting | Values | Effect |
|---------|--------|--------|
| `ai_enabled` | on/off | Master AI toggle |
| `personal_assistant_enabled` | on/off | CoS toggle |
| `ai_coaching_style` | direct/supportive/gentle | Tone and approach |
| `cos_display_name` | any string | "Max", "Jarvis", etc. |
| `cos_response_style` | concise/balanced/strategic/deep_dive | Response depth |
| `cos_v2_enabled` | on/off | Prompts, reflections, patterns |
| `faith_enabled` | on/off | Scripture integration |
| `ai_profile` | freetext | User-written self-description |
| `ai_personal_context` | freetext | AI-learned personal facts |
| `timezone_iana` | timezone | Time-aware features |
| `location_city` | city name | Weather queries |

### Blueprint Settings (governance layer)
- Operating style (Executive CoS, Calm Guide, Minimal, Coach, Custom)
- Life pillars ranked by priority
- Tier 1 protected behaviors (non-negotiables)
- Interruption tolerance (Low/Medium/High)
- Sleep & wake preferences

---

## 13. GAP ANALYSIS: What's Missing or Weak

### CRITICAL GAPS (would make CoS dramatically better)

#### Gap 1: No Proactive Push Delivery
**Current:** CoS can schedule prompts (`CosPromptSchedule`) but they only surface when the user opens the chat. The `CosPromptScheduler` runs every 6 hours and creates schedules, but there is no push mechanism.
**Impact:** CoS is fundamentally REACTIVE. A real chief of staff doesn't wait for you to walk into their office — they come find you.
**What's needed:** Push notifications (iOS/web), SMS delivery via the existing SMS app, email digests. The `apps/sms` app exists but isn't wired to CoS.

#### Gap 2: No General Knowledge / Web Search
**Current:** `web_search_service.py` only handles weather via Open-Meteo. When the user asks anything requiring real-time external information (recipes, news, general knowledge, how-to questions), CoS either makes something up or says "I don't have that information."
**Impact:** ChatGPT and Claude can answer any question. CoS can only answer about WLJ data + weather. This makes it feel limited.
**What's needed:** Integration with a web search API (Google Custom Search, Bing, or Serper) + general knowledge retrieval.

#### Gap 3: No Cross-Domain Pattern Analysis
**Current:** Pattern detection exists (`CosPatternService`) but it operates per-domain. There is no system that correlates across domains: "When your sleep drops below 6 hours, your journal mood is negative the next day and you skip workouts."
**Impact:** This is the biggest intelligence gap. A true chief of staff connects the dots. The data is ALL there — it just isn't being correlated.
**What's needed:** A cross-domain correlation engine that runs periodically, finds patterns across health/journal/habits/faith/goals, and injects insights into the system prompt.

#### Gap 4: No Predictive Goal Tracking
**Current:** CoS knows active goals and progress %. But it doesn't project whether the user is on track to hit their goal by the target date based on current velocity.
**Impact:** "You've lost 8 lbs in 6 weeks. At this rate, you'll hit your 20 lb goal by August — 2 months after your June target. You'd need to increase to 2 lbs/week to make it."
**What's needed:** Velocity calculation, trajectory projection, and proactive alert when goals are at risk.

#### Gap 5: No Pattern Insights Surfaced in Chat
**Current:** `CosPatternService` detects negative streaks, fatigue, consistency drops, positive momentum, and activity gaps. But these patterns are stored without being injected into the chat conversation's system prompt.
**Impact:** CoS has the pattern data but doesn't use it in responses. It should proactively say "I notice you've missed your Quiet Time 4 days in a row — is something going on?"
**What's needed:** Inject active patterns from `CosPatternService` into the system prompt, with instructions to reference them when relevant.

### SIGNIFICANT GAPS (important for parity with Claude/ChatGPT)

#### Gap 6: Missing Intents for Existing Data Types
The following data types have models AND query methods but NO chat intents:
- **Sleep** — `SleepEntry` model, `get_sleep_data()` exists, but no `log_sleep` intent
- **Water/Hydration** — `WaterEntry` model, `get_water_data()` exists, no `log_water` intent
- **Steps** — data queryable but no `log_steps` intent
- **Finance** — finance module exists but no intents for logging transactions or checking budgets
- **Cycle Tracking** — listed in feature URLs but no intent
- **Body Measurements** — no intent for waist, chest, etc.

#### Gap 7: No Undo/Correction Flow
**Current:** If CoS misinterprets an intent and logs wrong data, there's no "undo that" or "that's wrong, I meant..." flow. The user has to manually navigate to the data and delete it.
**What's needed:** An `undo_last_action` intent that reverses the most recent action, plus a "did you mean..." correction flow.

#### Gap 8: Calibration Answers Not Extracted
**Current:** Calibration answers are stored as raw text in `calibration_answers` but the learning extractor doesn't process them. The richest data about the user (from structured getting-to-know-you questions) isn't being fed into the learned profile.
**What's needed:** Run `extract_learning()` on calibration answers, or better — use AI to extract structured insights from calibration responses.

#### Gap 9: No Voice Output (TTS)
**Current:** Voice input exists (Web Speech API) but CoS cannot speak back.
**Impact:** For a mobile "executive assistant" experience, TTS would be transformative. "Good morning Danny. Your blood pressure this week averaged 128/82. You have 3 tasks due today."
**What's needed:** Web Speech Synthesis API or server-side TTS (OpenAI TTS API).

#### Gap 10: Cannot Edit Existing Data
**Current:** Intents are primarily "create" focused. Users can't say "change my weight entry from yesterday to 183" or "update my journal title." Only calendar events have full CRUD.
**What's needed:** `edit_weight`, `edit_journal`, `delete_last_weight` type intents, or a generalized `edit_last_<type>` intent.

#### Gap 11: No Scheduled Summaries
**Current:** Executive briefing only triggers on first-of-day or 4h+ gap. No weekly email, no daily digest, no end-of-day review.
**What's needed:** Weekly intelligence report (email/in-app), daily end-of-day summary, monthly progress review.

#### Gap 12: Hard-Coded Feature URLs
**Current:** The link directory in the system prompt is a static list (~30 URLs). If pages move or new features are added, CoS sends users to wrong/dead pages.
**What's needed:** Dynamic URL resolution from Django's URL registry, or a versioned link map.

### MODERATE GAPS

#### Gap 13: Action Contracts Only Partially Implemented
The `CosActionContract` system is well-designed but only `CalendarCosActions` and `JournalCosActions` are registered. Health, purpose, faith, and life modules have no action contracts.

#### Gap 14: No Contextual Follow-Up on Logged Data
When a user logs health data via intent, CoS confirms but doesn't analyze trends in the same response. "Logged your weight at 185. That's down 3 lbs from last week — great progress toward your goal." This requires combining the action confirmation with a trend query.

#### Gap 15: No Image Analysis Beyond LLM Vision
The chat supports image attachments, but there's no OCR service, food recognition, or structured data extraction from photos. A photo of a nutrition label should auto-parse calories/macros.

#### Gap 16: No Family/Household Coordination
CoS has no concept of shared users. Can't coordinate calendars, shared tasks, or family health tracking.

#### Gap 17: No Conversation Export
Users cannot export or save conversations for reference.

#### Gap 18: Rolling Summary Not Surfaced
The rolling conversation summary exists (`context_summary` on conversation) but it's generated by GPT-4o-mini and only used when messages exceed 20. It could be shown to the user as a "conversation summary" and used more proactively.

---

## 14. Comparison: CoS vs Claude Code vs ChatGPT

| Capability | CoS Today | Claude Code | ChatGPT |
|-----------|-----------|-------------|---------|
| **Context window** | 40 msgs (~8K tokens) | 200K tokens | 128K tokens |
| **Response quality** | GPT-4o, chain-of-thought | Claude Opus 4.6 | GPT-4o |
| **Intent recognition** | GPT-4o function calling (36 intents) | Full tool use | Function calling + GPTs |
| **Data access** | Full WLJ database (26 query types) | File system + web | Plugins + web + files |
| **Long-term memory** | RAG (500 memories, cosine similarity) | Persistent memory | Memory feature |
| **Web search** | Weather only | Web search tool | Full web search |
| **Proactive** | Scheduled prompts (no push) | Not proactive | Not proactive |
| **Self-correction** | Response validation + regeneration | Self-debugging | Not built-in |
| **Voice** | Input only (STT) | None | Input + output |
| **Multi-step reasoning** | Chain-of-thought prompt | Full planning/iteration | Chain-of-thought |
| **Code execution** | None | Full shell access | Code Interpreter |
| **Image analysis** | GPT-4o vision | Multimodal | GPT-4o vision |
| **Learning** | Regex patterns + RAG | Persistent memory | Memory feature |
| **Accountability** | Commitment contracts, drift detection, tier activation | None | None |
| **Personal data** | Full life data (health, journal, faith, goals, habits, tasks, calendar, finance) | None | None |

### CoS's Unique Advantages Over Claude/ChatGPT:
1. **Deep personal data access** — knows everything about the user's life
2. **Accountability system** — commitment contracts, drift detection, trajectory monitoring
3. **Proactive prompting** — scheduled check-ins for habits, goals, events
4. **Domain actions** — can create tasks, log health data, manage calendar via natural language
5. **Faith integration** — scripture-aware, prayer tracking, reading plan context
6. **Behavioral intelligence** — pattern detection, recalibration, governance

### Where Claude/ChatGPT Are Clearly Better:
1. **General knowledge** — can answer any question
2. **Web search** — real-time information access
3. **Multi-step reasoning** — can plan, iterate, self-debug
4. **Voice output** — ChatGPT can speak back
5. **Context window** — 16-32x larger
6. **File/image analysis** — deeper capabilities

---

## 15. Priority Roadmap to Close Gaps

### Tier 1: High Impact, Achievable Now

| # | Gap | Impact | Effort | Notes |
|---|-----|--------|--------|-------|
| 1 | **Cross-domain pattern analysis** | Transform CoS from data reporter to insight engine | Medium-High | Build a nightly job that correlates sleep↔mood↔workouts↔habits. Inject top 3 patterns into system prompt. |
| 2 | **Pattern insights in chat** | CoS uses its own pattern data | Low | Inject `CosPatternService` results into system prompt |
| 3 | **Missing intents (sleep, water, steps)** | Complete the data logging capability | Low | Copy existing intent patterns, add new handlers |
| 4 | **Predictive goal tracking** | Proactive goal risk alerts | Medium | Calculate velocity, project completion date, flag at-risk goals |
| 5 | **Calibration answer extraction** | Use the richest user data | Low | Run learning extractor on calibration answers |
| 6 | **Contextual follow-up on logged data** | Trend awareness on every log | Medium | After action, query recent trend and append to response |

### Tier 2: Medium Impact, Medium Effort

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 7 | **Undo/correction flow** | Error recovery | Medium |
| 8 | **General web search** | Answer any question | Medium |
| 9 | **Push notifications (SMS/iOS)** | True proactive CoS | High |
| 10 | **Weekly intelligence report** | Scheduled insight delivery | Medium |
| 11 | **Voice output (TTS)** | Full voice experience | Low-Medium |
| 12 | **Edit existing data intents** | Complete CRUD | Medium |

### Tier 3: Nice to Have

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 13 | **Dynamic URL resolution** | No stale links | Low |
| 14 | **Remaining action contracts** | Complete architecture | Medium |
| 15 | **Image analysis (OCR, food recognition)** | Smart photo processing | High |
| 16 | **Family/household** | Multi-user coordination | Very High |
| 17 | **Conversation export** | User convenience | Low |

---

*End of report. This document captures the complete state of CoS as of 2026-02-25, every capability, every data source, every engine, and every known gap.*
