# Data migration to transfer existing ScriptureVerse entries to SavedVerse for Danny
# This is a one-time migration to fix the data leak bug where saved verses
# were visible to all users instead of just the user who saved them.

from django.db import migrations


def migrate_verses_to_danny(apps, schema_editor):
    """
    Copy existing ScriptureVerse entries to SavedVerse for user dannyjenkins71@gmail.com

    This migration assumes all existing saved verses belong to Danny since
    he was the first user to save Scripture verses.
    """
    User = apps.get_model('users', 'User')
    ScriptureVerse = apps.get_model('faith', 'ScriptureVerse')
    SavedVerse = apps.get_model('faith', 'SavedVerse')

    # Find Danny's user account
    try:
        danny = User.objects.get(email='dannyjenkins71@gmail.com')
    except User.DoesNotExist:
        # If Danny doesn't exist, skip migration (e.g., fresh install)
        return

    # Get all existing Scripture verses (these were user-saved verses)
    # Skip verses that are part of the original fixture (if any)
    # The fixture verses typically have specific references
    scripture_verses = ScriptureVerse.objects.filter(is_active=True)

    for verse in scripture_verses:
        # Check if this verse already exists in SavedVerse for this user
        if not SavedVerse.objects.filter(
            user=danny,
            reference=verse.reference,
            translation=verse.translation
        ).exists():
            SavedVerse.objects.create(
                user=danny,
                reference=verse.reference,
                text=verse.text,
                translation=verse.translation,
                book_name=verse.book_name,
                book_order=verse.book_order,
                chapter=verse.chapter,
                verse_start=verse.verse_start,
                verse_end=verse.verse_end,
                themes=verse.themes,
                notes='',  # No notes in the old model
            )


def reverse_migration(apps, schema_editor):
    """
    Reverse the migration by deleting Danny's SavedVerse entries.
    The original ScriptureVerse entries remain untouched.
    """
    User = apps.get_model('users', 'User')
    SavedVerse = apps.get_model('faith', 'SavedVerse')

    try:
        danny = User.objects.get(email='dannyjenkins71@gmail.com')
        SavedVerse.objects.filter(user=danny).delete()
    except User.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("faith", "0002_add_saved_verse_model"),
        ("users", "0001_initial"),  # Ensure users app is ready
    ]

    operations = [
        migrations.RunPython(migrate_verses_to_danny, reverse_migration),
    ]
