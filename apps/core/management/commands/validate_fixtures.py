"""
Validate fixture JSON files without loading them.

Checks structure, duplicate PKs, model existence, and required fields.
Use before deploy to catch broken fixtures that could crash the site.

Usage:
    python manage.py validate_fixtures              # Validate all
    python manage.py validate_fixtures release_notes # Validate specific fixture
"""

import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Validate fixture JSON files without loading them'

    def add_arguments(self, parser):
        parser.add_argument(
            'fixture_names', nargs='*',
            help='Specific fixture names to validate (default: all)',
        )

    def handle(self, *args, **options):
        fixture_names = options.get('fixture_names', [])
        apps_dir = Path(__file__).resolve().parent.parent.parent.parent

        errors = []
        checked = 0

        for fixture_dir in sorted(apps_dir.glob('*/fixtures')):
            for json_file in sorted(fixture_dir.glob('*.json')):
                name = json_file.stem
                if fixture_names and name not in fixture_names:
                    continue

                # Skip non-fixture JSON files (not a list of records)
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                    if not isinstance(data, list):
                        self.stdout.write(f'  SKIP {name} (not a fixture)')
                        continue
                except json.JSONDecodeError:
                    pass  # Let _validate report the error

                checked += 1
                file_errors = self._validate(json_file)
                if file_errors:
                    errors.extend(file_errors)
                    self.stdout.write(self.style.ERROR(f'  FAIL {name}'))
                else:
                    self.stdout.write(f'  OK   {name}')

        self.stdout.write('')
        if errors:
            self.stdout.write(self.style.ERROR(f'{len(errors)} error(s):'))
            for err in errors:
                self.stdout.write(self.style.ERROR(f'  - {err}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'All {checked} fixture(s) valid.'))

    def _validate(self, path):
        errors = []
        try:
            with open(path) as f:
                records = json.load(f)
        except json.JSONDecodeError as e:
            return [f'{path.name}: Invalid JSON line {e.lineno}: {e.msg}']

        if not isinstance(records, list):
            return [f'{path.name}: must be a JSON array']

        seen = {}
        for i, record in enumerate(records):
            if 'model' not in record:
                errors.append(f'{path.name}[{i}]: missing "model"')
                continue
            if 'fields' not in record:
                errors.append(f'{path.name}[{i}]: missing "fields"')

            model = record.get('model', '')
            pk = record.get('pk')
            if pk is not None:
                key = (model, pk)
                if key in seen:
                    errors.append(f'{path.name}: duplicate pk={pk} for {model}')
                seen[key] = True

            try:
                apps.get_model(model)
            except (LookupError, ValueError):
                errors.append(f'{path.name}[{i}]: unknown model "{model}"')

        return errors
