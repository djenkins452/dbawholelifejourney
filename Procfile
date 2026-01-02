web: python manage.py migrate --noinput && python manage.py load_initial_data && python manage.py reload_help_content && python manage.py load_danny_workout_templates && python manage.py load_reading_plans && python manage.py load_phase1_data && python manage.py load_project_from_json project_blueprints/wlj_executable_work_orchestration.json && python manage.py recalculate_task_priorities && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file -
# Force rebuild: 2026-01-01-v13-load-executable-project
# NOTE: reload_help_content clears and reloads all help content from fixtures
# NOTE: load_danny_workout_templates is safe to run multiple times (uses get_or_create and checks for existing templates)
# NOTE: load_reading_plans loads Bible reading plans (idempotent, safe to run multiple times)
# NOTE: load_phase1_data creates Phase 1 for admin project tasks (idempotent, safe to run multiple times)
# NOTE: load_project_from_json loads executable project tasks (idempotent, skips existing tasks)
# NOTE: recalculate_task_priorities updates task priorities based on due dates (runs nightly via scheduler, also on deploy)
# NOTE: SMS scheduler runs embedded in web process (see config/wsgi.py) - no separate worker needed
