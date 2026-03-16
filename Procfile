web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi --preload --log-file - --workers 4 --timeout 30
worker: celery -A config worker --loglevel=info --concurrency=2
beat: celery -A config beat --loglevel=info
# Updated: 2026-03-16 — Removed APScheduler, all scheduling via Celery Beat
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
