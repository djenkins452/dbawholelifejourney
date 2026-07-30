# ==============================================================================
# File: apps/health/health_question_catalog.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Health Question Catalog — the reference implementation of the
#              data-driven Question Certification framework (apps.core.truth
#              .question_catalog). Declares the real customer questions the Health
#              domain must answer; the framework certifies each against the LIVE
#              capability registries. Future Health work adds questions here.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Health Question Catalog.

Each `Question` declares the deterministic truth it REQUIRES; certification is computed
(never asserted). GAP questions declare a not-yet-built capability (or an unregistered
page) so they report as uncertified with the exact first failing layer — and auto-certify
the day that capability ships. This module is DATA: to extend Health certification, add a
Question; do not invent questions ad hoc elsewhere.
"""
from apps.core.truth.question_catalog import (
    Question,
    Requirement as R,
    register_question,
)


def _q(qid, topic, category, examples, requires, note=""):
    # All Health-catalog questions share domain="health" (the certification scope);
    # `topic` is the sub-grouping (glucose, nutrition, weight, …).
    register_question(Question(id=qid, domain="health", topic=topic, category=category,
                               examples=tuple(examples), requires=tuple(requires),
                               note=note))


# ── GLUCOSE ────────────────────────────────────────────────────────────────
_q("health.glucose.current_context", "glucose", "current_context",
   ["look at my glucose page", "what am I looking at here"],
   [R("current_context", "health", "health.glucose")])
_q("health.glucose.current", "glucose", "current",
   ["what's my latest glucose", "what was my glucose reading"],
   [R("current", "health", "glucose_yesterday")])
_q("health.glucose.history", "glucose", "history",
   ["my glucose this week", "average glucose last month"],
   [R("history", "health", "glucose")])
_q("health.glucose.trend", "glucose", "trend",
   ["is my glucose improving", "how's my glucose trending"],
   [R("trend", "health", "glucose")])
_q("health.glucose.comparison", "glucose", "comparison",
   ["glucose this week vs last week"],
   [R("comparison", "health", "glucose")])
_q("health.glucose.analysis", "glucose", "analysis",
   ["evaluate my glucose", "analyze my blood sugar"],
   [R("analysis", "health", "glucose")])
_q("health.glucose.readings_lows", "glucose", "readings",
   ["my overnight lows", "how much time below 70", "when was my last urgent low"],
   [R("readings", "health", "glucose")])
_q("health.glucose.time_of_night_lows", "glucose", "readings",
   ["what time of night do my lows usually occur"],
   [R("by_hour", "health", "glucose")])
_q("health.glucose.lows_more_frequent", "glucose", "trend",
   ["are my overnight lows getting more frequent", "is this becoming more frequent"],
   [R("excursion_frequency", "health", "glucose")],
   note="GAP: comparison works on averages/totals, not on excursion COUNTS across "
        "windows. Needs an excursion-frequency series (Phase 3b).")

# ── NUTRITION (domain 'nutrition') ───────────────────────────────────────────
_q("nutrition.current_context", "nutrition", "current_context",
   ["look at my nutrition page"],
   [R("current_context", "nutrition", "health.nutrition")])
_q("nutrition.history_macro", "nutrition", "history",
   ["my carbs over the last week", "how much protein this week"],
   [R("history", "nutrition", "carbs")])
_q("nutrition.trend_macro", "nutrition", "trend",
   ["is my protein trending up"],
   [R("trend", "nutrition", "protein")])
_q("nutrition.comparison_macro", "nutrition", "comparison",
   ["carbs this week vs last week"],
   [R("comparison", "nutrition", "carbs")])
_q("nutrition.adherence_carbs", "nutrition", "adherence",
   ["am I eating enough carbs", "do I need more carbs or are they in line"],
   [R("adherence", "nutrition", "carbs")])
_q("nutrition.adherence_protein", "nutrition", "adherence",
   ["am I getting enough protein"],
   [R("adherence", "nutrition", "protein")])
_q("nutrition.adherence_calories", "nutrition", "adherence",
   ["am I averaging enough calories"],
   [R("adherence", "nutrition", "calories")])
_q("nutrition.adherence_missing_macros", "nutrition", "adherence",
   ["which macros am I consistently missing"],
   [R("adherence", "nutrition", "protein"), R("adherence", "nutrition", "carbs"),
    R("adherence", "nutrition", "fat")])
_q("nutrition.analysis_macros", "nutrition", "analysis",
   ["analyze my macros", "look at my macronutrient intake"],
   [R("analysis", "nutrition", "macronutrients")])
_q("nutrition.meals_most_carbs", "nutrition", "analysis",
   ["which meals tend to have the most carbs"],
   [R("ranked_entity", "nutrition", "meal_by_carbs")],
   note="GAP: meal record detail exists (get_entity('meal')), but no ranked-by-macro "
        "surface. Model must rank returned records (Phase 3+).")

# ── WEIGHT ───────────────────────────────────────────────────────────────────
_q("health.weight.current_context", "weight", "current_context",
   ["look at my weight page"], [R("current_context", "health", "health.weight")])
_q("health.weight.current", "weight", "current",
   ["what's my current weight"], [R("current", "health", "weight_yesterday")])
_q("health.weight.history", "weight", "history",
   ["my weight over the last month"], [R("history", "health", "weight")])
_q("health.weight.trend", "weight", "trend",
   ["am I losing weight too quickly", "is my weekly loss accelerating"],
   [R("trend", "health", "weight")])
_q("health.weight.comparison", "weight", "comparison",
   ["how does my weight compare with last month"],
   [R("comparison", "health", "weight")])
_q("health.weight.analysis", "weight", "analysis",
   ["analyze my weight loss"], [R("analysis", "health", "weight")])
_q("health.weight.trend_change_point", "weight", "trend",
   ["when did my weight trend change"],
   [R("change_point", "health", "weight")],
   note="GAP: no change-point detection; trend gives one slope, not the inflection "
        "date (Phase 3c).")

# ── SLEEP ─────────────────────────────────────────────────────────────────────
_q("health.sleep.current_context", "sleep", "current_context",
   ["look at my sleep page"], [R("current_context", "health", "health.sleep")])
_q("health.sleep.current", "sleep", "current",
   ["how did I sleep last night"], [R("current", "health", "sleep_last_night")])
_q("health.sleep.history", "sleep", "history",
   ["my sleep this week", "am I sleeping enough"], [R("history", "health", "sleep")])
_q("health.sleep.trend", "sleep", "trend",
   ["has my sleep improved"], [R("trend", "health", "sleep")])
_q("health.sleep.comparison", "sleep", "comparison",
   ["sleep this week vs last"], [R("comparison", "health", "sleep")])
_q("health.sleep.analysis", "sleep", "analysis",
   ["evaluate my sleep", "what nights were the worst"],
   [R("analysis", "health", "sleep")])
_q("health.sleep.consistency", "sleep", "analysis",
   ["how consistent is my sleep schedule"],
   [R("consistency", "health", "sleep")],
   note="GAP: no bedtime-variance/consistency metric (Phase 3a variance capability).")

# ── HEART RATE ────────────────────────────────────────────────────────────────
_q("health.heart_rate.current_context", "heart_rate", "current_context",
   ["look at my heart rate page"], [R("current_context", "health", "health.heart_rate")])
_q("health.heart_rate.history", "heart_rate", "history",
   ["my resting heart rate this month"], [R("history", "health", "resting_heart_rate")])
_q("health.heart_rate.trend", "heart_rate", "trend",
   ["has my resting heart rate improved", "what is my resting heart rate trend"],
   [R("trend", "health", "resting_heart_rate")])
_q("health.heart_rate.comparison", "heart_rate", "comparison",
   ["resting HR this month vs last"],
   [R("comparison", "health", "resting_heart_rate")])
_q("health.heart_rate.analysis", "heart_rate", "analysis",
   ["analyze my heart rate"], [R("analysis", "health", "heart_rate")])
_q("health.heart_rate.readings", "heart_rate", "readings",
   ["my heart rate through the day"], [R("readings", "health", "heart_rate")])
_q("health.heart_rate.recovery", "heart_rate", "analysis",
   ["is my recovery improving", "did exercise change my baseline"],
   [R("hrv_recovery", "health", "heart_rate")],
   note="GAP: SleepEntry HRV/heart-rate fields not exposed as history; no recovery "
        "composite; cross-domain correlation (Phase 3c).")

# ── BLOOD PRESSURE ────────────────────────────────────────────────────────────
_q("health.blood_pressure.current_context", "blood_pressure", "current_context",
   ["look at my blood pressure page"],
   [R("current_context", "health", "health.blood_pressure")])
_q("health.blood_pressure.history", "blood_pressure", "history",
   ["my blood pressure this month"], [R("history", "health", "bp_systolic")])
_q("health.blood_pressure.trend", "blood_pressure", "trend",
   ["is my blood pressure improving"], [R("trend", "health", "bp_systolic")])
_q("health.blood_pressure.comparison", "blood_pressure", "comparison",
   ["BP this month vs last"], [R("comparison", "health", "bp_systolic")])
_q("health.blood_pressure.analysis", "blood_pressure", "analysis",
   ["analyze my blood pressure"], [R("analysis", "health", "blood_pressure")])
_q("health.blood_pressure.time_of_day", "blood_pressure", "readings",
   ["what time of day is my blood pressure highest", "how often am I above range"],
   [R("by_hour", "health", "blood_pressure")])

# ── BODY COMPOSITION ──────────────────────────────────────────────────────────
_q("health.body_composition.current_context", "body_composition", "current_context",
   ["look at my body composition"],
   [R("current_context", "health", "health.body_intelligence")])
_q("health.body_composition.muscle", "body_composition", "trend",
   ["am I gaining muscle"], [R("trend", "health", "lean_mass")])
_q("health.body_composition.fat", "body_composition", "trend",
   ["am I losing fat", "is my body fat trend healthy"],
   [R("trend", "health", "body_fat_pct")])
_q("health.body_composition.comparison", "body_composition", "comparison",
   ["body fat this month vs last"], [R("comparison", "health", "body_fat_pct")])
_q("health.body_composition.analysis", "body_composition", "analysis",
   ["analyze my body composition"], [R("analysis", "health", "body_composition")])

# ── STEPS ─────────────────────────────────────────────────────────────────────
_q("health.steps.current_context", "steps", "current_context",
   ["look at my steps page"], [R("current_context", "health", "health.steps")])
_q("health.steps.current", "steps", "current",
   ["how many steps today"], [R("current", "health", "steps_today")])
_q("health.steps.history", "steps", "history",
   ["my steps last week"], [R("history", "health", "steps")])
_q("health.steps.trend", "steps", "trend",
   ["are my steps trending up"], [R("trend", "health", "steps")])
_q("health.steps.comparison", "steps", "comparison",
   ["steps this week vs last week"], [R("comparison", "health", "steps")])
_q("health.steps.adherence", "steps", "adherence",
   ["am I hitting my step goal"], [R("adherence", "health", "steps")])
_q("health.steps.analysis", "steps", "analysis",
   ["analyze my activity"], [R("analysis", "health", "steps")])

# ── SPO2 (blood oxygen) ───────────────────────────────────────────────────────
_q("health.spo2.current_context", "spo2", "current_context",
   ["look at my blood oxygen page"],
   [R("current_context", "health", "health.blood_oxygen")],
   note="GAP: BloodOxygenListView has no page summary yet (Phase 2c).")
_q("health.spo2.history", "spo2", "history",
   ["my SpO2 this week"], [R("history", "health", "spo2")])
_q("health.spo2.trend", "spo2", "trend",
   ["is my blood oxygen trending down"], [R("trend", "health", "spo2")])
_q("health.spo2.comparison", "spo2", "comparison",
   ["SpO2 this week vs last"], [R("comparison", "health", "spo2")])
_q("health.spo2.analysis", "spo2", "analysis",
   ["analyze my blood oxygen"], [R("analysis", "health", "spo2")])
_q("health.spo2.readings", "spo2", "readings",
   ["did my oxygen dip", "my SpO2 readings overnight"],
   [R("readings", "health", "spo2")])

# ── BODY TEMPERATURE ──────────────────────────────────────────────────────────
_q("health.body_temperature.history", "body_temperature", "history",
   ["my temperature this week"], [R("history", "health", "body_temperature")])
_q("health.body_temperature.trend", "body_temperature", "trend",
   ["is my temperature trending up"], [R("trend", "health", "body_temperature")])
_q("health.body_temperature.analysis", "body_temperature", "analysis",
   ["analyze my temperature"], [R("analysis", "health", "body_temperature")])
_q("health.body_temperature.readings", "body_temperature", "readings",
   ["any fever readings", "my temperature through the day"],
   [R("readings", "health", "body_temperature")])
_q("health.body_temperature.current_context", "body_temperature", "current_context",
   ["look at my temperature page"],
   [R("current_context", "health", "health.body_temperature")],
   note="GAP: no dedicated temperature overview page (Phase 2c).")

# ── WATER ─────────────────────────────────────────────────────────────────────
_q("health.water.current_context", "water", "current_context",
   ["look at my water page"], [R("current_context", "health", "health.water")])
_q("health.water.history", "water", "history",
   ["my water intake this week"], [R("history", "health", "water")])
_q("health.water.trend", "water", "trend",
   ["is my hydration improving"], [R("trend", "health", "water")])
_q("health.water.comparison", "water", "comparison",
   ["water this week vs last"], [R("comparison", "health", "water")])
_q("health.water.adherence", "water", "adherence",
   ["am I drinking enough water"], [R("adherence", "health", "water")])
_q("health.water.analysis", "water", "analysis",
   ["analyze my hydration"], [R("analysis", "health", "water")])

# ── WORKOUTS ──────────────────────────────────────────────────────────────────
_q("health.workouts.history", "workouts", "history",
   ["how many workouts last week"], [R("history", "health", "workouts")])
_q("health.workouts.trend", "workouts", "trend",
   ["is my workout frequency trending up"], [R("trend", "health", "workouts")])
_q("health.workouts.comparison", "workouts", "comparison",
   ["workouts this week vs last"], [R("comparison", "health", "workouts")])
_q("health.workouts.analysis", "workouts", "analysis",
   ["analyze my workout trends", "what exercises did I do"],
   [R("analysis", "health", "workouts")])
_q("health.workouts.current_context", "workouts", "current_context",
   ["look at my fitness page"],
   [R("current_context", "health", "health.fitness")],
   note="GAP: FitnessHomeView has no page summary yet (Phase 2c).")
