"""
Setup default Purpose module data.

Creates default Life Domains and Reflection Prompts.
Run with: python manage.py setup_purpose_defaults
"""

from django.core.management.base import BaseCommand
from apps.purpose.models import LifeDomain, ReflectionPrompt


class Command(BaseCommand):
    help = 'Set up default Purpose module data (Life Domains and Reflection Prompts)'
    
    def handle(self, *args, **options):
        self.setup_life_domains()
        self.setup_reflection_prompts()
        self.stdout.write(self.style.SUCCESS('Purpose module defaults created successfully!'))
    
    def setup_life_domains(self):
        """Create default life domains."""
        domains = [
            {
                'name': 'Faith',
                'slug': 'faith',
                'description': 'Spiritual growth, relationship with God, church involvement',
                'icon': '✝️',
                'color': '#8b5cf6',
                'sort_order': 1,
            },
            {
                'name': 'Health',
                'slug': 'health',
                'description': 'Physical health, fitness, nutrition, mental wellness',
                'icon': '❤️',
                'color': '#ef4444',
                'sort_order': 2,
            },
            {
                'name': 'Family',
                'slug': 'family',
                'description': 'Marriage, parenting, extended family relationships',
                'icon': '👨‍👩‍👧‍👦',
                'color': '#ec4899',
                'sort_order': 3,
            },
            {
                'name': 'Work',
                'slug': 'work',
                'description': 'Career, profession, calling, vocational development',
                'icon': '💼',
                'color': '#3b82f6',
                'sort_order': 4,
            },
            {
                'name': 'Finances',
                'slug': 'finances',
                'description': 'Financial health, stewardship, generosity, security',
                'icon': '💰',
                'color': '#10b981',
                'sort_order': 5,
            },
            {
                'name': 'Learning',
                'slug': 'learning',
                'description': 'Education, skills development, intellectual growth',
                'icon': '📚',
                'color': '#f59e0b',
                'sort_order': 6,
            },
            {
                'name': 'Personal Growth',
                'slug': 'personal-growth',
                'description': 'Character development, habits, self-improvement',
                'icon': '🌱',
                'color': '#14b8a6',
                'sort_order': 7,
            },
            {
                'name': 'Relationships',
                'slug': 'relationships',
                'description': 'Friendships, community, social connections',
                'icon': '🤝',
                'color': '#f97316',
                'sort_order': 8,
            },
        ]
        
        created_count = 0
        for domain_data in domains:
            domain, created = LifeDomain.objects.get_or_create(
                slug=domain_data['slug'],
                defaults=domain_data
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created domain: {domain.name}")
            else:
                self.stdout.write(f"  Domain exists: {domain.name}")
        
        self.stdout.write(f"Life Domains: {created_count} created, {len(domains) - created_count} existed")
    
    def setup_reflection_prompts(self):
        """Create default reflection prompts."""
        year_end_prompts = [
            "What gave me life this year?",
            "What drained me this year?",
            "Where did I grow quietly, in ways others might not have noticed?",
            "What warning signs did I ignore?",
            "What patterns repeated themselves this year?",
            "What am I most grateful for from this year?",
            "What was my biggest challenge, and what did it teach me?",
            "Where did I feel most aligned with my purpose?",
            "What relationships deepened? Which ones faded?",
            "If I could go back to January 1st, what advice would I give myself?",
        ]
        
        year_start_prompts = [
            "What word or theme do I want to guide this year?",
            "What do I want to feel more of this year?",
            "What do I want to release or let go of?",
            "What does success look like for me this year?",
            "What habits do I want to build or break?",
            "How do I want to grow spiritually this year?",
            "What relationships do I want to invest in?",
            "What would make this year meaningful?",
        ]
        
        quarterly_prompts = [
            "How am I progressing toward my annual direction?",
            "What adjustments do I need to make?",
            "What has surprised me this quarter?",
            "Am I living in alignment with my word of the year?",
            "What do I need to start, stop, or continue?",
        ]
        
        created_count = 0
        
        # Year End prompts
        for i, question in enumerate(year_end_prompts):
            prompt, created = ReflectionPrompt.objects.get_or_create(
                prompt_type='year_end',
                question=question,
                defaults={'sort_order': i}
            )
            if created:
                created_count += 1
        
        # Year Start prompts
        for i, question in enumerate(year_start_prompts):
            prompt, created = ReflectionPrompt.objects.get_or_create(
                prompt_type='year_start',
                question=question,
                defaults={'sort_order': i}
            )
            if created:
                created_count += 1
        
        # Quarterly prompts
        for i, question in enumerate(quarterly_prompts):
            prompt, created = ReflectionPrompt.objects.get_or_create(
                prompt_type='quarterly',
                question=question,
                defaults={'sort_order': i}
            )
            if created:
                created_count += 1
        
        total = len(year_end_prompts) + len(year_start_prompts) + len(quarterly_prompts)
        self.stdout.write(f"Reflection Prompts: {created_count} created, {total - created_count} existed")
