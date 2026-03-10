# ==============================================================================
# File: reference_ranges.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Clinical reference ranges for health data interpretation.
#              Educational information only — not medical advice.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Health Reference Ranges — Deterministic constants for PIE health analysis.

All ranges are for healthy adults and based on published sleep science literature.
These are used by PIE analysis rules to evaluate extracted health data.

NOT medical advice — educational reference only.
"""

# ── Sleep Duration (minutes) ─────────────────────────────────────────

SLEEP_DURATION_MIN = 420       # 7 hours — lower bound of healthy range
SLEEP_DURATION_MAX = 540       # 9 hours — upper bound of healthy range
SLEEP_DURATION_MILD_DEFICIT = 390  # 6.5h — mild deficit threshold
SLEEP_DURATION_SEVERE_DEFICIT = 360  # 6h — significant deficit

# ── Sleep Cycles ─────────────────────────────────────────────────────

SLEEP_CYCLE_MINUTES = 90       # Average duration of one full sleep cycle
OPTIMAL_CYCLES = 5             # Recommended number of complete cycles
MIN_ACCEPTABLE_CYCLES = 4      # Below this, recommend extending sleep

# ── Sleep Stage Distribution (% of total sleep time) ─────────────────

SLEEP_STAGES = {
    'rem': {
        'min_pct': 20,
        'max_pct': 25,
        'label': 'REM',
        'function': 'memory consolidation, emotional processing',
    },
    'deep': {
        'min_pct': 13,
        'max_pct': 23,
        'label': 'Deep (Slow-Wave)',
        'function': 'physical restoration, immune function, growth hormone',
    },
    'core': {
        'min_pct': 50,
        'max_pct': 60,
        'label': 'Core/Light',
        'function': 'transition sleep, memory sorting',
    },
}

# ── Sleep Efficiency ─────────────────────────────────────────────────

SLEEP_EFFICIENCY_GOOD = 85     # % — above this is healthy
SLEEP_EFFICIENCY_POOR = 75     # % — below this needs attention

# ── Future: Vital Sign Ranges ────────────────────────────────────────
# Add as new analysis modules are implemented.

# Heart Rate (resting, BPM)
RESTING_HR_LOW = 60
RESTING_HR_HIGH = 100
RESTING_HR_ATHLETIC = 50  # Lower bound for trained athletes

# Blood Pressure (mmHg)
BP_SYSTOLIC_NORMAL = 120
BP_SYSTOLIC_ELEVATED = 130
BP_SYSTOLIC_HIGH = 140
BP_DIASTOLIC_NORMAL = 80
BP_DIASTOLIC_HIGH = 90

# Blood Glucose (mg/dL, fasting)
GLUCOSE_FASTING_NORMAL_MIN = 70
GLUCOSE_FASTING_NORMAL_MAX = 99
GLUCOSE_FASTING_PREDIABETIC = 126

# HRV (ms, RMSSD)
HRV_LOW = 20
HRV_MODERATE = 40
HRV_GOOD = 60

MEDICAL_DISCLAIMER = (
    "_Educational information only — not medical advice. "
    "Please consult your healthcare provider for medical guidance._"
)
