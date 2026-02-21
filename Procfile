web: python manage.py migrate --noinput && python manage.py load_initial_data -v 0 && python manage.py recalculate_task_priorities -v 0 && python manage.py collectstatic --noinput && gunicorn config.wsgi --preload --log-file - --timeout 300
worker: celery -A config worker --loglevel=info --concurrency=2
beat: celery -A config beat --loglevel=info
# Updated: 2026-02-21 — Cleaned startup chain, added worker/beat entries
#
# Web service startup (idempotent, non-destructive):
#   - migrate: Apply pending DB migrations
#   - load_initial_data: One-time fixture loading (tracked by DataLoadConfig, skips if done)
#   - recalculate_task_priorities: Runs every deploy (fast, no side effects)
#   - collectstatic: Gather static files
#   - gunicorn: WSGI server (APScheduler for 15 jobs starts inside wsgi.py)
#
# Worker service:
#   - Celery worker consumes tasks from Redis queue
#   - Executes run_same_cycle_task (SAME monitoring) dispatched by Beat
#
# Beat service:
#   - Celery Beat schedules periodic tasks (currently: SAME every 60s)
#   - Must be single-instance (multiple Beats = duplicate task dispatch)
#
# IMPORTANT: Do NOT add reload_help_content to startup.
# Help content is loaded by load_initial_data (one-time) and reload_help_content
# (on-demand via CLI only). Both use update_or_create, not destructive loaddata.
