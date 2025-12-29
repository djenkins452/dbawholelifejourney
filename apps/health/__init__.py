"""
Whole Life Journey - Health Application Package

Project: Whole Life Journey
Path: apps/health/__init__.py
Purpose: Physical wellness tracking including fitness, nutrition, and medicine

Description:
    The Health module provides gentle, judgment-free tracking for physical
    wellness. Includes weight logging, fitness/workout tracking, nutrition/food
    logging, medicine schedules, and biometric tracking (heart rate, glucose).

Key Responsibilities:
    - Weight logging with trend tracking
    - Workout/fitness logging with exercise types and PRs
    - Nutrition tracking with food entries and macro calculations
    - Medicine schedules with daily tracker and adherence stats
    - Fasting windows for intermittent fasting
    - Heart rate and blood glucose tracking
    - Dashboard integration with AI insights

Package Contents:
    - models.py: WeightEntry, Workout, Exercise, Medicine, FoodEntry, etc.
    - views.py: CRUD views for all health tracking features
    - forms.py: Forms for health data entry
    - urls.py: URL routing

Sections:
    - /health/weight/      : Weight tracking
    - /health/fitness/     : Workout logging
    - /health/nutrition/   : Food/calorie tracking
    - /health/medicine/    : Medicine schedules
    - /health/fasting/     : Fasting windows
    - /health/heart-rate/  : Heart rate logging
    - /health/glucose/     : Blood glucose logging

Design Principles:
    - Manual entry (no device sync yet)
    - No imposed targets or goals
    - Gentle, not judgmental
    - Data is private and secure

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.health.apps.HealthConfig"
