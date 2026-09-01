# ==============================================================================
# File: apps/finance/migrations/0047_run_recurring_detection.py
# Description: Ask the detector to look, once, at history it has never been shown.
# ==============================================================================
"""Run recurring detection over existing history.

The detector, the model and the nightly sweep all shipped over the last two days. The
sweep proposes candidates from that point on — but a person who has been using WLJ for
two years should not have to wait for tomorrow's cron to be told about the mortgage it
has been watching all along. This runs it once, for everyone, over what is already
there.

It CONFIRMS NOTHING. Every row it writes is a candidate awaiting review, and `persist`
refuses to overwrite a decision anybody has already made — so running this twice, or
running it after the sweep has already run, changes nothing.

Deliberately not `atomic`: this walks every user's transaction history, and holding one
transaction open across all of it would lock the table for the length of a deploy.
"""
from django.db import migrations


def run_detection(apps, schema_editor):
    # Real model classes, not the historical ones: the detector reads properties and
    # managers that a migration-frozen model does not carry.
    from django.contrib.auth import get_user_model

    from apps.finance.models import Transaction
    from apps.finance.services.finance_calc import recurring as REC

    User = get_user_model()
    user_ids = (Transaction.objects.values_list("user_id", flat=True)
                .distinct().order_by())
    for user in User.objects.filter(id__in=list(user_ids)).iterator():
        try:
            REC.persist(user, REC.detect(user), commit=True)
        except Exception:
            # One person's odd history must not stop the deploy for everybody else.
            # The nightly sweep will try them again tomorrow.
            import logging
            logging.getLogger(__name__).error(
                "Initial recurring detection failed for user %s", user.pk,
                exc_info=True)


def noop_reverse(apps, schema_editor):
    """Nothing to undo. The candidates it writes are reviewable and deletable, and
    removing them on a rollback would throw away decisions made since."""


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("finance", "0046_payoffscenario_and_more"),
    ]

    operations = [
        migrations.RunPython(run_detection, noop_reverse),
    ]
