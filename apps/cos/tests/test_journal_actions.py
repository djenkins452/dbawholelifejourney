"""
CoS v2 — Phase 3 Tests: JournalCosActions — Append Not Duplicate

Tests:
1. Create: new entry when no same-date entry exists
2. Append: same-date entry gets content appended, not duplicated
3. force_new: bypasses append and creates new entry
4. Update: title, body, mood, append_body
5. Delete: soft-delete
6. Retrieve: by ID
7. Summarise: date range, word counts
8. check_duplicate: same-date detection
9. Reflection hook
"""

import datetime as dt

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.cos.actions.journal_actions import APPEND_SEPARATOR, JournalCosActions
from apps.cos.contracts import ActionResult, DuplicateCheck
from apps.cos.models import CosReflection
from apps.journal.models import JournalEntry

User = get_user_model()


def _create_test_user(email="jcosactions@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    return user


# ──────────────────────────────────────────────────────────
# Create — New Entry
# ──────────────────────────────────────────────────────────


class JournalCreateNewTests(TestCase):
    """Test JournalCosActions.create() when no same-date entry exists."""

    def setUp(self):
        self.user = _create_test_user("jcreate@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.today = dt.date.today()

    def test_module_name(self):
        self.assertEqual(self.actions.module_name, "journal")

    def test_create_new_entry(self):
        """Creates new entry when no same-date entry exists."""
        result = self.actions.create(
            title="Morning Thoughts",
            body="Today I reflected on gratitude and purpose.",
            entry_date=self.today,
        )
        self.assertIsInstance(result, ActionResult)
        self.assertTrue(result.success)
        self.assertFalse(result.reused)
        self.assertEqual(result.metadata["action"], "created")
        self.assertEqual(result.entity.title, "Morning Thoughts")
        self.assertEqual(result.entity.user, self.user)

    def test_create_auto_title(self):
        """Entry gets auto-generated title when title is blank."""
        result = self.actions.create(
            body="No title provided",
            entry_date=self.today,
        )
        self.assertTrue(result.success)
        # Title should be auto-generated (date string)
        self.assertTrue(len(result.entity.title) > 0)

    def test_create_with_mood(self):
        """Entry can include mood."""
        result = self.actions.create(
            body="Feeling great today!",
            entry_date=self.today,
            mood="great",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.entity.mood, "great")

    def test_create_empty_body_fails(self):
        """Creating with empty body returns failure."""
        result = self.actions.create(body="", entry_date=self.today)
        self.assertFalse(result.success)
        self.assertIn("required", result.error)

    def test_create_default_date_is_today(self):
        """Default entry_date is today."""
        result = self.actions.create(body="Default date test")
        self.assertTrue(result.success)
        self.assertEqual(result.entity.entry_date, self.today)

    def test_create_word_count_computed(self):
        """Word count is computed on save."""
        result = self.actions.create(body="one two three four five")
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["word_count"], 5)


# ──────────────────────────────────────────────────────────
# Create — Append to Existing (Core Behavior)
# ──────────────────────────────────────────────────────────


class JournalAppendTests(TestCase):
    """Test the append-not-duplicate behavior."""

    def setUp(self):
        self.user = _create_test_user("jappend@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.today = dt.date.today()
        # Create an existing entry for today
        self.existing = JournalEntry.objects.create(
            user=self.user,
            title="Morning Entry",
            body="Morning thoughts about the day ahead.",
            entry_date=self.today,
        )

    def test_append_to_existing(self):
        """Second create on same date appends instead of creating new."""
        result = self.actions.create(
            body="Evening reflection: today was productive.",
            entry_date=self.today,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.reused)  # Signals append, not create
        self.assertEqual(result.entity_id, self.existing.pk)
        self.assertEqual(result.metadata["action"], "appended")

        # Verify body was appended
        self.existing.refresh_from_db()
        self.assertIn("Morning thoughts", self.existing.body)
        self.assertIn("Evening reflection", self.existing.body)
        self.assertIn("---", self.existing.body)  # Separator present

    def test_append_word_count_increases(self):
        """Word count increases after append."""
        original_wc = self.existing.word_count
        result = self.actions.create(
            body="Additional words for the entry.",
            entry_date=self.today,
        )
        self.assertTrue(result.success)
        self.assertGreater(result.metadata["new_word_count"], original_wc)
        self.assertGreater(result.metadata["words_added"], 0)

    def test_append_preserves_original_title(self):
        """Appending doesn't change the existing title."""
        self.actions.create(
            title="New Title Should Be Ignored",
            body="Appended content",
            entry_date=self.today,
        )
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.title, "Morning Entry")

    def test_append_mood_only_if_empty(self):
        """Mood is set on append only if existing entry has no mood."""
        self.assertFalse(self.existing.mood)  # No mood initially
        self.actions.create(
            body="Content with mood",
            entry_date=self.today,
            mood="good",
        )
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.mood, "good")

    def test_append_no_mood_override(self):
        """Mood is NOT overridden if existing entry already has one."""
        self.existing.mood = "great"
        self.existing.save()
        self.actions.create(
            body="Content with different mood",
            entry_date=self.today,
            mood="low",
        )
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.mood, "great")  # Preserved

    def test_only_one_entry_after_multiple_appends(self):
        """Multiple appends don't create multiple entries."""
        self.actions.create(body="Second append", entry_date=self.today)
        self.actions.create(body="Third append", entry_date=self.today)
        count = JournalEntry.objects.filter(
            user=self.user, entry_date=self.today,
        ).count()
        self.assertEqual(count, 1)

    def test_force_new_creates_separate(self):
        """force_new=True bypasses append and creates a new entry."""
        result = self.actions.create(
            title="Separate Entry",
            body="This should be a new entry.",
            entry_date=self.today,
            force_new=True,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)
        self.assertNotEqual(result.entity_id, self.existing.pk)
        count = JournalEntry.objects.filter(
            user=self.user, entry_date=self.today,
        ).count()
        self.assertEqual(count, 2)

    def test_deleted_entry_not_appended_to(self):
        """Soft-deleted entries are not considered for append."""
        self.existing.soft_delete()
        result = self.actions.create(
            body="New content after delete",
            entry_date=self.today,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)  # New entry, not append
        self.assertNotEqual(result.entity_id, self.existing.pk)

    def test_different_date_creates_new(self):
        """Entry for a different date creates new, doesn't append."""
        tomorrow = self.today + dt.timedelta(days=1)
        result = self.actions.create(
            body="Tomorrow's thoughts",
            entry_date=tomorrow,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)


# ──────────────────────────────────────────────────────────
# Update
# ──────────────────────────────────────────────────────────


class JournalUpdateTests(TestCase):
    """Test JournalCosActions.update()."""

    def setUp(self):
        self.user = _create_test_user("jupdate@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.entry = JournalEntry.objects.create(
            user=self.user,
            title="Original",
            body="Original body content.",
            entry_date=dt.date.today(),
        )

    def test_update_title(self):
        result = self.actions.update(
            entity_id=self.entry.pk, title="Updated Title"
        )
        self.assertTrue(result.success)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, "Updated Title")

    def test_update_body(self):
        result = self.actions.update(
            entity_id=self.entry.pk, body="Completely new body."
        )
        self.assertTrue(result.success)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.body, "Completely new body.")

    def test_update_mood(self):
        result = self.actions.update(
            entity_id=self.entry.pk, mood="good"
        )
        self.assertTrue(result.success)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.mood, "good")

    def test_update_append_body(self):
        """append_body adds to existing body instead of replacing."""
        result = self.actions.update(
            entity_id=self.entry.pk, append_body="Additional thoughts."
        )
        self.assertTrue(result.success)
        self.entry.refresh_from_db()
        self.assertIn("Original body content.", self.entry.body)
        self.assertIn("Additional thoughts.", self.entry.body)
        self.assertEqual(result.metadata["action"], "updated")

    def test_update_nonexistent(self):
        result = self.actions.update(entity_id=999999, title="No Entry")
        self.assertFalse(result.success)

    def test_update_no_changes(self):
        """Updating with same values returns no_changes."""
        result = self.actions.update(
            entity_id=self.entry.pk, title="Original"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["action"], "no_changes")


# ──────────────────────────────────────────────────────────
# Delete + Retrieve
# ──────────────────────────────────────────────────────────


class JournalDeleteRetrieveTests(TestCase):
    """Test JournalCosActions.delete() and retrieve()."""

    def setUp(self):
        self.user = _create_test_user("jdelret@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.entry = JournalEntry.objects.create(
            user=self.user,
            title="Test Entry",
            body="Test content",
            entry_date=dt.date.today(),
        )

    def test_retrieve_existing(self):
        result = self.actions.retrieve(entity_id=self.entry.pk)
        self.assertTrue(result.success)
        self.assertEqual(result.entity_id, self.entry.pk)
        self.assertEqual(result.metadata["title"], "Test Entry")

    def test_retrieve_nonexistent(self):
        result = self.actions.retrieve(entity_id=999999)
        self.assertFalse(result.success)

    def test_delete_soft_deletes(self):
        result = self.actions.delete(entity_id=self.entry.pk)
        self.assertTrue(result.success)
        # Should not appear in default queryset
        self.assertFalse(JournalEntry.objects.filter(pk=self.entry.pk).exists())
        # But exists in all_objects
        self.assertTrue(JournalEntry.all_objects.filter(pk=self.entry.pk).exists())

    def test_delete_nonexistent(self):
        result = self.actions.delete(entity_id=999999)
        self.assertFalse(result.success)


# ──────────────────────────────────────────────────────────
# Summarise
# ──────────────────────────────────────────────────────────


class JournalSummariseTests(TestCase):
    """Test JournalCosActions.summarise()."""

    def setUp(self):
        self.user = _create_test_user("jsum@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.today = dt.date.today()

        # Create entries across multiple dates
        for i in range(3):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body=f"Content for day {i} with some words.",
                entry_date=self.today - dt.timedelta(days=i),
            )

    def test_summarise_all(self):
        """Summarise returns all entries."""
        result = self.actions.summarise()
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["entry_count"], 3)

    def test_summarise_specific_date(self):
        """Summarise for a specific date."""
        result = self.actions.summarise(date=self.today)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["entry_count"], 1)

    def test_summarise_date_range(self):
        """Summarise for a date range."""
        result = self.actions.summarise(
            start_date=self.today - dt.timedelta(days=1),
            end_date=self.today,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["entry_count"], 2)

    def test_summarise_includes_word_count(self):
        result = self.actions.summarise(date=self.today)
        self.assertIn("total_words", result.metadata)
        self.assertGreater(result.metadata["total_words"], 0)

    def test_summarise_empty_range(self):
        """Summarise for a date with no entries."""
        future = self.today + dt.timedelta(days=30)
        result = self.actions.summarise(date=future)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["entry_count"], 0)


# ──────────────────────────────────────────────────────────
# Duplicate Check
# ──────────────────────────────────────────────────────────


class JournalDuplicateCheckTests(TestCase):
    """Test JournalCosActions.check_duplicate()."""

    def setUp(self):
        self.user = _create_test_user("jdup@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.today = dt.date.today()

    def test_no_duplicate(self):
        result = self.actions.check_duplicate(entry_date=self.today)
        self.assertFalse(result.is_duplicate)

    def test_same_date_duplicate(self):
        JournalEntry.objects.create(
            user=self.user,
            title="Existing Entry",
            body="Existing content",
            entry_date=self.today,
        )
        result = self.actions.check_duplicate(entry_date=self.today)
        self.assertTrue(result.is_duplicate)
        self.assertEqual(result.match_type, "same_date")
        self.assertIn("appended", result.message)

    def test_deleted_entry_not_duplicate(self):
        """Soft-deleted entries don't count as duplicates."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title="Deleted",
            body="Content",
            entry_date=self.today,
        )
        entry.soft_delete()
        result = self.actions.check_duplicate(entry_date=self.today)
        self.assertFalse(result.is_duplicate)


# ──────────────────────────────────────────────────────────
# Reflection Hook
# ──────────────────────────────────────────────────────────


class JournalReflectionHookTests(TestCase):
    """Test JournalCosActions.capture_reflection_hook()."""

    def setUp(self):
        self.user = _create_test_user("jrefl@example.com")
        self.actions = JournalCosActions(user=self.user)
        self.entry = JournalEntry.objects.create(
            user=self.user,
            title="Reflection Test",
            body="Content",
            entry_date=dt.date.today(),
        )

    def test_capture_reflection(self):
        success = self.actions.capture_reflection_hook(
            entity_id=self.entry.pk,
            reflection_text="Writing helped me process my feelings.",
            sentiment="positive",
        )
        self.assertTrue(success)
        ct = ContentType.objects.get_for_model(JournalEntry)
        refl = CosReflection.objects.get(
            user=self.user,
            content_type=ct,
            object_id=self.entry.pk,
        )
        self.assertEqual(refl.activity_type, "journal")

    def test_capture_reflection_nonexistent(self):
        success = self.actions.capture_reflection_hook(
            entity_id=999999,
            reflection_text="Should fail",
        )
        self.assertFalse(success)

    def test_supports_reflections(self):
        self.assertTrue(self.actions.supports_reflections())

    def test_supports_proactive_prompts(self):
        self.assertTrue(self.actions.supports_proactive_prompts())
