"""
Management command to clean up medical data for a user.

Usage:
    python manage.py cleanup_medical_data <email> --confirm
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.medical.models import (
    ImportBatch,
    LabPanel,
    LabResult,
    MedicalAuditLog,
    MedicalDocument,
)
from apps.users.models import User


class Command(BaseCommand):
    help = "Remove all medical lab data (documents, batches, results, panels) for a user"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="User email")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually perform the cleanup (without this flag, dry run only)",
        )

    def handle(self, *args, **options):
        email = options["email"]
        confirm = options["confirm"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(f"User not found: {email}")
            return

        # Count everything (including soft-deleted via all_objects)
        docs = MedicalDocument.all_objects.filter(user=user)
        batches = ImportBatch.all_objects.filter(user=user)
        results = LabResult.all_objects.filter(user=user)
        panels = LabPanel.all_objects.filter(user=user)

        self.stdout.write(f"User: {email} (id={user.id})")
        self.stdout.write(f"  Documents (all statuses): {docs.count()}")
        self.stdout.write(f"  Import Batches (all statuses): {batches.count()}")
        self.stdout.write(f"  Lab Results (all statuses): {results.count()}")
        self.stdout.write(f"  Panels (all statuses): {panels.count()}")

        if not confirm:
            self.stdout.write("\nDry run. Use --confirm to actually delete.")
            return

        # Hard delete everything
        error_count = 0
        for batch in batches:
            error_count += batch.error_rows.all().count()
            batch.error_rows.all().delete()

        result_count = results.count()
        results.delete()

        panel_count = panels.count()
        panels.delete()

        batch_count = batches.count()
        batches.delete()

        doc_count = docs.count()
        docs.delete()

        # Audit
        MedicalAuditLog.objects.create(
            user=user,
            action="admin_cleanup",
            detail=(
                f"Admin cleanup: {doc_count} docs, {batch_count} batches, "
                f"{result_count} results, {panel_count} panels, {error_count} error rows"
            ),
        )

        self.stdout.write(self.style.SUCCESS(
            f"Deleted: {doc_count} documents, {batch_count} batches, "
            f"{result_count} results, {panel_count} panels, {error_count} error rows"
        ))
