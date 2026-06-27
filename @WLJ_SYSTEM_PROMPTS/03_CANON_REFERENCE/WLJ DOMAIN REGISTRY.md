WLJ DOMAIN REGISTRY

Version: 1.2
Last updated: 2026-06-26
Authority: Danny Jenkins
Project: Whole Life Journey (WLJ)
Load class: CANON (load for architecture / domain work)

> v1.2 (2026-06-26): corrected Sports to awareness-only (routine modification not
> implemented); added code-attribution note for MEDICAL (providers/intake live in
> apps/health). Travel remains a future domain. Verified against code 2026-06-23.

This document defines the canonical life domains used by the Whole Life Journey system.

Domains represent the major areas of life that produce structured data and signals used by the Chief of Staff (CoS).

All CoS reasoning must follow the WLJ architecture rule:

Raw Data → Signals / State → CoS → LLM Narration

Domains are responsible for generating deterministic signals that the CoS can interpret.

---

DOMAIN CLASSIFICATION

WLJ domains fall into three primary categories.

1. Behavioral Domains
2. Influence Domains
3. Context Domains

These classifications determine how signals are generated and interpreted.

---

RENDERER STATUS

The Signal Rendering Framework Phase 1 (apps/core/signals/signal_renderer.py) provides canonical, table-driven user prose for a subset of domains. Other domains still fall back to bespoke per-surface rendering.

Phase 1 wired (canonical renderer):

• Health
• Medical
• Faith
• Life (tasks / routines)

Phase 2 candidates (legacy bespoke rendering):

• Meals
• Purpose
• Journal
• Sleep (within Health, partially)
• Capture
• Brain Training
• Finance
• Relationships
• Sports
• Notes

Adding a new domain to the renderer requires entries in SIGNAL_RENDER_MAP and DOMAIN_PRIORITY.

---

BEHAVIORAL DOMAINS

Behavioral domains track what the user does.

These domains generate activity, performance, and trend signals.

---

HEALTH

Tracks physical health metrics and wellness indicators.

Raw Data Examples:

Weight
Body composition
Sleep
Heart rate
Activity
Blood glucose
Apple Health integrations
Workouts
Recovery indicators

Example Signals:

sleep_deficit
glucose_variability
training_load_high
weight_trend_down
recovery_low

---

MEDICAL

Tracks clinical health information.

> **Code-attribution note (as built, 2026-06-23):** `MedicalProvider` /
> `ProviderStaff` and medication-adherence computation actually live in
> `apps/health`, not `apps/medical`. There is no standalone `Medication` model —
> medications and supplements are unified under `Intake`. The MEDICAL domain here
> is the conceptual grouping; the canonical code owners are as noted.

Raw Data Examples:

Medications (code: `health.Intake`)
Lab results (code: `medical.LabResult`)
Medical providers (code: `health.MedicalProvider`)
Appointments
Medical conditions

Example Signals:

lab_abnormal
medication_adherence
follow_up_required
health_risk_detected

---

MEALS

Tracks food intake and nutrition.

Raw Data Examples:

Meals logged
Food items
Macros
Pantry items
Meal plans

Example Signals:

calorie_intake_high
protein_target_met
meal_skipped
nutrition_balance

---

PURPOSE

Tracks long-term goals, habits, and life direction.

Raw Data Examples:

Life goals
Habit goals
Habit entries
Goal progress
Momentum scoring

Example Signals:

goal_momentum_high
habit_streak
goal_stalled
discipline_signal

---

LIFE (TASKS & CALENDAR)

Tracks execution of daily responsibilities.

Raw Data Examples:

Tasks
Calendar events
Reminders
Appointments

Example Signals:

task_overload
schedule_conflict
deep_work_detected
task_completion_rate

---

FINANCE

Tracks financial planning and activity.

Raw Data Examples:

Budgets
Financial goals
Spending categories
Savings progress

Example Signals:

budget_drift
savings_progress
spending_spike
financial_goal_progress

---

RELATIONSHIPS

Tracks relational engagement and interaction patterns.

Raw Data Examples:

People
Interactions
Shared events
Relationship notes

Example Signals:

relationship_attention_gap
social_connection_high
family_engagement
friendship_activity

---

BRAIN TRAINING

Tracks cognitive activity and mental training.

Raw Data Examples:

Sudoku
Memory games
Training sessions
Performance metrics

Example Signals:

cognitive_training_streak
mental_engagement
performance_improvement

---

JOURNAL

Tracks reflection and emotional state.

Raw Data Examples:

Journal entries
Gratitude entries
Mood notes

Example Signals:

mood_trend
stress_signal
gratitude_signal
reflection_frequency

---

NOTES

Unified notes layer with attachments to other entities (tasks, goals, people, captures).

Raw Data Examples:

Notes
Note attachments
Linked entities (cross-domain references)

Example Signals:

note_thread_active
attached_to_goal
attached_to_relationship

---

CALENDAR ENGINE

Unified calendar / CoS Time Command Center. Distinct from Life (which owns tasks). Calendar Engine owns time blocks, recurring events, conflict detection, and the active-block resolver.

Raw Data Examples:

Calendar events
Recurring patterns
Time windows (morning / mid_morning / lunch / afternoon / evening / nightly)
Active block state

Example Signals:

active_block_resolved
schedule_conflict
free_block_detected
window_transition

---

INFLUENCE DOMAINS

Influence domains track learning, content consumption, and ideas that influence behavior.

These domains generate learning and influence signals.

---

CAPTURE

Capture records meetings, sermons, ideas, and conversations.

Raw Data Examples:

Audio recordings
Transcripts
Summaries
Key points
Action items
Quotes
Scripture references

Example Signals:

learning_event
influence_theme
leadership_theme
relationship_learning
action_item_detected
faith_learning

Capture is a cross-domain ingestion system that may produce signals affecting multiple domains.

---

FAITH

Tracks spiritual growth and engagement.

Raw Data Examples:

Prayer entries
Bible reading
Devotionals
Saved verses
Faith study notes

Example Signals:

prayer_streak
scripture_engagement
faith_learning
spiritual_growth

---

CONTEXT DOMAINS

Context domains modify how other signals are interpreted.

They provide environmental or situational context.

---

SPORTS

Tracks favorite teams, schedules, and game-day disruption to routines.

Raw Data Examples:

Followed teams
Game schedules
Game outcomes
Watch windows

Example Signals:

game_day_active
late_game_routine_risk
team_outcome_mood_modifier

Sports is an **awareness-only context domain (as built)**: `GameEvent` is the
single source of truth and the domain emits game-day signals into CoS context, but
it does **NOT** currently modify routine/calendar interpretation (late games do not
auto-shift evening routines). Routine-modification is a *future* capability, not
implemented. (Verified 2026-06-23 — see `04_DISCOVERY_REFERENCE/02c_Domain_Catalog_Capture_Notes_Sports_BrainTraining_Misc.md`.)

---

OWNER FINANCE

Internal cost telemetry and operational dashboards for the operator. Distinct from user-facing FINANCE.

Raw Data Examples:

LLM token spend
Infrastructure cost rollups
API call telemetry

Example Signals:

cost_drift
token_budget_breach
api_anomaly

This is operator-facing only. It is NOT surfaced to end users by the CoS.

---

TRAVEL (Future Domain)

Tracks location changes and travel activity.

Raw Data Examples:

Trips
Locations
Flights
Hotels
Travel dates

Example Signals:

travel_active
routine_disruption
timezone_shift
conference_mode
vacation_mode

Travel signals help interpret behavioral changes in other domains.

Example:

travel_active + workout_gap → expected behavior change

---

SYSTEM DOMAIN (INTERNAL)

Some signals originate from system-level analysis.

These are used for observability and CoS reasoning.

Examples:

signal_drought
system_anomaly
engine_failure
context_gap

These signals help monitor system health and intelligence quality.

---

SUPPORT APPS (Non-Domain Infrastructure)

These Django apps are part of WLJ but are NOT life domains — they do not emit user-facing signals through the CoS pipeline.

• billing — Stripe subscription + entitlement
• security — auth, MFA enforcement, audit logs
• sms — Twilio SMS delivery for reminders/notifications
• mobile — iOS/Android app integration shims (HealthKit, deep links)
• scan — receipt / document scanning (feeds Capture)
• help — in-app help topics + teaching destinations
• admin_console — operator dashboards
• cos — Chief of Staff action framework (CoS v2)
• core / core.ai_relationships / core.ai_eae — shared AI infrastructure
• ai — intent recognition + action handlers
• dashboard / dashboard_v2 — UI surfaces
• calendar_engine — covered above as a domain

Adding a new app to INSTALLED_APPS does NOT make it a domain. A domain emits canonical signals; a support app provides plumbing.

---

DOMAIN GOVERNANCE RULES

1. Every first-class domain must produce signals or structured state.

2. Domains must have a deterministic data source.

3. Signals must originate from structured data, not LLM interpretation.

4. Cross-domain patterns should be produced through signal analysis.

5. Domains must support observability where possible.

---

DOMAIN EXPANSION

Future domains may be introduced when a new life area produces meaningful signals for CoS reasoning.

Possible future domains:

Learning
Work / Career
Environment
Media consumption
Travel analytics
Personal knowledge base

All new domains must comply with the WLJ Architecture Laws.

---

END OF DOCUMENT