"""
Whole Life Journey - Celery Configuration

Project: Whole Life Journey
Path: config/celery.py
Purpose: Celery application factory for background task processing

Description:
    Configures Celery with Redis as broker/result backend.
    Autodiscovers tasks from all installed Django apps.
    Used by Celery Worker and Celery Beat services on Railway.

Services:
    - Worker: celery -A config worker --loglevel=info --concurrency=2
    - Beat:   celery -A config beat --loglevel=info

Environment Variables:
    - CELERY_BROKER_URL: Redis connection string (overrides REDIS_URL)
    - REDIS_URL: Fallback broker URL (typically set by Railway Redis addon)

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import os

from celery import Celery

# Set the default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("wlj")

# Load Celery settings from Django settings, using the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in all installed apps (looks for tasks.py in each app)
app.autodiscover_tasks()
