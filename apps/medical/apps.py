"""
Whole Life Journey - Medical App Configuration

Project: Whole Life Journey
Path: apps/medical/apps.py
Purpose: Django app configuration for the Medical module
"""

from django.apps import AppConfig


class MedicalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.medical"
    verbose_name = "Medical"
