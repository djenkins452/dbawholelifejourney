"""
Whole Life Journey - Faith Application Package

Project: Whole Life Journey
Path: apps/faith/__init__.py
Purpose: Spiritual growth, Scripture study, prayer journaling, and devotionals

Description:
    The Faith module provides a gentle, grounding space for spiritual growth.
    It respects user choice - only active when faith_enabled = True. Features
    Scripture study, prayer requests, devotionals, fasting logs, and faith
    milestones. Assumes personal relationship with Jesus Christ.

Key Responsibilities:
    - Scripture reading and verse saving (API.Bible integration)
    - Prayer request tracking with answered prayers
    - Daily devotionals and faith reflections
    - Fasting logs with duration tracking
    - Faith milestones (baptism, rededication, etc.)
    - Verse of the Day feature

Package Contents:
    - models.py: PrayerRequest, ScriptureVerse, SavedVerse, Devotional, etc.
    - views.py: Scripture, prayer, devotional views
    - urls.py: URL routing
    - api.py: Server-side Bible API proxy

Design Principles:
    - Gentle, grounding, never forced
    - Respects user's spiritual journey
    - Optional module (faith_enabled preference)
    - Content is encouraging, not judgmental

Dependencies:
    - API.Bible for Scripture lookups
    - apps.core.models for UserOwnedModel base class

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.faith.apps.FaithConfig"
