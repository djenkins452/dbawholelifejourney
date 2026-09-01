# ==============================================================================
# File: apps/finance/migrations/0049_align_roles_after_transfer_fix.py
# Description: Realign persisted roles after classifier 1.3.1, and RECORD what it did.
# ==============================================================================
"""Second alignment: classifier 1.3.1 stops a provider-named transfer becoming a purchase.

`0048` aligned the column to 1.3.0. The classifier has moved again — an outflow the
provider labels `TRANSFER_OUT` is now held rather than counted as consumer spending when
the transfer pass never ran — so every persisted row is stale against it once more.

The nightly sweep deliberately does not heal drift, so each classifier bump needs its own
alignment. That is the cost of keeping automatic rewrites off, and it is the right trade:
a mass reclassification is a decision, not a cron job.

Same gate as `0048`: only transitions that cannot raise apparent spending are applied.
Unlike `0048`, the outcome is written to `FinanceAuditLog` as well as the cache — that
run left no durable account of itself because Redis was `circuit_open` at the time.

Not atomic: this walks every transaction.
"""
from django.db import migrations


def align(apps, schema_editor):
    from apps.finance.services.finance_calc import backfill as B

    try:
        report = B.rehearse_and_apply(commit=True)
    except Exception:
        import logging
        logging.getLogger(__name__).error(
            "Role alignment failed; persisted roles are unchanged and the nightly "
            "reconciliation sweep will report the drift.", exc_info=True)
        B.record_rehearsal({"classifier_version": None}, mode="failed", success=False)
        return
    B.record_rehearsal(report, mode="applied")
    B.publish_rehearsal(report)


def noop_reverse(apps, schema_editor):
    """Nothing to undo: these are what the current classifier says, and restoring older
    roles would reinstate the defect this corrects."""


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("finance", "0048_reclassify_roles_safely"),
    ]

    operations = [
        migrations.RunPython(align, noop_reverse),
    ]
