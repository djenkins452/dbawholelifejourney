# Universal Arbitration Layer — Implementation Report

**Date:** 2026-02-21
**Engine:** UAL — Universal Arbitration Layer
**Location:** `apps/core/ai_arbitration/`
**Status:** Deployed

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES                       │
├────────┬──────────┬──────────┬──────────┬─────────────┤
│  SAE   │   PIE    │  PRIE    │   PGE    │   Drift     │
│ State  │ Insights │ Predict  │ Guidance │   Engine    │
├────────┼──────────┼──────────┼──────────┼─────────────┤
│ Sleep  │ Medicine │ Calendar │ Schedule │ Relation-   │
│ Entry  │   Logs   │  Events  │ Density  │ ship Engine │
├────────┴──────────┴──────────┴──────────┴─────────────┤
│                  Life Events / Open Loops               │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────┐
        │    SIGNAL COLLECTOR              │
        │    Normalise → 0-1 strengths     │
        │    14 signal dimensions          │
        └──────────────────┬───────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
  ┌─────────────────────┐  ┌─────────────────────┐
  │ SCENARIO CLASSIFIER │  │   SIGNAL FUSER      │
  │ Weighted scoring    │  │ Cross-domain         │
  │ → 1 dominant        │  │ composites           │
  │ → N secondaries     │  │ (7 patterns)         │
  └──────────┬──────────┘  └──────────┬──────────┘
             │                        │
             └────────────┬───────────┘
                          ▼
          ┌───────────────────────────────┐
          │  INTERVENTION DECISION ENGINE │
          │  Style selection              │
          │  Surface max 3                │
          │  Suppress competing           │
          └───────────────┬───────────────┘
                          ▼
          ┌───────────────────────────────┐
          │  NARRATIVE ENGINE             │
          │  "What is the story of this   │
          │   moment?"                    │
          │  → System prompt injection    │
          └───────────────┬───────────────┘
                          ▼
          ┌───────────────────────────────┐
          │  DECISION LOG                 │
          │  ArbitrationDecisionLog       │
          │  (non-blocking)               │
          └───────────────┬───────────────┘
                          ▼
          ┌───────────────────────────────┐
          │  PERSONAL ASSISTANT           │
          │  System prompt injection      │
          │  between Executive Briefing   │
          │  and final message gen        │
          └───────────────────────────────┘
```

---

## Signal Scoring Model

### 14 Signal Dimensions (normalised 0-1)

| Signal | Source | Normalisation |
|--------|--------|---------------|
| `calendar_urgency` | LifeEvent, ScheduledBlock | Events in next 4h + conflicts |
| `deadline_pressure` | Task (overdue + approaching) | `overdue×0.3 + approaching×0.15` |
| `medication_risk` | MedicineLog | 0 = all taken, 0.3 = pending, 0.5+ = missed |
| `sleep_deficit` | SleepEntry | `1 - (duration/target)`, clamped 0-1 |
| `injury_risk` | Journal keywords | 0.7 if injury terms detected |
| `drift_severity` | DriftEngine | `score/60 + 0.2 if 24h_prob > 0.7` |
| `non_negotiable_miss` | DriftEvent | `count × 0.4`, capped at 1.0 |
| `mood_decline` | Journal mood trend | 0.6+ if falling, boosted by emotional keywords |
| `emotional_load` | Journal keywords | `count × 0.25` (stress, anxiety, fatigue, etc.) |
| `relationship_drift` | RelationshipEngine | `tier1×0.5 + tier2×0.2` |
| `relationship_event` | SignificantEvent | 1.0 today, 0.8 tomorrow, 0.6 within 3d, 0.3 within 7d |
| `schedule_overload` | WeeklyPressure | `(capacity - 50) / 50`, clamped 0-1 |
| `open_loop_count` | Task (overdue) | Stepped: 0→0, 1-2→0.2, 3-5→0.4, 6-10→0.6, 10+→0.8 |

---

## Scenario Classification Logic

### 6 Scenario Types

| Scenario | Primary Signals | Weights |
|----------|----------------|---------|
| `TIME_CRITICAL` | calendar_urgency (0.35), deadline_pressure (0.30), schedule_overload (0.20), open_loops (0.15) |
| `HEALTH_CRITICAL` | medication_risk (0.35), sleep_deficit (0.25), injury_risk (0.20), mood (0.10), schedule (0.10) |
| `DRIFT_CRITICAL` | drift_severity (0.40), non_negotiable_miss (0.35), open_loops (0.15), schedule (0.10) |
| `MOOD_CRITICAL` | mood_decline (0.40), emotional_load (0.30), sleep_deficit (0.20), schedule (0.10) |
| `RELATIONSHIP_CRITICAL` | relationship_event (0.40), relationship_drift (0.35), emotional (0.15), schedule (0.10) |
| `STABLE_EXECUTION` | Default when max scenario score < 0.30 |

**Threshold:** Score ≥ 0.30 required for any non-stable scenario.
**Confidence:** Based on gap between top and second scenario.

---

## Fusion Examples

### 1. LOW_CAPACITY_DAY
**Trigger:** `sleep_deficit ≥ 0.4` AND `schedule_overload ≥ 0.3`
**Example:** 5h sleep + 85% schedule capacity
**Effect:** Overrides intervention to PROTECTIVE regardless of dominant scenario

### 2. PHYSICAL_RISK
**Trigger:** `injury_risk ≥ 0.5`
**Example:** "My shoulder hurts" in journal + workout scheduled today
**Effect:** Overrides to PROTECTIVE

### 3. RELATIONAL_OPPORTUNITY
**Trigger:** `relationship_event ≥ 0.5` AND NOT `schedule_overload ≥ 0.6` AND NOT `medication_risk ≥ 0.5`
**Example:** Mom's birthday in 2 days, light schedule today
**Effect:** Used by narrative engine for gentle surfacing

### 4. EMOTIONAL_OVERLOAD
**Trigger:** `mood_decline ≥ 0.4` AND `emotional_load ≥ 0.4`
**Example:** Falling mood + stress/anxiety in journal
**Effect:** Overrides to SUPPORTIVE

### 5. ALIGNMENT_CRISIS
**Trigger:** `drift_severity ≥ 0.5` AND `non_negotiable_miss ≥ 0.4`
**Example:** Drift score 40+ with 2 non-negotiables missed today
**Effect:** Overrides to ACCOUNTABILITY

---

## Sample Transcripts

### Scenario 1: LOW_CAPACITY_DAY
```
=== EXECUTIVE JUDGMENT (UAL) ===

DOMINANT SCENARIO: HEALTH_CRITICAL
Secondary: MOOD_CRITICAL
COMPOSITE: LOW_CAPACITY_DAY

INTERVENTION STYLE: PROTECTIVE
- Protect energy. Suggest reducing load. Frame suggestions as optional.

NARRATIVE FRAME:
Running on 300 minutes of sleep with 87% schedule capacity.
Today is about protection, not production.
Lead with health gates, then help identify what can move.

SURFACE (max 3):
  1. Medication adherence — 1/3 taken, 2 missed/late [HEALTH_GATE]
  2. Sleep deficit — 300min vs 480min target [HEALTH]
  3. Schedule density — 87% capacity [PROTECTIVE]

SUPPRESS (do not proactively raise):
  - Deadline pressure (DIRECTIVE)
  - Drift detected (ACCOUNTABILITY)

=== END EXECUTIVE JUDGMENT ===
```

### Scenario 2: TIME_CRITICAL with Deadline Convergence
```
=== EXECUTIVE JUDGMENT (UAL) ===

DOMINANT SCENARIO: TIME_CRITICAL
Secondary: DRIFT_CRITICAL

INTERVENTION STYLE: DIRECTIVE
- Time-sensitive. Lead with the urgent action. Be clear and direct.

NARRATIVE FRAME:
Time-sensitive: Team Standup at 08:00 AM.
Focus on what must happen before then.
Defer everything that can wait.

SURFACE (max 3):
  1. Next: Team Standup — At 08:00 AM [DIRECTIVE]
  2. Deadline pressure — 3 overdue, 2 approaching [DIRECTIVE]
  3. Non-negotiables missed — 1 missed today [ACCOUNTABILITY]

=== END EXECUTIVE JUDGMENT ===
```

### Scenario 3: MOOD_CRITICAL
```
=== EXECUTIVE JUDGMENT (UAL) ===

DOMINANT SCENARIO: MOOD_CRITICAL
COMPOSITE: EMOTIONAL_OVERLOAD

INTERVENTION STYLE: SUPPORTIVE
- Emotional weight present. Acknowledge first. Gentle next move only.

NARRATIVE FRAME:
Mood trend is falling (mentioning: stress, fatigue, anxiety).
Acknowledge the emotional weight first.
Offer one gentle next move, not a to-do list.

SURFACE (max 3):
  1. Mood trend — Trend: falling [SUPPORTIVE]
  2. Sleep deficit — 360min vs 480min target [HEALTH]

SUPPRESS (do not proactively raise):
  - Deadline pressure (DIRECTIVE)
  - Schedule density (PROTECTIVE)

=== END EXECUTIVE JUDGMENT ===
```

### Scenario 4: RELATIONAL_OPPORTUNITY
```
=== EXECUTIVE JUDGMENT (UAL) ===

DOMINANT SCENARIO: RELATIONSHIP_CRITICAL
COMPOSITE: RELATIONAL_OPPORTUNITY

INTERVENTION STYLE: STRATEGIC
- Forward planning opportunity. Frame the prep action and timeline.

NARRATIVE FRAME:
Mom's birthday is in 2 days. Schedule is light enough to prepare.
Surface the opportunity without being pushy.

SURFACE (max 3):
  1. Upcoming: Mom's Birthday — In 2 days (Mom) [STRATEGIC]

=== END EXECUTIVE JUDGMENT ===
```

### Scenario 5: STABLE_EXECUTION
```
=== EXECUTIVE JUDGMENT (UAL) ===

DOMINANT SCENARIO: STABLE_EXECUTION

INTERVENTION STYLE: EXECUTION
- Clean execution day. Top priority, one secondary, go.

NARRATIVE FRAME:
Clean morning. No critical signals.
Execute the day plan. Be responsive, not directive.

SURFACE: No critical items — focus on user's request.

=== END EXECUTIVE JUDGMENT ===
```

---

## Performance Impact

| Metric | Value |
|--------|-------|
| **Execution time** | <50ms typical (all DB queries, no AI calls) |
| **Database queries** | 8-12 per arbitration cycle |
| **New model** | ArbitrationDecisionLog (~500 bytes per row) |
| **Migration** | `core.0075_ual_arbitration_decision_log` |
| **Test count** | 42 tests |
| **Test runtime** | <1 second |

---

## Token Impact

| Component | Estimated Tokens |
|-----------|-----------------|
| **Minimal (STABLE_EXECUTION)** | ~80 tokens |
| **Moderate (single scenario)** | ~150 tokens |
| **Full (scenario + composite + suppress)** | ~250 tokens |
| **Maximum possible** | ~300 tokens |

The narrative injection is designed to be concise. It adds ~150 tokens on average to the system prompt — well within budget given the value of unified framing vs. raw signal dump.

---

## Future Refinement List

See `docs/FOLLOWUP_UAL.md` for deferred items including:
- Rate limiting and caching
- Mood-confidence thresholds
- Social suggestion safeguards
- Escalation calibration
- Interruption cost modeling
- Composite refinement
- Feedback loop
- Performance optimization
- Token impact mitigation

---

## Files Created/Modified

| File | Action |
|------|--------|
| `apps/core/ai_arbitration/__init__.py` | Created — Public API |
| `apps/core/ai_arbitration/models.py` | Created — ArbitrationDecisionLog |
| `apps/core/ai_arbitration/signal_collector.py` | Created — Signal collection + normalisation |
| `apps/core/ai_arbitration/scenario_classifier.py` | Created — Weighted scenario scoring |
| `apps/core/ai_arbitration/signal_fuser.py` | Created — Cross-domain composites |
| `apps/core/ai_arbitration/intervention_engine.py` | Created — Style selection + surfacing |
| `apps/core/ai_arbitration/narrative_engine.py` | Created — Executive narrative builder |
| `apps/core/ai_arbitration/arbitration_engine.py` | Created — Main orchestrator |
| `apps/core/ai_arbitration/admin.py` | Created — Read-only admin |
| `apps/core/ai_arbitration/tests.py` | Created — 42 tests |
| `apps/core/models.py` | Modified — Import ArbitrationDecisionLog |
| `apps/ai/personal_assistant.py` | Modified — UAL integration point |
| `apps/core/migrations/0075_ual_arbitration_decision_log.py` | Created |
| `docs/FOLLOWUP_UAL.md` | Created — Deferred guardrails |
| `docs/UNIVERSAL_ARBITRATION_IMPLEMENTATION_REPORT.md` | Created — This report |

---

*This layer converts intelligent signals into executive judgment. Clean. Decisive. Human.*
