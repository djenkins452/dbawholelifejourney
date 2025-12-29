"""
Whole Life Journey - Life Application Package

Project: Whole Life Journey
Path: apps/life/__init__.py
Purpose: Personal life management - tasks, projects, events, inventory, and more

Description:
    The Life module provides comprehensive personal life management tools
    including task management, projects, calendar events, inventory tracking,
    pet care, recipes, maintenance logs, and document storage.

Key Responsibilities:
    - Task management with priority-based sorting (Now/Soon/Someday)
    - Project organization with task grouping
    - Calendar events with reminders
    - Inventory/belonging tracking with photos
    - Pet care logs and information
    - Recipe collection with ingredients
    - Home/vehicle maintenance tracking
    - Document storage and organization

Package Contents:
    - models.py: Task, Project, Event, Inventory, Pet, Recipe, Maintenance, etc.
    - views.py: CRUD views for all life management features
    - forms.py: Forms for data entry
    - urls.py: URL routing

Sections:
    - /life/tasks/       : Task management
    - /life/projects/    : Project organization
    - /life/events/      : Calendar events
    - /life/inventory/   : Belongings tracking
    - /life/pets/        : Pet care
    - /life/recipes/     : Recipe collection
    - /life/maintenance/ : Maintenance logs
    - /life/documents/   : Document storage

Dependencies:
    - apps.core.models for UserOwnedModel base class
    - apps.scan for AI Camera integration

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
