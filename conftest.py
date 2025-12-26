"""
Pytest/Django Test Configuration

This file is automatically loaded by Django's test runner.
It sets the test settings module before any tests run.

Location: Project root (same level as manage.py)
"""

import os

# Set the settings module for tests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')