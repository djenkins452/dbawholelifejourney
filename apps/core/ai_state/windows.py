"""
Phase 2 — Canonical lookback windows.

Single source of truth for "how many days does this signal look back?".
The audit found that adapters, state builders, insight rules, and prediction
rules all picked their own day counts (7, 14, 28, 30, 60, 90, 120) for the
same metrics — sometimes diverging by a factor of 8. This module gives every
layer a single named constant to import so future changes happen in one place.

Usage:
    from apps.core.ai_state.windows import HEALTH_TREND_DAYS, MOOD_CURRENT_DAYS

    cutoff = now - timedelta(days=HEALTH_TREND_DAYS)

These constants are NOT enforcement — they are documentation that the
adapter/state/rule layer should converge on. Existing rules with their own
hardcoded windows are not bulk-rewritten in Phase 2 (too much regression
surface); new code MUST use these constants, and code touched during Phase 3/4
will be migrated to them.
"""

# ── Universal adapter cap ────────────────────────────────────────
# Every event adapter caps its lookback at this value. Adapters never
# return rows older than this, so any state builder / rule that wants more
# history must query the model directly.
ADAPTER_MAX_LOOKBACK_DAYS = 30
ADAPTER_MAX_FORWARD_DAYS = 14


# ── Health vitals ────────────────────────────────────────────────
# 7d = current week / weekly average (sleep, HR, glucose, SpO2, water)
# 30d = trend window (weight delta, BP avg)
# 90d = historical aggregation (weight entries, body composition history)
# 120d = projection baseline (body composition slope)
HEALTH_WEEKLY_DAYS = 7
HEALTH_TREND_DAYS = 30
HEALTH_HISTORY_DAYS = 90
HEALTH_PROJECTION_DAYS = 120


# ── Fitness ──────────────────────────────────────────────────────
# 7d = current week (workouts_7d, training_load_7d)
# 14d = exercise progress comparison (volume, sets)
# 30d = monthly summary (workouts_30d, prs_30d)
FITNESS_WEEKLY_DAYS = 7
FITNESS_PROGRESS_DAYS = 14
FITNESS_MONTHLY_DAYS = 30


# ── Nutrition ────────────────────────────────────────────────────
# 7d = rolling average (calories, protein, macros)
# 30d = compliance / planning rhythm
NUTRITION_ROLLING_DAYS = 7
NUTRITION_PLANNING_DAYS = 30


# ── Fasting ──────────────────────────────────────────────────────
# 7d is the canonical fasting window across the whole app.
FASTING_ROLLING_DAYS = 7


# ── Mood / journal ───────────────────────────────────────────────
# 3d = CoS context "what's recent on the user's mind"
# 7d = current mood trend
# 14d = stress decay window
# 30d = entry frequency / mood distribution
MOOD_CONTEXT_DAYS = 3
MOOD_CURRENT_DAYS = 7
MOOD_STRESS_DAYS = 14
MOOD_FREQUENCY_DAYS = 30


# ── Habits ───────────────────────────────────────────────────────
# 14d = recent streak / momentum
# 28d = full 4-week cycle (predictions, monthly summary)
HABIT_RECENT_DAYS = 14
HABIT_CYCLE_DAYS = 28


# ── Faith ────────────────────────────────────────────────────────
# 8d = cockpit window (used by FaithDomainScorer for streak/freq)
# 30d = monthly reading consistency
FAITH_COCKPIT_DAYS = 8
FAITH_MONTHLY_DAYS = 30


# ── Steps ────────────────────────────────────────────────────────
STEPS_WEEKLY_DAYS = 7


# ── Cross-cutting ────────────────────────────────────────────────
# CDCE staleness gate — duplicates the constant in cdce_engine.py for
# convenience but the engine is the source of truth for that.
CDCE_STALENESS_HOURS = 6
