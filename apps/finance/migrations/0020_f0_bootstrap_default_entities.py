# ==============================================================================
# File: apps/finance/migrations/0020_f0_bootstrap_default_entities.py
# Description: F0 bootstrap — Personal/Unknown entities + historical account ownership
#              for FINANCE-ACTIVE users only. Creates ZERO attributions.
# ==============================================================================
"""Bootstrap entity truth for users who already use Finance.

Deliberately creates **no `TransactionAttribution` rows**. Every existing transaction stays
unattributed, which is the honest state — manufacturing attributions in a migration would
fabricate truth WLJ never established (Constitution I.1). Attribution begins when a rule or
a person says something.

Finance-active is proven from existing repository truth: a `FinancialAccount`, a
`Transaction`, or a `BankConnection`. Everyone else gets entities lazily through
`finance_entities.ensure_default_entities` on first use, so WLJ does not create rows for
users who never open Finance.

The FIRST assignment for an account reaches back to its earliest known activity so
imported history resolves truthfully; that is the temporal policy, not a shortcut.
"""
from django.db import migrations

DEFAULT_PERSONAL_NAME = "Personal"
UNKNOWN_NAME = "Unknown"


def _normalize(name):
    return " ".join((name or "").split()).casefold()


def bootstrap(apps, schema_editor):
    User = apps.get_model("users", "User")
    FinancialAccount = apps.get_model("finance", "FinancialAccount")
    Transaction = apps.get_model("finance", "Transaction")
    BankConnection = apps.get_model("finance", "BankConnection")
    FinancialEntity = apps.get_model("finance", "FinancialEntity")
    Assignment = apps.get_model("finance", "AccountEntityAssignment")

    active_ids = set()
    for model in (FinancialAccount, Transaction, BankConnection):
        active_ids.update(model.objects.values_list("user_id", flat=True).distinct())
    if not active_ids:
        return

    for user in User.objects.filter(id__in=active_ids).iterator():
        personal = FinancialEntity.objects.filter(
            user_id=user.id, is_default_personal=True, is_active=True, status="active",
        ).first()
        if personal is None:
            personal = FinancialEntity.objects.create(
                user_id=user.id, entity_type="personal", name=DEFAULT_PERSONAL_NAME,
                name_key=_normalize(DEFAULT_PERSONAL_NAME), is_default_personal=True,
                is_active=True, sort_order=0, status="active", created_via="import",
            )
        if not FinancialEntity.objects.filter(
            user_id=user.id, entity_type="unknown", is_active=True, status="active",
        ).exists():
            FinancialEntity.objects.create(
                user_id=user.id, entity_type="unknown", name=UNKNOWN_NAME,
                name_key=_normalize(UNKNOWN_NAME), is_default_personal=False,
                is_active=True, sort_order=99, status="active", created_via="import",
            )

        accounts = FinancialAccount.objects.filter(user_id=user.id, status="active")
        for account in accounts.iterator():
            if Assignment.objects.filter(account_id=account.id).exists():
                continue
            first_txn = (Transaction.objects.filter(account_id=account.id)
                         .order_by("date").values_list("date", flat=True).first())
            effective_from = first_txn or account.created_at.date()
            Assignment.objects.create(
                user_id=user.id, account_id=account.id, entity_id=personal.id,
                effective_from=effective_from, effective_to=None,
                actor="migration",
                reason="F0 bootstrap: existing accounts default to the personal entity.",
                status="active", created_via="import",
            )


def unbootstrap(apps, schema_editor):
    """Remove only what the bootstrap created, and only while nothing depends on it."""
    FinancialEntity = apps.get_model("finance", "FinancialEntity")
    Assignment = apps.get_model("finance", "AccountEntityAssignment")
    Attribution = apps.get_model("finance", "TransactionAttribution")

    Assignment.objects.filter(actor="migration").delete()
    referenced = set(Attribution.objects.values_list("attributed_entity_id", flat=True))
    referenced.update(Attribution.objects.values_list("paid_by_entity_id", flat=True))
    (FinancialEntity.objects
     .filter(created_via="import", entity_type__in=("personal", "unknown"))
     .exclude(id__in=referenced)
     .exclude(account_assignments__isnull=False)
     .delete())


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0019_f0_entity_attribution_truth"),
    ]

    operations = [
        migrations.RunPython(bootstrap, unbootstrap),
    ]
