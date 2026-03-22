"""
Seed message_templates for existing CoachingStyles.

Each style gets persona-appropriate templates for 5 message types
× 3 day statuses. These are used by persona_service.render_message()
to give Beth tone-consistent example phrases.
"""

from django.db import migrations


# Templates per coaching style key
_STYLE_TEMPLATES = {
    'supportive': {
        'next_action': {
            'low': "Let's start with {action}. You've got this.",
            'partial': "Nice progress. Next up: {action}.",
            'strong': "Keep the momentum — {action} is next.",
        },
        'day_summary': {
            'low': "Today's been quiet so far. One step at a time.",
            'partial': "{completed} of {total} done — you're building.",
            'strong': "Strong day — {completed} of {total} done. Well done.",
        },
        'nudge': {
            'low': "{action} is still open. Small steps count.",
            'partial': "Don't forget {action}.",
            'strong': "Almost there — {action} left.",
        },
        'empty_state': {
            'low': "Nothing started yet. What feels right to begin with?",
            'partial': "Nothing started yet. What feels right to begin with?",
            'strong': "Nothing started yet. What feels right to begin with?",
        },
        'progress_update': {
            'low': "{completed} of {total} done.",
            'partial': "{completed} of {total} done — good progress.",
            'strong': "{completed} of {total} done — great work.",
        },
    },
    'direct': {
        'next_action': {
            'low': "Start {action}. {duration} minutes.",
            'partial': "Next: {action}.",
            'strong': "{action} is next. Go.",
        },
        'day_summary': {
            'low': "{completed}/{total}. Pick one and start.",
            'partial': "{completed}/{total}. Keep moving.",
            'strong': "{completed}/{total}. Solid.",
        },
        'nudge': {
            'low': "{action}. Now.",
            'partial': "Handle {action}.",
            'strong': "Last one: {action}.",
        },
        'empty_state': {
            'low': "Nothing done. Start now.",
            'partial': "Nothing done. Start now.",
            'strong': "Nothing done. Start now.",
        },
        'progress_update': {
            'low': "{completed}/{total}.",
            'partial': "{completed}/{total}. Moving.",
            'strong': "{completed}/{total}. Strong.",
        },
    },
    'coach': {
        'next_action': {
            'low': "Here's the play: start with {action}. {duration} minutes, full focus.",
            'partial': "Good work so far. Next play: {action}.",
            'strong': "Closing strong — {action} is the finisher.",
        },
        'day_summary': {
            'low': "{completion_rate}% today. We're behind — let's get one win.",
            'partial': "{completed}/{total} — building momentum. Don't let up.",
            'strong': "{completed}/{total} — championship effort today.",
        },
        'nudge': {
            'low': "{action} is on the board. Execute.",
            'partial': "Stay locked in — {action} next.",
            'strong': "One more rep: {action}.",
        },
        'empty_state': {
            'low': "Game hasn't started yet. First play: get moving.",
            'partial': "Game hasn't started yet. First play: get moving.",
            'strong': "Game hasn't started yet. First play: get moving.",
        },
        'progress_update': {
            'low': "{completed} of {total}. We need more.",
            'partial': "{completed} of {total}. Building.",
            'strong': "{completed} of {total}. Dominant.",
        },
    },
    'gentle': {
        'next_action': {
            'low': "Whenever you're ready, {action} is a good place to start.",
            'partial': "When you have a moment, {action} is next.",
            'strong': "You've done so well — {action} when you're ready.",
        },
        'day_summary': {
            'low': "It's been a quiet day. No pressure — every day is different.",
            'partial': "{completed} of {total} — that's meaningful progress.",
            'strong': "What a day — {completed} of {total} done. Be proud of that.",
        },
        'nudge': {
            'low': "{action} is still there when you're ready.",
            'partial': "Gentle reminder: {action}.",
            'strong': "Just {action} left — no rush.",
        },
        'empty_state': {
            'low': "Nothing started yet, and that's okay. What sounds doable?",
            'partial': "Nothing started yet, and that's okay. What sounds doable?",
            'strong': "Nothing started yet, and that's okay. What sounds doable?",
        },
        'progress_update': {
            'low': "{completed} of {total} done.",
            'partial': "{completed} of {total} — lovely progress.",
            'strong': "{completed} of {total} — beautiful work.",
        },
    },
}


def seed_templates(apps, schema_editor):
    CoachingStyle = apps.get_model('ai', 'CoachingStyle')
    updated = 0
    for style in CoachingStyle.objects.all():
        templates = _STYLE_TEMPLATES.get(style.key)
        if templates and not style.message_templates:
            style.message_templates = templates
            style.save(update_fields=['message_templates'])
            updated += 1
    if updated:
        print(f"  Seeded message_templates for {updated} coaching style(s)")


def reverse_seed(apps, schema_editor):
    CoachingStyle = apps.get_model('ai', 'CoachingStyle')
    CoachingStyle.objects.all().update(message_templates={})


class Migration(migrations.Migration):
    dependencies = [
        ('ai', '0027_coaching_style_message_templates'),
    ]

    operations = [
        migrations.RunPython(seed_templates, reverse_seed),
    ]
