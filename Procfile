web: python manage.py migrate --noinput && python manage.py load_initial_data && python manage.py reload_help_content && python manage.py load_danny_workout_templates && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file -
# Force rebuild: 2025-12-31-v1
# NOTE: reload_help_content clears and reloads all help content from fixtures
# NOTE: load_danny_workout_templates is safe to run multiple times (uses get_or_create and checks for existing templates)
