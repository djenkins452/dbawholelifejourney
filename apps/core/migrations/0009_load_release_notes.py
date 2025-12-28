# Generated data migration to load initial release notes
from django.db import migrations


def load_release_notes(apps, schema_editor):
    """
    Load initial release notes from fixture data.

    These represent retroactive entries for features already released.
    """
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Only load if no release notes exist (to prevent duplicates on re-run)
    if ReleaseNote.objects.exists():
        return

    # Release notes data - retroactive entries for existing features
    release_notes = [
        {
            'title': 'AI Camera Scanning',
            'description': 'Point your phone at food, medicine, documents, or workout equipment and let AI identify it and suggest actions. Supports 8 categories with smart routing to the right module.',
            'entry_type': 'feature',
            'release_date': '2025-12-28',
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Medicine Tracking',
            'description': 'Comprehensive medicine management with daily tracker, schedules, adherence stats, refill alerts, and PRN support. One-tap check-off for doses.',
            'entry_type': 'feature',
            'release_date': '2025-12-28',
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Nutrition & Food Tracking',
            'description': 'Log meals with macro tracking, daily summaries, and nutrition goals. Includes custom foods, meal type categorization, and eating context tracking.',
            'entry_type': 'feature',
            'release_date': '2025-12-28',
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Enhanced Dashboard',
            'description': "Dashboard now shows Today's Medicine Schedule with status badges, Recent Workouts with PR highlights, and Quick Stats for medicine doses and workout counts.",
            'entry_type': 'enhancement',
            'release_date': '2025-12-28',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'AI Camera Source Tracking',
            'description': 'Entries created via AI Camera now show a camera badge on detail pages. Track which entries came from AI-powered scanning.',
            'entry_type': 'enhancement',
            'release_date': '2025-12-28',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Security Improvements',
            'description': 'Enhanced security with rate limiting, secure admin URL, improved cookie settings, and server-side API key handling for Bible lookups.',
            'entry_type': 'security',
            'release_date': '2025-12-28',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Onboarding Wizard',
            'description': 'New users are guided through a friendly 6-step wizard to personalize their experience - choose theme, enable modules, configure AI coaching, and set location.',
            'entry_type': 'feature',
            'release_date': '2025-12-20',
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Scripture Library',
            'description': 'Save, edit, and organize your favorite Scripture verses in a personal library. Add themes and personal notes to each verse.',
            'entry_type': 'feature',
            'release_date': '2025-12-18',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'AI Coaching Styles',
            'description': 'Choose how the AI communicates with you. Pick from 7 styles including Supportive Partner, Direct Coach, Gentle Guide, and more.',
            'entry_type': 'feature',
            'release_date': '2025-12-15',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Task Undo',
            'description': 'Accidentally marked a task complete? Now you can easily undo with a single click using the new Undo link.',
            'entry_type': 'enhancement',
            'release_date': '2025-12-12',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Fitness Tracking',
            'description': 'Track workouts, log exercises, and monitor your fitness journey with comprehensive workout logging.',
            'entry_type': 'feature',
            'release_date': '2025-12-10',
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Journal Prompts',
            'description': '20 curated writing prompts across 8 categories to inspire your daily reflections. Get a random prompt with one click.',
            'entry_type': 'feature',
            'release_date': '2025-12-08',
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Life Module',
            'description': 'Manage your whole life with Projects, Tasks, Calendar, Inventory, Pets, Recipes, Maintenance logs, and Document storage.',
            'entry_type': 'feature',
            'release_date': '2025-12-05',
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Purpose Module',
            'description': 'Set your annual direction with Word of the Year, life goals, change intentions, and seasonal reflections.',
            'entry_type': 'feature',
            'release_date': '2025-12-03',
            'is_published': True,
            'is_major': True,
        },
    ]

    from datetime import datetime

    for note_data in release_notes:
        ReleaseNote.objects.create(
            title=note_data['title'],
            description=note_data['description'],
            entry_type=note_data['entry_type'],
            release_date=datetime.strptime(note_data['release_date'], '%Y-%m-%d').date(),
            is_published=note_data['is_published'],
            is_major=note_data['is_major'],
        )


def reverse_release_notes(apps, schema_editor):
    """Remove the loaded release notes."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_whats_new_models'),
    ]

    operations = [
        migrations.RunPython(load_release_notes, reverse_release_notes),
    ]
