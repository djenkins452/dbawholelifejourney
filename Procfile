# ====================================================================
# READ THIS FIRST — Procfile is NOT what Railway actually runs
# ====================================================================
# Railway uses Custom Start Commands configured in the Railway dashboard.
# This file is kept for local/heroku-compatible runs and as a reference
# for the *minimum-safe* command shape, but the real production start
# commands live in the Railway service settings and are documented in
# `railway.toml` (see the comment block in that file).
#
# In particular, the production web service Custom Start Command runs
# `load_initial_data` and `recalculate_task_priorities` on every deploy,
# which the "NEVER add to startup" comment block at the bottom of this
# file warns against. The comment block reflects the *desired* state of
# the boot chain, not the current operational reality. Do NOT rely on
# this Procfile to reason about production startup behavior — check the
# Railway dashboard.
#
# Source of truth ranking:
#   1. Railway dashboard Custom Start Command (actual runtime)
#   2. railway.toml comment block (documentation of #1)
#   3. This Procfile (historical / local-only / minimum-safe reference)
#
# If you change boot behavior, update both #1 and #2. Editing only this
# Procfile changes nothing in production.
# ====================================================================
web: python manage.py migrate --noinput && python manage.py load_sports_data && python manage.py collectstatic --noinput && gunicorn config.wsgi --preload --log-file - --workers 4 --timeout 30
worker: celery -A config worker --loglevel=info --concurrency=2
beat: celery -A config beat --loglevel=info
# Updated: 2026-05-20 — Added "Procfile is NOT what Railway runs" warning header
# Previously: 2026-03-16 — Removed APScheduler, all scheduling via Celery Beat
#
# Web service startup (minimal, deterministic, safe):
#   - migrate: Apply pending DB migrations (Django-tracked, safe)
#   - collectstatic: Gather static files (idempotent, no DB/cache)
#   - gunicorn: WSGI server (pure request handler, no background scheduling)
#
# Worker service:
#   - Celery worker consumes tasks from Redis queue (concurrency=2)
#
# Beat service:
#   - Celery Beat schedules ALL periodic tasks (SAME, ISE, reminders, cleanup, COAS)
#   - Must be single-instance (multiple Beats = duplicate task dispatch)
#   - Schedule defined in CELERY_BEAT_SCHEDULE (config/settings.py)
#
# NEVER add to startup:
#   - load_initial_data, reload_help_content, load_danny_workout_templates,
#     load_reading_plans, load_phase1_data, load_project_from_json,
#     recalculate_task_priorities, or any fixture/data loading commands
