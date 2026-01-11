web: python manage.py fix_stale_migrations && python manage.py migrate --noinput && python manage.py add_drill_sergeant && python manage.py load_initial_data -v 0 && python manage.py sync_workout_to_templates -v 0 && python manage.py recalculate_task_priorities -v 0 && python manage.py load_project_from_json docs/ux_improvements_tasks.json -v 0 && python manage.py reset_reading_plan_progress && python manage.py collectstatic --noinput && gunicorn config.wsgi --preload --log-file -
# Updated: 2026-01-11 - Added reset_reading_plan_progress to fix reading plan notes bug
# Updated: 2026-01-11 - Added fix_stale_migrations before migrate to fix broken dependencies
# load_initial_data now handles ALL one-time data loading with DataLoadConfig tracking:
#   - All fixtures (categories, encouragements, scripture, prompts, help content, etc.)
#   - All populate commands (choices, themes, exercises, etc.)
#   - Reading plans, workout templates, project phases
#   - Project blueprints
# recalculate_task_priorities runs every deploy (updates priorities based on due dates)
# SMS scheduler runs embedded in web process (see config/wsgi.py) - no separate worker needed
