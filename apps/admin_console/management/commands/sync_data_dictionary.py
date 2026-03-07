# ==============================================================================
# File: apps/admin_console/management/commands/sync_data_dictionary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Sync the WLJ Data Dictionary markdown file into guide sections/articles
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-07
# ==============================================================================
"""
Reads docs/WLJ_Data_Dictionary.md and creates/updates AdminGuideSection and
AdminGuideArticle records with guide_type='data_dictionary'.

Usage:
    python manage.py sync_data_dictionary
    python manage.py sync_data_dictionary --force  # re-sync even if unchanged
"""
import hashlib
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.admin_console.models import AdminGuideSection, AdminGuideArticle


# Section icons by keyword
SECTION_ICONS = {
    'architecture': '🏗️',
    'base model': '🧱',
    'user': '👤',
    'authentication': '🔐',
    'intelligence': '🧠',
    'engine': '⚙️',
    'domain': '📦',
    'journal': '📓',
    'health': '❤️',
    'faith': '✝️',
    'life': '🗂️',
    'purpose': '🎯',
    'finance': '💰',
    'medical': '🏥',
    'brain': '🧩',
    'capture': '🎤',
    'supporting': '🔧',
    'core': '⚙️',
    'ai': '🤖',
    'admin': '🛠️',
    'help': '❓',
    'billing': '💳',
    'mobile': '📱',
    'scan': '📷',
    'sms': '📲',
    'security': '🔒',
    'relationship': '👥',
    'matrix': '📊',
    'relationship': '🔗',
    'keyword': '🔍',
    'master': '📋',
    'table': '📊',
    'overview': '📖',
}


def _pick_icon(title):
    """Pick an emoji icon based on the section title."""
    title_lower = title.lower()
    for keyword, icon in SECTION_ICONS.items():
        if keyword in title_lower:
            return icon
    return '📄'


def _clean_section_title(raw):
    """Strip numbered prefix from section title (e.g. '1. Architecture Overview' -> 'Architecture Overview')."""
    return re.sub(r'^\d+\.\s*', '', raw).strip()


class Command(BaseCommand):
    help = 'Sync the WLJ Data Dictionary markdown file into admin guide sections/articles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-sync even if content hash is unchanged',
        )

    def handle(self, *args, **options):
        force = options['force']
        dd_path = os.path.join(settings.BASE_DIR, 'docs', 'WLJ_Data_Dictionary.md')

        if not os.path.exists(dd_path):
            # Try fallback: resolve relative to this file's location
            fallback = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ))),
                'docs', 'WLJ_Data_Dictionary.md'
            )
            if os.path.exists(fallback):
                dd_path = fallback
            else:
                msg = (
                    f"Data dictionary not found at {dd_path} "
                    f"or fallback {fallback}. "
                    f"BASE_DIR={settings.BASE_DIR}"
                )
                self.stderr.write(self.style.ERROR(msg))
                raise FileNotFoundError(msg)

        with open(dd_path, 'r') as f:
            content = f.read()

        # Split by ## headers (level-2)
        sections = self._split_into_sections(content)

        if not sections:
            self.stderr.write(self.style.ERROR("No sections found in data dictionary"))
            return

        created_sections = 0
        updated_sections = 0
        created_articles = 0
        updated_articles = 0

        for order, (title, body) in enumerate(sections):
            section_key = slugify(title)[:100]
            icon = _pick_icon(title)

            section, sec_created = AdminGuideSection.objects.update_or_create(
                guide_type='data_dictionary',
                section_key=section_key,
                defaults={
                    'title': title,
                    'icon': icon,
                    'description': '',
                    'order': order,
                    'is_active': True,
                },
            )

            if sec_created:
                created_sections += 1
            else:
                updated_sections += 1

            # Split section body into sub-articles by ### headers
            articles = self._split_into_articles(title, body)

            for art_order, (art_title, art_content) in enumerate(articles):
                art_slug = slugify(art_title)[:200]
                content_hash = hashlib.md5(art_content.encode()).hexdigest()

                existing = AdminGuideArticle.objects.filter(
                    section=section, slug=art_slug
                ).first()

                if existing and not force:
                    # Check if content changed via hash comparison
                    old_hash = hashlib.md5(existing.content.encode()).hexdigest()
                    if old_hash == content_hash:
                        continue

                art, art_created = AdminGuideArticle.objects.update_or_create(
                    section=section,
                    slug=art_slug,
                    defaults={
                        'title': art_title,
                        'content': art_content,
                        'order': art_order,
                        'is_editable': False,
                        'is_active': True,
                    },
                )

                if art_created:
                    created_articles += 1
                else:
                    updated_articles += 1

        # Deactivate sections no longer in the source
        active_keys = [slugify(_clean_section_title(t))[:100] for t, _ in sections]
        deactivated = AdminGuideSection.objects.filter(
            guide_type='data_dictionary', is_active=True
        ).exclude(section_key__in=active_keys).update(is_active=False)

        msg = (
            f"Data Dictionary sync complete: "
            f"{created_sections} sections created, {updated_sections} updated, "
            f"{created_articles} articles created, {updated_articles} updated"
        )
        if deactivated:
            msg += f", {deactivated} sections deactivated"

        self.stdout.write(self.style.SUCCESS(msg))

    def _split_into_sections(self, content):
        """Split markdown content by ## headers into (title, body) tuples.
        Skip the Table of Contents section.
        """
        # Match ## headers at start of line
        pattern = r'^## (.+)$'
        parts = re.split(pattern, content, flags=re.MULTILINE)

        sections = []
        # parts[0] is content before first ##, then alternating title/body
        i = 1
        while i < len(parts):
            raw_title = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ''
            i += 2

            # Skip Table of Contents
            if raw_title.lower() == 'table of contents':
                continue

            title = _clean_section_title(raw_title)
            sections.append((title, body))

        return sections

    def _split_into_articles(self, section_title, body):
        """Split a section body into articles by ### headers.
        If no ### headers, the entire body becomes one article.
        """
        pattern = r'^### (.+)$'
        parts = re.split(pattern, body, flags=re.MULTILINE)

        # If there are no ### headers, the whole body is one article
        if len(parts) <= 1:
            return [(section_title, body)]

        articles = []
        # Content before first ### goes into an "Overview" article
        preamble = parts[0].strip()
        if preamble:
            articles.append((f"{section_title} Overview", preamble))

        i = 1
        while i < len(parts):
            art_title = parts[i].strip()
            art_body = parts[i + 1].strip() if i + 1 < len(parts) else ''
            i += 2
            # Clean up sub-header notation (e.g., "SAE — State Awareness Engine")
            articles.append((art_title, art_body))

        return articles
