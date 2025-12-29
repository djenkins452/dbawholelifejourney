"""
Whole Life Journey - Purpose Application Package

Project: Whole Life Journey
Path: apps/purpose/__init__.py
Purpose: Strategic life direction, goals, vision, and purpose tracking

Description:
    The Purpose module is the strategic and spiritual compass for life
    direction. It helps users define their life vision, set yearly direction,
    track goals across life areas, and maintain focus on what matters most.

Key Responsibilities:
    - Life Direction: Annual focus areas and themes
    - Goals: Long-term and short-term goal tracking
    - Vision: Personal vision statement and life purpose
    - Roles: Define key life roles (parent, spouse, professional, etc.)
    - Values: Core values and principles
    - Dashboard tile showing current year direction

Package Contents:
    - models.py: Direction, Goal, Vision, Role, Value
    - views.py: Direction, goal, and vision management views
    - forms.py: Forms for data entry
    - urls.py: URL routing

Integration:
    - Dashboard displays Purpose tile with current year direction
    - AI insights reference purpose data for personalized coaching

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = 'apps.purpose.PurposeConfig'
