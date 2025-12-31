web: python manage.py migrate --noinput && python manage.py load_initial_data && python manage.py reload_help_content && python manage.py load_danny_workout_templates && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file -
worker: python manage.py run_sms_scheduler
# Force rebuild: 2025-12-31-v2
# NOTE: reload_help_content clears and reloads all help content from fixtures
# NOTE: load_danny_workout_templates is safe to run multiple times (uses get_or_create and checks for existing templates)
# NOTE: worker process runs the SMS scheduler (sends pending SMS every 5 min, schedules daily at midnight)
