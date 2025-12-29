"""
Whole Life Journey - Core App Configuration

Project: Whole Life Journey
Path: apps/core/apps.py
Purpose: Django app configuration for the core module

Description:
    Standard Django app configuration class for the core application.
    Registers the app with Django and sets the verbose name for admin.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"
