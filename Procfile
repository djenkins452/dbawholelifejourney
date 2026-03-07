web: python manage.py migrate --noinput && python manage.py sync_data_dictionary && python manage.py sync_user_guide && python manage.py collectstatic --noinput && gunicorn config.wsgi --preload --log-file - --timeout 300
worker: celery -A config worker --loglevel=info --concurrency=2
beat: celery -A config beat --loglevel=info
# Updated: 2026-03-07 — Added guide sync commands to boot
#
# Web service startup (minimal, deterministic, safe):
#   - migrate: Apply pending DB migrations (Django-tracked, safe)
#   - sync_data_dictionary: Sync Data Dictionary from docs/WLJ_Data_Dictionary.md (idempotent, ~2s)
#   - sync_user_guide: Sync User Guide from HelpTopic/HelpArticle records (idempotent, ~1s)
#   - collectstatic: Gather static files (idempotent, no DB/cache)
#   - gunicorn: WSGI server (APScheduler starts inside wsgi.py)
#
# Guide sync commands are safe for boot:
#   - Idempotent (skip unchanged content via hash comparison)
#   - Fast (~2-3 seconds total)
#   - No cache/Redis dependency
#   - Only create/update AdminGuideSection + AdminGuideArticle records
#
# REMOVED FROM BOOT (2026-02-28):
#   - load_initial_data: Now manual-only. Run via: python manage.py load_initial_data
#   - recalculate_task_priorities: Now manual-only or scheduled via APScheduler
#   These commands must NEVER run during boot. They touch DB/cache and can block deploys.
#
# NEVER add to startup:
#   - load_initial_data, reload_help_content, load_danny_workout_templates,
#     load_reading_plans, load_phase1_data, load_project_from_json,
#     recalculate_task_priorities, or any fixture/data loading commands
#
# Worker service:
#   - Celery worker consumes tasks from Redis queue
#
# Beat service:
#   - Celery Beat schedules periodic tasks (SAME every 60s)
#   - Must be single-instance (multiple Beats = duplicate task dispatch)
