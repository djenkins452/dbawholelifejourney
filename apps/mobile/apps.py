"""
Whole Life Journey - Mobile App Configuration

Project: Whole Life Journey
Path: apps/mobile/apps.py
Purpose: Django app configuration for the mobile API module

Description:
    Standard Django app configuration class for the mobile application.
    Provides token-based authentication and HealthKit data ingestion
    for the native iOS app.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.apps import AppConfig


class MobileConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mobile"
    verbose_name = "Mobile App"
