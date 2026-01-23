# ==============================================================================
# File: apps/security/apps.py
# Project: Whole Life Journey
# Description: Security app configuration
# ==============================================================================

from django.apps import AppConfig


class SecurityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.security'
    verbose_name = 'Security Assessment'
