"""
Data migration to load journal prompts into the database.

This ensures prompts exist in production even if fixture loading fails.
Safe to run multiple times - uses get_or_create pattern.
"""

from django.db import migrations


JOURNAL_PROMPTS = [
    {
        "pk": 1,
        "text": "What are three things you're grateful for today?",
        "category_pk": 5,  # Gratitude
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 2,
        "text": "Describe a moment today when you felt truly present.",
        "category_pk": None,
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 3,
        "text": "What challenged you today, and how did you respond?",
        "category_pk": 6,  # Growth
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 4,
        "text": "Write about someone who made a positive impact on your day.",
        "category_pk": 7,  # Relationships
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 5,
        "text": "What's one thing you want to remember about this season of life?",
        "category_pk": None,
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 6,
        "text": "Reflect on a recent conversation that stayed with you.",
        "category_pk": 7,  # Relationships
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 7,
        "text": "What does rest look like for you right now?",
        "category_pk": 4,  # Health
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 8,
        "text": "Describe your ideal day. What parts of it are already present in your life?",
        "category_pk": 8,  # Dreams
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 9,
        "text": "What's weighing on your heart today?",
        "category_pk": None,
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 10,
        "text": "Write about something you're looking forward to.",
        "category_pk": None,
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 11,
        "text": "How have you seen God at work in your life recently?",
        "category_pk": 1,  # Faith
        "is_faith_specific": True,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 12,
        "text": "What verse or passage has been speaking to you lately?",
        "category_pk": 1,  # Faith
        "is_faith_specific": True,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 13,
        "text": "Write a prayer for someone on your heart today.",
        "category_pk": 1,  # Faith
        "is_faith_specific": True,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 14,
        "text": "Reflect on this: 'Do not be anxious about anything, but in every situation, by prayer and petition, with thanksgiving, present your requests to God.'",
        "category_pk": 1,  # Faith
        "is_faith_specific": True,
        "scripture_reference": "Philippians 4:6",
        "scripture_text": "Do not be anxious about anything, but in every situation, by prayer and petition, with thanksgiving, present your requests to God.",
    },
    {
        "pk": 15,
        "text": "Where do you sense God calling you to trust Him more deeply?",
        "category_pk": 1,  # Faith
        "is_faith_specific": True,
        "scripture_reference": "Proverbs 3:5-6",
        "scripture_text": "Trust in the Lord with all your heart and lean not on your own understanding; in all your ways submit to him, and he will make your paths straight.",
    },
    {
        "pk": 16,
        "text": "How can you show love to your family this week?",
        "category_pk": 2,  # Family
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 17,
        "text": "What's one thing you're learning at work right now?",
        "category_pk": 3,  # Work
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 18,
        "text": "Describe how your body feels today. What does it need?",
        "category_pk": 4,  # Health
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 19,
        "text": "What's something small that brought you joy today?",
        "category_pk": 5,  # Gratitude
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
    {
        "pk": 20,
        "text": "What's one step you can take toward a goal this week?",
        "category_pk": 8,  # Dreams
        "is_faith_specific": False,
        "scripture_reference": "",
        "scripture_text": "",
    },
]


def load_prompts(apps, schema_editor):
    """Load journal prompts into the database."""
    JournalPrompt = apps.get_model('journal', 'JournalPrompt')
    Category = apps.get_model('core', 'Category')

    # Build category lookup by pk
    categories = {c.pk: c for c in Category.objects.all()}

    created_count = 0
    updated_count = 0

    for prompt_data in JOURNAL_PROMPTS:
        category = categories.get(prompt_data["category_pk"])

        prompt, created = JournalPrompt.objects.update_or_create(
            pk=prompt_data["pk"],
            defaults={
                "text": prompt_data["text"],
                "category": category,
                "is_faith_specific": prompt_data["is_faith_specific"],
                "scripture_reference": prompt_data["scripture_reference"],
                "scripture_text": prompt_data["scripture_text"],
                "is_active": True,
            }
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

    print(f"\nJournal Prompts Migration:")
    print(f"  Created: {created_count}")
    print(f"  Updated: {updated_count}")


def reverse_prompts(apps, schema_editor):
    """Remove loaded prompts (for migration rollback)."""
    JournalPrompt = apps.get_model('journal', 'JournalPrompt')
    pks = [p["pk"] for p in JOURNAL_PROMPTS]
    deleted, _ = JournalPrompt.objects.filter(pk__in=pks).delete()
    print(f"Removed {deleted} journal prompts")


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0002_import_chatgpt_journal'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(load_prompts, reverse_prompts),
    ]
