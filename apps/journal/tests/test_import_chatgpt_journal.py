"""
Tests for ChatGPT Journal Import Management Command

Tests the import_chatgpt_journal management command that imports
journal entries from ChatGPT JSON exports.

Location: apps/journal/tests/test_import_chatgpt_journal.py
"""

import json
import tempfile
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.core.models import Category
from apps.journal.models import JournalEntry
from apps.users.models import User


class ImportChatGPTJournalCommandTest(TestCase):
    """Tests for the import_chatgpt_journal management command."""

    def setUp(self):
        """Set up test user and categories."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

        # Create categories that match the import fields
        self.faith_category = Category.objects.create(
            name='Faith', slug='faith', order=1
        )
        self.health_category = Category.objects.create(
            name='Health', slug='health', order=2
        )
        self.family_category = Category.objects.create(
            name='Family', slug='family', order=3
        )
        self.work_category = Category.objects.create(
            name='Work', slug='work', order=4
        )

        # Sample valid JSON data
        self.valid_data = [
            {
                "date": "2025-12-01",
                "faith": "Attended church service.",
                "health": "Went for a morning run.",
                "family": "Had dinner with family.",
                "work": "Completed project milestone.",
                "reflection_summary": "A balanced and productive day."
            },
            {
                "date": "2025-12-02",
                "faith": None,
                "health": "Rested today.",
                "family": None,
                "work": "Regular workday.",
                "reflection_summary": "Quiet day of recovery."
            }
        ]

    def _create_temp_json_file(self, data):
        """Create a temporary JSON file with the given data."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        )
        json.dump(data, temp_file)
        temp_file.close()
        return temp_file.name

    def test_dry_run_does_not_create_entries(self):
        """Dry run shows what would be imported without creating entries."""
        json_file = self._create_temp_json_file(self.valid_data)
        out = StringIO()

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            '--dry-run',
            stdout=out
        )

        # No entries should be created
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

        # Output should mention dry run
        output = out.getvalue()
        self.assertIn('DRY RUN', output)

    def test_import_creates_entries(self):
        """Import creates journal entries for the specified user."""
        json_file = self._create_temp_json_file(self.valid_data)
        out = StringIO()

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            stdout=out
        )

        # Two entries should be created
        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 2)

        # Check first entry
        entry1 = entries.get(entry_date=date(2025, 12, 1))
        self.assertIn('Faith', entry1.body)
        self.assertIn('Health', entry1.body)
        self.assertIn('Family', entry1.body)
        self.assertIn('Work', entry1.body)
        self.assertIn('Reflection', entry1.body)

    def test_import_assigns_categories(self):
        """Import assigns appropriate categories based on content."""
        json_file = self._create_temp_json_file(self.valid_data)

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            stdout=StringIO()
        )

        # First entry has all four categories
        entry1 = JournalEntry.objects.get(
            user=self.user, entry_date=date(2025, 12, 1)
        )
        category_slugs = list(entry1.categories.values_list('slug', flat=True))
        self.assertIn('faith', category_slugs)
        self.assertIn('health', category_slugs)
        self.assertIn('family', category_slugs)
        self.assertIn('work', category_slugs)

        # Second entry only has health and work (faith and family are null)
        entry2 = JournalEntry.objects.get(
            user=self.user, entry_date=date(2025, 12, 2)
        )
        category_slugs = list(entry2.categories.values_list('slug', flat=True))
        self.assertNotIn('faith', category_slugs)
        self.assertIn('health', category_slugs)
        self.assertNotIn('family', category_slugs)
        self.assertIn('work', category_slugs)

    def test_import_generates_title_from_date(self):
        """Import generates readable title from entry date."""
        json_file = self._create_temp_json_file(self.valid_data)

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            stdout=StringIO()
        )

        entry = JournalEntry.objects.get(
            user=self.user, entry_date=date(2025, 12, 1)
        )
        # Title should be formatted like "Monday, December 01, 2025"
        self.assertIn('December', entry.title)
        self.assertIn('2025', entry.title)

    def test_skip_duplicates(self):
        """Import skips entries that already exist for a date."""
        # Create existing entry
        JournalEntry.objects.create(
            user=self.user,
            title='Existing Entry',
            body='Already here.',
            entry_date=date(2025, 12, 1)
        )

        json_file = self._create_temp_json_file(self.valid_data)
        out = StringIO()

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            stdout=out
        )

        # Only one new entry should be created (for 2025-12-02)
        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 2)

        # Original entry should be unchanged
        existing = entries.get(entry_date=date(2025, 12, 1))
        self.assertEqual(existing.title, 'Existing Entry')

        # Output should mention skipping
        self.assertIn('skipped', out.getvalue().lower())

    def test_user_not_found_raises_error(self):
        """Import raises error when user email doesn't exist."""
        json_file = self._create_temp_json_file(self.valid_data)

        with self.assertRaises(CommandError) as context:
            call_command(
                'import_chatgpt_journal',
                json_file,
                '--user', 'nonexistent@example.com',
                stdout=StringIO()
            )

        self.assertIn('not found', str(context.exception))

    def test_user_id_option(self):
        """Import works with --user-id option."""
        json_file = self._create_temp_json_file(self.valid_data)

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user-id', str(self.user.pk),
            stdout=StringIO()
        )

        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_invalid_json_raises_error(self):
        """Import raises error for invalid JSON file."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        temp_file.write('not valid json {{{')
        temp_file.close()

        with self.assertRaises(CommandError) as context:
            call_command(
                'import_chatgpt_journal',
                temp_file.name,
                '--user', self.user.email,
                stdout=StringIO()
            )

        self.assertIn('Invalid JSON', str(context.exception))

    def test_file_not_found_raises_error(self):
        """Import raises error when file doesn't exist."""
        with self.assertRaises(CommandError) as context:
            call_command(
                'import_chatgpt_journal',
                '/nonexistent/path/file.json',
                '--user', self.user.email,
                stdout=StringIO()
            )

        self.assertIn('not found', str(context.exception))

    def test_entry_without_date_raises_error(self):
        """Import handles entries missing required date field."""
        data = [{"faith": "Content but no date"}]
        json_file = self._create_temp_json_file(data)
        out = StringIO()

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            stdout=out
        )

        # No entries created, error reported
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)
        self.assertIn('Error', out.getvalue())

    def test_requires_user_when_not_dry_run(self):
        """Import requires user specification when not doing dry run."""
        json_file = self._create_temp_json_file(self.valid_data)

        with self.assertRaises(CommandError) as context:
            call_command(
                'import_chatgpt_journal',
                json_file,
                stdout=StringIO()
            )

        self.assertIn('must specify a user', str(context.exception))

    def test_dry_run_without_user_works(self):
        """Dry run works without specifying a user."""
        json_file = self._create_temp_json_file(self.valid_data)
        out = StringIO()

        # Should not raise an error
        call_command(
            'import_chatgpt_journal',
            json_file,
            '--dry-run',
            stdout=out
        )

        self.assertIn('DRY RUN', out.getvalue())

    def test_empty_content_fields_excluded(self):
        """Fields with null values are excluded from body."""
        data = [{
            "date": "2025-12-01",
            "faith": None,
            "health": "Health content only",
            "family": None,
            "work": None,
            "reflection_summary": "Summary"
        }]
        json_file = self._create_temp_json_file(data)

        call_command(
            'import_chatgpt_journal',
            json_file,
            '--user', self.user.email,
            stdout=StringIO()
        )

        entry = JournalEntry.objects.get(user=self.user)
        self.assertIn('## Health', entry.body)
        self.assertNotIn('## Faith', entry.body)
        self.assertNotIn('## Family', entry.body)
        self.assertNotIn('## Work', entry.body)
        self.assertIn('## Reflection', entry.body)
