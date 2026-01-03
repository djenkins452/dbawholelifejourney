# ==============================================================================
# File: apps/finance/apps.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance app configuration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================
from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    verbose_name = 'Finance'
