# ==============================================================================
# File: apps/finance/migrations/0048_reclassify_roles_safely.py
# Description: Realign persisted economic roles — rehearsed first, gated on apply.
# ==============================================================================
"""Bring the persisted `economic_role` column back in line with the classifier.

Spending measures classify LIVE, so they were never wrong. The persisted column is a
different thing: it bounds the ranked-spend read and drives the review queue, and it had
drifted 3,785 rows behind the classifier that wrote it.

Two passes. The first writes nothing and produces the impact report — which roles become
which, how many rows, how much money moves with each. The second applies only the
transitions whose direction cannot increase what a person appears to have spent
(`SAFE_BACKFILL_TARGETS`); anything that would move a row INTO `purchase`, `income` or a
refund is counted, reported and left exactly as it was. A deploy does not get to quietly
raise someone's spending.

The report is published to the cache so the audit endpoint can read it without
reclassifying anything on a request path.

Not atomic: this walks every transaction, and holding one transaction open across all of
them would lock the table for the length of a deploy.
"""
from django.db import migrations


def reclassify(apps, schema_editor):
    from apps.finance.services.finance_calc import backfill as B

    try:
        report = B.rehearse_and_apply(commit=True)
    except Exception:
        import logging
        logging.getLogger(__name__).error(
            "Role reclassification failed; persisted roles are unchanged and the "
            "nightly reconciliation sweep will report the drift.", exc_info=True)
        return
    B.publish_rehearsal(report)


def noop_reverse(apps, schema_editor):
    """Nothing to undo: the roles it writes are what the current classifier says, and
    restoring older ones would reinstate the defect this corrects."""


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("finance", "0047_run_recurring_detection"),
    ]

    operations = [
        migrations.RunPython(reclassify, noop_reverse),
    ]
