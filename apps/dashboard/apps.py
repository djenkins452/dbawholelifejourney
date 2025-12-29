"""
Whole Life Journey - Dashboard App Configuration

Project: Whole Life Journey
Path: apps/dashboard/apps.py
Purpose: Django app configuration for the dashboard module

Description:
    Standard Django app configuration class for the dashboard application.
    Registers the app with Django and sets the verbose name for admin.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
    verbose_name = "Dashboard"
