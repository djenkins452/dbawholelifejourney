#!/usr/bin/env python
"""
Whole Life Journey - Django Management Script

Project: Whole Life Journey
Path: manage.py
Purpose: Command-line utility for Django administrative tasks

Description:
    This is Django's command-line utility for administrative tasks such as
    running the development server, creating migrations, running tests,
    and executing management commands.

Common Commands:
    python manage.py runserver          - Start development server
    python manage.py migrate            - Apply database migrations
    python manage.py makemigrations     - Create new migrations
    python manage.py test               - Run test suite
    python manage.py createsuperuser    - Create admin user
    python manage.py load_initial_data  - Load fixtures and reference data
    python manage.py collectstatic      - Collect static files for production

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""
import os
import sys


def main():
    """Run administrative tasks by delegating to Django's command-line utility."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
