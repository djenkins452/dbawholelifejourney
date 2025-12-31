# ==============================================================================
# File: apps.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: SMS app configuration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""SMS app configuration."""

from django.apps import AppConfig


class SmsConfig(AppConfig):
    """Configuration for the SMS app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sms'
    verbose_name = 'SMS Notifications'
