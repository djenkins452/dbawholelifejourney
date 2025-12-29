web: python manage.py migrate --noinput && python manage.py load_initial_data && python manage.py load_danny_workout_templates && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file -
# Force redeploy: 2025-12-29 10:20
# NOTE: load_danny_workout_templates is safe to run multiple times (uses get_or_create and checks for existing templates)
