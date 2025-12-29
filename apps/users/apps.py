"""
Whole Life Journey - Users App Configuration

Project: Whole Life Journey
Path: apps/users/apps.py
Purpose: Django app configuration for the users module

Description:
    Standard Django app configuration class for the users application.
    Connects signal handlers in the ready() method to ensure
    UserPreferences are automatically created for new users.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"

    def ready(self):
        # Import signals when app is ready
        from . import signals  # noqa: F401
