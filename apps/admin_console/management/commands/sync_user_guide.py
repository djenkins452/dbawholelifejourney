# ==============================================================================
# File: apps/admin_console/management/commands/sync_user_guide.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Sync help topics and articles into a User Guide
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-07
# ==============================================================================
"""
Reads from HelpTopic and HelpArticle models, groups them by module/app,
and creates AdminGuideSection/AdminGuideArticle records with guide_type='user'.

Usage:
    python manage.py sync_user_guide
    python manage.py sync_user_guide --force  # re-sync even if unchanged
"""
import hashlib
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.admin_console.models import AdminGuideSection, AdminGuideArticle
from apps.help.models import HelpTopic, HelpArticle, HelpCategory


# Module display names and icons
MODULE_CONFIG = {
    'general': {'title': 'Getting Started', 'icon': '🚀', 'order': 0},
    'dashboard': {'title': 'Dashboard', 'icon': '📊', 'order': 1},
    'journal': {'title': 'Journal', 'icon': '📓', 'order': 2},
    'health': {'title': 'Health & Wellness', 'icon': '❤️', 'order': 3},
    'faith': {'title': 'Faith & Devotion', 'icon': '✝️', 'order': 4},
    'life': {'title': 'Life Organization', 'icon': '🗂️', 'order': 5},
    'purpose': {'title': 'Goals & Purpose', 'icon': '🎯', 'order': 6},
    'settings': {'title': 'Settings & Preferences', 'icon': '⚙️', 'order': 7},
    'ai': {'title': 'AI Assistant', 'icon': '🤖', 'order': 8},
    'scan': {'title': 'Scan & Capture', 'icon': '📷', 'order': 9},
    'finance': {'title': 'Finance', 'icon': '💰', 'order': 10},
    'medical': {'title': 'Medical Records', 'icon': '🏥', 'order': 11},
    'brain_training': {'title': 'Brain Training', 'icon': '🧩', 'order': 12},
}


class Command(BaseCommand):
    help = 'Sync help topics and articles into the User Guide'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-sync even if content hash is unchanged',
        )

    def handle(self, *args, **options):
        force = options['force']

        created_sections = 0
        updated_sections = 0
        created_articles = 0
        updated_articles = 0

        # ---------------------------------------------------------------
        # 1. Build sections from HelpTopic app_name groupings
        # ---------------------------------------------------------------
        topics = HelpTopic.objects.filter(is_active=True).order_by('app_name', 'order')
        topics_by_app = defaultdict(list)
        for topic in topics:
            app_key = topic.app_name or 'general'
            topics_by_app[app_key].append(topic)

        # ---------------------------------------------------------------
        # 2. Also pull HelpArticle records grouped by module
        # ---------------------------------------------------------------
        articles = HelpArticle.objects.filter(is_active=True).select_related('category').order_by('sort_order')
        articles_by_module = defaultdict(list)
        for article in articles:
            articles_by_module[article.module].append(article)

        # ---------------------------------------------------------------
        # 3. Merge all modules from both sources
        # ---------------------------------------------------------------
        all_modules = set(topics_by_app.keys()) | set(articles_by_module.keys())

        active_section_keys = []

        for module_key in sorted(all_modules, key=lambda k: MODULE_CONFIG.get(k, {}).get('order', 99)):
            config = MODULE_CONFIG.get(module_key, {
                'title': module_key.replace('_', ' ').title(),
                'icon': '📄',
                'order': 99,
            })

            section_key = slugify(module_key)[:100]
            active_section_keys.append(section_key)

            section, sec_created = AdminGuideSection.objects.update_or_create(
                guide_type='user',
                section_key=section_key,
                defaults={
                    'title': config['title'],
                    'icon': config['icon'],
                    'description': '',
                    'order': config.get('order', 99),
                    'is_active': True,
                },
            )

            if sec_created:
                created_sections += 1
            else:
                updated_sections += 1

            art_order = 0

            # Add HelpTopic entries as articles
            for topic in topics_by_app.get(module_key, []):
                art_slug = slugify(topic.help_id or topic.title)[:200]
                content = topic.content
                if topic.description:
                    content = f"*{topic.description}*\n\n{content}"

                content_hash = hashlib.md5(content.encode()).hexdigest()

                existing = AdminGuideArticle.objects.filter(
                    section=section, slug=art_slug
                ).first()

                if existing and not force:
                    old_hash = hashlib.md5(existing.content.encode()).hexdigest()
                    if old_hash == content_hash:
                        art_order += 1
                        continue

                _art, art_created = AdminGuideArticle.objects.update_or_create(
                    section=section,
                    slug=art_slug,
                    defaults={
                        'title': topic.title,
                        'content': content,
                        'order': art_order,
                        'is_editable': False,
                        'is_active': True,
                    },
                )

                if art_created:
                    created_articles += 1
                else:
                    updated_articles += 1

                art_order += 1

            # Add HelpArticle entries (avoiding duplicates with topics)
            existing_slugs = {
                slugify(t.help_id or t.title)[:200]
                for t in topics_by_app.get(module_key, [])
            }

            for help_article in articles_by_module.get(module_key, []):
                art_slug = slugify(help_article.slug or help_article.title)[:200]
                if art_slug in existing_slugs:
                    continue

                content = help_article.content
                if help_article.summary:
                    content = f"*{help_article.summary}*\n\n{content}"

                content_hash = hashlib.md5(content.encode()).hexdigest()

                existing = AdminGuideArticle.objects.filter(
                    section=section, slug=art_slug
                ).first()

                if existing and not force:
                    old_hash = hashlib.md5(existing.content.encode()).hexdigest()
                    if old_hash == content_hash:
                        art_order += 1
                        continue

                _art, art_created = AdminGuideArticle.objects.update_or_create(
                    section=section,
                    slug=art_slug,
                    defaults={
                        'title': help_article.title,
                        'content': content,
                        'order': art_order,
                        'is_editable': False,
                        'is_active': True,
                    },
                )

                if art_created:
                    created_articles += 1
                else:
                    updated_articles += 1

                art_order += 1

        # Deactivate sections no longer needed
        deactivated = AdminGuideSection.objects.filter(
            guide_type='user', is_active=True
        ).exclude(section_key__in=active_section_keys).update(is_active=False)

        msg = (
            f"User Guide sync complete: "
            f"{created_sections} sections created, {updated_sections} updated, "
            f"{created_articles} articles created, {updated_articles} updated"
        )
        if deactivated:
            msg += f", {deactivated} sections deactivated"

        self.stdout.write(self.style.SUCCESS(msg))
