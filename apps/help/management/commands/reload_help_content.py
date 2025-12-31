# ==============================================================================
# File: apps/help/management/commands/reload_help_content.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reload help content from fixtures (topics, articles, categories)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Reload help content from fixtures.

This command clears existing help content and reloads from fixtures.
Use this after updating help_topics.json, help_articles.json, or help_categories.json.

Usage:
    python manage.py reload_help_content
    python manage.py reload_help_content --dry-run
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from apps.help.models import HelpTopic, HelpArticle, HelpCategory, AdminHelpTopic


class Command(BaseCommand):
    help = 'Reload help content from fixtures (clears existing and reloads)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--topics-only',
            action='store_true',
            help='Only reload help topics (not articles or categories)',
        )
        parser.add_argument(
            '--articles-only',
            action='store_true',
            help='Only reload help articles (and categories)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        topics_only = options['topics_only']
        articles_only = options['articles_only']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made\n'))

        # Show current counts
        self.stdout.write('Current content counts:')
        self.stdout.write(f'  - HelpTopic: {HelpTopic.objects.count()}')
        self.stdout.write(f'  - AdminHelpTopic: {AdminHelpTopic.objects.count()}')
        self.stdout.write(f'  - HelpCategory: {HelpCategory.objects.count()}')
        self.stdout.write(f'  - HelpArticle: {HelpArticle.objects.count()}')
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('Would reload help content from fixtures'))
            return

        # Determine what to reload
        reload_topics = not articles_only
        reload_articles = not topics_only

        if reload_topics:
            # Clear existing topics
            topic_count = HelpTopic.objects.count()
            HelpTopic.objects.all().delete()
            self.stdout.write(f'Deleted {topic_count} HelpTopic records')

            # Load help topics fixture
            self.stdout.write('Loading help_topics.json...')
            call_command('loaddata', 'help_topics.json', verbosity=0)
            self.stdout.write(self.style.SUCCESS(
                f'  Loaded {HelpTopic.objects.count()} help topics'
            ))

            # Load admin help topics if fixture exists
            admin_count = AdminHelpTopic.objects.count()
            if admin_count > 0:
                AdminHelpTopic.objects.all().delete()
                self.stdout.write(f'Deleted {admin_count} AdminHelpTopic records')

            try:
                self.stdout.write('Loading admin_help_topics.json...')
                call_command('loaddata', 'admin_help_topics.json', verbosity=0)
                self.stdout.write(self.style.SUCCESS(
                    f'  Loaded {AdminHelpTopic.objects.count()} admin help topics'
                ))
            except Exception:
                self.stdout.write(self.style.WARNING(
                    '  admin_help_topics.json not found or empty - skipping'
                ))

        if reload_articles:
            # Clear existing categories and articles
            article_count = HelpArticle.objects.count()
            HelpArticle.objects.all().delete()
            self.stdout.write(f'Deleted {article_count} HelpArticle records')

            category_count = HelpCategory.objects.count()
            HelpCategory.objects.all().delete()
            self.stdout.write(f'Deleted {category_count} HelpCategory records')

            # Load categories first (articles depend on them)
            try:
                self.stdout.write('Loading help_categories.json...')
                call_command('loaddata', 'help_categories.json', verbosity=0)
                self.stdout.write(self.style.SUCCESS(
                    f'  Loaded {HelpCategory.objects.count()} help categories'
                ))
            except Exception:
                self.stdout.write(self.style.WARNING(
                    '  help_categories.json not found - skipping'
                ))

            # Load articles
            self.stdout.write('Loading help_articles.json...')
            call_command('loaddata', 'help_articles.json', verbosity=0)
            self.stdout.write(self.style.SUCCESS(
                f'  Loaded {HelpArticle.objects.count()} help articles'
            ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Help content reload complete!'))
        self.stdout.write('Final counts:')
        self.stdout.write(f'  - HelpTopic: {HelpTopic.objects.count()}')
        self.stdout.write(f'  - AdminHelpTopic: {AdminHelpTopic.objects.count()}')
        self.stdout.write(f'  - HelpCategory: {HelpCategory.objects.count()}')
        self.stdout.write(f'  - HelpArticle: {HelpArticle.objects.count()}')
