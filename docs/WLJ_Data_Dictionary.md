# WLJ Data Dictionary

**Last updated:** 2026-03-06
**Database:** PostgreSQL (production) / SQLite (development)
**Framework:** Django 5.x ORM

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Base Model Hierarchy](#2-base-model-hierarchy)
3. [User & Authentication](#3-user--authentication)
4. [Intelligence Engine Models](#4-intelligence-engine-models)
   - [SAE — State Awareness Engine](#sae--state-awareness-engine)
   - [PIE — Proactive Insight Engine](#pie--proactive-insight-engine)
   - [PRIE — Predictive Intelligence Engine](#prie--predictive-intelligence-engine)
   - [PGE — Proactive Guidance Engine](#pge--proactive-guidance-engine)
   - [DBE — Daily Briefing Engine](#dbe--daily-briefing-engine)
   - [WIRE — Weekly Intelligence Report Engine](#wire--weekly-intelligence-report-engine)
   - [DNE — Delivery & Notification Engine](#dne--delivery--notification-engine)
   - [E3 — Explain Engine](#e3--explain-engine)
   - [UAL — Unified Arbitration Logic](#ual--unified-arbitration-logic)
   - [EAE — Executive Arbitration Engine](#eae--executive-arbitration-engine)
   - [CDCE — Cross-Domain Correlation Engine](#cdce--cross-domain-correlation-engine)
   - [GLOE — Guidance Learning & Optimization Engine](#gloe--guidance-learning--optimization-engine)
   - [SLCME — Self-Learning Context Memory Engine](#slcme--self-learning-context-memory-engine)
   - [Blueprint Engine](#blueprint-engine)
   - [Governance Engine](#governance-engine)
   - [Feedback Loop Models](#feedback-loop-models)
   - [IOCD — Intelligence Observability Engine](#iocd--intelligence-observability-engine)
   - [SAME — System Anomaly Monitoring Engine](#same--system-anomaly-monitoring-engine)
   - [ISE — Intelligence Scheduling Engine](#ise--intelligence-scheduling-engine)
5. [Domain Models](#5-domain-models)
   - [Journal](#journal-app)
   - [Health](#health-app)
   - [Faith](#faith-app)
   - [Life (Organize)](#life-app)
   - [Purpose](#purpose-app)
   - [Finance](#finance-app)
   - [Medical (Lab Results)](#medical-app)
   - [Brain Training](#brain-training-app)
   - [Capture (Audio)](#capture-app)
6. [Supporting Models](#6-supporting-models)
   - [Core (Tags, Config, Themes)](#core-app)
   - [AI (Coaching, Prompts, Chat)](#ai-app)
   - [Admin Console (Tasks)](#admin-console-app)
   - [Help System](#help-app)
   - [Billing](#billing-app)
   - [Mobile & Devices](#mobile-app)
   - [Scan (Camera/OCR)](#scan-app)
   - [SMS Notifications](#sms-app)
   - [Security](#security-app)
   - [Relationships](#relationships)
7. [Engine-to-Table Matrix](#7-engine-to-table-matrix)
8. [Key Relationships & Common Joins](#8-key-relationships--common-joins)
9. [Keyword Search Index](#9-keyword-search-index)

---

## 1. Architecture Overview

WLJ uses a **three-phase intelligence pipeline** with 14+ engines:

```
Phase 1: INTERPRETATION
  SUE (Semantic Understanding) → stateless intent recognition
  SLCME (Context Memory) → learned phrase mappings
  HTIE (Temporal Intelligence) → stateless time resolution

Phase 2: EXECUTION
  UAIO (Orchestrator) → executes user intents via action handlers

Phase 3: POST-EXECUTION
  SAE → updates UserState (truth layer)
  PIE → generates Insights from state changes
  PRIE → generates Predictions from trends
  PGE → synthesizes Guidance from insights + predictions
  DBE → daily briefing aggregation
  WIRE → weekly report aggregation
  DNE → delivers notifications across channels
  E3 → attaches explanations to all outputs
  UAL → arbitrates competing signals
  EAE → executive-level prioritization
  CDCE → cross-domain correlations
  GLOE → learns user behavioral patterns
  Blueprint → daily schedule architecture
  SAME → system health monitoring
  IOCD → observability metrics
  ISE → schedules all engine runs
```

**Data Flow:**
```
User Action → SAE (UserState) → PIE (Insight) → PRIE (Prediction)
                                       ↓                ↓
                                  PGE (GuidanceItem) ←──┘
                                       ↓
                                  DNE (DeliveredNotification)
                                       ↓
                                  Feedback (Engagement tracking)
```

**CoS (Context of Self)** is NOT an engine — it's a read-only context builder that assembles data from SAE + PIE + PRIE + PGE into the AI system prompt for every chat interaction.

---

## 2. Base Model Hierarchy

All models inherit from one of these abstract bases:

### `TimeStampedModel` (abstract)
**File:** `apps/core/models.py`

| Field | Type | Notes |
|-------|------|-------|
| `created_at` | DateTimeField | auto_now_add=True |
| `updated_at` | DateTimeField | auto_now=True |

### `SoftDeleteModel` (extends TimeStampedModel, abstract)

| Field | Type | Notes |
|-------|------|-------|
| `status` | CharField(10) | Choices: `active`, `archived`, `deleted`. Default: `active`. Indexed |
| `deleted_at` | DateTimeField | null=True. Set when soft_delete() called |
| `created_at` | DateTimeField | Inherited |
| `updated_at` | DateTimeField | Inherited |

**Managers:**
- `objects` = SoftDeleteManager — default queries return only `status='active'`
- `all_objects` = models.Manager — bypasses soft delete filter

**Methods:** `soft_delete()`, `archive()`, `restore()`, `days_until_permanent_deletion`

**Important:** Default queries via `Model.objects.all()` exclude deleted/archived records. Use `Model.all_objects.all()` or `Model.objects.all_with_deleted()` to see everything.

### `UserOwnedModel` (extends SoftDeleteModel, abstract)

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | CASCADE. related_name = `%(class)ss` |
| `created_via` | CharField(20) | Choices: `manual`, `ai_camera`, `import`, `api`. Default: `manual` |
| `status` | CharField(10) | Inherited from SoftDeleteModel |
| `deleted_at` | DateTimeField | Inherited |
| `created_at` | DateTimeField | Inherited |
| `updated_at` | DateTimeField | Inherited |

**Inheritance Tree:**
```
models.Model
└── TimeStampedModel
    └── SoftDeleteModel
        └── UserOwnedModel  ← Most domain models inherit from this
```

---

## 3. User & Authentication

### `users.User` (AbstractBaseUser, PermissionsMixin)
**Table:** `users_user`
**File:** `apps/users/models.py`

The central user identity. Email-based authentication (no username).

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `email` | EmailField | **unique=True**. Login identifier |
| `first_name` | CharField(150) | blank=True |
| `last_name` | CharField(150) | blank=True |
| `avatar_url` | URLField | blank=True. Profile image |
| `is_active` | BooleanField | default=True |
| `is_staff` | BooleanField | default=False |
| `is_superuser` | BooleanField | default=False |
| `date_joined` | DateTimeField | auto_now_add |
| `last_login` | DateTimeField | null=True |

**Manager:** `UserManager` — `create_user(email, password)`, `create_superuser(email, password)`

**Key Relationships:**
- `user.preferences` → UserPreferences (OneToOne)
- `user.billingprofile` → BillingProfile (OneToOne)
- `user.entrys` → Journal entries
- Every UserOwnedModel has `user` FK back to this table

---

### `users.UserPreferences`
**Table:** `users_userpreferences`

Auto-created when User is created. Stores all user settings.

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | OneToOne → User | CASCADE. related_name='preferences' |
| `theme` | CharField | Choices: `light`, `dark`, `system`. Default: `system` |
| `modules_enabled` | JSONField | Dict of active modules per user |
| `timezone` | CharField(50) | Default: `UTC`. IANA timezone string |
| `ai_coaching_style` | FK → CoachingStyle | SET_NULL, null=True |
| `notifications_enabled` | BooleanField | default=True |
| `email_digest_frequency` | CharField | Choices: `daily`, `weekly`, `never` |
| `quiet_hours_start` | TimeField | null=True |
| `quiet_hours_end` | TimeField | null=True |
| `sms_enabled` | BooleanField | default=False |
| `sms_phone_number` | CharField(20) | blank=True |
| `sms_phone_verified` | BooleanField | default=False |
| `sms_categories` | JSONField | Dict of enabled SMS categories |
| `created_at` | DateTimeField | auto_now_add |
| `updated_at` | DateTimeField | auto_now |

**Common Join:** `User.objects.select_related('preferences')` — used everywhere for timezone, coaching style, notification settings.

---

### `users.TermsAcceptance`
**Table:** `users_termsacceptance`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `terms_version` | CharField | Version string |
| `accepted_at` | DateTimeField | auto_now_add |
| `ip_address` | GenericIPAddressField | null=True |

---

## 4. Intelligence Engine Models

### SAE — State Awareness Engine

**Purpose:** Central truth layer. Maintains ONE row per user containing a structured JSON snapshot of all module states. All other engines read from SAE rather than querying raw domain tables directly.

**File:** `apps/core/ai_state/models.py`

#### `core.UserState`
**Table:** `core_user_state`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | OneToOneField → User | CASCADE. **One row per user** |
| `state_data` | JSONField | Structured dict keyed by module (see below) |
| `schedule_instability_score` | FloatField | 0.0-1.0 |
| `schedule_instability_last_updated` | DateTimeField | null=True |
| `last_updated` | DateTimeField | auto_now=True |
| `created_at` | DateTimeField | auto_now_add=True |

**`state_data` JSON Structure:**

```json
{
  "health": {
    "weight_current": 185.0,
    "weight_trend": "declining",
    "weight_entries_90d": 45,
    "body_fat_current": 22.5,
    "sleep_avg_7d": 7.2,
    "bp_systolic": 120, "bp_diastolic": 80,
    "heart_rate_avg_7d": 68,
    "glucose_avg_7d": 95,
    "blood_oxygen_avg_7d": 97.5,
    "weight_goal": "lose",
    "weight_goal_target_date": "2026-06-01",
    "weight_goal_remaining": 15.0,
    "weight_goal_on_track": true
  },
  "goals": {
    "active_goal_count": 5,
    "next_deadline": "2026-04-01",
    "completion_rate": 0.72
  },
  "habits": {
    "active_habit_count": 8,
    "longest_streak": 45,
    "avg_completion_rate": 0.85
  },
  "journal": {
    "last_entry": "2026-03-05",
    "entry_frequency": "daily",
    "mood_distribution": {"happy": 40, "neutral": 35, "anxious": 25}
  },
  "faith": {
    "reading_streak": 12,
    "last_scripture_read": "Psalm 23",
    "answered_prayers": 3,
    "recent_prayer_titles": ["Family health", "Career guidance"],
    "urgent_prayers": 1,
    "bible_plan_name": "90-Day Bible"
  },
  "nutrition": {
    "calorie_avg_7d": 2100,
    "protein_avg_7d": 120,
    "macro_compliance": 0.8
  },
  "fasting": {
    "rolling_7d_hours": 48,
    "avg_fast_duration": 16.5,
    "compliance_score": 0.9
  },
  "fitness": {
    "workout_count_7d": 4,
    "total_volume": 25000,
    "pr_count": 2,
    "strength_trend": "increasing",
    "workout_calories_7d": 1800,
    "workout_minutes_7d": 240,
    "recent_workouts": [...]
  },
  "transformation": {
    "transformation_score": 72,
    "weight_trend_score": 8,
    "momentum_score": 7
  },
  "meals": {
    "pantry_item_count": 35,
    "expiring_item_names": ["milk", "eggs"],
    "has_dinner_planned": true,
    "dinner_recipe": "Grilled chicken"
  },
  "intervention": {
    "override_frequency_14d": 3,
    "override_count_10d": 2,
    "pending_friction_gates": 0,
    "deferrals_7d": 1,
    "tier1_skip_patterns": [],
    "consecutive_tier1_skips": 0
  },
  "feedback": {
    "insight_engagement": 0.75,
    "briefing_open_rate": 0.9,
    "preferred_briefing_length": "standard",
    "intervention_effectiveness": 0.65
  },
  "life_events": {
    "approaching_events": [...]
  },
  "scan": {
    "recent_analyses": [...]
  },
  "governance": {
    "declared_priorities": {...},
    "drift_scenario_count_14d": 2
  }
}
```

**How SAE is updated:** After every user action + ISE batch every 5 minutes. State builders in `apps/core/ai_state/state_builder.py` query raw domain tables and write the aggregated state.

**How SAE is read:** All engines call `get_state_value(user, 'module.key')` or `get_module_state(user, 'module')`. CoS context builder pre-loads `user._sae_cache` for efficient access.

---

### PIE — Proactive Insight Engine

**Purpose:** Generates factual insights from state changes. Rule-based (not AI-generated). Examples: "Your weight has declined 5 lbs over 30 days" or "Sleep average dropped below 6 hours".

**File:** `apps/core/ai_insights/models.py`

#### `core.Insight`
**Table:** `core_ai_insight`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `module` | CharField | e.g., `health`, `goals`, `faith`, `habits` |
| `insight_type` | CharField | e.g., `weight_trend_up`, `sleep_deficit`, `streak_milestone` |
| `severity` | CharField | Choices: `info`, `positive`, `warning`, `critical` |
| `title` | CharField | Human-readable title |
| `message` | TextField | Full insight text |
| `confidence_score` | FloatField | 0.0-1.0 |
| `explain_why` | TextField | blank=True. Plain-language explanation |
| `evidence` | JSONField | Structured evidence (data points, calculations) |
| `status` | CharField | Choices: `new`, `read`, `dismissed` |
| `dedupe_key` | CharField | **unique**. Prevents duplicate insights |
| `notified_at` | DateTimeField | null=True. When user was notified |
| `created_at` | DateTimeField | auto_now_add |
| `updated_at` | DateTimeField | auto_now |

**Deduplication:** `build_dedupe_key(user_id, insight_type, window_start, window_end, key_record_ids)` generates a hash. If an Insight with the same `dedupe_key` exists, it's skipped.

**Schedule:** Post-action trigger + ISE batch every 5 minutes.

**What reads PIE data:** PGE (to generate guidance), DBE (daily briefing snapshot), CoS context builder (recent insights in system prompt).

---

### PRIE — Predictive Intelligence Engine

**Purpose:** Generates trajectory projections using regression analysis. Examples: "At current rate, you'll reach goal weight by April 15" or "Sleep trend suggests deficit in 7 days".

**File:** `apps/core/ai_predictions/models.py`

#### `core.Prediction`
**Table:** `core_ai_prediction`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `prediction_type` | CharField | e.g., `weight_30d`, `sleep_trend`, `goal_completion` |
| `module` | CharField | e.g., `health`, `goals` |
| `predicted_value` | CharField | The predicted outcome |
| `predicted_date` | DateField | When the prediction is for |
| `confidence_score` | FloatField | 0.0-1.0 |
| `explanation` | TextField | Plain-language explanation |
| `evidence` | JSONField | Data points and methodology |
| `status` | CharField | Choices: `active`, `superseded`, `expired` |
| `dedupe_key` | CharField | **unique**. Prevents duplicates |
| `created_at` | DateTimeField | auto_now_add |
| `updated_at` | DateTimeField | auto_now |

**Status Lifecycle:** `active` → `superseded` (when newer prediction replaces it) → `expired` (past predicted_date).

**Schedule:** Post-action trigger + ISE batch every 1 hour.

**Validation:** PredictionOutcome (feedback model) tracks actual vs predicted values.

---

### PGE — Proactive Guidance Engine

**Purpose:** Synthesizes insights + predictions into actionable guidance items with full lifecycle tracking (acknowledge, dismiss, snooze, act upon).

**File:** `apps/core/ai_guidance/models.py`

#### `core.GuidanceItem`
**Table:** `core_guidance_item`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `title` | CharField | Guidance title |
| `message` | TextField | Full guidance text |
| `priority` | IntegerField | 1 (highest) to 5 (lowest) |
| `guidance_type` | CharField | e.g., `goal_risk`, `health_alert`, `habit_suggestion` |
| `source` | CharField | Choices: `pie_insight`, `prie_prediction`, `sae_state`, `composite` |
| `module` | CharField | Domain module |
| `confidence_score` | FloatField | 0.0-1.0 |
| `evidence` | JSONField | Supporting data |
| `is_active` | BooleanField | default=True |
| `is_read` | BooleanField | default=False |
| `expires_at` | DateTimeField | null=True |
| `acknowledged_at` | DateTimeField | null=True |
| `dismissed_at` | DateTimeField | null=True |
| `snoozed_until` | DateTimeField | null=True |
| `acted_upon_at` | DateTimeField | null=True |
| `action_type` | CharField | blank=True. What action was taken |
| `feedback` | TextField | blank=True. User feedback |
| `dedupe_key` | CharField | **unique** |
| `metadata` | JSONField | Additional context |
| `created_at` | DateTimeField | auto_now_add |
| `updated_at` | DateTimeField | auto_now |

**Lifecycle Methods:** `mark_read()`, `acknowledge()`, `dismiss()`, `snooze(until)`, `mark_acted_upon(action_type)`, `set_feedback()`, `deactivate()`

**Schedule:** ISE batch every 6 hours.

**Primary consumer:** CoS context builder injects active guidance into AI chat system prompt. DNE delivers via notifications.

---

### DBE — Daily Briefing Engine

**Purpose:** Generates a daily intelligence summary aggregating all engine outputs for a user. One briefing per user per day.

**File:** `apps/core/ai_briefing/models.py`

#### `core.DailyBriefing`
**Table:** `core_daily_briefing`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `briefing_date` | DateField | The date this briefing covers |
| `summary` | TextField | AI-generated narrative summary |
| `state_snapshot` | JSONField | SAE UserState at time of briefing |
| `guidance_snapshot` | JSONField | Active GuidanceItems |
| `insight_snapshot` | JSONField | Recent Insights |
| `prediction_snapshot` | JSONField | Active Predictions |
| `created_at` | DateTimeField | auto_now_add |

**Schedule:** ISE triggers daily (morning).

**Uniqueness:** One per user per day (briefing_date + user).

---

### WIRE — Weekly Intelligence Report Engine

**Purpose:** Weekly summary with state deltas — shows what changed week-over-week.

**File:** `apps/core/ai_weekly_report/models.py`

#### `core.WeeklyIntelligenceReport`
**Table:** `core_weekly_intelligence_report`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `week_start_date` | DateField | Monday of the week |
| `week_end_date` | DateField | Sunday of the week |
| `summary` | TextField | Narrative summary |
| `state_delta_snapshot` | JSONField | SAE state changes week-over-week |
| `insight_snapshot` | JSONField | Week's insights |
| `prediction_snapshot` | JSONField | Week's predictions |
| `guidance_snapshot` | JSONField | Guidance lifecycle summary |
| `learning_snapshot` | JSONField | GLOE learning updates |
| `created_at` | DateTimeField | auto_now_add |

**Schedule:** ISE triggers weekly (Sunday night / Monday morning).

---

### DNE — Delivery & Notification Engine

**Purpose:** Manages delivery of intelligence outputs across channels (in-app, email, SMS, push) with deduplication.

**File:** `apps/core/ai_delivery/models.py`

#### `core.DeliveredNotification`
**Table:** `core_delivered_notification`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `source_engine` | CharField | `PGE`, `DBE`, or `WIRE` |
| `source_object_type` | CharField | Model name (e.g., `GuidanceItem`) |
| `source_object_id` | CharField | PK of source object |
| `channel` | CharField | Choices: `in_app`, `email`, `sms`, `push` |
| `title` | CharField | Notification title |
| `message` | TextField | Notification body |
| `action_url` | CharField | blank=True. Deep link |
| `delivered_at` | DateTimeField | null=True |
| `status` | CharField | Choices: `queued`, `sent`, `skipped`, `failed` |
| `skip_reason` | CharField | blank=True. Why delivery was skipped |
| `dedupe_hash` | CharField | **unique**. Prevents duplicate delivery |
| `metadata` | JSONField | Additional context |
| `created_at` | DateTimeField | auto_now_add |

**Schedule:** ISE triggers every 10 minutes.

---

### E3 — Explain Engine

**Purpose:** Attaches human-readable explanations to all intelligence outputs for transparency.

**File:** `apps/core/ai_explain/models.py`

#### `core.ExplainRecord`
**Table:** `core_explain_record`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `source_engine` | CharField | `PIE`, `PRIE`, `PGE`, `DBE`, `WIRE` |
| `source_object_type` | CharField | Model name |
| `source_object_id` | CharField | PK of source object |
| `title` | CharField | Explanation title |
| `explanation` | TextField | Full explanation |
| `confidence_explanation` | TextField | Why the confidence score is what it is |
| `evidence` | JSONField | List of evidence items |
| `created_at` | DateTimeField | auto_now_add |

---

### UAL — Unified Arbitration Logic

**Purpose:** Arbitrates competing signals when multiple engines want to surface guidance simultaneously. Manages user cognitive load.

**File:** `apps/core/ai_arbitration/models.py`

#### `core.ArbitrationDecisionLog`
**Table:** `core_arbitration_decision_log`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `timestamp` | DateTimeField | |
| `dominant_scenario` | CharField | Active scenario (e.g., `DRIFT_RISK`, `MOMENTUM`) |
| `secondary_scenarios` | JSONField | Other active scenarios |
| `fused_signals` | JSONField | Combined signal data |
| `confidence_level` | CharField | `LOW`, `MODERATE`, `HIGH` |
| `capacity_state` | CharField | `CRITICAL`, `LOW`, `NORMAL`, `HIGH_CAPACITY` |
| `capacity_score` | FloatField | Computed capacity |
| `intervention_style` | CharField | Intervention approach |
| `surfaced_items` | JSONField | Items shown to user |
| `suppressed_items` | JSONField | Items withheld |
| `narrative` | TextField | Arbitration reasoning |
| `raw_signals` | JSONField | All input signals |
| `scenario_scores` | JSONField | Scored scenarios |
| `user_response` | CharField | blank=True. How user responded |
| `outcome_score` | FloatField | null=True. Effectiveness |
| `created_at` | DateTimeField | auto_now_add |

#### `core.DailyCapacityLog`
**Table:** `core_daily_capacity_log`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | unique_together with `date` |
| `date` | DateField | |
| `capacity_score` | FloatField | Composite capacity score |
| `capacity_state` | CharField | `CRITICAL`/`LOW`/`NORMAL`/`HIGH_CAPACITY` |
| `sleep_deficit` | FloatField | Hours below target |
| `mood_decline` | FloatField | Mood trend metric |
| `emotional_load` | FloatField | Stress indicator |
| `schedule_overload` | FloatField | Over-scheduled metric |
| `open_loop_count` | IntegerField | Unresolved items |

#### `core.ScenarioHistory`
**Table:** `core_scenario_history`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | unique_together with `date` |
| `date` | DateField | |
| `dominant_scenario` | CharField | That day's dominant scenario |
| `intervention_style` | CharField | Style used |
| `capacity_state` | CharField | User capacity |
| `suppressed_count` | IntegerField | Items suppressed |
| `surfaced_count` | IntegerField | Items surfaced |

#### `core.WeightAdjustment`
**Table:** `core_weight_adjustment`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | unique_together with scenario+signal |
| `scenario` | CharField | |
| `signal` | CharField | |
| `baseline_weight` | FloatField | Starting weight |
| `adjustment_delta` | FloatField | ±0.10 adjustments |
| `last_updated` | DateTimeField | |

#### `core.InterventionResponseLog`
**Table:** `core_intervention_response_log`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | unique_together with date+scenario |
| `date` | DateField | |
| `scenario` | CharField | |
| `surfaced_count` | IntegerField | |
| `complied_count` | IntegerField | |
| `ignored_count` | IntegerField | |
| `overrode_count` | IntegerField | |

#### `core.RecentNudgeMemory`
**Table:** `core_recent_nudge_memory`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `surfaced_at` | DateTimeField | |
| `scenario` | CharField | |
| `semantic_tag` | CharField | Content tag for dedup |
| `trace_id` | CharField | Engine trace reference |

**Short-lived:** Records expire after 12 hours to prevent nudge fatigue.

---

### EAE — Executive Arbitration Engine

**Purpose:** Top-level prioritization engine that manages escalation levels, focus management, and noise budgets per user.

**File:** `apps/core/ai_eae/models.py`

#### `core.EAEState`
**Table:** `ai_eae_eaestate`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | **One row per user** |
| `escalation_level` | IntegerField | Current escalation (0-5) |
| `escalation_since` | DateTimeField | null=True |
| `escalation_peak_drift` | FloatField | null=True |
| `drift_risk_severity` | CharField | |
| `primary_focus_label` | CharField | blank=True |
| `primary_focus_module` | CharField | blank=True |
| `primary_focus_set_at` | DateTimeField | null=True |
| `focus_changes_today` | IntegerField | default=0 |
| `focus_date` | DateField | null=True |
| `noise_budget_used_today` | IntegerField | default=0 |
| `noise_budget_date` | DateField | null=True |
| `last_arbitration_at` | DateTimeField | null=True |
| `updated_at` | DateTimeField | auto_now |

#### `core.EAEDecisionLog`
**Table:** `ai_eae_eaedecisionlog`

Append-only audit trail of every EAE prioritization decision.

| Field | Type | Notes |
|-------|------|-------|
| `decision_id` | UUIDField | PK |
| `user` | FK → User | |
| `channel` | CharField | |
| `created_at` | DateTimeField | auto_now_add |
| `escalation_level` | IntegerField | |
| `drift_risk_severity` | CharField | |
| `tone_band` | CharField | |
| `primary_focus_label` | CharField | |
| `cognitive_units_json` | JSONField | Items surfaced |
| `suppressed_items_json` | JSONField | Items suppressed |
| `total_candidates` | IntegerField | |
| `surfaced_count` | IntegerField | |
| `suppressed_count` | IntegerField | |
| `noise_budget_used` | IntegerField | |
| `noise_budget_max` | IntegerField | |
| `override_events_json` | JSONField | |
| `reason_codes` | JSONField | |
| `source_engines` | JSONField | |
| `arbitration_duration_ms` | IntegerField | |

#### `core.EAEOverride`
**Table:** `ai_eae_eaeoverride`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | unique_together with signal_type |
| `signal_type` | CharField | `ENGINE:type` format |
| `override_type` | CharField | `PERMANENT` or `TEMPORARY` |
| `strike_count` | IntegerField | 1-3. Three strikes = permanent suppression |
| `cooldown_until` | DateTimeField | null=True |
| `temporary_count_14d` | IntegerField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.EAEEscalationEvent`
**Table:** `ai_eae_eaeescalationevent`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `direction` | CharField | `up` or `down` |
| `from_level` | IntegerField | |
| `to_level` | IntegerField | |
| `trigger_reason` | CharField | |
| `drift_risk_at_event` | FloatField | |
| `created_at` | DateTimeField | |

---

### CDCE — Cross-Domain Correlation Engine

**Purpose:** Discovers correlations across domains (e.g., "Poor sleep correlates with lower mood scores").

**File:** `apps/core/ai_cross_domain/models.py`

#### `core.DomainCorrelation`
**Table:** `core_domain_correlation`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | CASCADE |
| `domain_a` | CharField | First domain (e.g., `health`) |
| `domain_b` | CharField | Second domain (e.g., `journal`) |
| `correlation_type` | CharField | e.g., `sleep_mood`, `exercise_energy` |
| `strength` | CharField | `strong`, `moderate`, `weak` |
| `strength_score` | FloatField | Numeric strength |
| `direction` | CharField | `positive` or `inverse` |
| `narrative` | TextField | Human-readable description |
| `evidence_summary` | TextField | Summary of supporting data |
| `evidence` | JSONField | Detailed data points |
| `data_points` | IntegerField | Number of data points used |
| `status` | CharField | `active`, `superseded`, `expired` |
| `dedupe_key` | CharField | **unique** |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

**Schedule:** ISE triggers every 6 hours.

---

### GLOE — Guidance Learning & Optimization Engine

**Purpose:** Learns behavioral patterns from user interactions. Transparent — user can see what the system has learned about them.

**File:** `apps/core/ai_learning/models.py`

#### `core.UserLearnedProfile`
**Table:** `core_user_learned_profile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | **One row per user** |
| `stated_values` | JSONField | List of stated values |
| `repeated_frustrations` | JSONField | Recurring frustrations |
| `recurring_goals` | JSONField | Goals mentioned repeatedly |
| `non_negotiables` | JSONField | Things user won't compromise on |
| `relationship_priorities` | JSONField | Important relationships |
| `identity_statements` | JSONField | "I am..." statements |
| `motivational_triggers` | JSONField | What motivates the user |
| `avoidance_patterns` | JSONField | What user avoids |
| `health_concerns` | JSONField | Health worries |
| `life_event_mentions` | JSONField | Significant life events |
| `commitments_made` | JSONField | Commitments to self |
| `explanation_preferences` | JSONField | How user likes info presented |
| `time_patterns` | JSONField | When user is active/productive |
| `total_extractions` | IntegerField | Total learning events |
| `last_extraction_at` | DateTimeField | null=True |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

All JSON fields are lists of extracted strings, injected into the AI system prompt to personalize responses.

#### `core.LearningExtraction`
**Table:** `core_learning_extraction`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | |
| `category` | CharField | Matches UserLearnedProfile field names |
| `extracted_text` | CharField | What was learned |
| `source_message` | TextField | The message it was extracted from |
| `confidence` | FloatField | 0.0-1.0 |
| `is_confirmed` | BooleanField | Whether user confirmed |
| `created_at` | DateTimeField | |

---

### SLCME — Self-Learning Context Memory Engine

**Purpose:** Learns phrase-to-meaning mappings from user clarifications (e.g., "gym" → health.workout).

**File:** `apps/core/ai_memory/models.py`

#### `core.LearnedMapping`
**Table:** `core_learned_mapping`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `phrase` | CharField | User's phrase |
| `meaning_type` | CharField | What it maps to |
| `meaning_identifier` | CharField | Specific identifier |
| `confidence_score` | FloatField | 0.0-1.0, increases with use |
| `usage_count` | IntegerField | Times used |
| `last_used_at` | DateTimeField | |
| `is_active` | BooleanField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.ContextSnapshot`
**Table:** `core_context_snapshot`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `context_type` | CharField | Page/entry type |
| `context_identifier` | CharField | Specific page/entry |
| `metadata` | JSONField | Additional context |
| `created_at` | DateTimeField | |

#### `core.ClarificationLog`
**Table:** `core_clarification_log`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `original_input` | TextField | What user said |
| `clarification_question` | TextField | What system asked |
| `user_response` | TextField | User's clarification |
| `resolved_meaning` | CharField | Final resolved meaning |
| `learned_mapping` | FK → LearnedMapping | null=True |
| `created_at` | DateTimeField | |

---

### Blueprint Engine

**Purpose:** Manages user's Personal Operating Blueprint — priorities, schedule architecture, drift detection, and interventions.

**File:** `apps/core/blueprint/models.py`

#### `core.PersonalOperatingBlueprint`
**Table:** `core_personaloperatingblueprint`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | **One row per user** |
| `total_weekly_time_blocks` | IntegerField | |
| `tier1_weekly_hours` | FloatField | Non-negotiable hours |
| `tier2_weekly_hours` | FloatField | Important hours |
| `protected_percentages` | JSONField | Per-tier protection |
| `stress_recovery_target` | FloatField | |
| `operating_style` | CharField | |
| `notes` | TextField | blank=True |
| `is_active` | BooleanField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.NonNegotiable`
**Table:** `core_nonnegotiable`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `blueprint` | FK → PersonalOperatingBlueprint | |
| `title` | CharField | |
| `description` | TextField | |
| `tier` | IntegerField | 1-5 priority tier |
| `weekly_target_hours` | FloatField | |
| `weekly_target_completions` | IntegerField | |
| `scheduling_flexibility` | CharField | `rigid` or `flexible` |
| `allowed_skip_count_14d` | IntegerField | |
| `protection_status` | CharField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.ArchitecturePlan`
**Table:** `core_architectureplan`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `plan_date` | DateField | The day this plan covers |
| `summary` | TextField | |
| `blocks` | JSONField | List of time blocks |
| `total_plan_hours` | FloatField | |
| `tier1_hours` | FloatField | |
| `tier2_hours` | FloatField | |
| `buffer_hours` | FloatField | |
| `built_at` | DateTimeField | |
| `created_at` | DateTimeField | |

#### `core.ScheduledBlock`
**Table:** `core_scheduledblock`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `architecture_plan` | FK → ArchitecturePlan | |
| `title` | CharField | |
| `time_start` | DateTimeField | |
| `time_end` | DateTimeField | |
| `duration_minutes` | IntegerField | |
| `tier` | IntegerField | 1-3 |
| `is_protected` | BooleanField | |
| `is_recurring` | BooleanField | |
| `recurring_type` | CharField | blank=True |
| `recurring_end_date` | DateField | null=True |
| `block_type` | CharField | |
| `related_object_id` | CharField | blank=True |
| `status` | CharField | `scheduled`, `completed`, `missed`, `skipped` |
| `actual_start` | DateTimeField | null=True |
| `actual_end` | DateTimeField | null=True |
| `completion_notes` | TextField | blank=True |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.DriftEvent`
**Table:** `core_driftevent`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `module` | CharField | Which module drifted |
| `event_type` | CharField | `skip`, `override`, `renegotiation` |
| `occurrence_date` | DateField | |
| `drift_severity` | FloatField | |
| `description` | TextField | |
| `related_id` | CharField | blank=True |

#### `core.DriftScore`
**Table:** `core_driftscore`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `score_date` | DateField | |
| `total_drift_score` | FloatField | Aggregate daily drift |
| `breakdown` | JSONField | Per-module drift details |
| `updated_at` | DateTimeField | |

#### `core.InterventionLog`
**Table:** `core_interventionlog`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `intervention_date` | DateField | |
| `escalation_level` | IntegerField | |
| `intervention_type` | CharField | |
| `outcome_status` | CharField | |
| `outcome_date` | DateField | null=True |
| `notes` | TextField | |
| `created_at` | DateTimeField | |

#### `core.FrictionGateLog`
**Table:** `core_frictiongatelog` *(Blueprint model — may be embedded in blueprint tables)*

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `gate_date` | DateField | |
| `gate_reason` | CharField | Why friction gate was shown |
| `user_response` | CharField | `complied`, `deferred`, `renegotiated` |
| `notes` | TextField | |
| `created_at` | DateTimeField | |

---

### Governance Engine

**File:** `apps/core/ai_governance/models.py`

#### `core.GovernanceProfile`
**Table:** `core_governanceprofile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `module_key` | CharField | e.g., `health`, `faith` |
| `display_name` | CharField | Human-readable name |
| `commitment_level` | CharField | `non_negotiable`, `important`, `flexible` |
| `importance_weight` | FloatField | Numeric weight |
| `escalation_preference` | CharField | `gentle`, `direct`, `firm` |
| `declared_reason` | TextField | Why this matters |
| `tied_goal_ids` | JSONField | Related goals |
| `review_interval_days` | IntegerField | |
| `last_reviewed_at` | DateTimeField | null=True |
| `is_active` | BooleanField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

**unique_together:** `[user, module_key]`

#### `core.GovernanceAlignmentSession`
**Table:** `core_governancealignmentsession`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `current_stage` | IntegerField | 1-6 |
| `responses` | JSONField | Stage responses |
| `pending_modules` | JSONField | Modules not yet configured |
| `is_complete` | BooleanField | |
| `started_at` | DateTimeField | |
| `completed_at` | DateTimeField | null=True |
| `updated_at` | DateTimeField | |

#### `core.SelfError`
**Table:** `core_selferror`

Append-only audit log of system self-detected errors.

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `created_at` | DateTimeField | |
| `level` | IntegerField | 1-3 severity |
| `category` | CharField | `STRUCTURAL`, `NUMERIC`, `GOVERNANCE` |
| `trigger_code` | CharField | Error code |
| `trigger_detail` | TextField | Details |
| `original_response_hash` | CharField | |
| `was_blocked` | BooleanField | Whether response was blocked |
| `engine_run_trace_id` | CharField | blank=True |
| `metadata` | JSONField | |

---

### Feedback Loop Models

**Purpose:** Track user engagement with intelligence outputs to calibrate future decisions.

**File:** `apps/core/ai_feedback/models.py`

#### `core.PredictionOutcome`
**Table:** `core_prediction_outcome`

| Field | Type | Notes |
|-------|------|-------|
| `prediction` | OneToOneField → Prediction | |
| `user` | FK → User | |
| `actual_value` | CharField | What actually happened |
| `error_abs` | FloatField | Absolute error |
| `error_pct` | FloatField | Percentage error |
| `accuracy_score` | FloatField | 0.0-1.0 |
| `validated_at` | DateTimeField | |

#### `core.PredictionAccuracyProfile`
**Table:** `core_prediction_accuracy_profile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `prediction_type` | CharField | unique_together with user |
| `total_validated` | IntegerField | |
| `total_accurate` | IntegerField | |
| `avg_accuracy` | FloatField | |
| `avg_error_pct` | FloatField | |
| `confidence_adjustment` | FloatField | Calibration factor |
| `last_validated_at` | DateTimeField | |

#### `core.InsightEngagement`
**Table:** `core_insight_engagement`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `insight` | FK → Insight | |
| `event_type` | CharField | `viewed`, `acted`, `dismissed` |
| `event_at` | DateTimeField | |

#### `core.InsightEngagementProfile`
**Table:** `core_insight_engagement_profile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | |
| `total_insights_shown` | IntegerField | |
| `total_viewed` | IntegerField | |
| `total_acted` | IntegerField | |
| `total_dismissed` | IntegerField | |
| `engagement_score` | FloatField | |
| `preferred_severity` | CharField | |
| `last_updated` | DateTimeField | |

#### `core.BriefingEngagement`
**Table:** `core_briefing_engagement`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `content_type` | CharField | `daily_briefing` or `weekly_report` |
| `content_id` | IntegerField | |
| `opened_at` | DateTimeField | |
| `time_spent_seconds` | IntegerField | |
| `scrolled_to_end` | BooleanField | |

#### `core.BriefingEngagementProfile`
**Table:** `core_briefing_engagement_profile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | |
| `total_briefings_generated` | IntegerField | |
| `total_briefings_opened` | IntegerField | |
| `total_reports_generated` | IntegerField | |
| `total_reports_opened` | IntegerField | |
| `avg_time_spent_seconds` | FloatField | |
| `open_rate` | FloatField | |
| `preferred_length` | CharField | `concise`, `standard`, `detailed` |
| `last_updated` | DateTimeField | |

#### `core.InterventionEffectivenessProfile`
**Table:** `core_intervention_effectiveness_profile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | |
| `total_interventions` | IntegerField | |
| `total_accepted` | IntegerField | |
| `total_dismissed` | IntegerField | |
| `total_drift_resolved` | IntegerField | |
| `effectiveness_score` | FloatField | |
| `avg_response_time_seconds` | FloatField | |
| `escalation_speed_modifier` | FloatField | Calibrates escalation speed |
| `last_updated` | DateTimeField | |

---

### IOCD — Intelligence Observability Engine

**Purpose:** System-wide observability — traces engine runs, records decisions, monitors cadence.

**File:** `apps/core/ai_observability/models.py`

#### `core.IntelligenceMetricsSnapshot`
**Table:** `core_intelligencemetricssnapshot`

Daily system-wide metrics across all intelligence engines.

| Field | Type | Notes |
|-------|------|-------|
| `snapshot_date` | DateField | |
| `guidance_total` | IntegerField | |
| `guidance_acknowledged` | IntegerField | |
| `guidance_dismissed` | IntegerField | |
| `guidance_acted` | IntegerField | |
| `guidance_expired` | IntegerField | |
| `guidance_acceptance_rate` | FloatField | |
| `guidance_action_rate` | FloatField | |
| `guidance_avg_response_seconds` | FloatField | |
| `predictions_total` | IntegerField | |
| `predictions_active` | IntegerField | |
| `predictions_expired` | IntegerField | |
| `predictions_avg_confidence` | FloatField | |
| `deliveries_total` | IntegerField | |
| `deliveries_sent` | IntegerField | |
| `deliveries_skipped` | IntegerField | |
| `deliveries_failed` | IntegerField | |
| `deliveries_success_rate` | FloatField | |
| `deliveries_by_channel` | JSONField | Per-channel breakdown |
| `active_users_count` | IntegerField | |
| `avg_responsiveness_score` | FloatField | |
| `avg_usefulness_score` | FloatField | |
| `total_suppressed` | IntegerField | |
| `persona_effectiveness_scores` | JSONField | |
| `created_at` | DateTimeField | |

#### `core.EngineRun`
**Table:** `core_diag_engine_run`

| Field | Type | Notes |
|-------|------|-------|
| `trace_id` | CharField | Trace identifier |
| `engine_name` | CharField | e.g., `PIE`, `PRIE`, `SAE` |
| `phase` | CharField | Pipeline phase |
| `started_at` | DateTimeField | |
| `ended_at` | DateTimeField | null=True |
| `duration_ms` | IntegerField | |
| `status` | CharField | `success`, `error`, `skipped` |
| `error_type` | CharField | blank=True |
| `error_message` | TextField | blank=True |
| `input_fingerprint` | CharField | blank=True |
| `output_fingerprint` | CharField | blank=True |
| `user_id` | IntegerField | null=True |
| `metadata` | JSONField | |
| `created_at` | DateTimeField | |

#### `core.EngineSpan`
**Table:** `core_diag_engine_span`

Sub-steps within an engine run for fine-grained tracing.

| Field | Type | Notes |
|-------|------|-------|
| `trace_id` | CharField | Same as parent EngineRun |
| `engine_name` | CharField | |
| `span_name` | CharField | e.g., `collect_signals`, `compute_score` |
| `started_at` | DateTimeField | |
| `ended_at` | DateTimeField | |
| `duration_ms` | IntegerField | |
| `status` | CharField | |
| `metadata` | JSONField | |

#### `core.DecisionRecord`
**Table:** `core_diag_decision_record`

Captures WHY an engine made a specific decision.

| Field | Type | Notes |
|-------|------|-------|
| `trace_id` | CharField | |
| `decision_type` | CharField | `arbitration`, `suppression`, `delivery_route`, `guidance_rank`, `insight_filter`, `noise_budget`, `prediction_store`, `validation` |
| `engine_name` | CharField | |
| `decision` | CharField | What was decided |
| `rationale` | TextField | Why |
| `inputs_summary` | JSONField | Input data |
| `affected_items` | JSONField | What was affected |
| `user_id` | IntegerField | null=True |
| `confidence` | FloatField | null=True |
| `created_at` | DateTimeField | |

#### `core.EngineExpectedCadence`
**Table:** `core_engine_expected_cadence`

| Field | Type | Notes |
|-------|------|-------|
| `engine_name` | CharField | **unique** |
| `expected_interval_seconds` | IntegerField | |
| `expected_jitter_seconds` | IntegerField | |
| `is_enabled` | BooleanField | |
| `notes` | TextField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.EngineHeartbeat`
**Table:** `core_engine_heartbeat`

| Field | Type | Notes |
|-------|------|-------|
| `engine_name` | CharField | |
| `observed_at` | DateTimeField | |
| `status` | CharField | `OK`, `MISSED`, `LATE`, `ERROR` |
| `last_run_at` | DateTimeField | |
| `next_expected_at` | DateTimeField | |
| `lateness_seconds` | IntegerField | |
| `metadata` | JSONField | |

---

### SAME — System Anomaly Monitoring Engine

Uses IOCD tables above plus these additional models:

#### `core.OpsAnomaly`
**Table:** `core_ops_anomaly`

| Field | Type | Notes |
|-------|------|-------|
| `severity` | CharField | `P1`, `P2`, `P3` |
| `engine_name` | CharField | |
| `anomaly_type` | CharField | `MISSED_RUN`, `ERROR_SPIKE`, `CONFIDENCE_VOLATILITY`, `SUPPRESSION_STORM`, `LOOPING_REMINDER`, `ENGINE_STARVATION`, `DELIVERY_RETRY_SPIKE`, `COMMITMENT_RACE_CONDITION`, `STRUCTURAL_VIOLATION`, `NUMERIC_DEVIATION`, `VALIDATOR_CRASH` |
| `summary` | TextField | |
| `evidence` | JSONField | |
| `suggested_actions` | JSONField | List of remediation steps |
| `is_active` | BooleanField | |
| `resolved_at` | DateTimeField | null=True |
| `original_severity` | CharField | |
| `escalation_count` | IntegerField | |
| `last_escalated_at` | DateTimeField | null=True |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

#### `core.OpsNarrativeSnapshot`
**Table:** `core_ops_narrative_snapshot`

| Field | Type | Notes |
|-------|------|-------|
| `created_at` | DateTimeField | |
| `posture` | CharField | `OK`, `DEGRADED`, `AT_RISK` |
| `headline` | CharField | |
| `bullets_now` | JSONField | Current state bullets |
| `recommendations` | JSONField | |
| `watching_next` | JSONField | What to monitor |
| `supporting_metrics` | JSONField | |

#### `core.SystemIntegritySnapshot`
**Table:** `core_system_integrity_snapshot`

| Field | Type | Notes |
|-------|------|-------|
| `score` | IntegerField | 0-100 |
| `posture` | CharField | `OPTIMAL`, `NOMINAL`, `DEGRADED`, `CRITICAL` |
| `components` | JSONField | Per-component scores |
| `created_at` | DateTimeField | |

#### `core.SAMEExecutionLog`
**Table:** `core_same_execution_log`

| Field | Type | Notes |
|-------|------|-------|
| `trigger_source` | CharField | `scheduled` or `manual` |
| `status` | CharField | `queued`, `running`, `completed`, `failed`, `timeout`, `skipped` |
| `celery_task_id` | CharField | blank=True |
| `triggered_by` | FK → User | null=True |
| `started_at` | DateTimeField | null=True |
| `completed_at` | DateTimeField | null=True |
| `duration_ms` | IntegerField | null=True |
| `error_detail` | TextField | blank=True |
| `created_at` | DateTimeField | |

#### `core.AdminIntervention`
**Table:** `core_admin_intervention`

| Field | Type | Notes |
|-------|------|-------|
| `admin_user` | FK → User | |
| `action_type` | CharField | `rerun_engine`, `requeue_job`, `clear_suppression_cache`, `restart_scheduler`, `acknowledge_anomaly`, `auto_rerun_engine`, `auto_clear_suppression` |
| `engine_name` | CharField | blank=True |
| `trace_id` | CharField | blank=True |
| `notes` | TextField | blank=True |
| `result_status` | CharField | `success`, `failure`, `pending` |
| `result_detail` | TextField | blank=True |
| `is_system_initiated` | BooleanField | default=False |
| `created_at` | DateTimeField | |

---

### ISE — Intelligence Scheduling Engine

**Purpose:** Schedules all engine runs via Celery Beat. 42+ registered tasks.

**File:** `apps/core/ai_scheduler/scheduler_registry.py`

#### `core.SchedulerHeartbeat`
**Table:** `core_scheduler_heartbeat`

| Field | Type | Notes |
|-------|------|-------|
| `scheduler_name` | CharField | **unique**. `ISE` or `SAME` |
| `last_tick_at` | DateTimeField | |
| `expected_interval_seconds` | IntegerField | |
| `cycle_result` | JSONField | Last cycle output |
| `alive_threshold_multiplier` | FloatField | |
| `offline_threshold_multiplier` | FloatField | |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

**Key Schedule Cadences:**
| Cadence | Engines |
|---------|---------|
| 60s | SAME |
| 5m | SAE sync, PIE batch, deadline checks |
| 10m | DNE delivery |
| 1h | PRIE batch |
| 6h | PGE refresh, CDCE correlations, GLOE learning |
| 24h | DBE briefing, Blueprint architecture, drift scoring |
| 7d | WIRE weekly reports |

---

## 5. Domain Models

### Journal App

**File:** `apps/journal/models.py`

#### `journal.JournalEntry` (UserOwnedModel)
**Table:** `journal_journalentry`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | PK |
| `user` | FK → User | Inherited from UserOwnedModel |
| `title` | CharField(200) | blank=True |
| `content` | TextField | Journal entry text |
| `mood` | CharField | blank=True. User's mood |
| `energy_level` | IntegerField | null=True. 1-10 scale |
| `tags` | M2M → Tag | blank=True |
| `entry_date` | DateField | The date this entry is for |
| `is_pinned` | BooleanField | default=False |
| `word_count` | IntegerField | default=0 |
| `status` | CharField | Inherited (active/archived/deleted) |
| `created_via` | CharField | Inherited (manual/ai_camera/import/api) |
| `created_at` | DateTimeField | |
| `updated_at` | DateTimeField | |

**SAE reads:** Last entry date, entry frequency, mood distribution → `UserState.state_data.journal`
**PIE watches:** Mood trends, journaling frequency changes

#### `journal.Emotion` (UserOwnedModel)
**Table:** `journal_emotion`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `content` | TextField | Emotion/gratitude content |
| `entry_date` | DateField | |
| `category` | CharField | blank=True |

---

### Health App

**File:** `apps/health/models.py`

#### `health.WeightEntry` (UserOwnedModel)
**Table:** `health_weightentry`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `weight` | DecimalField | Weight value |
| `unit` | CharField | `lbs` or `kg` |
| `body_fat_percentage` | DecimalField | null=True |
| `entry_date` | DateField | |
| `notes` | TextField | blank=True |

**SAE reads:** weight_current, weight_trend, weight_entries_90d, body_fat_current
**PIE watches:** Weight trend changes (up/down/plateau)
**PRIE predicts:** weight_30d trajectory

#### `health.SleepEntry` (UserOwnedModel)
**Table:** `health_sleepentry`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `sleep_date` | DateField | Night of sleep |
| `bedtime` | TimeField | null=True |
| `wake_time` | TimeField | null=True |
| `hours_slept` | DecimalField | Total hours |
| `quality` | IntegerField | 1-10 scale, null=True |
| `notes` | TextField | blank=True |

**SAE reads:** sleep_avg_7d
**CDCE correlates:** Sleep ↔ mood, sleep ↔ energy

#### `health.BloodPressureEntry` (UserOwnedModel)
**Table:** `health_bloodpressureentry`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `systolic` | IntegerField | Top number |
| `diastolic` | IntegerField | Bottom number |
| `heart_rate` | IntegerField | null=True. BPM |
| `entry_date` | DateField | |
| `time_of_day` | CharField | blank=True |
| `notes` | TextField | blank=True |

#### `health.GlucoseEntry` (UserOwnedModel)
**Table:** `health_glucoseentry`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `glucose_level` | DecimalField | mg/dL |
| `reading_type` | CharField | `fasting`, `post_meal`, `random` |
| `entry_date` | DateField | |
| `notes` | TextField | blank=True |

#### `health.MedicineSchedule` (UserOwnedModel)
**Table:** `health_medicineschedule`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `medicine_name` | CharField(200) | |
| `dosage` | CharField(100) | |
| `frequency` | CharField | `daily`, `twice_daily`, `weekly`, etc. |
| `time_of_day` | CharField | `morning`, `afternoon`, `evening`, `bedtime` |
| `scheduled_time` | TimeField | null=True |
| `instructions` | TextField | blank=True |
| `is_active` | BooleanField | default=True |
| `prescriber` | CharField | blank=True |
| `pharmacy` | CharField | blank=True |
| `refill_date` | DateField | null=True |

**SMS integration:** Generates SMSNotification records for medicine reminders.

#### `health.MedicineLog` (UserOwnedModel)
**Table:** `health_medicinelog`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `schedule` | FK → MedicineSchedule | null=True |
| `medicine_name` | CharField(200) | Denormalized from schedule |
| `taken_at` | DateTimeField | |
| `was_taken` | BooleanField | default=True |
| `skip_reason` | CharField | blank=True |
| `notes` | TextField | blank=True |

#### `health.NutritionEntry` (UserOwnedModel)
**Table:** `health_foodentry`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `meal_type` | CharField | `breakfast`, `lunch`, `dinner`, `snack` |
| `food_name` | CharField(200) | |
| `calories` | IntegerField | null=True |
| `protein_grams` | DecimalField | null=True |
| `carbs_grams` | DecimalField | null=True |
| `fat_grams` | DecimalField | null=True |
| `fiber_grams` | DecimalField | null=True |
| `serving_size` | CharField | blank=True |
| `entry_date` | DateField | |

**SAE reads:** calorie_avg_7d, protein_avg_7d, macro_compliance

#### `health.FastingEntry` (UserOwnedModel)
**Table:** `health_fastingwindow`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `start_time` | DateTimeField | |
| `end_time` | DateTimeField | null=True |
| `planned_hours` | DecimalField | Target duration |
| `actual_hours` | DecimalField | null=True |
| `fasting_type` | CharField | e.g., `intermittent`, `extended` |
| `notes` | TextField | blank=True |

**SAE reads:** rolling_7d_hours, avg_fast_duration, compliance_score

#### `health.WorkoutEntry` (UserOwnedModel)
**Table:** `health_workoutsession`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `workout_type` | CharField | e.g., `strength`, `cardio`, `flexibility` |
| `name` | CharField(200) | |
| `duration_minutes` | IntegerField | null=True |
| `calories_burned` | IntegerField | null=True |
| `notes` | TextField | blank=True |
| `entry_date` | DateField | |
| `heart_rate_avg` | IntegerField | null=True |
| `heart_rate_max` | IntegerField | null=True |
| `distance` | DecimalField | null=True |
| `distance_unit` | CharField | blank=True |

#### `health.ExerciseSet` (TimeStampedModel)
**Table:** `health_exerciseset`

| Field | Type | Notes |
|-------|------|-------|
| `workout` | FK → WorkoutEntry | |
| `exercise_name` | CharField(200) | |
| `set_number` | IntegerField | |
| `reps` | IntegerField | null=True |
| `weight` | DecimalField | null=True |
| `weight_unit` | CharField | `lbs` or `kg` |
| `duration_seconds` | IntegerField | null=True |
| `is_personal_record` | BooleanField | default=False |

#### `health.WeightGoal` (UserOwnedModel)
**Table:** `health_weightgoal`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `goal_type` | CharField | `lose`, `gain`, `maintain` |
| `target_weight` | DecimalField | |
| `target_date` | DateField | null=True |
| `starting_weight` | DecimalField | |
| `unit` | CharField | `lbs` or `kg` |
| `is_active` | BooleanField | |

**SAE reads:** weight_goal, weight_goal_target_date, weight_goal_remaining, weight_goal_on_track

#### `health.TransformationScore` (TimeStampedModel)
**Table:** `health_transformationprotocol`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `score_date` | DateField | |
| `total_score` | IntegerField | 0-100 composite |
| `weight_trend_score` | IntegerField | Component |
| `momentum_score` | IntegerField | Component |
| `breakdown` | JSONField | Full component breakdown |

#### `health.MealPlan`, `health.Recipe`, `health.PantryItem`

Meal planning and pantry management models. SAE reads pantry counts, expiring items, dinner plans.

---

### Faith App

**File:** `apps/faith/models.py`

#### `faith.PrayerRequest` (UserOwnedModel)
**Table:** `faith_prayerrequest`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `title` | CharField(200) | |
| `description` | TextField | |
| `category` | CharField | e.g., `health`, `family`, `career` |
| `priority` | CharField | `normal`, `urgent` |
| `is_answered` | BooleanField | default=False |
| `answered_date` | DateField | null=True |
| `answered_notes` | TextField | blank=True |

**SAE reads:** answered_prayers count, recent_prayer_titles, urgent_prayers count

#### `faith.ScriptureReading` (UserOwnedModel)
**Table:** `faith_userreadingprogress`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `book` | CharField | Bible book name |
| `chapter` | IntegerField | |
| `verse_start` | IntegerField | null=True |
| `verse_end` | IntegerField | null=True |
| `reading_date` | DateField | |
| `notes` | TextField | blank=True |
| `bible_plan` | FK → BibleReadingPlan | null=True |

**SAE reads:** reading_streak, last_scripture_read

#### `faith.BibleReadingPlan` (UserOwnedModel)
**Table:** `faith_userreadingplan`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `plan_name` | CharField | |
| `start_date` | DateField | |
| `end_date` | DateField | null=True |
| `is_active` | BooleanField | |
| `current_day` | IntegerField | |
| `total_days` | IntegerField | |

#### `faith.Reflection` (UserOwnedModel)
**Table:** `purpose_reflection`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `content` | TextField | |
| `scripture_reference` | CharField | blank=True |
| `entry_date` | DateField | |
| `mood` | CharField | blank=True |

---

### Life App

**File:** `apps/life/models.py`

#### `life.Project` (UserOwnedModel)
**Table:** `life_project`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `title` | CharField(200) | |
| `description` | TextField | blank=True |
| `status` | CharField | `active`, `paused`, `completed`, `archived` |
| `started_at` | DateTimeField | |
| `target_completion_date` | DateField | null=True |
| `completed_at` | DateTimeField | null=True |
| `category` | CharField(50) | blank=True |
| `is_featured` | BooleanField | |

#### `life.Document` (UserOwnedModel)
**Table:** `life_document`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `title` | CharField(255) | |
| `category` | CharField | `medical`, `financial`, `legal`, `insurance`, `tax`, `household`, `other` |
| `file` | FileField | Cloudinary storage |
| `file_size_bytes` | PositiveIntegerField | null=True |
| `file_hash` | CharField(64) | SHA-256 dedup |
| `extracted_text` | TextField | OCR/extraction result |
| `is_archived` | BooleanField | |

**Cross-reference:** `medical.MedicalDocument.organize_document` → links to this table for medical documents.

#### `life.Person` (UserOwnedModel)
**Table:** `relationships_person`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `name` | CharField(200) | |
| `relationship` | CharField | |
| `email` | EmailField | blank=True |
| `phone` | CharField(20) | blank=True |
| `birthday` | DateField | null=True |
| `notes` | TextField | blank=True |

#### `life.HouseholdMember` (UserOwnedModel)
**Table:** `meals_household` (members via `meals_householdmembership`)

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `name` | CharField(200) | |
| `relationship` | CharField | |
| `age` | PositiveIntegerField | null=True |
| `birthday` | DateField | null=True |
| `notes` | TextField | blank=True |

---

### Purpose App

**File:** `apps/purpose/models.py`

#### `purpose.LifeDomain`
**Table:** `purpose_lifedomain`

Configuration/lookup table (not per-user).

| Field | Type | Notes |
|-------|------|-------|
| `name` | CharField(100) | **unique** |
| `slug` | SlugField(100) | **unique** |
| `description` | TextField | blank=True |
| `icon` | CharField | Icon identifier |
| `sort_order` | IntegerField | |

#### `purpose.LifeGoal` (UserOwnedModel)
**Table:** `purpose_lifegoal`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `domain` | FK → LifeDomain | |
| `goal_text` | TextField | |

**SAE reads:** active_goal_count, next_deadline, completion_rate

#### `purpose.HabitGoal` (UserOwnedModel)
**Table:** `purpose_habitgoal`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `name` | CharField(200) | |
| `category` | CharField | |
| `frequency` | CharField | |

**SAE reads:** active_habit_count, longest_streak, avg_completion_rate

---

### Finance App

**File:** `apps/finance/models.py`

#### `finance.FinancialAccount` (UserOwnedModel)
**Table:** `finance_financialaccount`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `account_type` | CharField | `checking`, `savings`, `money_market`, `credit_card`, `investment`, `loan` |
| `name` | CharField(200) | |
| `institution` | CharField(200) | blank=True |
| `current_balance` | DecimalField(15,2) | |
| `is_active` | BooleanField | |

#### `finance.Transaction` (UserOwnedModel)
**Table:** `finance_transaction`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `account` | FK → FinancialAccount | |
| `category` | FK → TransactionCategory | |
| `description` | CharField(500) | |
| `amount` | DecimalField(15,2) | |
| `transaction_date` | DateField | |
| `transaction_type` | CharField | `income`, `expense`, `transfer` |
| `is_reconciled` | BooleanField | |

#### `finance.Budget` (UserOwnedModel)
**Table:** `finance_budget`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `name` | CharField(200) | |
| `period` | CharField | `monthly`, `quarterly`, `yearly` |
| `start_date` | DateField | |
| `end_date` | DateField | |
| `total_budget` | DecimalField(15,2) | |

#### `finance.FinancialGoal` (UserOwnedModel)
**Table:** `finance_financialgoal`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `goal_type` | CharField | `savings`, `debt_payoff`, `giving`, `purchase`, `investment` |
| `name` | CharField(200) | |
| `target_amount` | DecimalField(15,2) | |
| `current_amount` | DecimalField(15,2) | |
| `target_date` | DateField | null=True |
| `priority` | CharField | `low`, `medium`, `high` |
| `is_active` | BooleanField | |

#### `finance.FinancialMetricSnapshot` (TimeStampedModel)
**Table:** `finance_financialmetricsnapshot`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `snapshot_date` | DateField | |
| `total_assets` | DecimalField(15,2) | |
| `total_liabilities` | DecimalField(15,2) | |
| `net_worth` | DecimalField(15,2) | |
| `monthly_income` | DecimalField(15,2) | |
| `monthly_expenses` | DecimalField(15,2) | |
| `monthly_savings_rate` | DecimalField(5,2) | |

---

### Medical App

**File:** `apps/medical/models.py`

#### `medical.LabTestCatalog` (TimeStampedModel)
**Table:** `medical_labtestcatalog`

System-wide lab test reference (not per-user).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `name` | CharField(200) | **unique** |
| `short_name` | CharField(50) | Abbreviation (e.g., WBC) |
| `category` | CharField(30) | `hematology`, `chemistry`, `lipids`, `thyroid`, `diabetes`, etc. Indexed |
| `default_unit` | CharField(50) | |
| `default_range_low` | CharField(50) | |
| `default_range_high` | CharField(50) | |
| `loinc_code` | CharField(20) | LOINC standard code |
| `is_system_seeded` | BooleanField | |
| `needs_review` | BooleanField | Indexed |
| `description` | TextField | |
| `sort_order` | IntegerField | |

#### `medical.LabResult` (UserOwnedModel)
**Table:** `medical_labresult`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `canonical_test` | FK → LabTestCatalog | null=True |
| `raw_test_name` | CharField(500) | Original name from report |
| `value_text` | CharField(200) | |
| `value_numeric` | DecimalField(12,4) | null=True |
| `unit` | CharField(100) | |
| `range_low` | DecimalField(12,4) | null=True |
| `range_high` | DecimalField(12,4) | null=True |
| `range_text` | CharField(200) | |
| `abnormal_flag` | CharField(5) | `L`, `H`, `LL`, `HH`, `A`, or blank. Indexed |
| `collected_at` | DateTimeField | Indexed |
| `reported_at` | DateTimeField | null=True |
| `panel` | FK → LabPanel | null=True |
| `medical_document` | FK → MedicalDocument | null=True |
| `import_batch` | FK → ImportBatch | null=True |
| `provider` | CharField(200) | |
| `fingerprint` | CharField(64) | SHA-256 dedup. Indexed |
| `notes` | TextField | |

**Key joins:** `LabResult` → `LabTestCatalog` (canonical_test), `LabResult` → `LabPanel` (panel), `LabResult` → `MedicalDocument` (source document)

#### `medical.LabPanel` (UserOwnedModel)
**Table:** `medical_labpanel`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `panel_type` | CharField(30) | `cbc`, `cmp`, `lipid`, `thyroid`, etc. |
| `name` | CharField(200) | |
| `collected_at` | DateTimeField | |
| `provider` | CharField(200) | |
| `notes` | TextField | |

---

### Brain Training App

**File:** `apps/brain_training/models.py`

#### `brain_training.Game` (TimeStampedModel)
**Table:** `brain_training_game`

| Field | Type | Notes |
|-------|------|-------|
| `slug` | SlugField(50) | **unique** |
| `name` | CharField(100) | |
| `category` | CharField | `logic`, `math`, `visual`, `language`, `memory` |
| `is_active` | BooleanField | |

#### `brain_training.GameSession` (TimeStampedModel)
**Table:** `brain_training_gamesession`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `challenge` | FK → Challenge | |
| `started_at` | DateTimeField | |
| `completed_at` | DateTimeField | null=True |
| `time_spent_seconds` | PositiveIntegerField | |
| `status` | CharField | `in_progress`, `completed`, `abandoned`, `timeout` |
| `mistakes` | PositiveIntegerField | |
| `hints_used` | PositiveIntegerField | |
| `score` | PositiveIntegerField | |
| `platform` | CharField(20) | `ios`, `android`, `web` |

---

### Capture App

**File:** `apps/capture/models.py`

#### `capture.CaptureEntry` (TimeStampedModel)
**Table:** `capture_captureentry`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `title` | CharField(255) | blank=True |
| `duration_seconds` | PositiveIntegerField | null=True |
| `audio_file_url` | URLField(500) | S3 signed URL |
| `transcript` | TextField | blank=True |
| `summary` | TextField | blank=True |
| `category` | CharField | `faith`, `organize` |
| `subcategory` | CharField | `sermon`, `bible_study`, `devotional`, `meeting`, `notes`, `personal` |
| `status` | CharField | `uploading`, `transcribing`, `summarizing`, `ready`, `failed` |
| `error_message` | TextField | blank=True |

---

## 6. Supporting Models

### Core App

#### `core.Tag` (UserOwnedModel)
**Table:** `core_tag`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `name` | CharField | |

#### `core.SiteConfiguration` (Singleton)
**Table:** `core_siteconfiguration`

Site-wide settings. Always pk=1.

| Field | Type | Notes |
|-------|------|-------|
| `site_name` | CharField | |
| `tagline` | CharField | |
| Various feature toggles | BooleanField | |

#### `core.ReleaseNote`
**Table:** `core_releasenote`

| Field | Type | Notes |
|-------|------|-------|
| `version` | CharField | |
| `title` | CharField | |
| `content` | TextField | |
| `entry_type` | CharField | `feature`, `fix`, `enhancement`, `security` |
| `is_published` | BooleanField | |
| `published_date` | DateField | |

#### `core.CameraScan` (UserOwnedModel)
**Table:** `core_camerascan`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `scan_type` | CharField | `food`, `medicine`, `receipt`, `barcode`, etc. |
| `image` | ImageField | |
| `result_data` | JSONField | AI classification result |
| `action_taken` | CharField | What was done with the scan |
| `processing_status` | CharField | |

#### `core.APIRequestLog`
**Table:** `core_apirequestlog`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | null=True |
| `endpoint` | CharField | |
| `method` | CharField | |
| `status_code` | IntegerField | |
| `response_time_ms` | IntegerField | |
| `ip_address` | GenericIPAddressField | |
| `created_at` | DateTimeField | |

---

### AI App

**File:** `apps/ai/models.py`

#### `ai.CoachingStyle`
**Table:** `ai_coachingstyle`

| Field | Type | Notes |
|-------|------|-------|
| `key` | SlugField(50) | **unique** |
| `name` | CharField(100) | |
| `description` | CharField(300) | |
| `icon` | CharField(10) | Emoji |
| `category` | CharField(50) | blank=True |
| `prompt_instructions` | TextField | Full AI prompt |
| `is_active` | BooleanField | |
| `is_default` | BooleanField | |
| `sort_order` | PositiveIntegerField | |

**Referenced by:** `UserPreferences.ai_coaching_style` FK

#### `ai.AIInsight`
**Table:** `ai_aiinsight`

Cached AI-generated text insights (dashboard summaries, not PIE insights).

#### `ai.AIPromptConfig`
**Table:** `ai_aipromptconfig`

Database-driven AI prompt configurations.

---

### Admin Console App

**File:** `apps/admin_console/models.py`

#### `admin_console.AdminTask`
**Table:** `admin_console_admintask`

| Field | Type | Notes |
|-------|------|-------|
| `title` | CharField(200) | |
| `description` | JSONField | Executable Task Standard: `{objective, inputs, actions, output}` |
| `status` | CharField | `pending`, `in_progress`, `done`, `blocked` |
| `priority` | CharField | `low`, `medium`, `high`, `critical` |
| `assigned_to` | FK → User | null=True |

---

### Help App

**File:** `apps/help/models.py`

#### `help.HelpTopic`
**Table:** `help_helptopic`

| Field | Type | Notes |
|-------|------|-------|
| `context_id` | CharField(100) | **unique**, indexed. Maps to page HELP_CONTEXT_ID |
| `help_id` | SlugField(100) | **unique** |
| `title` | CharField(200) | |
| `content` | TextField | Markdown |
| `app_name` | CharField(50) | |
| `related_topics` | M2M → self | |

#### `help.HelpArticle`
**Table:** `help_helparticle`

| Field | Type | Notes |
|-------|------|-------|
| `title` | CharField(200) | |
| `slug` | SlugField(200) | **unique** |
| `summary` | CharField(300) | |
| `content` | TextField | Markdown |
| `category` | FK → HelpCategory | |
| `module` | CharField(20) | `general`, `dashboard`, `journal`, `health`, `faith`, `life`, `purpose`, `settings` |
| `keywords` | TextField | Comma-separated |

#### `help.TeachingDestination`
**Table:** `help_teachingdestination`

| Field | Type | Notes |
|-------|------|-------|
| `destination_id` | SlugField(100) | **unique** |
| `name` | CharField(100) | |
| `url` | CharField(300) | |
| `keywords` | TextField | Comma-separated matching |
| `module` | CharField(50) | |

---

### Billing App

**File:** `apps/billing/models.py`

#### `billing.BillingProfile` (TimeStampedModel)
**Table:** `billing_billingprofile`

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField → User | |
| `pricing_tier` | CharField | `free`, `faith_only`, `student`, `adult`, `founding` |
| `subscription_status` | CharField | `none`, `trialing`, `active`, `faith_only`, `past_due`, `canceled`, `lifetime` |
| `billing_cycle` | CharField | `monthly`, `annual`, `lifetime` |
| `stripe_customer_id` | CharField(255) | |
| `stripe_subscription_id` | CharField(255) | |
| `referral_code` | CharField(20) | **unique** |
| `referred_by` | FK → User | null=True |
| `account_credit` | DecimalField | |

#### `billing.CreditTransaction` (TimeStampedModel)
**Table:** `billing_credittransaction`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `amount` | DecimalField | Positive or negative |
| `transaction_type` | CharField | `referral_bonus`, `suggestion_reward`, `manual`, `applied_to_invoice`, `promo_code`, `refund` |
| `description` | TextField | |

---

### Mobile App

**File:** `apps/mobile/models.py`

#### `mobile.MobileDevice` (TimeStampedModel)
**Table:** `mobile_mobiledevice`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | unique_together with device_id |
| `device_id` | CharField(128) | iOS Keychain UUID |
| `device_name` | CharField(255) | |
| `device_model` | CharField(100) | |
| `os_version` | CharField(50) | |
| `app_version` | CharField(50) | |
| `push_token` | CharField(255) | APNs token |
| `push_enabled` | BooleanField | |

#### `mobile.HealthIngestionRun` (TimeStampedModel)
**Table:** `mobile_healthingestionrun`

Tracks HealthKit data sync sessions from iOS.

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `device` | FK → MobileDevice | |
| `status` | CharField | `pending`, `processing`, `completed`, `partial`, `failed` |
| `metrics_received` | PositiveIntegerField | |
| `metrics_created` | PositiveIntegerField | |
| `metrics_updated` | PositiveIntegerField | |
| `metrics_skipped` | PositiveIntegerField | |

---

### Scan App

**File:** `apps/scan/models.py`

#### `scan.ScanLog` (TimeStampedModel)
**Table:** `scan_scanlog`

| Field | Type | Notes |
|-------|------|-------|
| `request_id` | UUIDField | **unique**, indexed |
| `user` | FK → User | |
| `status` | CharField | `pending`, `success`, `failed`, `timeout`, `rate_limited` |
| `category` | CharField(30) | `food`, `medicine`, `supplement`, `receipt`, `document`, etc. |
| `confidence` | FloatField | 0.0-1.0 |
| `items_json` | JSONField | Identified items |
| `processing_time_ms` | PositiveIntegerField | |

#### `scan.ImageAnalysis` (TimeStampedModel)
**Table:** `scan_imageanalysis`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `user` | FK → User | |
| `source_type` | CharField | `chat`, `scan`, `inventory`, `pet`, `recipe`, `project`, `document`, `note`, `medical` |
| `content_type` | FK → ContentType | GenericFK |
| `object_id` | PositiveIntegerField | GenericFK |
| `status` | CharField | `pending`, `analyzing`, `completed`, `failed` |
| `image_hash` | CharField(64) | SHA-256 dedup |
| `summary` | TextField | |
| `objects_identified` | JSONField | |
| `text_detected` | TextField | OCR |
| `relevance_tags` | JSONField | |
| `actionable_insights` | JSONField | |

---

### SMS App

**File:** `apps/sms/models.py`

#### `sms.SMSNotification` (TimeStampedModel)
**Table:** `sms_smsnotification`

| Field | Type | Notes |
|-------|------|-------|
| `notification_id` | UUIDField | **unique**, indexed |
| `user` | FK → User | |
| `category` | CharField | `medicine`, `medicine_refill`, `task`, `event`, `prayer`, `fasting`, `significant_event`, `milestone`, `verification`, `system` |
| `message` | CharField(320) | SMS body |
| `scheduled_for` | DateTimeField | indexed |
| `status` | CharField | `pending`, `sent`, `delivered`, `failed`, `cancelled` |
| `twilio_sid` | CharField(50) | |
| `content_type` | FK → ContentType | GenericFK — links to source object |
| `object_id` | PositiveIntegerField | |

#### `sms.SMSResponse` (TimeStampedModel)
**Table:** `sms_smsresponse`

| Field | Type | Notes |
|-------|------|-------|
| `notification` | FK → SMSNotification | null=True |
| `user` | FK → User | null=True |
| `from_number` | CharField(20) | |
| `body` | TextField | |
| `parsed_action` | CharField | `done`, `remind`, `skip`, `unknown` |

---

### Security App

**File:** `apps/security/models.py`

Uses **encrypted fields** (Fernet AES-256) for sensitive security assessment data.

#### `security.SecurityRun`
**Table:** `security_securityrun`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `run_timestamp` | DateTimeField | indexed |
| `status` | CharField | `running`, `completed`, `failed` |
| `total_tests` | IntegerField | |
| `passed_tests` | IntegerField | |
| `failed_tests` | IntegerField | |
| `total_findings` | IntegerField | |
| `critical_findings` | IntegerField | |
| `_executive_summary` | EncryptedTextField | Encrypted at rest |

#### `security.SecurityFinding`
**Table:** `security_securityfinding`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField | PK |
| `run` | FK → SecurityRun | |
| `finding_id` | CharField(20) | indexed |
| `severity` | CharField | `critical`, `high`, `medium`, `low`, `info` |
| `cvss_score` | DecimalField(4,1) | |
| `_description` | EncryptedTextField | Encrypted |
| `_evidence` | EncryptedJSONField | Encrypted |
| `status` | CharField | `new`, `recurring`, `fixed`, `regressed` |

---

### Relationships

**File:** `apps/core/ai_relationships/models.py`

#### `core.Person` (Relationship tracking)
**Table:** `ai_relationships_person` (distinct from `relationships_person`)

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `display_name` | CharField | |
| `person_type` | CharField | `family`, `friend`, `colleague`, `mentor`, `other` |
| `is_active` | BooleanField | |

#### `core.Relationship`
**Table:** `ai_relationships_relationship`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `person` | FK → core.Person | |
| `relationship_type` | CharField | `spouse`, `child`, `parent`, `friend`, `boss` |
| `importance_tier` | IntegerField | 1-3 |
| `cadence_target` | CharField | `daily`, `weekly`, `biweekly`, `monthly`, `quarterly` |
| `last_interaction` | DateTimeField | null=True |

#### `core.InteractionSignal`
**Table:** `ai_relationships_interactionsignal`

| Field | Type | Notes |
|-------|------|-------|
| `user` | FK → User | |
| `person` | FK → core.Person | |
| `signal_date` | DateField | |
| `signal_type` | CharField | `mention`, `event`, `call`, `message`, `manual` |
| `source_type` | CharField | `journal`, `calendar`, `reflection`, `manual`, `chat` |
| `source_id` | CharField | blank=True |
| `confidence` | FloatField | |

---

## 7. Engine-to-Table Matrix

| Engine | Reads From | Writes To | Schedule |
|--------|-----------|-----------|----------|
| **SAE** | All domain tables (health_*, journal_*, faith_*, etc.) | `core_user_state` | Post-action + 5m |
| **PIE** | `core_user_state` + domain events | `core_ai_insight` | Post-action + 5m |
| **PRIE** | `core_user_state` + historical data | `core_ai_prediction` | Post-action + 1h |
| **PGE** | `core_user_state`, `core_ai_insight`, `core_ai_prediction` | `core_guidance_item` | 6h |
| **DBE** | `core_user_state`, `core_ai_insight`, `core_ai_prediction`, `core_guidance_item` | `core_daily_briefing` | 24h (morning) |
| **WIRE** | All engine tables | `core_weekly_intelligence_report` | 7d |
| **DNE** | `core_guidance_item`, `core_daily_briefing`, `core_weekly_intelligence_report` | `core_delivered_notification` | 10m |
| **E3** | Engine output tables | `core_explain_record` | With parent engine |
| **UAL** | `core_user_state`, domain signals | `core_arbitration_decision_log`, `core_daily_capacity_log`, `core_scenario_history` | 5m |
| **EAE** | Signal queue | `ai_eae_eaestate`, `ai_eae_eaedecisionlog`, `ai_eae_eaeescalationevent` | Per-request |
| **CDCE** | Historical time series | `core_domain_correlation` | 6h |
| **GLOE** | Chat transcripts | `core_user_learned_profile`, `core_learning_extraction` | 6h |
| **SLCME** | User clarifications | `core_learned_mapping`, `core_clarification_log` | Real-time |
| **Blueprint** | `core_governanceprofile`, domain schedules | `core_architectureplan`, `core_scheduledblock`, `core_driftscore` | 24h (7 PM) |
| **Governance** | User alignment sessions | `core_governanceprofile`, `core_governancealignmentsession` | Real-time |
| **Feedback** | User interactions | `core_insight_engagement`, `core_prediction_outcome`, `core_briefing_engagement` | Real-time |
| **IOCD** | All engine runs | `core_diag_engine_run`, `core_diag_engine_span`, `core_diag_decision_record`, `core_intelligencemetricssnapshot` | With engines |
| **SAME** | `core_engine_heartbeat`, `core_diag_engine_run` | `core_ops_anomaly`, `core_ops_narrative_snapshot`, `core_system_integrity_snapshot` | 60s |
| **ISE** | Registry config | `core_scheduler_heartbeat` | 5m tick |

---

## 8. Key Relationships & Common Joins

### User-Centric Queries

All user data connects through the `user` FK on every `UserOwnedModel`:

```sql
-- Get user with all preferences and billing
SELECT * FROM users_user u
JOIN users_userpreferences p ON p.user_id = u.id
JOIN billing_billingprofile b ON b.user_id = u.id
WHERE u.id = ?
```

### Intelligence Pipeline Chain

```sql
-- Follow the full intelligence pipeline for a user
-- 1. SAE truth layer
SELECT state_data FROM core_user_state WHERE user_id = ?

-- 2. PIE insights generated from state
SELECT * FROM core_ai_insight WHERE user_id = ? AND status = 'new' ORDER BY created_at DESC

-- 3. PRIE predictions
SELECT * FROM core_ai_prediction WHERE user_id = ? AND status = 'active'

-- 4. PGE guidance synthesized from insights + predictions
SELECT * FROM core_guidance_item WHERE user_id = ? AND is_active = TRUE ORDER BY priority

-- 5. DNE delivery audit
SELECT * FROM core_delivered_notification WHERE user_id = ? ORDER BY delivered_at DESC
```

### PIE Evidence Trail

```sql
-- Trace a PIE insight back to its evidence
SELECT i.*, e.explanation, e.evidence
FROM core_ai_insight i
LEFT JOIN core_explain_record e ON e.source_object_id = CAST(i.id AS VARCHAR)
  AND e.source_engine = 'PIE'
WHERE i.user_id = ? AND i.insight_type = 'weight_trend_up'
```

### Health Data with SAE State

```sql
-- Compare raw health data with SAE-computed state
SELECT
  w.weight, w.entry_date,
  us.state_data->'health'->'weight_current' as sae_weight,
  us.state_data->'health'->'weight_trend' as sae_trend
FROM health_weightentry w
JOIN core_user_state us ON us.user_id = w.user_id
WHERE w.user_id = ? AND w.status = 'active'
ORDER BY w.entry_date DESC
```

### Medicine Schedule → SMS → Response

```sql
-- Track medicine reminder flow
SELECT ms.medicine_name, ms.scheduled_time,
  sn.message, sn.scheduled_for, sn.status as sms_status,
  sr.body as response, sr.parsed_action
FROM health_medicineschedule ms
LEFT JOIN sms_smsnotification sn ON sn.object_id = ms.id
  AND sn.category = 'medicine'
LEFT JOIN sms_smsresponse sr ON sr.notification_id = sn.id
WHERE ms.user_id = ? AND ms.is_active = TRUE
```

### Lab Results with Catalog

```sql
-- Get lab results with canonical test info and abnormal flags
SELECT lr.value_numeric, lr.unit, lr.abnormal_flag, lr.collected_at,
  ltc.name as test_name, ltc.category, ltc.default_range_low, ltc.default_range_high,
  lp.name as panel_name, lp.panel_type
FROM medical_labresult lr
JOIN medical_labtestcatalog ltc ON ltc.id = lr.canonical_test_id
LEFT JOIN medical_labpanel lp ON lp.id = lr.panel_id
WHERE lr.user_id = ? AND lr.status = 'active'
ORDER BY lr.collected_at DESC
```

### Arbitration Decision Audit

```sql
-- UAL arbitration decisions with capacity context
SELECT a.dominant_scenario, a.confidence_level, a.capacity_state,
  a.surfaced_items, a.suppressed_items, a.narrative,
  dc.capacity_score, dc.sleep_deficit, dc.emotional_load
FROM core_arbitration_decision_log a
LEFT JOIN core_daily_capacity_log dc ON dc.user_id = a.user_id AND dc.date = DATE(a.timestamp)
WHERE a.user_id = ?
ORDER BY a.timestamp DESC
```

### IOCD Engine Diagnostics

```sql
-- Find slow or failing engine runs
SELECT engine_name, status, duration_ms, error_message, started_at
FROM core_diag_engine_run
WHERE status = 'error' OR duration_ms > 5000
ORDER BY started_at DESC LIMIT 50

-- Active anomalies
SELECT severity, engine_name, anomaly_type, summary, evidence
FROM core_ops_anomaly
WHERE is_active = TRUE
ORDER BY severity, created_at DESC
```

### Blueprint Schedule Tracking

```sql
-- Today's schedule with completion status
SELECT sb.title, sb.time_start, sb.time_end, sb.tier, sb.status,
  sb.actual_start, sb.actual_end
FROM core_scheduledblock sb
JOIN core_architectureplan ap ON ap.id = sb.architecture_plan_id
WHERE sb.user_id = ? AND ap.plan_date = CURRENT_DATE
ORDER BY sb.time_start
```

### Cross-Domain Correlations

```sql
-- Active correlations for a user
SELECT domain_a, domain_b, correlation_type, strength, direction, narrative
FROM core_domain_correlation
WHERE user_id = ? AND status = 'active'
ORDER BY strength_score DESC
```

---

## 9. Keyword Search Index

Quick reference for finding where specific concepts live in the database:

| Keyword | Tables | Engine | Notes |
|---------|--------|--------|-------|
| **PIE** | `core_ai_insight` | PIE | Proactive Insight Engine. Rule-based insights |
| **PRIE** | `core_ai_prediction` | PRIE | Predictive Intelligence Engine. Regression projections |
| **SAE** | `core_user_state` | SAE | State Awareness Engine. Single truth layer |
| **PGE** | `core_guidance_item` | PGE | Proactive Guidance Engine. Actionable guidance |
| **CoS** | No own tables — reads from `core_user_state`, `core_ai_insight`, `core_ai_prediction`, `core_guidance_item` | Context Builder | Context of Self. Assembles AI system prompt |
| **DBE** | `core_daily_briefing` | DBE | Daily Briefing Engine |
| **WIRE** | `core_weekly_intelligence_report` | WIRE | Weekly reports |
| **DNE** | `core_delivered_notification` | DNE | Delivery & Notification Engine |
| **EAE** | `ai_eae_eaestate`, `ai_eae_eaedecisionlog`, `ai_eae_eaeoverride`, `ai_eae_eaeescalationevent` | EAE | Executive Arbitration Engine |
| **UAL** | `core_arbitration_decision_log`, `core_daily_capacity_log`, `core_scenario_history`, `core_weight_adjustment` | UAL | Unified Arbitration Logic |
| **CDCE** | `core_domain_correlation` | CDCE | Cross-Domain Correlation Engine |
| **GLOE** | `core_user_learned_profile`, `core_learning_extraction` | GLOE | Guidance Learning & Optimization |
| **SLCME** | `core_learned_mapping`, `core_context_snapshot`, `core_clarification_log` | SLCME | Self-Learning Context Memory |
| **ISE** | `core_scheduler_heartbeat` | ISE | Intelligence Scheduling Engine |
| **SAME** | `core_ops_anomaly`, `core_ops_narrative_snapshot`, `core_system_integrity_snapshot`, `core_same_execution_log` | SAME | System Anomaly Monitoring |
| **IOCD** | `core_diag_engine_run`, `core_diag_engine_span`, `core_diag_decision_record`, `core_engine_heartbeat`, `core_engine_expected_cadence`, `core_intelligencemetricssnapshot` | IOCD | Intelligence Observability |
| **Blueprint** | `core_personaloperatingblueprint`, `core_nonnegotiable`, `core_architectureplan`, `core_scheduledblock`, `core_driftevent`, `core_driftscore`, `core_interventionlog`, `core_frictiongatelog` | Blueprint | Schedule architecture & drift detection |
| **Governance** | `core_governanceprofile`, `core_governancealignmentsession`, `core_selferror` | Governance | Module commitment levels |
| **Feedback** | `core_prediction_outcome`, `core_prediction_accuracy_profile`, `core_insight_engagement`, `core_insight_engagement_profile`, `core_briefing_engagement`, `core_briefing_engagement_profile`, `core_intervention_effectiveness_profile` | Feedback Loop | Engagement tracking & calibration |
| **Weight** | `health_weightentry`, `health_weightgoal`, `health_transformationprotocol` | Domain | Weight tracking & goals |
| **Sleep** | `health_sleepentry` | Domain | Sleep tracking |
| **Blood Pressure** | `health_bloodpressureentry` | Domain | BP tracking |
| **Glucose** | `health_glucoseentry` | Domain | Blood sugar tracking |
| **Medicine** | `health_medicineschedule`, `health_medicinelog` | Domain | Medicine schedules & logging |
| **Nutrition** | `health_foodentry` | Domain | Food/calorie tracking |
| **Fasting** | `health_fastingwindow` | Domain | Intermittent fasting |
| **Workout** | `health_workoutsession`, `health_exerciseset` | Domain | Exercise tracking |
| **Prayer** | `faith_prayerrequest` | Domain | Prayer tracking |
| **Scripture** | `faith_userreadingprogress`, `faith_userreadingplan` | Domain | Bible reading |
| **Journal** | `journal_journalentry`, `journal_emotion` | Domain | Journaling |
| **Lab Results** | `medical_labresult`, `medical_labtestcatalog`, `medical_labpanel` | Domain | Medical lab data |
| **Finance** | `finance_financialaccount`, `finance_transaction`, `finance_budget`, `finance_financialgoal` | Domain | Financial tracking |
| **SMS** | `sms_smsnotification`, `sms_smsresponse` | DNE/Domain | Text message notifications |
| **Billing** | `billing_billingprofile`, `billing_credittransaction` | Billing | Subscription & payments |
| **Coaching Style** | `ai_coachingstyle` | AI | AI personality customization |
| **Soft Delete** | Any `UserOwnedModel` or `SoftDeleteModel` — `status` field | Framework | `active`/`archived`/`deleted` |
| **Drift** | `core_driftevent`, `core_driftscore` | Blueprint | Behavioral drift from commitments |
| **Escalation** | `ai_eae_eaeescalationevent`, `core_interventionlog` | EAE/Blueprint | Escalation level changes |
| **Capacity** | `core_daily_capacity_log` | UAL | User cognitive/emotional capacity |
| **Anomaly** | `core_ops_anomaly` | SAME | System health anomalies |
| **Correlation** | `core_domain_correlation` | CDCE | Cross-domain data correlations |
| **Noise Budget** | `core_eaestate.noise_budget_used_today` | EAE | Daily notification limit |
| **Override** | `ai_eae_eaeoverride` | EAE | User signal suppression (3-strike) |
| **Dedupe** | `dedupe_key` field on Insight, Prediction, GuidanceItem, DomainCorrelation | Multiple | Prevents duplicate intelligence outputs |
| **Calendar** | `calendar_engine_calendarevent`, `calendar_engine_recurrencerule` | Domain | Calendar events & scheduling |
| **Meals** | `meals_mealplan`, `meals_pantryitem`, `meals_ingredient`, `meals_receipt` | Domain | Meal planning & pantry |
| **Notes** | `notes_note`, `notes_noteattachment`, `notes_noteimage` | Domain | Quick notes & attachments |
| **CoS Reflections** | `cos_cosreflection`, `cos_cospromptschedule`, `cos_cosgoalsuggestion` | CoS | Contextual reflections & prompts |
| **Tasks** | `life_task` | Domain | User tasks & to-dos |
| **Pets** | `life_pet`, `life_petrecord` | Domain | Pet tracking |
| **Inventory** | `life_inventoryitem`, `life_inventoryphoto` | Domain | Home inventory |
| **Relationships** | `relationships_person`, `relationships_relationshipinteraction`, `relationships_mention` | Domain | People & interaction tracking |
| **Owner Finance** | `owner_finance_llmusageevent`, `owner_finance_dailycostrollup`, `owner_finance_budgetguardrail` | Admin | Platform cost tracking |
| **Conversation** | `ai_assistantconversation`, `ai_assistantmessage` | AI | Chat history |
| **LLM Usage** | `owner_finance_llmusageevent`, `owner_finance_llmpricebook` | Admin | AI cost tracking per call |

---

## 10. Master Table Listing

Every table in the WLJ database, verified against Django ORM. Use these exact names in DBeaver.

### admin_console (18 tables)
| Table | Model |
|-------|-------|
| `admin_console_adminactivitylog` | AdminActivityLog |
| `admin_console_adminguidearticle` | AdminGuideArticle |
| `admin_console_adminguidesection` | AdminGuideSection |
| `admin_console_adminproject` | AdminProject |
| `admin_console_adminprojectphase` | AdminProjectPhase |
| `admin_console_admintask` | AdminTask |
| `admin_console_admintaskcategoryconfig` | AdminTaskCategoryConfig |
| `admin_console_admintaskeffortconfig` | AdminTaskEffortConfig |
| `admin_console_admintaskpriorityconfig` | AdminTaskPriorityConfig |
| `admin_console_admintaskstatusconfig` | AdminTaskStatusConfig |
| `admin_console_dataloadconfig` | DataLoadConfig |
| `admin_console_emailnotificationtemplate` | EmailNotificationTemplate |
| `admin_console_systemannouncement` | SystemAnnouncement |
| `admin_console_systemannouncementdismissal` | SystemAnnouncementDismissal |
| `admin_console_testcycle` | TestCycle |
| `admin_console_testitem` | TestItem |
| `admin_console_testphase` | TestPhase |
| `admin_console_uitestrun` | UITestRun |

### ai (17 tables)
| Table | Model |
|-------|-------|
| `ai_aiinsight` | AIInsight |
| `ai_aipromptconfig` | AIPromptConfig |
| `ai_aiusagelog` | AIUsageLog |
| `ai_assistantconversation` | AssistantConversation |
| `ai_assistantmessage` | AssistantMessage |
| `ai_behavioralpattern` | BehavioralPattern |
| `ai_coachingstyle` | CoachingStyle |
| `ai_conversationmemory` | ConversationMemory |
| `ai_correctionrecord` | CorrectionRecord |
| `ai_dailypriority` | DailyPriority |
| `ai_messageimage` | MessageImage |
| `ai_reflectionpromptqueue` | ReflectionPromptQueue |
| `ai_responsepreference` | ResponsePreference |
| `ai_trendanalysis` | TrendAnalysis |
| `ai_userstatesnapshot` | UserStateSnapshot |
| `ai_valuesguardrailpattern` | ValuesGuardrailPattern |
| `ai_valuesredirectsuggestion` | ValuesRedirectSuggestion |

### ai_eae (4 tables)
| Table | Model |
|-------|-------|
| `ai_eae_eaedecisionlog` | EAEDecisionLog |
| `ai_eae_eaeescalationevent` | EAEEscalationEvent |
| `ai_eae_eaeoverride` | EAEOverride |
| `ai_eae_eaestate` | EAEState |

### ai_relationships (3 tables)
| Table | Model |
|-------|-------|
| `ai_relationships_interactionsignal` | InteractionSignal |
| `ai_relationships_person` | Person |
| `ai_relationships_relationship` | Relationship |

### assistant (2 tables)
| Table | Model |
|-------|-------|
| `assistant_improvementtaskmodel` | ImprovementTaskModel |
| `assistant_safetylimitoverride` | SafetyLimitOverride |

### billing (11 tables)
| Table | Model |
|-------|-------|
| `billing_billingconfiguration` | BillingConfiguration |
| `billing_billingprofile` | BillingProfile |
| `billing_credittransaction` | CreditTransaction |
| `billing_featuresuggestion` | FeatureSuggestion |
| `billing_foundingmemberpayout` | FoundingMemberPayout |
| `billing_paymentauditlog` | PaymentAuditLog |
| `billing_promocodeusage` | PromoCodeUsage |
| `billing_referralqualification` | ReferralQualification |
| `billing_referralreward` | ReferralReward |
| `billing_vippromocode` | VIPPromoCode |
| `billing_vippromocodeusage` | VIPPromoCodeUsage |

### brain_training (7 tables)
| Table | Model |
|-------|-------|
| `brain_training_challenge` | Challenge |
| `brain_training_challengequeue` | ChallengeQueue |
| `brain_training_dailystats` | DailyStats |
| `brain_training_game` | Game |
| `brain_training_gamesession` | GameSession |
| `brain_training_usergamestats` | UserGameStats |
| `brain_training_useroverallstats` | UserOverallStats |

### calendar_engine (5 tables)
| Table | Model |
|-------|-------|
| `calendar_engine_calendarevent` | CalendarEvent |
| `calendar_engine_calendaroverridelog` | CalendarOverrideLog |
| `calendar_engine_declinedsuggestion` | DeclinedSuggestion |
| `calendar_engine_recurrenceexception` | RecurrenceException |
| `calendar_engine_recurrencerule` | RecurrenceRule |

### capture (2 tables)
| Table | Model |
|-------|-------|
| `capture_captureentry` | CaptureEntry |
| `capture_pendingcapture` | PendingCapture |

### core — Intelligence & Platform (70+ tables)
| Table | Model | Engine |
|-------|-------|--------|
| `core_admin_intervention` | AdminIntervention | SAME |
| `core_ai_insight` | Insight | PIE |
| `core_ai_prediction` | Prediction | PRIE |
| `core_apirequestlog` | APIRequestLog | — |
| `core_arbitration_decision_log` | ArbitrationDecisionLog | UAL |
| `core_architectureplan` | ArchitecturePlan | Blueprint |
| `core_behavioraltrend` | BehavioralTrend | — |
| `core_briefing_engagement` | BriefingEngagement | Feedback |
| `core_briefing_engagement_profile` | BriefingEngagementProfile | Feedback |
| `core_camerascan` | CameraScan | — |
| `core_category` | Category | — |
| `core_choicecategory` | ChoiceCategory | — |
| `core_choiceoption` | ChoiceOption | — |
| `core_clarification_log` | ClarificationLog | SLCME |
| `core_commitment` | Commitment | Governance |
| `core_commitmentanalytics` | CommitmentAnalytics | Governance |
| `core_commitmentrenegotiation` | CommitmentRenegotiation | Governance |
| `core_context_snapshot` | ContextSnapshot | SLCME |
| `core_daily_briefing` | DailyBriefing | DBE |
| `core_daily_capacity_log` | DailyCapacityLog | UAL |
| `core_deadlinesnapshot` | DeadlineSnapshot | — |
| `core_delivered_notification` | DeliveredNotification | DNE |
| `core_diag_decision_record` | DecisionRecord | IOCD |
| `core_diag_engine_run` | EngineRun | IOCD |
| `core_diag_engine_span` | EngineSpan | IOCD |
| `core_domain_correlation` | DomainCorrelation | CDCE |
| `core_drift_signal` | DriftSignal | Blueprint |
| `core_driftevent` | DriftEvent | Blueprint |
| `core_driftscore` | DriftScore | Blueprint |
| `core_engine_execution_log` | EngineExecutionLog | IOCD |
| `core_engine_expected_cadence` | EngineExpectedCadence | IOCD |
| `core_engine_heartbeat` | EngineHeartbeat | IOCD |
| `core_engine_run_token` | EngineRunToken | IOCD |
| `core_escalationevent` | EscalationEvent | Blueprint |
| `core_escalationstate` | EscalationState | Blueprint |
| `core_eventreflection` | EventReflection | — |
| `core_execution_log` | ExecutionLog | — |
| `core_explain_record` | ExplainRecord | E3 |
| `core_favoritepage` | FavoritePage | — |
| `core_governancealignmentsession` | GovernanceAlignmentSession | Governance |
| `core_governanceprofile` | GovernanceProfile | Governance |
| `core_guidance_item` | GuidanceItem | PGE |
| `core_guidance_learning_event` | GuidanceLearningEvent | GLOE |
| `core_guidance_learning_profile` | GuidanceLearningProfile | GLOE |
| `core_insight_engagement` | InsightEngagement | Feedback |
| `core_insight_engagement_profile` | InsightEngagementProfile | Feedback |
| `core_intelligencemetricssnapshot` | IntelligenceMetricsSnapshot | IOCD |
| `core_intervention_effectiveness_profile` | InterventionEffectivenessProfile | Feedback |
| `core_intervention_response_log` | InterventionResponseLog | UAL |
| `core_interventionlog` | InterventionLog | Blueprint |
| `core_learned_mapping` | LearnedMapping | SLCME |
| `core_learning_extraction` | LearningExtraction | GLOE |
| `core_nonnegotiable` | NonNegotiable | Blueprint |
| `core_notification` | Notification | — |
| `core_ops_anomaly` | OpsAnomaly | SAME |
| `core_ops_narrative_snapshot` | OpsNarrativeSnapshot | SAME |
| `core_pageview` | PageView | — |
| `core_personaloperatingblueprint` | PersonalOperatingBlueprint | Blueprint |
| `core_prediction_accuracy_profile` | PredictionAccuracyProfile | Feedback |
| `core_prediction_outcome` | PredictionOutcome | Feedback |
| `core_pressuresnapshot` | PressureSnapshot | — |
| `core_pressureweightconfig` | PressureWeightConfig | — |
| `core_protectiveactionlog` | ProtectiveActionLog | — |
| `core_protectivealert` | ProtectiveAlert | — |
| `core_protectiverecommendation` | ProtectiveRecommendation | — |
| `core_quality_metric_aggregate` | QualityMetricAggregate | IOCD |
| `core_quality_suppression` | QualitySuppressionRecord | IOCD |
| `core_recent_nudge_memory` | RecentNudgeMemory | UAL |
| `core_releasenote` | ReleaseNote | — |
| `core_same_execution_log` | SAMEExecutionLog | SAME |
| `core_scenario_history` | ScenarioHistory | UAL |
| `core_scheduled_intelligence_task` | ScheduledIntelligenceTask | ISE |
| `core_scheduledblock` | ScheduledBlock | Blueprint |
| `core_scheduler_heartbeat` | SchedulerHeartbeat | ISE |
| `core_scheduler_lock` | SchedulerLock | ISE |
| `core_selferror` | SelfError | Governance |
| `core_semantic_decision_log` | SemanticDecisionLog | — |
| `core_siteconfiguration` | SiteConfiguration | — |
| `core_system_integrity_snapshot` | SystemIntegritySnapshot | SAME |
| `core_tag` | Tag | — |
| `core_testrun` | TestRun | — |
| `core_testrundetail` | TestRunDetail | — |
| `core_theme` | Theme | — |
| `core_tier1overrideevent` | Tier1OverrideEvent | Blueprint |
| `core_user_learned_profile` | UserLearnedProfile | GLOE |
| `core_user_state` | UserState | SAE |
| `core_useractivitypattern` | UserActivityPattern | — |
| `core_userdailyactivity` | UserDailyActivity | — |
| `core_userpriorityprofile` | UserPriorityProfile | — |
| `core_userreleasenoteview` | UserReleaseNoteView | — |
| `core_weekly_intelligence_report` | WeeklyIntelligenceReport | WIRE |
| `core_weight_adjustment` | WeightAdjustment | UAL |

### cos (4 tables)
| Table | Model |
|-------|-------|
| `cos_cosautoshiftlog` | CosAutoShiftLog |
| `cos_cosgoalsuggestion` | CosGoalSuggestion |
| `cos_cospromptschedule` | CosPromptSchedule |
| `cos_cosreflection` | CosReflection |

### dashboard (1 table)
| Table | Model |
|-------|-------|
| `dashboard_dailyencouragement` | DailyEncouragement |

### faith (14 tables)
| Table | Model |
|-------|-------|
| `faith_biblebookmark` | BibleBookmark |
| `faith_biblehighlight` | BibleHighlight |
| `faith_biblestudynote` | BibleStudyNote |
| `faith_dailyverse` | DailyVerse |
| `faith_faithmilestone` | FaithMilestone |
| `faith_prayerrequest` | PrayerRequest |
| `faith_readingplanassessment` | ReadingPlanAssessment |
| `faith_readingplanday` | ReadingPlanDay |
| `faith_readingplantemplate` | ReadingPlanTemplate |
| `faith_savedverse` | SavedVerse |
| `faith_scriptureverse` | ScriptureVerse |
| `faith_userassessmentresponse` | UserAssessmentResponse |
| `faith_userreadingplan` | UserReadingPlan |
| `faith_userreadingprogress` | UserReadingProgress |

### finance (12 tables)
| Table | Model |
|-------|-------|
| `finance_bankconnection` | BankConnection |
| `finance_bankintegrationlog` | BankIntegrationLog |
| `finance_budget` | Budget |
| `finance_financeauditlog` | FinanceAuditLog |
| `finance_financialaccount` | FinancialAccount |
| `finance_financialgoal` | FinancialGoal |
| `finance_financialmetricsnapshot` | FinancialMetricSnapshot |
| `finance_payee` | Payee |
| `finance_recurringtransaction` | RecurringTransaction |
| `finance_transaction` | Transaction |
| `finance_transactioncategory` | TransactionCategory |
| `finance_transactionimport` | TransactionImport |

### health (38 tables)
| Table | Model |
|-------|-------|
| `health_audioexposureentry` | AudioExposureEntry |
| `health_bloodoxygenentry` | BloodOxygenEntry |
| `health_bloodpressureentry` | BloodPressureEntry |
| `health_bodycompositionentry` | BodyCompositionEntry |
| `health_bodytemperatureentry` | BodyTemperatureEntry |
| `health_cardiodetails` | CardioDetails |
| `health_classdetails` | ClassDetails |
| `health_customfood` | CustomFood |
| `health_cycle` | Cycle |
| `health_cycledailylog` | CycleDailyLog |
| `health_cycleprediction` | CyclePrediction |
| `health_cyclesettings` | CycleSettings |
| `health_dailyhealthsummary` | DailyHealthSummary |
| `health_dailynutritionsummary` | DailyNutritionSummary |
| `health_dexcomcredential` | DexcomCredential |
| `health_dietarynutriententry` | DietaryNutrientEntry |
| `health_exercise` | Exercise |
| `health_exerciseset` | ExerciseSet |
| `health_fastingwindow` | FastingWindow |
| `health_foodentry` | FoodEntry |
| `health_fooditem` | FoodItem |
| `health_fooditemoverride` | FoodItemOverride |
| `health_glucoseentry` | GlucoseEntry |
| `health_healthprofile` | HealthProfile |
| `health_heartrateentry` | HeartRateEntry |
| `health_heartrateevententry` | HeartRateEventEntry |
| `health_insightresult` | InsightResult |
| `health_mealtemplate` | MealTemplate |
| `health_mealtemplateitem` | MealTemplateItem |
| `health_medicalprovider` | MedicalProvider |
| `health_medicine` | Medicine |
| `health_medicinelog` | MedicineLog |
| `health_medicineschedule` | MedicineSchedule |
| `health_mobilityentry` | MobilityEntry |
| `health_nutritionentryaudit` | NutritionEntryAudit |
| `health_nutritiongoals` | NutritionGoals |
| `health_nutritionlabelevidence` | NutritionLabelEvidence |
| `health_personalrecord` | PersonalRecord |
| `health_providerstaff` | ProviderStaff |
| `health_sleepentry` | SleepEntry |
| `health_stepsentry` | StepsEntry |
| `health_templateexercise` | TemplateExercise |
| `health_templateexerciseset` | TemplateExerciseSet |
| `health_transformationprotocol` | TransformationProtocol |
| `health_waterentry` | WaterEntry |
| `health_weightentry` | WeightEntry |
| `health_workoutexercise` | WorkoutExercise |
| `health_workoutplan` | WorkoutPlan |
| `health_workoutschedule` | WorkoutSchedule |
| `health_workoutsession` | WorkoutSession |
| `health_workouttemplate` | WorkoutTemplate |

### help (7 tables)
| Table | Model |
|-------|-------|
| `help_adminhelptopic` | AdminHelpTopic |
| `help_helparticle` | HelpArticle |
| `help_helpcategory` | HelpCategory |
| `help_helpconversation` | HelpConversation |
| `help_helpmessage` | HelpMessage |
| `help_helptopic` | HelpTopic |
| `help_teachingdestination` | TeachingDestination |

### journal (4 tables)
| Table | Model |
|-------|-------|
| `journal_emotion` | Emotion |
| `journal_entrylink` | EntryLink |
| `journal_journalentry` | JournalEntry |
| `journal_journalprompt` | JournalPrompt |

### life (17 tables)
| Table | Model |
|-------|-------|
| `life_document` | Document |
| `life_gmailcredential` | GmailCredential |
| `life_googlecalendarcredential` | GoogleCalendarCredential |
| `life_inventoryitem` | InventoryItem |
| `life_inventoryphoto` | InventoryPhoto |
| `life_lifeevent` | LifeEvent |
| `life_maintenancelog` | MaintenanceLog |
| `life_pet` | Pet |
| `life_petrecord` | PetRecord |
| `life_processedemail` | ProcessedEmail |
| `life_project` | Project |
| `life_recipe` | Recipe |
| `life_recipebulkimportphoto` | RecipeBulkImportPhoto |
| `life_recipebulkimportsession` | RecipeBulkImportSession |
| `life_shoppingitem` | ShoppingItem |
| `life_shoppinglist` | ShoppingList |
| `life_significantevent` | SignificantEvent |
| `life_task` | Task |

### meals (14 tables)
| Table | Model |
|-------|-------|
| `meals_dietaryprofile` | DietaryProfile |
| `meals_household` | Household |
| `meals_householdmembership` | HouseholdMembership |
| `meals_ingredient` | Ingredient |
| `meals_inventorytransaction` | InventoryTransaction |
| `meals_mealplan` | MealPlan |
| `meals_mealplanentry` | MealPlanEntry |
| `meals_pantryitem` | PantryItem |
| `meals_pantryphotodetection` | PantryPhotoDetection |
| `meals_pantryphotoupload` | PantryPhotoUpload |
| `meals_pantryscansession` | PantryScanSession |
| `meals_receipt` | Receipt |
| `meals_receiptitem` | ReceiptItem |
| `meals_recipeingredient` | RecipeIngredient |

### medical (9 tables)
| Table | Model |
|-------|-------|
| `medical_importbatch` | ImportBatch |
| `medical_importerrorrow` | ImportErrorRow |
| `medical_labeducationcontent` | LabEducationContent |
| `medical_labpanel` | LabPanel |
| `medical_labresult` | LabResult |
| `medical_labtestalias` | LabTestAlias |
| `medical_labtestcatalog` | LabTestCatalog |
| `medical_medicalauditlog` | MedicalAuditLog |
| `medical_medicaldocument` | MedicalDocument |

### mobile (4 tables)
| Table | Model |
|-------|-------|
| `mobile_healthingestionrun` | HealthIngestionRun |
| `mobile_mobileapitoken` | MobileAPIToken |
| `mobile_mobiledevice` | MobileDevice |
| `mobile_mobiletokenexchangecode` | MobileTokenExchangeCode |

### notes (3 tables)
| Table | Model |
|-------|-------|
| `notes_note` | Note |
| `notes_noteattachment` | NoteAttachment |
| `notes_noteimage` | NoteImage |

### owner_finance (7 tables)
| Table | Model |
|-------|-------|
| `owner_finance_budgetguardrail` | BudgetGuardrail |
| `owner_finance_dailycostrollup` | DailyCostRollup |
| `owner_finance_llmpricebook` | LLMPriceBook |
| `owner_finance_llmusageevent` | LLMUsageEvent |
| `owner_finance_thirdpartyvendor` | ThirdPartyVendor |
| `owner_finance_usersubscriptionsnapshot` | UserSubscriptionSnapshot |
| `owner_finance_vendorbillingrecord` | VendorBillingRecord |

### purpose (12 tables)
| Table | Model |
|-------|-------|
| `purpose_annualdirection` | AnnualDirection |
| `purpose_changeintention` | ChangeIntention |
| `purpose_goalinsight` | GoalInsight |
| `purpose_goalmilestone` | GoalMilestone |
| `purpose_habitentry` | HabitEntry |
| `purpose_habitgoal` | HabitGoal |
| `purpose_lifedomain` | LifeDomain |
| `purpose_lifegoal` | LifeGoal |
| `purpose_planningaction` | PlanningAction |
| `purpose_reflection` | Reflection |
| `purpose_reflectionprompt` | ReflectionPrompt |
| `purpose_reflectionresponse` | ReflectionResponse |

### relationships (4 tables)
| Table | Model |
|-------|-------|
| `relationships_mention` | Mention |
| `relationships_person` | Person |
| `relationships_persongroup` | PersonGroup |
| `relationships_relationshipinteraction` | RelationshipInteraction |

### scan (3 tables)
| Table | Model |
|-------|-------|
| `scan_imageanalysis` | ImageAnalysis |
| `scan_scanconsent` | ScanConsent |
| `scan_scanlog` | ScanLog |

### security (6 tables)
| Table | Model |
|-------|-------|
| `security_acknowledgedfinding` | AcknowledgedFinding |
| `security_securityauditlog` | SecurityAuditLog |
| `security_securityfinding` | SecurityFinding |
| `security_securityrun` | SecurityRun |
| `security_securityscore` | SecurityScore |
| `security_securitytest` | SecurityTest |

### sms (2 tables)
| Table | Model |
|-------|-------|
| `sms_smsnotification` | SMSNotification |
| `sms_smsresponse` | SMSResponse |

### users (13 tables)
| Table | Model |
|-------|-------|
| `users_account_deletion_audit` | AccountDeletionAudit |
| `users_allowed_international_email` | AllowedInternationalEmail |
| `users_disposable_email_domain` | DisposableEmailDomain |
| `users_externallink` | ExternalLink |
| `users_ip_blocklist` | IPBlocklist |
| `users_mfaemailcode` | MFAEmailCode |
| `users_moduledefinition` | ModuleDefinition |
| `users_signup_attempt` | SignupAttempt |
| `users_termsacceptance` | TermsAcceptance |
| `users_user` | User |
| `users_usermodulepreference` | UserModulePreference |
| `users_userpreferences` | UserPreferences |
| `users_webauthncredential` | WebAuthnCredential |

### Third-Party Tables (also in database)
| Prefix | Package | Purpose |
|--------|---------|---------|
| `account_*` | django-allauth | Email verification & social auth |
| `auth_*` | Django auth | Groups & permissions |
| `axes_*` | django-axes | Login attempt throttling |
| `django_apscheduler_*` | APScheduler | Background job scheduling |
| `djstripe_*` | dj-stripe | Stripe payment integration (50+ tables) |
| `django_content_type` | Django | Content type registry for GenericFK |
| `django_session` | Django | Session storage |
| `django_site` | Django sites | Multi-site support |

---

*This document was generated from Django model definitions and verified against the production database on 2026-03-06. Table names are authoritative — use exactly as shown in DBeaver.*
