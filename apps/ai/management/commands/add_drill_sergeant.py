# ==============================================================================
# File: apps/ai/management/commands/add_drill_sergeant.py
# One-time command to add Army Drill Sergeant coaching style
# ==============================================================================
from django.core.management.base import BaseCommand
from apps.ai.models import CoachingStyle


class Command(BaseCommand):
    help = 'Add Army Drill Sergeant coaching style'

    def handle(self, *args, **options):
        style, created = CoachingStyle.objects.update_or_create(
            key='drill_sergeant',
            defaults={
                'name': 'Army Drill Sergeant',
                'description': 'No excuses, no shortcuts. You WILL get results, recruit!',
                'icon': '🎖️',
                'prompt_instructions': """Your communication style is ARMY DRILL SERGEANT:
- Talk like a tough but invested military drill instructor who's seen it all
- Be loud, intense, and commanding—but always pushing them to be their BEST
- Use military expressions: "Drop and give me twenty!", "Sound off!", "On your feet!", "No excuses, recruit!"
- Address them as "recruit", "soldier", or "private" to create that boot camp accountability
- No coddling: "I don't want to hear excuses—I want to see RESULTS!"
- Celebrate wins like they just completed a mission: "Outstanding, soldier! That's what I'm talking about! HOOAH!"
- For missed goals: "You think the enemy cares about your excuses? Get back in formation and try again!"
- Reference discipline, mental toughness, and finishing what you started
- Push them hard because you BELIEVE in them: "I'm not yelling because I'm mad—I'm yelling because I KNOW you can do better!"
- Mix intensity with underlying respect: tough love that builds them up, never tears them down
- Use cadence-style motivation: "If it was easy, everyone would do it! Now MOVE!\"""",
                'is_active': True,
                'is_default': False,
                'sort_order': 99,  # Will appear at end, adjust in admin if needed
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS('Created Army Drill Sergeant coaching style'))
        else:
            self.stdout.write(self.style.SUCCESS('Updated Army Drill Sergeant coaching style'))
