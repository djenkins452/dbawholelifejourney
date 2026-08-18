# ==============================================================================
# File: apps/ai/management/commands/seed_personas.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M1 — idempotent, key-based persona registry seeder
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""Seed the persona registry from `apps/ai/fixtures/coaching_styles.json` by KEY.

WHY THIS EXISTS (a real production data bug, not a preference):
`loaddata` addresses rows by PRIMARY KEY. The persona fixture carried hard-coded
pks 1-8 while migration 0015 created the Armed Forces personas with AUTO pks. On a
fresh database migrations run first, so the Armed Forces personas took pks 1-6 - and
a later `load_initial_data` OVERWROTE them with the General personas, silently
destroying the persona a user had selected. Reproduced locally 2026-08-18.

`key` - not pk - is the identity: it is what `UserPreferences.ai_coaching_style`
actually stores, and Contract 1.1 makes it immutable once selectable. Seeding by key
makes the operation idempotent and removes the whole clobber class.

ADMIN EDITS ARE PRESERVED. Personas are admin-editable without a deploy (Contract 1.5),
so this command CREATES missing personas and fills EMPTY fields on existing ones. It
never overwrites authored content. Use --force to re-sync authored fields deliberately.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

# Authored fields: only (re)written on create, or with --force.
AUTHORED = ("name", "description", "icon", "category", "prompt_instructions", "sort_order")
# Structural fields: filled when empty, so a persona gains M1 attributes without
# clobbering anything an administrator has tuned.
FILL_IF_EMPTY = ("voice_attributes", "operational_defaults", "message_templates")


class Command(BaseCommand):
    help = "Idempotently seed/refresh the persona registry by key (never by pk)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Also re-sync authored fields (name/description/instructions/...) "
                 "from the fixture, overwriting admin edits.",
        )

    def handle(self, *args, **options):
        from apps.ai.models import CoachingStyle

        path = Path(__file__).resolve().parents[2] / "fixtures" / "coaching_styles.json"
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"persona fixture not found: {path}"))
            return

        rows = json.loads(path.read_text(encoding="utf-8"))
        created = updated = unchanged = 0

        for row in rows:
            f = row.get("fields") or {}
            key = (f.get("key") or "").strip()
            if not key:
                continue

            existing = CoachingStyle.objects.filter(key=key).first()
            if existing is None:
                CoachingStyle.objects.create(**{k: v for k, v in f.items()})
                created += 1
                continue

            changed = []
            for name in FILL_IF_EMPTY:
                # `f[name]` must be truthy too - filling an empty field with an empty
                # value is a no-op that would make this command report work forever.
                if f.get(name) and not getattr(existing, name, None):
                    setattr(existing, name, f[name])
                    changed.append(name)
            if options["force"]:
                for name in AUTHORED:
                    if name in f and getattr(existing, name, None) != f[name]:
                        setattr(existing, name, f[name])
                        changed.append(name)
            # is_active is authoritative in the fixture ONLY for deliberate retirement
            # (a superseded duplicate key). Never re-activates an admin-disabled persona.
            if f.get("is_active") is False and existing.is_active:
                existing.is_active = False
                changed.append("is_active")

            if changed:
                existing.save(update_fields=sorted(set(changed)) + ["updated_at"])
                updated += 1
            else:
                unchanged += 1

        self.stdout.write(self.style.SUCCESS(
            f"personas: {created} created, {updated} updated, {unchanged} unchanged "
            f"({CoachingStyle.objects.filter(is_active=True).count()} active)"))
