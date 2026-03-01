"""
Whole Life Journey - Notes Module

Project: Whole Life Journey
Path: apps/notes/__init__.py
Purpose: Unified notes system for capturing and organizing thoughts

Description:
    A general-purpose notes system that serves as WLJ's long-term memory layer.
    Notes can stand alone or be attached to any WLJ entity (tasks, goals,
    journal entries, projects, events, etc.) via GenericForeignKey attachments.

Key Responsibilities:
    - Standalone and contextual note creation
    - Note organization via tags, colors, and pinning
    - Entity attachment via NoteAttachment (GenericFK)
    - CRUD operations with soft delete support

Package Contents:
    - models.py: Note, NoteAttachment
    - views.py: List, Create, Detail, Update, Delete, TogglePin
    - urls.py: URL routing
    - forms.py: NoteForm
    - admin.py: Admin registration
    - utils.py: Attachable model whitelist and resolver

Integration:
    - Dashboard: Notes module in left rail navigation
    - Cross-app: Attachable to any UserOwnedModel entity
    - Future: CoS intelligence layer, search engine, note conversion

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.notes.apps.NotesConfig"
