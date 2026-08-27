# ==============================================================================
# File: apps/finance/migrations/0029_dedupe_provider_transactions_and_constrain.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Retire duplicate provider transactions, then make them impossible.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Remove the 2026-08-27 duplicate rows and close the race that created them.

Two concurrent webhook-triggered syncs each read "not present" for the same provider
transaction and both inserted it. The read and the write were never one atomic step and
nothing at the database level forbade the result, so 1,677 exact duplicates landed.

**Nothing is destroyed.** Extras are SOFT-deleted, matching WLJ's convention: the rows
stay readable through `all_objects`, every Finance total already reads through
`SoftDeleteManager`, and the operation is reversible by the backwards migration below.

**Why the predicate is `status='active'` and NOT `deleted_at IS NULL`.**
WLJ has three lifecycle states — active / archived / deleted.
`SoftDeleteManager.get_queryset()` filters `status="active"` and never reads
`deleted_at`; `deleted_at` is purge metadata for the 30-day grace window.
`archive()` sets `status="archived"` with `deleted_at=None`, so an ARCHIVED row has
`deleted_at IS NULL` while being invisible to every Finance query. A
`deleted_at IS NULL` predicate would therefore be STRICTER than the manager: archived
rows would contend for uniqueness and block Plaid from re-delivering a transaction the
user had archived. `status='active'` is the manager's own predicate, exactly.

**Canonical survivor rule:** within each `(account, plaid_transaction_id)` group of
active rows, keep the one with the earliest `created_at`; ties break on the lowest
`pk`. The survivor is therefore the row the first sync wrote — the one any later
processing would already have referenced — and the rule is total, so it cannot leave
two survivors or none.
"""
from django.db import migrations, models
from django.db.models import Count, Min, Q


def retire_duplicate_provider_transactions(apps, schema_editor):
    Transaction = apps.get_model("finance", "Transaction")

    # `apps.get_model` returns the historical model with a PLAIN manager, so this sees
    # soft-deleted rows too — which is what we want: only ACTIVE rows contend for the
    # partial constraint, and an already-retired row must not be retired twice.
    active = Transaction.objects.filter(status="active").exclude(plaid_transaction_id="")

    contended = (active.values("account_id", "plaid_transaction_id")
                 .annotate(n=Count("id"))
                 .filter(n__gt=1))

    retired = 0
    for group in contended:
        rows = list(active.filter(
            account_id=group["account_id"],
            plaid_transaction_id=group["plaid_transaction_id"],
        ).order_by("created_at", "id").values_list("id", flat=True))
        survivor, extras = rows[0], rows[1:]
        if not extras:
            continue
        retired += Transaction.objects.filter(id__in=extras).update(
            status="deleted",
            deleted_at=models.functions.Now(),
        )

    if retired:
        print(f"\n    Retired {retired} duplicate provider transaction(s).")


def restore_retired_duplicates(apps, schema_editor):
    """Rollback path.

    Deliberately a NO-OP on the data. Reversing the constraint is what makes the
    schema rollback safe; blindly reactivating every soft-deleted transaction would
    also resurrect rows a USER deleted on purpose, which this migration never touched.
    The retired rows remain in the table and can be reactivated selectively by pk if
    that is ever genuinely wanted.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0028_bankconnection_last_webhook_rejected_at_and_more"),
    ]

    operations = [
        # Order matters: the constraint cannot be created while duplicates are active.
        migrations.RunPython(
            retire_duplicate_provider_transactions,
            restore_retired_duplicates,
        ),
        migrations.AddConstraint(
            model_name="transaction",
            constraint=models.UniqueConstraint(
                fields=["account", "plaid_transaction_id"],
                condition=Q(status="active") & ~Q(plaid_transaction_id=""),
                name="uq_txn_provider_id_per_active_account",
            ),
        ),
    ]
