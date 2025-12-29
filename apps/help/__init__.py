"""
Whole Life Journey - Help Application Package

Project: Whole Life Journey
Path: apps/help/__init__.py
Purpose: Context-aware help system for user guidance

Description:
    The Help module provides a context-aware help system that displays
    relevant documentation based on the user's current screen. Features
    a "?" icon in the UI that opens precise, step-by-step guidance.

Key Responsibilities:
    - HelpContextMixin: Add help_context_id to views
    - Help button component for templates
    - Help content indexing and lookup
    - Markdown rendering for help documentation

Package Contents:
    - mixins.py: HelpContextMixin for views
    - views.py: Help content display views
    - urls.py: URL routing (mounted at /help/)

Help System Design:
    - Each page declares a HELP_CONTEXT_ID
    - Help index maps IDs to documentation files
    - Documentation is step-by-step, click-by-click
    - Designed for both humans and chatbot parsing

Documentation Location:
    - docs/help/*.md: Help content files
    - docs/help/index.json: Context ID to file mapping

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
