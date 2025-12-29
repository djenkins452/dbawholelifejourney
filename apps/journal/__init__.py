"""
Whole Life Journey - Journal Application Package

Project: Whole Life Journey
Path: apps/journal/__init__.py
Purpose: Personal journaling and reflection space for daily entries

Description:
    The Journal module provides a calm, intentional space for users to
    write daily reflections, track mood patterns, and organize thoughts
    using categories and tags. Supports prompts for inspiration and
    integrates with AI for insights.

Key Responsibilities:
    - Create, read, update, delete journal entries
    - Categorize entries (Faith, Family, Work, Health, Gratitude, etc.)
    - Tag entries with user-defined custom tags
    - Track mood (optional, lightweight)
    - Provide curated writing prompts with optional Scripture
    - Support speech-to-text for hands-free journaling
    - Archive or soft-delete entries with 30-day retention

Package Contents:
    - models.py: JournalEntry, JournalPrompt
    - views.py: Entry CRUD views, prompt views, statistics
    - forms.py: JournalEntryForm, TagForm
    - urls.py: URL routing

Dependencies:
    - apps.core.models for UserOwnedModel, Category, Tag base classes
    - apps.faith for Scripture integration (when Faith enabled)

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.journal.apps.JournalConfig"
