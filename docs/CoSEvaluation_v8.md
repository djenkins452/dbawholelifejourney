# CoS Behavioral Evaluation Report — v8

**Date:** 2026-03-07
**Evaluator:** Claude (System Evaluation Agent)
**Status:** ARCHITECTURE DEPLOYED — Full LLM-based evaluation pending OpenAI API quota reset.

---

## Executive Summary

v8 introduces the **Situational Awareness Summary** — a deterministic behavioral pattern layer that transforms the CoS from state-aware to pattern-aware. The CoS can now distinguish one-off misses from true drift, reinforce momentum, call out drift with accountability (only when priority is provable), and modulate emotional sensitivity.

### Architecture

```
build_cos_context(user)
  → _PARALLEL_BUILDERS (13 builders, ThreadPoolExecutor)
    → _build_situational_awareness_context(user)  ← NEW (v8)
      → build_situational_awareness(user)
        → _get_workout_pattern()      → DailyHealthSummary (7d)
        → _get_weight_tracking_pattern() → WeightEntry (7d)
        → _get_journal_pattern()       → JournalEntry (14d) + accountability gate
        → _get_mood_trend()            → JournalEntry.mood (7d, weak signal)
        → _get_medication_adherence()  → medicine_utils (7d)
        → _get_fatigue_signals()       → AssistantMessage user-only (14d)
        → _get_goal_streaks()          → HabitGoal + streak_service
      → Returns: {lines, momentum_signals, drift_signals,
                   one_off_sensitive_domains, emotional_context}
  → format_cos_system_injection(context)
    → === SITUATIONAL AWARENESS SUMMARY (v8) ===
    → PATTERN-AWARE GUIDANCE RULES (6 rules)
    → === END SITUATIONAL AWARENESS ===

Check-in path (personal_assistant.py):
  → Explicit SA injection after LOW-DATA DAY HANDLING block
  → Same build_situational_awareness() call

Executive briefing (executive_briefing.py):
  → _build_pattern_section(user) between health gate and day overview
  → PATTERN/DRIFT/ONE-OFF/EMOTIONAL CONTEXT labels
```

---

## Code Changes

| File | Change | Lines |
|------|--------|-------|
| `apps/ai/situational_awareness.py` | **NEW** — Core SA builder + formatter with 7 data signals, pattern classification, accountability gate, fatigue scanning | ~350 lines |
| `apps/core/ai_orchestrator/cos_context.py` | Added parallel builder, SA block injection, Step 7 to mandatory eval | ~25 lines added |
| `apps/ai/personal_assistant.py` | SA injection into check-in path after LOW-DATA DAY HANDLING | ~10 lines added |
| `apps/ai/executive_briefing.py` | `_build_pattern_section()` + briefing integration | ~55 lines added |
| `apps/ai/tests/test_situational_awareness.py` | **NEW** — 24 tests covering builder, formatter, integration | ~300 lines |

---

## Pattern Classification Model

| Days Active (of 7) | Classification | Meaning |
|---------------------|----------------|---------|
| 5-7 | consistent | Momentum signal, one-off sensitive |
| 3-4 | mixed | Neither momentum nor drift |
| 0-2 | slipping | Drift signal (if proven priority) |

**Critical rule:** "Not yet logged today" in a consistent domain is NOT drift — it's "outstanding" or "not yet completed." Classification is based on the 7-day trailing window, not today's incomplete state.

---

## Accountability Gate

Drift/accountability framing ONLY triggers when priority is provable:
- Active `HabitGoal` exists for that domain
- Active routine/habit in the system
- User explicitly declared it as a priority

Without evidence → informational only (softer tone).

---

## Evaluation Test Cases (Q34-Q40)

### Q34: "I usually log my weight, but I haven't today. What should I do?"
**Expected behavior:** Gentle nudge. Recognizes recent consistency. Not framed as failure. "You've been consistent with weight tracking recently — it just hasn't been logged yet today."

### Q35: "I said I wanted to journal, but I haven't done it in several days. What do you think?"
**Expected behavior:** Accountability (if journal goal exists). Recommit or remove framing. Not generic encouragement. "Journaling has dropped off this week, and you have an active goal for it. Time to recommit or formally deprioritize."

### Q36: "Should I do my workout or my bike ride today?"
**Expected behavior:** Workout treated as core discipline (non-negotiable). Bike ride treated as optional extra. "Your workout is the core habit — protect that first. The bike ride is extra and drops first if energy is limited."

### Q37: "I've been tired a lot lately. What pattern do you see?"
**Expected behavior:** References fatigue keyword matches from recent conversations. Grounded, not diagnostic. "You've mentioned tiredness in several recent conversations. That's a pattern worth paying attention to."

### Q38: "What are you noticing about how I handle my day?"
**Expected behavior:** Pattern-aware summary using workout/weight/journal/task data. Observational and executive, not generic. References specific consistency numbers.

### Q39: Open CoS midday after several days of mixed consistency
**Expected behavior:** Briefing recognizes momentum (where consistent), drift (where slipping with proven priority), and one-off sensitivity (consistent but not yet done today). Ends with focused recommendation.

### Q40: "I usually work out by now, but I haven't today."
**Expected behavior:** Recognizes recent workout consistency. Treats as outstanding, not drift. Suggests completing it rather than shaming the miss. Considers time of day context.

---

## Test Results

| Test | Status | Description |
|------|--------|-------------|
| `test_consistent` | PASS | 5-7 days = consistent |
| `test_mixed` | PASS | 3-4 days = mixed |
| `test_slipping` | PASS | 0-2 days = slipping |
| `test_empty_user_no_data` | PASS | New user returns minimal SA |
| `test_workout_consistency_high` | PASS | 5+ workouts → momentum + one_off_sensitive |
| `test_workout_consistency_low` | PASS | 1 workout → slipping classification |
| `test_workout_mixed` | PASS | 3-4 workouts → mixed, neither momentum nor drift |
| `test_journal_gap_with_active_goal` | PASS | Journal gap + active goal → drift signal |
| `test_journal_gap_no_goal` | PASS | Journal gap without goal → NOT drift |
| `test_mood_insufficient_data` | PASS | < 3 entries → mood skipped |
| `test_mood_trend_weak_signal` | PASS | Mood labeled as weak signal |
| `test_medication_adherence_included` | PASS | Active meds → line included |
| `test_medication_no_active_meds` | PASS | No meds → line skipped |
| `test_fatigue_keyword_detection` | PASS | User messages with keywords → fatigue context |
| `test_fatigue_ignores_assistant_messages` | PASS | Assistant messages → NOT detected |
| `test_no_fatigue_clean_messages` | PASS | Clean messages → none context |
| `test_one_off_sensitive_domains` | PASS | Consistent domains in one_off list |
| `test_format_with_data` | PASS | Full data → formatted block |
| `test_format_empty` | PASS | No data → empty string |
| `test_momentum_drift_labels` | PASS | Correct labels generated |
| `test_one_off_rule_in_output` | PASS | One-off guidance rule present |
| `test_emotional_context_in_output` | PASS | Emotional context guidance present |
| `test_guidance_rules_always_present` | PASS | Core discipline rule always present |
| `test_sa_in_parallel_builders` | PASS | SA key in build_cos_context() output |

**24/24 tests pass. 73/73 existing PA + briefing tests pass. 0 regressions.**

---

## Hallucination Protection Status

All v4-v7 protections confirmed intact:
- v4 Data State Snapshot + ABSOLUTE GROUNDING RULES
- v4 Calibration suppression for functional queries
- v5 Web search PERSONAL_DATA_EXCLUSIONS
- v5 Personal data query guard
- v6 CHIEF OF STAFF OPERATIONAL RULES (6 rules)
- v6 MANDATORY CONTEXT EVALUATION (now 7 steps, with SA Step 7)
- v6 Anti-template test
- v7 Proactive briefing trigger flow + cooldown

SA adds pattern awareness WITHOUT creating new AI paths — all data flows through existing `_generate_response()` pipeline.

---

## Key Design Decisions

1. **Deterministic only** — All DB queries + math, no LLM calls
2. **Parallel builder** — Runs concurrently with 12 existing builders, zero added latency
3. **Conservative classification** — consistent/mixed/slipping tiers avoid overreacting
4. **Accountability gate** — Drift framing only when priority is provable
5. **One-off sensitivity** — Consistent domains with single-day gap = gentle nudge
6. **User-only fatigue scanning** — Prevents feedback loops from assistant message amplification
7. **Mood as weak signal** — Never anchors major guidance on mood averages alone
8. **Separation of concerns** — SA provides pattern data; time context from existing builders

---

*Generated by CoS Evaluation Pipeline v8 — 2026-03-07*
*Full LLM-based Q34-Q40 evaluation pending API quota reset*
