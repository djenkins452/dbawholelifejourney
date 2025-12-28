"""
Tests for Journal Prompts Data Migration

Tests that the 0003_load_journal_prompts migration properly loads
all journal prompts into the database.

Location: apps/journal/tests/test_journal_prompts_migration.py
"""

import importlib.util
import os

from django.test import TestCase

from apps.core.models import Category
from apps.journal.models import JournalPrompt


def load_migration_module():
    """Load the migration module using importlib (since it starts with a number)."""
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'migrations',
        '0003_load_journal_prompts.py'
    )
    spec = importlib.util.spec_from_file_location("migration_0003", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JournalPromptsMigrationTest(TestCase):
    """Tests for journal prompts data integrity."""

    @classmethod
    def setUpTestData(cls):
        """Create categories that prompts reference."""
        cls.faith = Category.objects.create(pk=1, name='Faith', slug='faith', order=1)
        cls.family = Category.objects.create(pk=2, name='Family', slug='family', order=2)
        cls.work = Category.objects.create(pk=3, name='Work', slug='work', order=3)
        cls.health = Category.objects.create(pk=4, name='Health', slug='health', order=4)
        cls.gratitude = Category.objects.create(pk=5, name='Gratitude', slug='gratitude', order=5)
        cls.growth = Category.objects.create(pk=6, name='Growth', slug='growth', order=6)
        cls.relationships = Category.objects.create(pk=7, name='Relationships', slug='relationships', order=7)
        cls.dreams = Category.objects.create(pk=8, name='Dreams', slug='dreams', order=8)

    def test_prompts_fixture_has_20_prompts(self):
        """The fixture should contain 20 journal prompts."""
        migration = load_migration_module()
        self.assertEqual(len(migration.JOURNAL_PROMPTS), 20)

    def test_prompts_have_required_fields(self):
        """Each prompt in fixture has all required fields."""
        migration = load_migration_module()

        required_fields = ['pk', 'text', 'category_pk', 'is_faith_specific',
                          'scripture_reference', 'scripture_text']

        for prompt in migration.JOURNAL_PROMPTS:
            for field in required_fields:
                self.assertIn(field, prompt, f"Prompt {prompt.get('pk')} missing {field}")

    def test_faith_specific_prompts_have_faith_category(self):
        """Faith-specific prompts should be in the Faith category."""
        migration = load_migration_module()

        faith_specific = [p for p in migration.JOURNAL_PROMPTS if p['is_faith_specific']]

        # There should be some faith-specific prompts
        self.assertGreater(len(faith_specific), 0)

        # All faith-specific prompts should have category_pk=1 (Faith)
        for prompt in faith_specific:
            self.assertEqual(
                prompt['category_pk'], 1,
                f"Faith-specific prompt {prompt['pk']} not in Faith category"
            )

    def test_scripture_prompts_have_references(self):
        """Prompts with scripture_text should have scripture_reference."""
        migration = load_migration_module()

        for prompt in migration.JOURNAL_PROMPTS:
            if prompt['scripture_text']:
                self.assertTrue(
                    prompt['scripture_reference'],
                    f"Prompt {prompt['pk']} has scripture_text but no reference"
                )

    def test_migration_creates_prompts(self):
        """Test that the migration function creates prompts correctly."""
        migration = load_migration_module()
        from django.apps import apps

        # Call the migration function
        migration.load_prompts(apps, None)

        # All 20 prompts should exist
        self.assertEqual(JournalPrompt.objects.count(), 20)

    def test_migration_is_idempotent(self):
        """Running migration multiple times should not create duplicates."""
        migration = load_migration_module()
        from django.apps import apps

        # Run migration twice
        migration.load_prompts(apps, None)
        migration.load_prompts(apps, None)

        # Should still have exactly 20 prompts
        self.assertEqual(JournalPrompt.objects.count(), 20)

    def test_prompts_are_active(self):
        """All loaded prompts should be active."""
        migration = load_migration_module()
        from django.apps import apps

        migration.load_prompts(apps, None)

        inactive_count = JournalPrompt.objects.filter(is_active=False).count()
        self.assertEqual(inactive_count, 0)

    def test_prompts_have_categories_assigned(self):
        """Prompts with category_pk should have category assigned."""
        migration = load_migration_module()
        from django.apps import apps

        migration.load_prompts(apps, None)

        # Count prompts with categories in fixture
        prompts_with_categories = [p for p in migration.JOURNAL_PROMPTS if p['category_pk'] is not None]

        # Count prompts with categories in database
        db_prompts_with_categories = JournalPrompt.objects.exclude(category=None).count()

        self.assertEqual(len(prompts_with_categories), db_prompts_with_categories)

    def test_gratitude_prompts_exist(self):
        """Gratitude category should have prompts."""
        migration = load_migration_module()
        from django.apps import apps

        migration.load_prompts(apps, None)

        gratitude_prompts = JournalPrompt.objects.filter(category=self.gratitude)
        self.assertGreater(gratitude_prompts.count(), 0)

    def test_health_prompts_exist(self):
        """Health category should have prompts."""
        migration = load_migration_module()
        from django.apps import apps

        migration.load_prompts(apps, None)

        health_prompts = JournalPrompt.objects.filter(category=self.health)
        self.assertGreater(health_prompts.count(), 0)

    def test_general_prompts_exist(self):
        """Some prompts should have no category (general prompts)."""
        migration = load_migration_module()
        from django.apps import apps

        migration.load_prompts(apps, None)

        general_prompts = JournalPrompt.objects.filter(category=None)
        self.assertGreater(general_prompts.count(), 0)

    def test_scripture_prompts_loaded_correctly(self):
        """Scripture prompts should have both reference and text."""
        migration = load_migration_module()
        from django.apps import apps

        migration.load_prompts(apps, None)

        scripture_prompts = JournalPrompt.objects.exclude(scripture_reference='')
        self.assertGreater(scripture_prompts.count(), 0)

        for prompt in scripture_prompts:
            self.assertTrue(prompt.scripture_text,
                          f"Prompt {prompt.pk} has reference but no text")


class JournalPromptFixtureValidationTest(TestCase):
    """Tests to validate the fixture file structure."""

    def test_all_pks_are_unique(self):
        """All prompt PKs should be unique."""
        migration = load_migration_module()

        pks = [p['pk'] for p in migration.JOURNAL_PROMPTS]
        self.assertEqual(len(pks), len(set(pks)), "Duplicate PKs found in prompts")

    def test_pks_are_sequential(self):
        """PKs should be sequential 1-20."""
        migration = load_migration_module()

        pks = sorted([p['pk'] for p in migration.JOURNAL_PROMPTS])
        expected = list(range(1, 21))
        self.assertEqual(pks, expected)

    def test_category_pks_are_valid(self):
        """All category PKs should be 1-8 or None."""
        migration = load_migration_module()

        valid_category_pks = {None, 1, 2, 3, 4, 5, 6, 7, 8}

        for prompt in migration.JOURNAL_PROMPTS:
            self.assertIn(
                prompt['category_pk'], valid_category_pks,
                f"Prompt {prompt['pk']} has invalid category_pk: {prompt['category_pk']}"
            )

    def test_prompts_text_not_empty(self):
        """All prompts should have non-empty text."""
        migration = load_migration_module()

        for prompt in migration.JOURNAL_PROMPTS:
            self.assertTrue(
                prompt['text'].strip(),
                f"Prompt {prompt['pk']} has empty text"
            )

    def test_boolean_fields_are_booleans(self):
        """is_faith_specific should be boolean."""
        migration = load_migration_module()

        for prompt in migration.JOURNAL_PROMPTS:
            self.assertIsInstance(
                prompt['is_faith_specific'], bool,
                f"Prompt {prompt['pk']} is_faith_specific is not boolean"
            )
