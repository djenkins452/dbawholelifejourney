"""
Whole Life Journey - Core Application Package

Project: Whole Life Journey
Path: apps/core/__init__.py
Purpose: Central shared functionality used across all application modules

Description:
    The core app provides foundational functionality that other apps inherit
    and depend on. It contains abstract base models, shared utilities, context
    processors, and system-wide features.

Key Responsibilities:
    - Abstract base models (TimeStampedModel, SoftDeleteModel, UserOwnedModel)
    - Site configuration and theming
    - Context processors for templates
    - Landing page and static content views
    - Custom template tags for safe URLs
    - Test run history tracking
    - Release notes / What's New feature
    - Camera scan base model for AI features

Package Contents:
    - models.py: Base models, site config, themes, test tracking, camera scans
    - views.py: Landing page, terms, privacy, error handlers, What's New
    - urls.py: URL routing for core pages
    - admin.py: Django admin configuration
    - context_processors.py: Theme and site context injection
    - utils.py: Safe redirect URL validation
    - templatetags/: Custom template tags
    - management/commands/: Data loading and utility commands

Dependencies:
    - Django core framework
    - django.core.cache for performance optimization
    - apps.users.models for user preferences

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = "apps.core.apps.CoreConfig"
