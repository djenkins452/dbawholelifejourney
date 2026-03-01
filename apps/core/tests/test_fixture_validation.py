"""
Fixture schema validation tests.

Validates all JSON fixture files to catch broken records, duplicate PKs,
and missing required fields BEFORE they reach production. This prevents
cascading boot failures from malformed fixture data.

These tests catch issues like the pk=41/42 release_notes outage (2026-02-28)
where missing release_date fields crashed the entire deploy.
"""

import json
from pathlib import Path

from django.apps import apps
from django.test import TestCase


# Required fields for critical fixtures (fields that are NOT NULL with no default)
# Fields with defaults (entry_type, is_published, etc.) are not listed since
# Django will apply the default if missing from the fixture.
FIXTURE_REQUIRED_FIELDS = {
    'release_notes': {
        'model': 'core.releasenote',
        'fields': ['title', 'description', 'release_date'],
    },
    'help_topics': {
        'model': 'help.helptopic',
        'fields': ['context_id', 'help_id', 'title', 'content'],
    },
    'help_topics_brain_training': {
        'model': 'help.helptopic',
        'fields': ['context_id', 'help_id', 'title', 'content'],
    },
    'admin_help_topics': {
        'model': 'help.adminhelptopic',
        'fields': ['context_id', 'title', 'content'],
    },
    'teaching_destinations': {
        'model': 'help.teachingdestination',
        'fields': ['destination_id', 'name', 'url'],
    },
}


class FixtureJSONValidationTest(TestCase):
    """Validate that all fixture JSON files parse correctly."""

    def _find_all_fixtures(self):
        """Find all Django fixture .json files under apps/.

        Skips JSON files that are not Django fixtures (not a list of records).
        """
        apps_dir = Path(__file__).resolve().parent.parent.parent
        fixtures = []
        for path in sorted(apps_dir.glob('*/fixtures/*.json')):
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    fixtures.append(path)
            except (json.JSONDecodeError, OSError):
                fixtures.append(path)  # Include so validation catches the error
        return fixtures

    def test_all_fixtures_are_valid_json(self):
        """Every fixture file must parse as valid JSON array."""
        for path in self._find_all_fixtures():
            with self.subTest(fixture=path.name):
                with open(path) as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError as e:
                        self.fail(f"{path.name}: Invalid JSON at line {e.lineno}: {e.msg}")
                self.assertIsInstance(data, list, f"{path.name}: must be a JSON array")

    def test_all_fixtures_have_required_structure(self):
        """Each record must have model and fields keys (pk optional for natural keys)."""
        for path in self._find_all_fixtures():
            with open(path) as f:
                try:
                    records = json.load(f)
                except json.JSONDecodeError:
                    continue
            if not isinstance(records, list):
                continue
            for i, record in enumerate(records):
                with self.subTest(fixture=path.name, index=i):
                    self.assertIn('model', record, f"{path.name}[{i}]: missing 'model'")
                    self.assertIn('fields', record, f"{path.name}[{i}]: missing 'fields'")

    def test_no_duplicate_pks(self):
        """No two records in the same fixture should share a PK for the same model."""
        for path in self._find_all_fixtures():
            with open(path) as f:
                try:
                    records = json.load(f)
                except json.JSONDecodeError:
                    continue
            if not isinstance(records, list):
                continue
            seen = {}
            for record in records:
                model = record.get('model', '')
                pk = record.get('pk')
                if pk is None:
                    continue  # Natural key fixtures don't have explicit PKs
                key = (model, pk)
                with self.subTest(fixture=path.name, model=model, pk=pk):
                    self.assertNotIn(key, seen,
                        f"{path.name}: duplicate PK {pk} for {model}")
                seen[key] = True

    def test_fixture_models_exist(self):
        """Every model referenced in fixtures must be a valid Django model."""
        for path in self._find_all_fixtures():
            with open(path) as f:
                try:
                    records = json.load(f)
                except json.JSONDecodeError:
                    continue
            if not isinstance(records, list):
                continue
            checked = set()
            for record in records:
                model_label = record.get('model', '')
                if model_label in checked:
                    continue
                checked.add(model_label)
                with self.subTest(fixture=path.name, model=model_label):
                    try:
                        apps.get_model(model_label)
                    except (LookupError, ValueError):
                        self.fail(f"{path.name}: unknown model '{model_label}'")


class FixtureRequiredFieldsTest(TestCase):
    """Validate that critical fixtures have all NOT NULL fields present."""

    def test_required_fields_present(self):
        """Each record in critical fixtures must have all required fields."""
        apps_dir = Path(__file__).resolve().parent.parent.parent

        for fixture_name, schema in FIXTURE_REQUIRED_FIELDS.items():
            fixture_path = None
            for candidate in apps_dir.glob(f'*/fixtures/{fixture_name}.json'):
                fixture_path = candidate
                break

            if fixture_path is None:
                continue

            with open(fixture_path) as f:
                try:
                    records = json.load(f)
                except json.JSONDecodeError:
                    continue

            for record in records:
                if record.get('model') != schema['model']:
                    continue
                fields = record.get('fields', {})
                pk = record.get('pk')
                for field_name in schema['fields']:
                    with self.subTest(fixture=fixture_name, pk=pk, field=field_name):
                        self.assertIn(field_name, fields,
                            f"{fixture_name} pk={pk}: missing required field '{field_name}'")
                        self.assertIsNotNone(fields.get(field_name),
                            f"{fixture_name} pk={pk}: field '{field_name}' is null")
