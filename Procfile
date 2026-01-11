web: python manage.py migrate --noinput && python manage.py load_initial_data --reset coaching_styles && python manage.py load_initial_data -v 0 && python manage.py sync_workout_to_templates -v 0 && python manage.py recalculate_task_priorities -v 0 && python manage.py load_project_from_json docs/ux_improvements_tasks.json -v 0 && python manage.py collectstatic --noinput && gunicorn config.wsgi --preload --log-file -
# Updated: 2026-01-03 - Consolidated all data loaders into load_initial_data
# load_initial_data now handles ALL one-time data loading with DataLoadConfig tracking:
#   - All fixtures (categories, encouragements, scripture, prompts, help content, etc.)
#   - All populate commands (choices, themes, exercises, etc.)
#   - Reading plans, workout templates, project phases
#   - Project blueprints
# recalculate_task_priorities runs every deploy (updates priorities based on due dates)
# SMS scheduler runs embedded in web process (see config/wsgi.py) - no separate worker needed
