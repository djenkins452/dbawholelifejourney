"""
Whole Life Journey - Dashboard Application Package

Project: Whole Life Journey
Path: apps/dashboard/__init__.py
Purpose: AI-powered command center and personalized daily landing page

Description:
    The Dashboard is the primary landing page for authenticated users,
    providing a personalized view of their wellness journey. Features
    AI-driven insights, daily encouragement, module overviews, and
    quick access to common actions.

Key Responsibilities:
    - Display AI-generated personalized insights based on user data
    - Show daily encouragement (with optional Scripture for Faith users)
    - Provide module overview tiles with key metrics
    - Highlight celebrations and gentle accountability nudges
    - Display weather context (when configured)
    - Aggregate data from all modules for AI analysis

Package Contents:
    - models.py: DailyEncouragement for curated messages
    - views.py: DashboardView with comprehensive data gathering
    - urls.py: URL routing
    - admin.py: Django admin configuration

Dependencies:
    - apps.ai.services for AI insight generation
    - apps.journal, apps.faith, apps.health, apps.life, apps.purpose for data

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.dashboard.apps.DashboardConfig"
