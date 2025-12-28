"""
One-time data migration to import ChatGPT journal entries for dannyjenkins71@gmail.com.

This migration runs automatically during deploy and imports historical journal
entries from ChatGPT conversations.
"""

from django.db import migrations


CHATGPT_ENTRIES = [
    {
        "date": "2025-12-03",
        "faith": None,
        "health": "Cut out sweets for the last two days and noticed improvement in blood sugar levels. Feeling more in control.",
        "family": None,
        "work": "Returned home from work at 10:30 PM and back out by 6:30 AM. Payroll process under strain due to WFM timesheet issues. Trying to clean up meal deductions logic—if two short shifts are worked, meals shouldn't be deducted. Also trying to automate meal deduction identification using punch data.",
        "reflection_summary": "A heavy week with long hours, but took a healthy step with sugar intake. Actively troubleshooting payroll edge cases."
    },
    {
        "date": "2025-12-11",
        "faith": "Missed another Bible study. Struggling with motivation and feeling disconnected from the group. Feel like a 'rebel' compared to others who seem more Biblically knowledgeable. Desire to support Heather and Jarra, but unsure of how to connect authentically with the group.",
        "health": "Working from home this week has brought small moments of peace. Making a conscious effort to reduce stress and adjust mindset.",
        "family": "Processing Haley's upcoming move to Kansas. She'll be gone through Christmas and possibly into spring due to Parker's deployment. Emotional mix of support and sadness as she continues growing into her new life. House is currently full with Haley, Celine, and Kira visiting. Evening plans include dinner, decorating the tree, and watching Christmas movies together.",
        "work": "Managing multiple layers: testing WFM items, processing a missed performance increase, running special payroll, training a timekeeper, and resolving a PTO display issue that misrepresents balances during approval. Staying calm amidst a busy week.",
        "reflection_summary": "Balancing leadership and emotion. Grateful for small moments of peace at home. Feeling tension between spiritual community and spiritual belonging."
    },
    {
        "date": "2025-12-12",
        "faith": "Offering support to team members is a way of living out faith in action. Feeling spiritually stretched but focused on balance and being present.",
        "health": None,
        "family": "Looking forward to attending a basketball game for Ty's birthday, or dinner with Jason and his family on Sunday.",
        "work": "Led the team through complex payroll issues: a retro pay error going back to 2023, FLSA complexities with OT calculations, and a rounding/truncation issue over time. Team recalculated and is within three cents, but striving for penny-level accuracy. Elizabeth out sick; covering leadership responsibilities. Also focusing on testing the payroll export.",
        "reflection_summary": "Tense but productive day. Deep commitment to payroll integrity and team care. Managing pressure while planning meaningful personal time."
    },
    {
        "date": "2025-12-17",
        "faith": None,
        "health": "Feeling tired but aware. Avoiding burnout and beginning to make intentional choices about energy management.",
        "family": None,
        "work": "Team had a rough previous day; showing up to provide emotional and moral support. Focused on two priorities: compensation info for Chandra and ensuring payroll goes out. Learning how to create work-life boundaries.",
        "reflection_summary": "Feeling the weight of the week, but prioritizing care for your team. Reflection on boundaries and balance in life and work."
    },
    {
        "date": "2025-12-18",
        "faith": None,
        "health": "Day felt more balanced emotionally. One of the calmer busy days.",
        "family": "Looking forward to going out to The Abbey with Heather to enjoy live music (The Dark Water Project), pending schedule. Planning a relaxing evening: dinner, chores, and project time together.",
        "work": "Busy but calm and productive day. Finalizing payroll prep. Work felt more in control than earlier in the week.",
        "reflection_summary": "Calm during the storm. Balanced a productive workday with time at home and anticipation of a meaningful night out."
    },
    {
        "date": "2025-12-19",
        "faith": "Chose to avoid a social event that could jeopardize sobriety. A conscious and faithful decision to protect your growth.",
        "health": "Acknowledged temptation around alcohol. Chose peace and safety over pressure—staying home instead of risking relapse.",
        "family": "Plans to go out with Heather changed when friends canceled. Opted to spend the evening at home, help with groceries, and relax with football and coding.",
        "work": "Major payroll day: dealing with allocation/import errors, missing time for Anne, leave approvals, WFM hours file, and team readiness. Elizabeth was out sick but still supporting from home. You're managing the weight of leading while others are down.",
        "reflection_summary": "Led through a critical payroll day, made strong personal choices, and prioritized peace. Supporting others while holding your own boundaries."
    }
]

USER_EMAIL = "dannyjenkins71@gmail.com"


def import_chatgpt_entries(apps, schema_editor):
    """Import ChatGPT journal entries for the specified user."""
    from datetime import datetime

    User = apps.get_model('users', 'User')
    JournalEntry = apps.get_model('journal', 'JournalEntry')
    Category = apps.get_model('core', 'Category')

    # Get the user
    try:
        user = User.objects.get(email=USER_EMAIL)
    except User.DoesNotExist:
        print(f"User {USER_EMAIL} not found. Skipping import.")
        return

    # Load categories
    category_map = {}
    for category in Category.objects.all():
        category_map[category.slug.lower()] = category

    # Field to category mapping
    field_category_map = {
        "faith": "faith",
        "health": "health",
        "family": "family",
        "work": "work",
    }

    created_count = 0
    skipped_count = 0

    for entry_data in CHATGPT_ENTRIES:
        # Parse date
        entry_date = datetime.strptime(entry_data["date"], "%Y-%m-%d").date()

        # Check for existing entry on this date
        if JournalEntry.objects.filter(user=user, entry_date=entry_date).exists():
            print(f"  Skipping {entry_data['date']}: Entry already exists")
            skipped_count += 1
            continue

        # Build body from sections
        body_parts = []
        categories_to_add = []

        for field, category_slug in field_category_map.items():
            content = entry_data.get(field)
            if content:
                body_parts.append(f"## {field.title()}\n{content}")
                if category_slug in category_map:
                    categories_to_add.append(category_map[category_slug])

        # Add reflection
        reflection = entry_data.get("reflection_summary")
        if reflection:
            body_parts.append(f"## Reflection\n{reflection}")

        if not body_parts:
            continue

        body = "\n\n".join(body_parts)
        title = entry_date.strftime("%A, %B %d, %Y")
        word_count = len(body.split())

        # Create the entry
        entry = JournalEntry.objects.create(
            user=user,
            title=title,
            body=body,
            entry_date=entry_date,
            word_count=word_count,
            status="active",
        )

        # Add categories (ManyToMany)
        entry.categories.set(categories_to_add)

        print(f"  Created: {title} ({len(categories_to_add)} categories)")
        created_count += 1

    print(f"\nChatGPT Journal Import Complete:")
    print(f"  Created: {created_count}")
    print(f"  Skipped: {skipped_count}")


def reverse_import(apps, schema_editor):
    """Remove imported entries (for migration rollback)."""
    from datetime import datetime

    User = apps.get_model('users', 'User')
    JournalEntry = apps.get_model('journal', 'JournalEntry')

    try:
        user = User.objects.get(email=USER_EMAIL)
    except User.DoesNotExist:
        return

    # Delete entries by date
    dates = [datetime.strptime(e["date"], "%Y-%m-%d").date() for e in CHATGPT_ENTRIES]
    deleted, _ = JournalEntry.objects.filter(user=user, entry_date__in=dates).delete()
    print(f"Removed {deleted} imported entries")


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0001_initial'),
        ('users', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(import_chatgpt_entries, reverse_import),
    ]
