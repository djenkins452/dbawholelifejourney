web: python manage.py migrate --noinput && python manage.py load_initial_data && python manage.py reload_help_content && python manage.py load_danny_workout_templates && python manage.py load_reading_plans && python manage.py load_bible_app_task && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file -
# Force rebuild: 2026-01-01-v5
# NOTE: reload_help_content clears and reloads all help content from fixtures
# NOTE: load_danny_workout_templates is safe to run multiple times (uses get_or_create and checks for existing templates)
# NOTE: load_reading_plans loads Bible reading plans (idempotent, safe to run multiple times)
# NOTE: load_bible_app_task loads Bible App Updates task to ClaudeTask queue (idempotent)
# NOTE: --preload flag ensures WSGI app (and SMS scheduler) loads once before forking workers
# NOTE: SMS scheduler runs embedded in web process (see config/wsgi.py) - no separate worker needed
