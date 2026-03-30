# Whole Life Journey — Complete Documentation Suite

**Generated:** 2026-03-30
**Source:** Full codebase audit and reconciliation against actual system state
**Architecture Law:** Raw Data → Signals → CoS → LLM (LLM never determines truth)

---

## Table of Contents

1. [System Summary (Current State)](#1-system-summary-current-state)
2. [What's New (Last 30 Days)](#2-whats-new-last-30-days)
3. [User Guide](#3-user-guide)
4. [Admin Guide](#4-admin-guide)
5. [Technical Guide](#5-technical-guide)
6. [Context-Aware Help System](#6-context-aware-help-system)
7. [Changelog Audit Results](#7-changelog-audit-results)
8. [Gap Analysis](#8-gap-analysis)
9. [Recommended Next Actions](#9-recommended-next-actions)

---

# 1. System Summary (Current State)

## What Is WLJ?

Whole Life Journey (WLJ) is a Django 5.x personal operating system that tracks, coordinates, and coaches across every domain of daily life: health, faith, productivity, finance, relationships, nutrition, and purpose. It runs on Railway (PostgreSQL, Gunicorn, Celery) with a Swift/SwiftUI iOS app.

## Architecture in One Sentence

Raw user data flows through deterministic signal engines, which feed a State Assessment Engine (SAE), which powers a Chief of Staff (CoS) AI layer — the LLM is always last, never authoritative.

## System Scale (as of 2026-03-30)

| Metric | Value |
|--------|-------|
| Django apps | 34 installed |
| Intelligence engines | 15+ named engines |
| AI intent types | ~50 registered |
| SAE state builders | 28 domain modules |
| PIE insight rules | 26 across 13 domains |
| PRIE prediction rules | 10 across 6 domains |
| PGE guidance rules | 9+ |
| Celery Beat tasks | 22 scheduled |
| ISE registry tasks | 43+ (5min to 7-day intervals) |
| Help topics | 148 context-aware |
| Teaching destinations | 60+ |
| Tests | ~4,400 |
| Templates | 200+ across 28 directories |
| URL patterns | 30+ top-level mounts |

## Core Modules

| Module | Path | Purpose |
|--------|------|---------|
| Dashboard V2 | `/dashboard/` | Life Command Center — execution surface |
| Health | `/health/` | Weight, vitals, fitness, medicine, hydration, sleep, fasting |
| Faith | `/faith/` | Prayer, scripture, Bible reading plans, milestones |
| Journal | `/journal/` | Daily journaling with mood, prompts, archiving |
| Life/Organize | `/life/` | Tasks, projects, routines, inventory, recipes, pets, documents |
| Purpose | `/purpose/` | Goals, habits, life vision, values |
| Finance | `/finance/` | Accounts, transactions, budgets, financial goals |
| Meals | `/meals/` | Meal planning, pantry, recipes, receipt scanning |
| Calendar | `/calendar/` | Time Command Center — smart scheduling |
| Relationships | `/relationships/` | Contact management, interaction tracking, relational health |
| Notes | `/notes/` | Quick reference notes |
| Capture | `/capture/` | Voice recording, transcription, summarization |
| AI Assistant | `/assistant/` | Chief of Staff — conversational AI |
| Brain Training | `/health/cognitive/` | Sudoku, KenKen, Memory Matrix, Nonogram, Word Ladder |
| Medical | `/medical/` | Lab results, provider management |
| Scan | `/scan/` | AI camera for receipts and documents |
| Sports | `/sports/` | Team following |
| Billing | `/billing/` | Subscriptions, Stripe integration |

---

# 2. What's New (Last 30 Days)

## March 2026 Feature Releases

### Hydration System with Drink Type Intelligence (March 29-30)
**What changed:** Complete hydration tracking overhaul. Users can now log water, coffee, tea, electrolytes, creatine drinks, juice, and milk — each with a scientifically-grounded hydration coefficient (e.g., coffee counts as 0.9x, electrolytes as 1.05x). Creatine integration detects consistent creatine usage (4+ days in last 7) and adjusts hydration goals accordingly.
**User impact:** More accurate hydration tracking. Quick-log buttons on the health dashboard for common drinks. See both raw and effective hydration totals.
**Where:** Health dashboard hydration card, `/health/physical/water/`

### Life Alignment Cockpit (March 25)
**What changed:** Three domain "dials" on Dashboard V2 — Faith, Health, and Work/Purpose — each showing a 7-day execution score. Clickable to expand details. Health reads from SAE state; Faith uses the Execution Truth Engine.
**User impact:** At-a-glance view of life balance across your three core domains.
**Where:** Dashboard V2 home page, top section

### Smart Task Coaching (March 24)
**What changed:** Beth (the CoS persona) now provides deterministic task coaching — time-aware nudges, overdue reminders, and prioritization guidance. Pure function (no LLM), feeds into CoS context.
**User impact:** Proactive task reminders and coaching integrated into the AI assistant's responses.
**Where:** AI assistant responses when tasks are relevant

### Physical Intelligence Coach V2 (March 22-24)
**What changed:** Upgraded health coaching panel on Dashboard V2. Services: physical decision engine, body composition signals, outcome validation, conflict detection. Reads exclusively from SAE state.
**User impact:** Smarter health coaching that considers body composition, workout history, and recovery signals together.
**Where:** Dashboard V2, Physical Intelligence section

### Compliance Engine (March 20-22)
**What changed:** New pipeline tracking execution compliance across 6 domains (tasks, journal, workouts, medication, faith, routines). Domain adapters normalize events into a canonical `ComplianceEvent` model. Supports reconciliation and drill-down.
**User impact:** System can now tell you exactly what you committed to vs. what you actually did.
**Where:** Dashboard V2 reconciliation section

### Morning Reconciliation (March 18-20)
**What changed:** Dashboard V2 now shows items from yesterday that were missed (routines, medications, etc.). Users respond Yes/No to each item. Items disappear once addressed.
**User impact:** Start each morning by accounting for yesterday — no lost commitments.
**Where:** Dashboard V2, below the Goal Cockpit

### Routine System Maturity (March 15-18)
**What changed:** Routines gained activity-type completion (workout, journal, Bible reading routine items auto-complete from real data), bulk actions per time window, obligation types, execution truth integration, and adherence tracking.
**User impact:** Routine items that match real activities complete automatically. Bulk "Complete All" and "Skip All" per time window.
**Where:** `/life/routines/`

### Critical Signal V3 (March 14-16)
**What changed:** Third iteration of the behavioral signal system. Grouped event presentation, observability instrumentation, edge-case hardening. Signal presenter now shows adaptive cards with feedback buttons.
**User impact:** More relevant behavioral signals surfaced on the dashboard with Yes/No feedback.
**Where:** Dashboard V2 signal suggestions section

### Dashboard V2 Action Center Redesign (March 12-14)
**What changed:** Unified action center grouping items by time phase (Now, Upcoming, Later Today). Inline completion (checkbox directly in the dashboard), deduplication, progress badges.
**User impact:** One place to see everything due today with instant completion.
**Where:** Dashboard V2 main content area

### Execution Truth Engine (March 10-12)
**What changed:** New canonical engine answering "what was expected today?" and "what was completed?". Cross-domain bridges (e.g., "Prayer Time" routine item satisfies faith.prayer). Single source of truth for all completion queries.
**User impact:** Consistency — every part of the system agrees on what's done and what's not.
**Where:** Backend engine, powers Dashboard V2, Today Engine, compliance

### Today Engine (March 8-10)
**What changed:** Unified "what does today look like?" service. Collects routines, tasks, calendar events, and medication doses into time-bucketed dataset with foundation/overdue/coming_up/later classifications.
**User impact:** Powers the day view and "What should I do next?" queries.
**Where:** Backend engine, powers action center and CoS responses

### Goal Momentum Scoring (March 8)
**What changed:** Nightly-computed momentum scores per goal with 5 weighted drivers: habits (30%), tasks (20%), domain signals (20%), discipline (15%), recency (15%).
**User impact:** See which goals are gaining or losing momentum over time.
**Where:** Dashboard V2 goal section

### Celebration Detection (March 8)
**What changed:** System detects milestones (streaks, goal completions, discipline achievements, health breakthroughs) and surfaces celebration cards with cooldown periods.
**User impact:** Positive reinforcement when you hit milestones.
**Where:** Dashboard V2 celebration banner

### Receipt Photo Scanning (March 8)
**What changed:** Scan grocery receipts with phone camera. AI vision extracts items and prices. Items flow into pantry inventory.
**User impact:** Snap a receipt to update your pantry automatically.
**Where:** `/meals/receipts/upload/`, `/scan/`

### Meal Intelligence (March 2-5)
**What changed:** Full meal planning system with pantry management, household profiles, dietary profiles, storage tracking, and AI-powered meal suggestions.
**User impact:** Plan meals around what's in your pantry, get suggestions based on dietary preferences.
**Where:** `/meals/`

### Additional March Improvements
- **Workout movement types** — exercises now have proper movement categorization
- **Health screenshot analysis** — upload health app screenshots for AI parsing
- **iOS HealthKit integration** — bulk ingest from Apple Health (steps, heart rate, sleep, glucose, workouts, water, blood oxygen)
- **Relationship intelligence** — relational health scoring, @mention parsing, contact import
- **Finance module** — accounts, transactions, budgets, goals, recurring transactions, bank import
- **Calendar conflict detection** — smart scheduling with importance-based conflict resolution
- **CoS persona customization** — rename your AI assistant, adjust coaching style
- **Brain training games** — 5 cognitive exercise types
- **Signal feedback system** — thumbs up/down on behavioral signals

---

# 3. User Guide

## 3.1 Getting Started

### First Login
After creating your account, you'll complete a brief onboarding:
1. **Accept terms** — review and accept the terms of service
2. **Choose your modules** — enable the life domains you want to track (Health, Faith, Journal, Finance, etc.)
3. **Set your theme** — pick from 11 visual themes (Sanctuary, Scholar, Momentum, etc.)
4. **Meet your Chief of Staff** — your AI assistant introduces itself

### Navigation
- **Desktop:** Left sidebar rail with icons for each enabled module. Collapsible. Right rail has the AI assistant always visible.
- **Mobile:** Bottom tab bar with your top 3 modules plus Home and More. AI assistant accessible via floating chat bubble (bottom-right).
- **Top bar:** Search, notifications, settings.

### The Chief of Staff (CoS)
Your personal AI assistant is always available. It knows your schedule, health data, goals, and habits. It can:
- Answer questions about your data ("How's my blood pressure trending?")
- Log data by conversation ("I weighed 185 this morning")
- Plan your day ("What should I do next?")
- Coach you on priorities and commitments
- Surface insights and suggestions proactively

The CoS follows **LLM-last architecture**: it reads pre-computed state from deterministic engines, never invents data, and every claim is backed by your real records.

## 3.2 Dashboard (Life Command Center)

The dashboard at `/dashboard/` is your daily operating surface.

### Goal Cockpit
Three circular dials at the top show your 7-day execution scores:
- **Faith** — prayer, Bible reading, devotional practice
- **Health** — workouts, medication adherence, vitals logging
- **Work/Purpose** — task completion, goal progress, habit streaks

Tap a dial to see the breakdown. Only enabled domains appear.

### Celebrations
When you hit a milestone — a 7-day workout streak, a goal completion, a discipline achievement — a celebration banner appears. Tap "Reveal" to see the details. Dismiss when you're ready.

### Morning Reconciliation
Items you missed yesterday appear in a reconciliation section. For each:
- **Yes** — "I actually did this" (marks it retroactively)
- **No** — "I missed it" (logs the miss)

Items disappear once addressed.

### Action Center
The main section groups your day into time phases:
- **Now** — overdue items + currently due
- **Upcoming** — due within 90 minutes
- **Later Today** — everything else

Each item has a checkbox for instant completion. Progress badge shows "X/Y done". When everything's complete, you see a celebration state.

### Signal Suggestions
AI-generated suggestions appear as cards: "Have you logged your weight today?" "Time for your afternoon medication." Respond Yes/No to each — your feedback improves future suggestions.

### Physical Intelligence
A coaching panel that synthesizes your health data into actionable guidance — considering body composition, workout patterns, recovery signals, and nutrition together.

## 3.3 Health Tracking

### Overview (`/health/`)
The health home shows today's status for every tracked metric in a grid:
- Workout status, medication adherence by time window, blood glucose, sleep, hydration, active fasts, and priority actions.

### Weight (`/health/physical/weight/`)
Log weight entries with date, value, and optional notes. View trends over 30/60/90 days. The system detects trends and generates insights.

### Medications (`/health/medicines/`)
Set up medications with dose schedules (morning, afternoon, evening, bedtime). Track adherence per dose window. Overdue doses surface prominently on the dashboard.

### Fitness (`/health/physical/workouts/`)
Log workout sessions with exercises, sets, reps, and weight. Track personal records. Workout routine items auto-complete when a session is logged.

### Hydration (`/health/physical/water/`)
Log drinks with type selection:
- **Water** (1.0x coefficient) — full hydration credit
- **Coffee** (0.9x) — slight dehydration offset
- **Tea** (0.95x) — near-full credit
- **Electrolyte** (1.05x) — bonus hydration
- **Creatine drink** (1.0x) — also tracks creatine intake for goal adjustment
- **Juice, Milk, Other** (0.9x)

Quick-log buttons on the health dashboard: +16oz Water, +Coffee, +Creatine. See both raw and effective totals. If you're consistently taking creatine (4+ days in last 7), your hydration goal increases automatically.

### Fasting (`/health/physical/fasting/`)
Start and end fasting windows. Track fasting type, duration, and history. Active fasts show a progress bar on the health home.

### Blood Glucose (`/health/physical/glucose/`)
Log readings with context (fasting, before/after meal). View variability analysis and trends.

### Blood Pressure (`/health/physical/blood-pressure/`)
Log systolic/diastolic with category classification (normal, elevated, stage 1/2 hypertension).

### Heart Rate (`/health/physical/heart-rate/`)
Log resting and active heart rate. Track averages over time.

### Sleep (`/health/physical/sleep/`)
Log sleep duration and quality. View 7-day averages. Integrates with iOS HealthKit for automatic tracking.

### Steps (`/health/physical/steps/`)
View daily step counts (primarily from HealthKit sync). Track against daily goals.

### Blood Oxygen (`/health/physical/blood-oxygen/`)
SpO2 tracking with category classification.

### Cycle Tracking (`/health/cycle/`)
Opt-in menstrual cycle tracking with period logging, symptom tracking, and cycle predictions.

### Body Composition (`/health/body-composition/`)
Track body fat percentage, muscle mass, bone density, and related metrics.

## 3.4 Faith

### Home (`/faith/`)
Daily scripture verse, reading plan progress, prayer requests, and milestones.

### Bible Reading Plans (`/faith/reading-plans/`)
Follow structured reading plans. Track daily progress. Routine items for "Bible Reading" auto-complete when you mark a reading done.

### Prayer Requests (`/faith/prayers/`)
Log prayer requests with status tracking (active, answered, archived). View answered prayers as a gratitude record.

### Milestones (`/faith/milestones/`)
Record spiritual milestones and reflections.

### Scripture Memory (`/faith/memory-verse/`)
Track memory verses with practice reminders.

## 3.5 Journal

### Writing (`/journal/create/`)
Create journal entries with optional mood tracking, prompts, and @mentions (linking entries to people in your contacts). Entries support rich text.

### History (`/journal/`)
Browse past entries. Filter by date, mood, or search. Archive or soft-delete entries.

### Calendar View (`/journal/calendar/`)
Visual calendar showing which days have journal entries.

## 3.6 Life & Organization

### Tasks (`/life/tasks/`)
Simple, human-prioritized tasks. Features:
- **Priority levels:** Now, Soon, Someday
- **Commitment levels:** Foundational, Important, Flexible
- **Effort estimates** for planning
- **Project grouping** — assign tasks to projects
- **Due dates** with overdue highlighting
- **Module assignment** — link tasks to Health, Faith, etc.
- **Instant completion** — tap checkbox for animated completion
- **Skip** — forward-arrow to skip without completing
- **Search and filter** — by status, priority, text

### Routines (`/life/routines/`)
Named collections of daily habits grouped by time of day (Morning, Afternoon, Evening).

**Two types of routine items:**
1. **Binary** — manual check/uncheck (e.g., "Make bed")
2. **Activity** — auto-completes from real data (e.g., "Workout" completes when you log a WorkoutSession)

Supported activity types: workout, journal, bible_reading, faith_reflection, prayer, medicine, meal_logging.

**Actions per item:** Complete, Complete at Scheduled Time, Skip.
**Bulk actions per time window:** Complete All, Skip All.
**Adherence tracking:** View your routine completion rates over time at `/life/routines/adherence/`.

### Projects (`/life/projects/`)
Group related tasks under projects with status (active, paused, completed), priority (now, soon, someday), and progress tracking.

### Inventory, Recipes, Pets, Documents, Maintenance
Various life organization features under `/life/`.

## 3.7 Meals & Nutrition

### Meal Dashboard (`/meals/`)
Plan meals, manage your pantry, browse recipes, and get AI suggestions based on what you have available.

### Pantry (`/meals/pantry/`)
Track what's in your kitchen with expiration dates and storage locations.

### Receipt Scanning (`/meals/receipts/upload/`)
Photograph grocery receipts. AI extracts items and prices. Confirm and import to pantry.

### Meal Planning (`/meals/plan/`)
Create weekly meal plans with breakfast, lunch, dinner, and snacks.

## 3.8 Finance

### Dashboard (`/finance/`)
Overview of accounts, recent transactions, budget status, and financial goals.

### Accounts (`/finance/accounts/`)
Track bank accounts, credit cards, and investment accounts.

### Budgets (`/finance/budgets/`)
Set monthly budgets by category. Track spending against budgets.

### Goals (`/finance/goals/`)
Set savings goals with target amounts and dates.

### Transactions (`/finance/transactions/`)
Log and categorize transactions. Import from bank files.

## 3.9 Relationships

### People (`/relationships/`)
Manage contacts with relationship types (spouse, parent, friend, mentor, etc.). Track interaction frequency and last contact date.

### @Mentions
Type @Name anywhere (journal entries, tasks, notes) to link content to a person. The system tracks these interactions for relational health scoring.

### Relational Health Score
A 0-100 score based on: interaction frequency (stale contacts deduct), context diversity (one-dimensional relationships deduct), and consistency (weekly patterns add).

### Contact Import
Import contacts from iOS via vCard or the Contacts API.

## 3.10 Calendar (Time Command Center)

### Main View (`/calendar/`)
Smart calendar with event management. Features:
- **Conflict detection** — warns when events overlap
- **Importance-based resolution** — higher-importance events take priority
- **Recurrence** — daily, weekly, monthly patterns
- **Suggestions** — CoS can suggest schedule optimizations

## 3.11 Capture

### Record (`/capture/record/`)
Record voice memos. System transcribes and summarizes them.

### Upload (`/capture/upload/`)
Upload audio files for transcription.

### History (`/capture/`)
Browse past captures with transcripts and summaries.

## 3.12 Brain Training

### Hub (`/health/cognitive/`)
Five cognitive exercise types:
- **Sudoku** — logic puzzles at varying difficulty
- **KenKen** — mathematical reasoning
- **Memory Matrix** — visual memory challenges
- **Nonogram** — picture logic puzzles
- **Word Ladder** — vocabulary and word association

Track cognitive fitness scores and streaks.

## 3.13 AI Assistant

### How to Talk to Beth (or Your Custom CoS Name)

**Logging data by conversation:**
- "I weighed 185 this morning" → logs weight entry
- "Took my metformin" → logs medication dose
- "Just finished a 30-minute run" → logs workout
- "Had a chicken salad for lunch" → logs food entry

**Asking questions:**
- "How's my blood pressure trending?" → deterministic health summary
- "What's on my schedule today?" → Today Engine agenda
- "What should I do next?" → single priority action
- "How am I doing on my goals?" → goal momentum summary

**Managing tasks:**
- "Add a task: call the dentist" → creates task
- "Reschedule my meeting to 3pm" → modifies calendar event
- "Complete my morning routine" → marks routine items done

**The CoS will proactively:**
- Remind you of overdue medications
- Suggest logging when patterns are detected
- Alert you to health trends
- Coach on task prioritization
- Celebrate milestones

---

# 4. Admin Guide

## 4.1 Module Configuration

### Enabling/Disabling Modules
Modules are controlled by `ModuleDefinition` records in the database and per-user preferences via `UserModulePreference`. The context processor `navigation_modules_context` reads these to determine which modules appear in navigation.

**Module flags** (from `context_processors.py`):
- `journal_enabled`, `health_enabled`, `faith_enabled`, `life_enabled`, `purpose_enabled`
- `finance_enabled`, `relationships_enabled`, `capture_enabled`, `documents_enabled`
- `meals_enabled`, `sports_enabled`

### Sub-Feature Flags
Nested under `features` dict:
- `features.health.weight`, `features.health.fasting`, `features.health.blood_pressure`, etc.
- `features.organize.projects`, `features.organize.inventory`, etc.
- `features.goals.habits`, `features.goals.transformation`
- `features.faith.memory_verse`, `features.faith.reading_plans`

### Adding a New Module
1. Create the Django app in `apps/`
2. Register in `INSTALLED_APPS` in `config/settings.py`
3. Add URL patterns in `config/urls.py`
4. Create a `ModuleDefinition` fixture or migration
5. Add `capabilities.py` for domain registry auto-discovery
6. Add templates in `templates/<app_name>/`
7. Add help topics, teaching destinations, and release notes

## 4.2 Routine Setup and Scheduling

### Creating Routines
Routines are created at `/life/routines/create/`. Each routine has:
- **Name** (e.g., "Morning Routine")
- **Time of day** — determines grouping on the routine list
- **Active status** — inactive routines don't show in daily view

### Adding Routine Items
Each `RoutineSchedule` (item within a routine) specifies:
- **Name** — what the item is (e.g., "Take morning pills")
- **Type** — `binary` (manual) or `activity` (auto-complete from data)
- **Activity type** (if activity) — `workout`, `journal`, `bible_reading`, `faith_reflection`, `prayer`, `medicine`, `meal_logging`
- **Days of week** — which days this item applies
- **Scheduled time** — when it should be done
- **Importance** — foundational, important, or flexible
- **Obligation type** — categorization for compliance tracking

### Completion Sources
When a routine item is completed, the `completion_source` tracks how:
- `manual` — user checked it off
- `workout` — a WorkoutSession was logged
- `medicine` — medication dose was logged
- `bible` — Bible reading progress was recorded
- `journal` — journal entry was created
- `faith` — faith activity was recorded

### Legacy Migration
Old-style "routine tasks" (tasks with `is_routine=True`) can be migrated to the new Routine system via the migration UI at `/life/routines/migrate/`.

## 4.3 Medication Setup

### Creating Medications (`/health/medicines/`)
Each medication specifies:
- Name, dosage, unit
- Schedule: which time windows (morning, afternoon, evening, bedtime)
- Days of week
- Start/end dates

### Adherence Tracking
The system tracks adherence per dose window. Overdue doses are highlighted on the health dashboard and surfaced in the Action Center. The Execution Truth Engine includes medication completion in its daily assessment.

### CoS Integration
The CoS knows your medication schedule and can:
- Remind you of overdue doses
- Log doses via conversation
- Report adherence trends
- Flag missed doses in morning reconciliation

## 4.4 Signal Generation

### Signal Pipeline
1. **Raw data** enters the system (weight log, workout, medication dose, etc.)
2. **Django signals** fire `post_save` hooks that create `ExecutionSignal` records
3. **Signal engine** detects behavioral patterns from text (journal entries, workout notes)
4. **Health signals** builder creates deterministic health signals from canonical state
5. **Signal presenter** formats signals for dashboard display
6. **EAE** arbitrates which signals to surface based on noise budget and user preferences

### Expected Signal Types
Each domain registers expected signal types in the Domain Registry:
- Health: medication_adherence, sleep_recovery, activity_momentum, cardiometabolic_stability
- Faith: prayer_consistency, reading_plan_progress
- Journal: journaling_frequency, mood_trends
- Life: task_completion, routine_adherence

## 4.5 Data Integrity

### Soft Deletes
All major models use `soft_delete()` instead of hard deletion. The `SoftDeleteManager` filters out soft-deleted records by default. Soft-deleted records are purged after 30 days by the weekly Celery task.

### Idempotency
Calendar events use idempotency keys to prevent duplicate creation. The `sync_id` field on health records prevents duplicate HealthKit imports.

### Audit Logging
- `ComplianceEvent` — canonical execution audit trail
- `EAEDecisionLog` — intelligence surfacing decisions
- `FinanceAuditLog` — financial transaction audit
- `CosAutoShiftLog` — calendar auto-shift audit
- `HealthIngestionRun` — HealthKit bulk import audit

## 4.6 System Constraints

### Rate Limits
- Mobile health ingest: max 5,000 metrics per request, 1MB payload
- AI assistant: idempotency guard prevents double-processing
- CoS goal suggestions: max ~1/month per theme, 3 declines → opt-out

### Performance Rules
- **Never compute on request path** — all heavy analytics run in background workers
- Gunicorn has 2-4 workers; one slow request blocks the site
- Cache reads return `None` (not live computation fallback) when data isn't pre-computed
- SAME cycle runs every 60 seconds for signal aggregation

### Celery Beat Schedule (Key Tasks)
| Interval | Task |
|----------|------|
| 60s | SAME cycle (signals, metrics, engine) |
| 5min | ISE cycle, capture stuck entries |
| Daily 03:00 UTC | Health summary generation |
| Daily 06:00 UTC | Task priority recalculation, recurring task generation |
| Daily 07:00 UTC | Activity pattern computation, operating profiles |
| Daily 07:30 UTC | Dashboard momentum nightly |
| Daily 08:00 UTC | Celebration detection, expiration reminders |

---

# 5. Technical Guide

## 5.1 Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    User Interface                         │
│  Dashboard V2 │ Module Pages │ AI Chat │ Mobile API       │
└────────────┬─────────────────────────┬───────────────────┘
             │                         │
    ┌────────▼─────────┐     ┌────────▼─────────┐
    │  Today Engine     │     │  Deterministic    │
    │  (day aggregator) │     │  Router           │
    └────────┬─────────┘     └────────┬──────────┘
             │                         │
    ┌────────▼─────────┐     ┌────────▼──────────┐
    │  Execution Truth  │     │  Intent Service   │
    │  Engine           │     │  (OpenAI func     │
    │  (completion      │     │   calling)        │
    │   authority)      │     └────────┬──────────┘
    └────────┬─────────┘              │
             │              ┌─────────▼──────────┐
    ┌────────▼─────────┐   │  UAIO Orchestrator  │
    │  Signal Pipeline  │   │  (time, context,    │
    │  (exec signals,   │   │   safety, execute)  │
    │   health signals, │   └─────────┬──────────┘
    │   behavioral)     │             │
    └────────┬─────────┘   ┌─────────▼──────────┐
             │             │  Action Handlers    │
    ┌────────▼─────────┐   │  (CRUD on models)   │
    │  SAE State        │   └────────────────────┘
    │  (28 builders)    │
    └────────┬─────────┘
             │
    ┌────────▼─────────────────────────────────────┐
    │  Intelligence Pipeline (Post-Execution)       │
    │  PIE → PRIE → PGE → DBE → EAE → DNE          │
    └──────────────────────────────────────────────┘
             │
    ┌────────▼─────────┐
    │  CoS Context      │
    │  Builder          │
    │  (19 parallel     │
    │   builders)       │
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │  LLM (OpenAI)    │  ← ALWAYS LAST
    │  (response gen)   │
    └──────────────────┘
```

## 5.2 Three-Phase Intelligence Pipeline

### Phase 1: Interpretation
Engines that parse and understand user input before any action occurs.

| Engine | Acronym | Purpose |
|--------|---------|---------|
| Human Temporal Intelligence Engine | HTIE | Parses natural language time ("next Tuesday at 3pm") |
| Self-Learning Context Memory Engine | SLCME | Resolves contextual references ("mark that prayer answered") |
| Semantic Understanding Engine | SUE | Intent and entity parsing with confidence scoring |

### Phase 2: Execution
Engines that take action based on interpreted input.

| Engine | Acronym | Purpose |
|--------|---------|---------|
| Unified AI Orchestrator | UAIO | Central orchestration — time resolution, context, safety, execution |
| State Assessment Engine | SAE | Maintains 28-module user state from raw data |
| Execution Truth Engine | ETE | Single source of truth for expected vs. completed |

### Phase 3: Post-Execution
Engines that analyze, learn, and deliver intelligence after actions complete.

| Engine | Acronym | Purpose |
|--------|---------|---------|
| Proactive Insight Engine | PIE | 26 rules across 13 domains, event-driven insights |
| Predictive Intelligence Engine | PRIE | Linear regression projections, 10 rules across 6 domains |
| Proactive Guidance Engine | PGE | Guidance rules with ranking, delivery scheduling |
| Guidance Learning Optimization Engine | GLOE | Responsiveness scoring for PGE ranking |
| Daily Briefing Engine | DBE | Aggregates all engines into daily briefing |
| Intelligence Scheduler Engine | ISE | Cron-based orchestration of engine runs |
| Weekly Intelligence Report Engine | WIRE | Weekly longitudinal summaries |
| Evidence & Explainability Engine | E3 | Evidence chains and explanations for AI decisions |
| Delivery & Notification Engine | DNE | Multi-channel delivery with policies |
| Universal Arbitration Layer | UAL | Scenario classification, intervention styles |
| Executive Arbitration Engine | EAE | Decides what intelligence to surface and how |

### Blueprint & Governance
| Engine | Purpose |
|--------|---------|
| AI Persona Engine | Persona adaptation and rendering |
| AI Governance Engine | Alignment, consistency, strategy selection |
| AI Quality Engine | Response quality validation |

## 5.3 Today Engine + Execution Truth Engine

### Today Engine (`apps/core/today/today_engine.py`)

**Entry point:** `get_today_context(user)`

**Sources collected:**
1. Routine items (from Execution Truth Engine)
2. Tasks (due today or overdue)
3. Calendar events (excluding auto-generated)
4. Medication schedules

**Output structure:**
```python
{
    "all_items": [...],          # Every item, normalized
    "foundation": [...],         # Priority "foundational" items
    "overdue": [...],            # Scheduled < now, not completed
    "coming_up": [...],          # Now to now+90min
    "later": [...],              # After 90min
    "completed": [...],          # Done items
    "next": "Take morning meds"  # Locked next action
}
```

Each item normalized to: `{id, name, scheduled_time, time_str, completed, priority, source}`

**Architecture rule:** No coaching, no interpretation — pure data aggregation. Computes once, renders everywhere.

### Execution Truth Engine (`apps/core/execution/`)

**Entry point:** `get_execution_truth(user)`

**Three modules:**
1. **execution_truth_engine.py** — answers what is expected + completed today using ONLY raw authoritative data (RoutineLog, Task, WorkoutSession, JournalEntry, UserReadingProgress, MedicineLog)
2. **expected_map.py** — translates ETE output into flat boolean map for signal computers
3. **today_execution.py** — builds atomic `ExecutionItem` objects for Dashboard V2 with toggle URLs, grouping, and domain summaries

**Cross-domain bridges:**
- Routine item named "Prayer Time" → satisfies `faith.prayer`
- Routine item named "Bible Reading" → satisfies `faith.bible`

**Consumers:** Dashboard V2 Action Center, Today Engine, Compliance Engine, Signal Computers, SAE State Builders, CoS Context Builder.

## 5.4 Signal Pipeline

```
Raw Data Event (post_save)
    │
    ▼
ExecutionSignal Record ← execution_signals.py (Django signal handlers)
    │
    ▼
Signal Engine ← signal_engine.py (behavioral pattern detection from text)
    │
    ▼
Health Signals ← health_signals.py (deterministic from canonical state)
    │
    ▼
Signal Presenter ← signal_presenter.py (adaptive cards for dashboard)
    │
    ▼
EAE Arbitration ← eae_engine.py (noise budget, scoring, dedup)
    │
    ▼
Dashboard / CoS / DNE (surfaced to user)
```

**Signal types:**
- `possible_completion` — user may have completed something
- `effort_signal` — user showing effort in a domain
- `intent_signal` — user expressing intent
- `inconsistency_signal` — detected contradiction

**Health signal states:** strong, moderate, poor
**Health signal trends:** improving, declining, stable

## 5.5 Event Access System

### Event Adapters (`apps/core/ai_events/adapters/`)
17 domain-specific adapters normalize events from various models into a standard `EventRecord` format:
- blood_pressure, faith, fasting, finance, glucose, habits, heart_rate, journal, medication, nutrition, routine, sleep, steps, water, weight, workout

Each adapter: reads from the domain model, produces `EventRecord` objects with `event_type`, `timestamp`, `domain`, `summary`, `details`, `source_model`, `source_id`.

### Event Resolution (`apps/core/ai_events/resolver.py`)
Resolves follow-up questions ("what date was that?", "tell me more about my last workout") by looking up stored event context.

### Truth Depth (`apps/core/ai_events/truth_depth.py`)
Ensures event data returned to the CoS includes appropriate depth — surface summaries for overviews, full records for drill-downs.

## 5.6 Routing and Guardrails

### Deterministic Router (`apps/ai/deterministic_router.py`)
**LLM-last enforcement.** Messages are classified deterministically BEFORE any LLM call.

**Route priority:**
| Phase | Route | Terminal? |
|-------|-------|-----------|
| -1 | Event follow-up | Yes |
| 0a | Status query ("How's my day?") | Yes |
| 0b | Next action ("What should I do next?") | Yes |
| 0c | Day agenda | Yes |
| 1 | Registered data matchers | Yes |
| 1b | Routine time queries | Yes |
| 2 | Health summary fast path | Yes |
| 3 | Strict health status | Yes |
| 4 | Check-in prefilter | No (skips intent) |
| -- | Fallthrough to LLM | No |

**Action signal detection:** `has_action_signal()` checks for logging verbs, mutation verbs, numeric+unit patterns, BP patterns. If no action signal and `WLJ_INTENT_BYPASS_ENABLED`, skips the expensive intent recognition LLM call.

### Intent Service (`apps/ai/intent_service.py`)
**Recognition:** OpenAI function calling with domain-scoped tools (reduces ~19K tokens to ~2-6K). Post-processing safeguards: mutation verb enforcement, domain-lock, keyword safeguard for `set_cos_name`.

**Execution:** ~50 elif branches mapping intent names to `ActionHandler.handle_<intent>()` methods.

### Safety Gates
- **Correction filter** — detects "you're wrong" patterns, returns `no_action`
- **Learning Mode gate** — blocks all intents except learning mode toggle
- **Calibration gate** — only calibration intents during calibration
- **Domain-lock safeguard** — rejects intents from wrong domain
- **Validator gate** — post-response structural validation
- **Health intelligence validator** — health-specific claim verification
- **CoS purity guard** — ensures CoS never determines truth

## 5.7 Deterministic vs. LLM Boundaries

### Deterministic (No LLM)
- All signal computation
- All state building (SAE)
- Execution truth (expected + completed)
- Today Engine (day aggregation)
- Health signals
- Goal momentum scoring
- Compliance tracking
- Route classification
- Task coaching
- Physical intelligence decisions

### LLM-Involved (Always Last)
- Intent recognition (OpenAI function calling)
- Response generation (with full CoS context)
- Image analysis (vision API)
- Receipt text extraction
- Capture transcription and summarization
- Meal suggestions

### Hard Rules
1. LLM never determines truth — it reads pre-computed state
2. LLM never stores data directly — it produces intent + parameters, handlers do the CRUD
3. LLM failures are non-fatal — deterministic responses always available as fallback
4. Every LLM claim can be verified against SAE state

## 5.8 Caching and Invalidation

### Cache Strategy
- **SAE state:** Rebuilt on schedule (ISE cycle every 5 minutes) and on-demand after mutations
- **CoS context:** Built per-request with 6-thread parallelism, builders read from SAE cache
- **Dashboard sections:** HTMX lazy-loaded, each section independently cached
- **Navigation modules:** Cached 5 minutes per user
- **Favorites/Quick links:** Cached 60 seconds per user
- **Notifications count:** Cached 60 seconds per user

### Cache Keys (Pattern)
```
wlj:ops:{metric_name}          # Observability metrics
wlj:sae:{user_id}:{module}     # SAE state per user per module
wlj:dashboard:{user_id}:{section}  # Dashboard section data
```

### Invalidation Rules
- SAE state invalidated on any domain mutation (weight log, task complete, etc.)
- Dashboard sections re-fetched via HTMX polling or on explicit user action
- CoS context always built fresh (reads from SAE cache)
- Background SAME cycle (60s) recomputes signal aggregation and metrics

### Critical Rule: Never Compute on Request Path
```python
# CORRECT
def _get_expensive_metric():
    cached = cache.get("wlj:ops:metric_key")
    if cached is not None:
        return cached
    return None  # Return nothing — background worker will populate

# WRONG — blocks Gunicorn worker
def _get_expensive_metric():
    cached = cache.get("wlj:ops:metric_key")
    if cached is not None:
        return cached
    return compute_expensive_metric()  # NEVER do this
```

## 5.9 Observability and Telemetry

### SAME Cycle (Every 60 seconds)
Signal Aggregation, Metrics, Engine — the continuous background loop that:
1. Aggregates signals across all domains
2. Computes system health metrics
3. Runs engine health checks
4. Updates cache for real-time dashboard display

### Diagnostic Engine (`apps/core/ai_observability/diagnostic_engine.py`)
Self-diagnostic capability that checks engine health, signal health, validator health, and system maturity.

### Maturity Engine
Scores system maturity across 6 dimensions, tracking how complete and reliable each intelligence subsystem is.

### Ops Command Center (`/admin-console/ops/`)
Admin-only dashboard showing:
- System health scores
- Signal health per domain
- Engine status and latency
- Anomaly detection
- Operational feed of recent events

## 5.10 Mobile API

### Authentication Flow
1. Web session generates one-time exchange code (`POST /api/mobile/generate-code/`)
2. iOS app exchanges code for Bearer token (`POST /api/mobile/token/exchange/`)
3. All subsequent requests use `Authorization: Bearer <token>`

### Health Ingestion (`POST /api/mobile/health/ingest/`)
Bulk ingest from Apple HealthKit. Supports: steps, weight, sleep, heart rate, glucose, blood pressure, blood oxygen, body temperature, workouts, water, dietary nutrients, audio exposure, mobility.
- Max 5,000 metrics per request, 1MB payload
- `sync_id` deduplication prevents duplicate records
- Triggers async summary rebuilds for affected dates
- Creates `HealthIngestionRun` audit record

### Push Notifications
Register/unregister APNS device tokens. DNE delivers notifications via `apns_sender.py`.

### Contacts
Import iOS contacts via `POST /api/mobile/contacts/import/` (vCard parsing).

---

# 6. Context-Aware Help System

## Design

Each major view has a `help_context_id` that maps to a help topic. The help system auto-detects the current page and offers relevant guidance via a Help modal accessible from the top bar.

## Help Content by Module

### Dashboard V2 (`DASHBOARD_HOME`)
- **What you're seeing:** Your Life Command Center — a unified view of today's commitments, health status, and goal progress.
- **What it means:** The Goal Cockpit dials show your 7-day execution scores. Green = strong, yellow = moderate, red = needs attention. The Action Center shows everything due today.
- **What to do next:** Start with any overdue items (red), then work through "Now" items. Address Morning Reconciliation items. Check Signal Suggestions for personalized recommendations.
- **Behind the scenes:** The Execution Truth Engine compiles your commitments from routines, tasks, calendar, and medications. The Today Engine time-buckets everything. Signal computers detect behavioral patterns.

### Health Home (`HEALTH_HOME`)
- **What you're seeing:** Your physical health overview — today's status for every tracked metric.
- **What it means:** Each card shows your latest data with trend indicators. Red/yellow items need attention (overdue meds, missed workouts). The "Right Now" section prioritizes your next health action.
- **What to do next:** Address "Needs Attention" items first. Use quick-log buttons for water. Check medication time windows.
- **Behind the scenes:** Health signals are computed deterministically from your raw data. The Physical Intelligence Coach synthesizes signals across body composition, fitness, and recovery.

### Routines (`ROUTINE_LIST`)
- **What you're seeing:** Your daily habits organized by time of day.
- **What it means:** Checked items are done. Gray items are pending. "Activity" items (workout, journal, etc.) complete automatically when you do the activity. The progress bar shows today's completion rate.
- **What to do next:** Work through items in order. Use "Complete All" for batch completion. Skip items you intentionally won't do.
- **Behind the scenes:** The Routine system feeds into the Execution Truth Engine. Completion data powers your Goal Cockpit scores and Compliance Engine tracking.

### Tasks (`LIFE_TASKS`)
- **What you're seeing:** Your task list organized by time horizon — Overdue, Today, Tomorrow, Future, No Date.
- **What it means:** The "Next Up" badge marks your highest-priority actionable task. Red dates = overdue. "Non-Negotiable" badge = foundational commitment.
- **What to do next:** Complete the "Next Up" task. Address overdue items. Use the search to find specific tasks.
- **Behind the scenes:** Task priorities combine human-assigned priority with due-date urgency. The CoS uses task coaching to nudge you on important items.

### AI Assistant (`AI_ASSISTANT`)
- **What you're seeing:** Your Chief of Staff — a conversational AI that knows your data, schedule, and goals.
- **What it means:** Beth (or your custom name) can log data, answer questions, manage tasks, and provide coaching. Everything it says is backed by your actual data.
- **What to do next:** Ask anything about your data, schedule, or goals. Log entries by describing them naturally. Ask "What should I do next?" for prioritized guidance.
- **Behind the scenes:** Your message goes through the Deterministic Router first (no LLM for simple queries). If needed, Intent Recognition identifies your action. The Orchestrator executes it. Only response generation uses the LLM, and it receives your full CoS context.

### Faith (`FAITH_HOME`)
- **What you're seeing:** Your spiritual practice dashboard — today's scripture, reading plan progress, prayer requests, and milestones.
- **What it means:** Reading plan progress shows your consistency. Active prayer requests are tracked. Scripture memory shows your current verse.
- **What to do next:** Read today's assigned passage. Review prayer requests. Record any spiritual reflections.
- **Behind the scenes:** Faith activities feed into the Goal Cockpit's Faith dial. Bible reading routine items auto-complete when you mark readings done. Prayer patterns contribute to your faith state in SAE.

### Journal (`JOURNAL_HOME`)
- **What you're seeing:** Your journal entries with mood tracking and @mention linking.
- **What it means:** Entries are organized chronologically. Mood indicators show emotional trends. @mentions link entries to people in your contacts.
- **What to do next:** Write today's entry. Review recent entries for patterns. Use prompts if you need inspiration.
- **Behind the scenes:** Journal entries fire PIE events for insight generation. The Signal Engine detects behavioral patterns in your text. @mentions create Relationship Interactions that feed relational health scores.

### Finance (`FINANCE_DASHBOARD`)
- **What you're seeing:** Your financial overview — accounts, recent transactions, budget status, and goals.
- **What it means:** Budget bars show spending vs. limits. Goal progress shows savings vs. targets. Red = over budget or behind on goals.
- **What to do next:** Review recent transactions for categorization. Check budget status. Import new transactions if needed.
- **Behind the scenes:** Financial data feeds into the SAE finance state builder. The CoS can answer financial questions and the PIE generates finance-related insights.

### Meals (`MEALS_DASHBOARD`)
- **What you're seeing:** Your meal planning dashboard — current plan, pantry status, and recipe suggestions.
- **What it means:** The meal plan shows what's planned for each meal. Pantry shows what's available (and what's expiring). Suggestions are based on your dietary profile and pantry contents.
- **What to do next:** Review today's meal plan. Check pantry for expiring items. Scan a receipt to update inventory.
- **Behind the scenes:** Meal intelligence considers your dietary profile, household preferences, pantry inventory, and nutrition goals. Receipt scanning uses AI vision to extract items.

### Calendar (`CALENDAR_MAIN`)
- **What you're seeing:** Your time management view with events, routines, and scheduled tasks.
- **What it means:** Events show commitments and their importance level. Conflicts are highlighted. The CoS can suggest schedule optimizations.
- **What to do next:** Review upcoming events. Address any conflicts. Use the CoS to reschedule if needed.
- **Behind the scenes:** The Calendar Engine detects conflicts using importance-based resolution. Events use idempotency keys to prevent duplicates. The Today Engine includes calendar events in your daily view.

### Relationships (`RELATIONSHIPS_PEOPLE`)
- **What you're seeing:** Your contact list with relationship types, last interaction dates, and relational health indicators.
- **What it means:** Green indicators = healthy interaction frequency. Yellow/red = stale relationship. The health score considers frequency, diversity, and consistency.
- **What to do next:** Reach out to contacts you haven't interacted with recently. Use @mentions in journal entries to log interactions.
- **Behind the scenes:** The Relational Health Service computes scores. @Mention Parser detects name references across the system. Contact interactions are tracked cross-module via GenericForeignKey.

### Capture (`CAPTURE_LIST`)
- **What you're seeing:** Your voice recordings and transcriptions.
- **What it means:** Each capture shows the audio recording, transcript, and AI-generated summary. Status shows processing progress.
- **What to do next:** Record thoughts, ideas, or reflections. Review transcripts for accuracy.
- **Behind the scenes:** Audio is transcribed via AI, then summarized. Captures can link to journal entries or tasks. Pending captures show a banner in the navigation.

### Brain Training (`BRAIN_TRAINING_HUB`)
- **What you're seeing:** Five cognitive exercise types with difficulty levels and performance tracking.
- **What it means:** Scores track your cognitive fitness over time. Streaks encourage consistent practice. Different games target different cognitive skills (logic, memory, vocabulary).
- **What to do next:** Play a game daily. Try increasing difficulty as you improve. Track your streaks.
- **Behind the scenes:** Game generators create puzzles algorithmically. Performance data feeds into the brain training SAE state builder.

---

# 7. Changelog Audit Results

## Methodology
Cross-referenced the March 2026 changelog (~11,000 lines, 200+ entries) against actual codebase. Verified: code exists, models migrated, views wired, templates present.

## Verified Implementations (All Confirmed)

| Feature | Changelog Date | Code Status |
|---------|---------------|-------------|
| Hydration drink types + creatine | Mar 29-30 | CONFIRMED — models, views, templates, migrations |
| Life Alignment Cockpit | Mar 25 | CONFIRMED — service, views, templates, tests |
| Smart Task Coaching | Mar 24 | CONFIRMED — service, CoS integration, tests |
| Physical Intelligence V2 | Mar 22-24 | CONFIRMED — services, templates, tests |
| Compliance Engine | Mar 20-22 | CONFIRMED — models, service, 6 adapters, tests |
| Morning Reconciliation | Mar 18-20 | CONFIRMED — service, templates, views |
| Routine system maturity | Mar 15-18 | CONFIRMED — models, migrations, bulk actions, activity types |
| Critical Signal V3 | Mar 14-16 | CONFIRMED — signal engine, presenter, feedback, models |
| Dashboard V2 Action Center | Mar 12-14 | CONFIRMED — inline completion, dedup, progress badges |
| Execution Truth Engine | Mar 10-12 | CONFIRMED — 3 modules, cross-domain bridges |
| Today Engine | Mar 8-10 | CONFIRMED — service module, 4 collectors, tests |
| Goal Momentum | Mar 8 | CONFIRMED — model, service, Celery task, tests |
| Celebration Detection | Mar 8 | CONFIRMED — model, service, 7 types, cooldowns |
| Receipt Scanning | Mar 8 | CONFIRMED — scan app, meals integration, vision service |
| Meal Intelligence | Mar 2-5 | CONFIRMED — full app with pantry, plans, receipts |

## Partial Implementations

| Feature | Issue |
|---------|-------|
| Signal Taxonomy DB models | `SignalFeedback` and `ExecutionSignal` models defined in `apps/core/signals/models.py` but `apps/core/signals/` is NOT in `INSTALLED_APPS` and has NO migrations directory. The signal engine logic works but DB persistence of these specific models may not be operational. |

## Documentation Drift

| Item | Issue |
|------|-------|
| `docs/wlj_claude_features.md` | Last updated 2026-03-05. Missing ~15 features added in March. |
| `docs/ENGINE_COS_REFERENCE.md` | Engine inventory table doesn't list Today Engine or Execution Truth Engine |
| Release notes fixture | Covers through Mar 25 but missing hydration drink types (Mar 29-30) |
| Help topics fixture | 148 topics present. Missing context IDs for Morning Reconciliation and Compliance views |
| Teaching destinations | Missing entries for: routine adherence, morning reconciliation, compliance drill-down |

---

# 8. Gap Analysis

## A. Features in Code but NOT Documented

| Feature | Location | Status |
|---------|----------|--------|
| Hydration drink types + creatine integration | `apps/health/models.py` WaterEntry | NOT in features doc |
| Life Alignment Cockpit (3-domain dials) | `apps/dashboard_v2/services/cockpit_service.py` | NOT in features doc |
| Smart Task Coaching | `apps/life/services/task_coaching_builder.py` | NOT in features doc |
| Physical Intelligence Coach V2 | `apps/health/services/physical_decision.py` | NOT in features doc |
| Compliance Engine | `apps/dashboard_v2/compliance/` | NOT in features doc |
| Morning Reconciliation | `apps/life/services/morning_reconciliation.py` | NOT in features doc |
| Execution Truth Engine | `apps/core/execution/` | NOT in features doc, NOT in Engine Reference |
| Today Engine | `apps/core/today/` | NOT in features doc, NOT in Engine Reference |
| Goal Momentum scoring | `apps/dashboard_v2/services/momentum_service.py` | NOT in features doc |
| Celebration Detection | `apps/dashboard_v2/services/celebration_service.py` | NOT in features doc |
| Critical Signal V3 | `apps/core/signals/` | NOT in features doc |
| Daily Progress Snapshot | `apps/dashboard_v2/models.py` DailyProgressSnapshot | NOT in features doc |
| CosReflection system | `apps/cos/` | Minimal documentation |
| CosPromptSchedule system | `apps/cos/` | Minimal documentation |
| CosAutoShift audit logging | `apps/cos/` | NOT documented |
| CoS Action Registry | `apps/cos/services/action_registry.py` | NOT documented |
| Domain Registry validation | `apps/core/domain_registry/` | NOT documented |
| Expected Map (signal bridge) | `apps/core/execution/expected_map.py` | NOT documented |

## B. Features Documented but NOT in Code

| Feature | Document | Status |
|---------|----------|--------|
| None found | — | All documented features verified as present in code |

**Note:** All features listed in `docs/wlj_claude_features.md` and release notes were confirmed as existing in the codebase. No phantom documentation found.

## C. Features Potentially Violating Architecture

| Issue | Location | Violation |
|-------|----------|-----------|
| Signal models without migrations | `apps/core/signals/models.py` | `SignalFeedback` and `ExecutionSignal` models are defined but `apps/core/signals/` is not in `INSTALLED_APPS` and has no migrations. If these models need DB persistence, this is an incomplete implementation. If they're managed through another app, the architecture is unclear. |
| CoS context builder parallelism | `apps/core/ai_orchestrator/cos_context.py` | Uses `ThreadPoolExecutor(max_workers=6)` on the request path. While builders read from SAE cache (not raw DB), this is still 6 threads per request on a 2-4 worker Gunicorn. Under load, this could exhaust thread pools. |
| EAE `prompt_injection` naming | `apps/core/ai_eae/eae_engine.py` | The field `prompt_injection` is confusingly named — it's not a security injection but rather intelligence context inserted into the LLM prompt. Consider renaming to `prompt_context` or `intelligence_context` to avoid confusion in security audits. |

## D. Duplicate or Conflicting Logic

| Issue | Location A | Location B | Risk |
|-------|-----------|-----------|------|
| Completion tracking | `RoutineLog` completion in `apps/life/` | `ComplianceEvent` in `apps/dashboard_v2/compliance/` | Two systems tracking completion. ComplianceEvent reconciles from RoutineLog, so no conflict — but if either changes independently, they could drift. |
| Morning reconciliation | `apps/life/services/morning_reconciliation.py` | `apps/dashboard_v2/compliance/reconciliation.py` | Two reconciliation services exist. The life service and the compliance reconciliation service may have overlapping responsibilities. Need to verify they don't conflict. |
| State assessment | SAE state builders (28 modules) | CoS context builders (19 parallel) | CoS context reads from SAE, but some builders may duplicate calculations. No confirmed conflict, but the surface area is large. |

---

# 9. Recommended Next Actions

## Priority 1: Critical (Fix Before Next Release)

### 1.1 Signal Models Migration Gap
**Issue:** `apps/core/signals/models.py` defines `SignalFeedback` and `ExecutionSignal` but the app is not in `INSTALLED_APPS` and has no migrations directory.
**Action:** Either (a) add `apps.core.signals` to `INSTALLED_APPS` and create migrations, or (b) move these models to an app that already has migrations (e.g., `apps.core.ai_eae`), or (c) confirm the models are managed elsewhere and document this.
**Risk:** If these models are being used with ORM queries, they'll fail silently. If they're intentionally unmanaged, this should be documented.

### 1.2 Update Features Documentation
**Issue:** `docs/wlj_claude_features.md` is 25 days stale. 15+ features undocumented.
**Action:** Add sections for all items listed in Gap Analysis section A. Update the Table of Contents.

### 1.3 Update ENGINE_COS_REFERENCE.md
**Issue:** Missing Today Engine, Execution Truth Engine, Compliance Engine, Signal V3 from engine inventory.
**Action:** Add these to the engine inventory table. Update the Key File Paths section.

## Priority 2: Important (This Week)

### 2.1 Add Missing Help Topics
**Issue:** No `help_context_id` for Morning Reconciliation views, Compliance drill-down, Routine Adherence page.
**Action:** Add help topics to `apps/help/fixtures/help_topics.json`. Add teaching destinations to `apps/help/fixtures/teaching_destinations.json`.

### 2.2 Add Missing Release Notes
**Issue:** Hydration drink types (Mar 29-30) not yet in release notes fixture.
**Action:** Add entry to `apps/core/fixtures/release_notes.json`.

### 2.3 Reconciliation Service Deduplication Audit
**Issue:** Two reconciliation services identified (`apps/life/services/morning_reconciliation.py` and `apps/dashboard_v2/compliance/reconciliation.py`).
**Action:** Audit both services to confirm they serve distinct purposes and don't conflict. Document the boundary.

### 2.4 Fixture Loader Reset
**Issue:** If help topics or teaching destinations were modified, `apps/core/management/commands/load_initial_data.py` may need a reset flag update.
**Action:** Verify fixture loader covers all new fixture changes.

## Priority 3: Improvement (This Month)

### 3.1 Rename EAE `prompt_injection`
**Issue:** Confusing naming in security-sensitive context.
**Action:** Rename to `prompt_context` or `intelligence_context` across EAE engine and consumers.

### 3.2 CoS Thread Pool Analysis
**Issue:** 6-thread parallelism per request in CoS context builder.
**Action:** Profile under load. Consider reducing workers or adding connection pooling.

### 3.3 Document CoS Module Fully
**Issue:** `apps/cos/` has substantial functionality (reflections, prompts, goal suggestions, auto-shifts) that is minimally documented.
**Action:** Add a dedicated CoS section to the features doc and technical guide.

### 3.4 Domain Registry Documentation
**Issue:** The domain registry validation system (`apps/core/domain_registry/`) is undocumented.
**Action:** Add to technical guide. Document the 4-layer governance validation.

### 3.5 Architecture Decision Records
**Issue:** Key architectural decisions (Execution Truth Engine as single source, Today Engine as aggregator, Signal V3 grouped events) are only captured in changelog, not in formal decision records.
**Action:** Add entries to `docs/decisions.md` for the major March architectural additions.

---

*End of Documentation Suite — Generated 2026-03-30 via full codebase audit*
