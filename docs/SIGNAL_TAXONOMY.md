# WLJ Signal Taxonomy — Canonical Reference

**Date:** 2026-03-16 (Phase 4 domain alignment applied)
**Status:** LOCKED — Canonical signal taxonomy for WLJ Architecture Evolution
**Phase:** 3 (Signal Taxonomy Design), updated Phase 4 (Signal Governance Alignment)

---

## 1. Purpose

This document defines the complete signal taxonomy for WLJ — the normalized vocabulary
through which all domain activity is expressed, scored, classified, and consumed by
the goal momentum engine and Beth's reasoning layer.

---

## 2. Signal Types

### 2.1 health_activity

| Property | Value |
|----------|-------|
| **Domain** | health |
| **Description** | Physical activity level for the day |
| **Sources** | WorkoutSession, Steps (HealthKit), manual exercise entries |
| **Default signal_class** | `verified_action` (workout), `verified_measurement` (steps) |

**Normalization:**
- 0.0 = No activity recorded
- 0.5 = 5,000 steps OR 20 minutes structured exercise
- 1.0 = 10,000+ steps OR 45+ minutes structured exercise
- Interpolation: linear between reference points
- Multiple sources: max(structured_exercise_score, step_score)

**Aggregation:** When both workout and step data exist for one day, take the
higher of the two normalized scores. Both contribute but don't stack.

---

### 2.2 health_biometrics

| Property | Value |
|----------|-------|
| **Domain** | health |
| **Description** | Vital sign stability — how well biometric markers are in range |
| **Sources** | WeightEntry, GlucoseEntry, BloodPressureEntry, SleepEntry |
| **Default signal_class** | `verified_measurement` |

**Normalization:**
- Score is average of available sub-scores (only scored if data exists):
  - Weight: 1.0 if within ±2% of goal weight, 0.5 if ±5%, 0.0 if ±10%+
  - Glucose: 1.0 if fasting 70-100 mg/dL, 0.5 if 100-126, 0.0 if >150
  - Blood pressure: 1.0 if <120/80, 0.5 if <140/90, 0.0 if ≥160/100
  - Sleep: 1.0 if 7-9 hours, 0.5 if 6 or 9-10 hours, 0.0 if <5 or >11 hours
- Missing sub-metric: excluded from average (not scored as 0)

**Aggregation:** Average of all available sub-metric scores for the day.

---

### 2.3 medication_adherence

| Property | Value |
|----------|-------|
| **Domain** | health |
| **Description** | Medication compliance — percentage of scheduled doses taken |
| **Sources** | MedicineLog (vs MedicineSchedule) |
| **Default signal_class** | `verified_action` |

**Normalization:**
- 0.0 = <50% of scheduled doses taken
- 0.5 = 80% of scheduled doses taken
- 1.0 = 100% of scheduled doses taken on time
- Late doses count at 0.8 (80% credit)
- Skipped doses count at 0.0

**Aggregation:** `taken_count / scheduled_count` for the day, with late discount.

---

### 2.4 nutrition_compliance

| Property | Value |
|----------|-------|
| **Domain** | health |
| **Description** | Dietary adherence — tracking and target compliance |
| **Sources** | DailyNutritionLog, WaterIntake, FastingWindow |
| **Default signal_class** | `verified_action` |

**Normalization:**
- Score is average of available sub-scores:
  - Food logging: 1.0 if meals logged, 0.0 if not
  - Calorie target: 1.0 if within ±10% of target, 0.5 if ±20%, 0.0 if ±30%+
  - Water intake: 1.0 if ≥64oz, 0.5 if ≥32oz, 0.0 if <16oz
  - Fasting compliance: 1.0 if window maintained, 0.0 if broken
- Missing sub-metric: excluded from average

**Aggregation:** Average of available sub-scores.

---

### 2.5 faith_practice

| Property | Value |
|----------|-------|
| **Domain** | faith |
| **Description** | Spiritual discipline engagement for the day |
| **Sources** | UserReadingProgress, PrayerRequest activity, HabitEntry (faith habits) |
| **Default signal_class** | `verified_action` |

**Normalization:**
- Score is average of available sub-scores:
  - Bible reading: 1.0 if day's reading completed, 0.0 if not
  - Prayer: 1.0 if prayer habit completed, 0.0 if not
  - Other faith habits: 1.0 if completed, 0.0 if not
- If only one discipline tracked (e.g., only reading plan), that's the full score

**Aggregation:** Average of all faith-related completions for the day.

---

### 2.6 mental_reflection

| Property | Value |
|----------|-------|
| **Domain** | mind |
| **Description** | Introspective and journaling activity |
| **Sources** | JournalEntry, JournalSignal (NLP — Phase 7), CaptureEntry |
| **Default signal_class** | `verified_action` (journal entry), `inferred_behavior` (NLP signals) |

**Normalization:**
- 0.0 = No reflective activity
- 0.5 = Brief journal entry (<100 words) OR capture entry
- 1.0 = Substantive journal entry (100+ words) with mood tracking
- Mood tracking adds 0.2 bonus (capped at 1.0)

**Aggregation:** max(entry_score, capture_score). Journal trumps capture.

---

### 2.7 cognitive_fitness

| Property | Value |
|----------|-------|
| **Domain** | mind |
| **Description** | Brain training engagement and performance |
| **Sources** | GameSession, DailyStats |
| **Default signal_class** | `verified_action` |

**Normalization:**
- 0.0 = No brain training
- 0.5 = 1 completed session
- 1.0 = 2+ completed sessions with improvement trend
- Performance bonus: +0.1 if score improved over 7-day average (capped at 1.0)

**Aggregation:** Based on session count and performance.

---

### 2.8 productivity_progress

| Property | Value |
|----------|-------|
| **Domain** | life |
| **Description** | Task and project execution progress |
| **Sources** | Task completions, ProjectMilestone completions |
| **Default signal_class** | `verified_action` |

**Normalization:**
- Based on ratio of tasks completed to tasks due/scheduled today
- 0.0 = No tasks completed (and tasks were due)
- 0.5 = 50% of due/scheduled tasks completed
- 1.0 = All due/scheduled tasks completed
- If no tasks were due: score = 1.0 if any task completed, 0.5 if nothing due or done, skip if truly empty day

**Aggregation:** `completed_count / max(due_count, 1)` capped at 1.0.

---

### 2.9 financial_health

| Property | Value |
|----------|-------|
| **Domain** | finance |
| **Description** | Financial behavior signals |
| **Sources** | Transaction logging, Budget adherence, FinancialGoal progress |
| **Default signal_class** | `verified_action` |

**Normalization:**
- 0.0 = Over budget or no financial tracking
- 0.5 = Financial activity logged but over budget
- 1.0 = Under budget with savings progress
- This signal may be sparse (not daily) — only scored when financial data exists

**Aggregation:** Based on daily financial activity. Sparse signal — skip days with no data.

---

### 2.10 relational_engagement

| Property | Value |
|----------|-------|
| **Domain** | relationships |
| **Description** | Social and family activity |
| **Sources** | LifeEvent (family/social types), relationship interactions |
| **Default signal_class** | `verified_action` |

**Normalization:**
- 0.0 = No relational activity
- 0.5 = One social/family interaction logged
- 1.0 = Multiple meaningful interactions
- This signal is inherently sparse — many days may have no data

**Aggregation:** Based on count of relational activities. Sparse signal.

---

## 3. Signal Classes

| Class | Meaning | Set At | Framing Rule |
|-------|---------|--------|-------------|
| `verified_action` | User explicitly completed an action | Creation time, based on source model | State as fact |
| `verified_measurement` | Sensor/device/manual data entry | Creation time, based on source model | State as fact with source |
| `inferred_behavior` | NLP-extracted from unstructured text | Creation time, by NLP pipeline | Hedge: "It sounds like..." |
| `derived_pattern` | Computed from multiple signals over time | Creation time, by pattern engine | Frame as observation |

### Signal Class Assignment Rules

| Source Model | Signal Class |
|-------------|-------------|
| Task (completed) | verified_action |
| MedicineLog (taken) | verified_action |
| WorkoutSession | verified_action |
| HabitEntry (completed) | verified_action |
| UserReadingProgress (completed) | verified_action |
| JournalEntry (created) | verified_action |
| GameSession (completed) | verified_action |
| WeightEntry | verified_measurement |
| GlucoseEntry | verified_measurement |
| BloodPressureEntry | verified_measurement |
| SleepEntry | verified_measurement |
| Steps (HealthKit) | verified_measurement |
| JournalSignal (NLP extraction) | inferred_behavior |
| CaptureEntry (NLP extraction) | inferred_behavior |
| Momentum trend (computed) | derived_pattern |
| Cross-domain correlation | derived_pattern |

### Mixed Signal Class Aggregation

When a signal_type has sources from multiple signal classes on the same day:
1. Separate sources by class
2. Compute sub-score for each class independently
3. Final score = max(verified_score, inferred_score × 0.7)
4. Final signal_class = class of the highest-scoring source
5. If verified sources exist, signal_class = verified (regardless of inferred contribution)

---

## 4. Normalization Rules

### General Approach
- All scores are 0.0–1.0 (float)
- Linear interpolation between reference points
- Missing data = no SignalSnapshot row (NOT score=0.0)
- Sparse signals (finance, relationships): only scored when data exists

### Confidence Calculation
- `verified_action`: confidence = 1.0
- `verified_measurement`: confidence = 1.0 (device data) or 0.9 (manual entry)
- `inferred_behavior`: confidence = NLP extraction confidence × 0.7 (trust discount)
- `derived_pattern`: confidence = min(source_confidences) × 0.8

### No-Data vs Zero

**Critical distinction:**
- No WeightEntry today → No `health_biometrics` weight sub-score (excluded from average)
- WeightEntry shows dangerous value → `health_biometrics` weight sub-score = 0.0

Never impute missing data. Absence of data means absence of signal, not zero signal.

---

## 5. Signal → Domain Mapping

| Signal Type | Primary Domain | Cross-Domain Goals That May Consume |
|-------------|---------------|-------------------------------------|
| health_activity | health | journal (exercise supports mental health) |
| health_biometrics | health | — |
| medication_adherence | health | — (non-compensable) |
| nutrition_compliance | health | — |
| faith_practice | faith | journal (spiritual practice supports reflection) |
| mental_reflection | journal | faith (journaling supports spiritual growth) |
| cognitive_fitness | brain_training | life (brain fitness supports productivity) |
| productivity_progress | life | — |
| financial_health | finance | — |
| relational_engagement | relationships | journal (social connection supports mental health) |

> **Phase 4 Note:** Domain values are aligned with the Domain Registry (Phase 3).
> `mind` was split into `journal` and `brain_training` to match canonical domain keys.
> `work` was consolidated to `life`.

---

## 6. Aggregation Schedule

| Method | Trigger | Use Case |
|--------|---------|----------|
| **Nightly batch** | Celery Beat at 11:30 PM local | Primary: compute all signal types for all active users |
| **On-demand** | API call / dashboard load | Secondary: recompute signals for current user for today (cache 5 min) |

The nightly batch is the authoritative run. On-demand computation allows real-time
feedback during the day but may not reflect the final daily score (activities may
still occur after the on-demand call).

---

*This document is the canonical signal taxonomy for WLJ. Signal types, classes, and
normalization rules defined here are implemented in Phase 4 (Signal Persistence) and
consumed by Phase 5 (Goal-Signal Configuration) and beyond.*
