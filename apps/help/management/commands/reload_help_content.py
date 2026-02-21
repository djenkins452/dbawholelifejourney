# ==============================================================================
# File: apps/help/management/commands/reload_help_content.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Idempotent help content loader using update_or_create
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-31
# Last Updated: 2026-02-21
# ==============================================================================
"""
Reload help content from fixture JSON files — idempotent and non-destructive.

Uses update_or_create keyed on each model's unique field (context_id, slug,
destination_id) so records are upserted, not deleted and recreated. This is
safe for production deployment chains and works correctly with PostgreSQL
NOT NULL constraints (no loaddata/raw=True bypass issues).

Handles:
    - HelpTopic (help_topics.json, help_topics_brain_training.json)
    - AdminHelpTopic (admin_help_topics.json)
    - HelpCategory (help_categories.json)
    - HelpArticle (help_articles.json)
    - TeachingDestination (teaching_destinations.json)

Usage:
    python manage.py reload_help_content
    python manage.py reload_help_content --dry-run
    python manage.py reload_help_content --topics-only
    python manage.py reload_help_content --articles-only
"""

import json
import os

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

# Map of model label → (unique_key_field, fixture_files, group)
MODEL_FIXTURE_MAP = {
    'help.helptopic': {
        'unique_key': 'context_id',
        'fixtures': [
            'apps/help/fixtures/help_topics.json',
            'apps/help/fixtures/help_topics_brain_training.json',
        ],
        'group': 'topics',
    },
    'help.adminhelptopic': {
        'unique_key': 'context_id',
        'fixtures': [
            'apps/help/fixtures/admin_help_topics.json',
        ],
        'group': 'topics',
    },
    'help.helpcategory': {
        'unique_key': 'slug',
        'fixtures': [
            'apps/help/fixtures/help_categories.json',
        ],
        'group': 'articles',
    },
    'help.helparticle': {
        'unique_key': 'slug',
        'fixtures': [
            'apps/help/fixtures/help_articles.json',
        ],
        'group': 'articles',
    },
    'help.teachingdestination': {
        'unique_key': 'destination_id',
        'fixtures': [
            'apps/help/fixtures/teaching_destinations.json',
        ],
        'group': 'topics',
    },
}

# Fields managed by Django or M2M — never include in update_or_create defaults
EXCLUDED_FIELDS = {
    'created_at', 'updated_at',
    'related_topics', 'related_articles', 'source_articles',
}


class Command(BaseCommand):
    help = 'Reload help content from fixtures (idempotent upsert, non-destructive)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--topics-only',
            action='store_true',
            help='Only reload help topics and teaching destinations',
        )
        parser.add_argument(
            '--articles-only',
            action='store_true',
            help='Only reload help articles and categories',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        topics_only = options['topics_only']
        articles_only = options['articles_only']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made\n'))

        # Determine which groups to load
        if topics_only:
            groups = {'topics'}
        elif articles_only:
            groups = {'articles'}
        else:
            groups = {'topics', 'articles'}

        total_created = 0
        total_updated = 0
        total_errors = 0

        for model_label, config in MODEL_FIXTURE_MAP.items():
            if config['group'] not in groups:
                continue

            try:
                Model = apps.get_model(model_label)
            except LookupError:
                self.stdout.write(self.style.WARNING(
                    f'  Model {model_label} not found — skipping'
                ))
                continue

            unique_key = config['unique_key']

            for fixture_path in config['fixtures']:
                created, updated, errors = self._load_fixture(
                    Model, model_label, unique_key, fixture_path, dry_run
                )
                total_created += created
                total_updated += updated
                total_errors += errors

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'DRY RUN complete: would create {total_created}, '
                f'update {total_updated}, errors {total_errors}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Help content reload complete: '
                f'created {total_created}, updated {total_updated}, errors {total_errors}'
            ))

        self._show_counts()

    def _load_fixture(self, Model, model_label, unique_key, fixture_path, dry_run):
        """Load a single fixture file using update_or_create."""
        full_path = os.path.join(settings.BASE_DIR, fixture_path)

        if not os.path.exists(full_path):
            self.stdout.write(self.style.WARNING(
                f'  {fixture_path} not found — skipping'
            ))
            return 0, 0, 0

        try:
            with open(full_path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.stdout.write(self.style.ERROR(
                f'  {fixture_path} read error: {e}'
            ))
            return 0, 0, 1

        created_count = 0
        updated_count = 0
        error_count = 0

        self.stdout.write(f'  Loading {fixture_path} ({len(data)} records)...')

        # Build a map of FK field names → attnames for this model
        # e.g. {'category': 'category_id'} for HelpArticle.category FK
        fk_map = {}
        for field in Model._meta.get_fields():
            if hasattr(field, 'attname') and field.attname != field.name:
                fk_map[field.name] = field.attname

        for entry in data:
            entry_model = entry.get('model', '')
            fields = entry.get('fields', {})

            if entry_model != model_label:
                continue

            if unique_key not in fields:
                self.stdout.write(self.style.WARNING(
                    f'    Missing unique key "{unique_key}" in entry — skipping'
                ))
                error_count += 1
                continue

            # Build lookup and defaults
            lookup = {unique_key: fields[unique_key]}
            defaults = {}

            for k, v in fields.items():
                if k == unique_key or k in EXCLUDED_FIELDS:
                    continue
                # Convert FK field names to _id suffix for raw values
                if k in fk_map:
                    defaults[fk_map[k]] = v
                else:
                    defaults[k] = v

            if dry_run:
                exists = Model.objects.filter(**lookup).exists()
                if exists:
                    updated_count += 1
                else:
                    created_count += 1
                continue

            try:
                _, was_created = Model.objects.update_or_create(
                    **lookup, defaults=defaults
                )
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'    Error on {lookup}: {e}'
                ))
                error_count += 1

        action = 'Would process' if dry_run else 'Processed'
        self.stdout.write(self.style.SUCCESS(
            f'    {action}: {created_count} created, {updated_count} updated'
            + (f', {error_count} errors' if error_count else '')
        ))

        return created_count, updated_count, error_count

    def _show_counts(self):
        """Display current record counts."""
        from apps.help.models import (
            HelpTopic, AdminHelpTopic, HelpCategory, HelpArticle, TeachingDestination
        )

        self.stdout.write('Final counts:')
        self.stdout.write(f'  - HelpTopic: {HelpTopic.objects.count()}')
        self.stdout.write(f'  - AdminHelpTopic: {AdminHelpTopic.objects.count()}')
        self.stdout.write(f'  - HelpCategory: {HelpCategory.objects.count()}')
        self.stdout.write(f'  - HelpArticle: {HelpArticle.objects.count()}')
        self.stdout.write(f'  - TeachingDestination: {TeachingDestination.objects.count()}')
