"""
Management command to import journal entries from ChatGPT JSON export.

This is a one-time migration command to import journal data from ChatGPT
conversations into the Whole Life Journey application.

Usage:
    # Dry run to see what will be imported
    python manage.py import_chatgpt_journal path/to/export.json --dry-run

    # Import for a specific user
    python manage.py import_chatgpt_journal path/to/export.json --user=danny@example.com

    # Import with specific user ID
    python manage.py import_chatgpt_journal path/to/export.json --user-id=1
"""

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Category
from apps.journal.models import JournalEntry
from apps.users.models import User


class Command(BaseCommand):
    help = "Import journal entries from a ChatGPT JSON export file"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to the JSON file containing ChatGPT journal entries",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Email of the user to assign entries to",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="ID of the user to assign entries to",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--skip-duplicates",
            action="store_true",
            default=True,
            help="Skip entries with duplicate dates (default: True)",
        )

    def handle(self, *args, **options):
        json_file = options["json_file"]
        dry_run = options["dry_run"]
        skip_duplicates = options["skip_duplicates"]

        # Get the user
        user = self._get_user(options)
        if not user and not dry_run:
            raise CommandError(
                "You must specify a user with --user or --user-id when not doing a dry run"
            )

        # Load JSON data
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                entries_data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"File not found: {json_file}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON file: {e}")

        if not isinstance(entries_data, list):
            raise CommandError("JSON file must contain a list of journal entries")

        self.stdout.write(f"Found {len(entries_data)} entries in the JSON file")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
        if user:
            self.stdout.write(f"Importing for user: {user.email}")

        # Load categories for mapping
        category_map = self._load_categories()

        # Process entries
        created_count = 0
        skipped_count = 0
        errors = []

        with transaction.atomic():
            for i, entry_data in enumerate(entries_data, 1):
                try:
                    result = self._process_entry(
                        entry_data, user, category_map, dry_run, skip_duplicates
                    )
                    if result == "created":
                        created_count += 1
                    elif result == "skipped":
                        skipped_count += 1
                except Exception as e:
                    errors.append(f"Entry {i}: {str(e)}")

            if dry_run:
                # Rollback in dry run mode
                transaction.set_rollback(True)

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Entries that would be created: {created_count}")
            if dry_run
            else self.style.SUCCESS(f"Entries created: {created_count}")
        )
        if skipped_count:
            self.stdout.write(self.style.WARNING(f"Entries skipped (duplicates): {skipped_count}"))
        if errors:
            self.stdout.write(self.style.ERROR(f"Errors: {len(errors)}"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"  - {error}"))

    def _get_user(self, options):
        """Get the user from command options."""
        if options.get("user_id"):
            try:
                return User.objects.get(pk=options["user_id"])
            except User.DoesNotExist:
                raise CommandError(f"User with ID {options['user_id']} not found")

        if options.get("user"):
            try:
                return User.objects.get(email=options["user"])
            except User.DoesNotExist:
                raise CommandError(f"User with email {options['user']} not found")

        return None

    def _load_categories(self):
        """Load categories and create a mapping from JSON field names to Category objects."""
        category_map = {}
        for category in Category.objects.all():
            category_map[category.slug.lower()] = category
        return category_map

    def _process_entry(self, entry_data, user, category_map, dry_run, skip_duplicates):
        """Process a single entry from the JSON data."""
        # Parse date
        date_str = entry_data.get("date")
        if not date_str:
            raise ValueError("Entry missing 'date' field")

        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str}")

        # Check for duplicates
        if skip_duplicates and user and not dry_run:
            existing = JournalEntry.objects.filter(user=user, entry_date=entry_date).first()
            if existing:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping {date_str}: Entry already exists")
                )
                return "skipped"

        # Build the journal body from available sections
        body_parts = []
        categories_to_add = []

        # Map JSON fields to categories
        field_category_map = {
            "faith": "faith",
            "health": "health",
            "family": "family",
            "work": "work",
        }

        for field, category_slug in field_category_map.items():
            content = entry_data.get(field)
            if content:
                # Add section header and content
                body_parts.append(f"## {field.title()}\n{content}")
                # Add category if it exists
                if category_slug in category_map:
                    categories_to_add.append(category_map[category_slug])

        # Add reflection summary at the end
        reflection = entry_data.get("reflection_summary")
        if reflection:
            body_parts.append(f"## Reflection\n{reflection}")

        if not body_parts:
            raise ValueError("Entry has no content in any field")

        body = "\n\n".join(body_parts)

        # Create title from date
        title = entry_date.strftime("%A, %B %d, %Y")

        # Display what will be created
        self.stdout.write(f"\n  {self.style.SUCCESS('+')} {title}")
        self.stdout.write(f"    Categories: {', '.join(c.name for c in categories_to_add)}")
        self.stdout.write(f"    Body preview: {body[:100]}...")

        if not dry_run and user:
            # Create the journal entry
            entry = JournalEntry.objects.create(
                user=user,
                title=title,
                body=body,
                entry_date=entry_date,
            )
            # Add categories
            entry.categories.set(categories_to_add)

        return "created"
