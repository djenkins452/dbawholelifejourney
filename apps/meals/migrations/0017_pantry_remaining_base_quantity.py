# Foundation 2 — Pantry Container Truth refinement: store Remaining Truth as an EXACT
# base quantity (e.g. 312 ml), never a container fraction (0.53 bottles). Container
# fractions/percentages are derived at presentation.
#
# This converts any pantry row written under the earlier (fractional-container)
# representation — net_content set but `unit` still the container/piece unit — into the
# base representation: quantity = quantity × net_content, unit = net_content_unit. A
# single reconciling InventoryTransaction is appended so the ledger still folds exactly
# to the new quantity (G4 — reproducible). Rows already in the base unit are untouched.
from decimal import Decimal

from django.db import migrations


def to_base_quantity(apps, schema_editor):
    PantryItem = apps.get_model("meals", "PantryItem")
    InventoryTransaction = apps.get_model("meals", "InventoryTransaction")

    qs = PantryItem.objects.exclude(net_content__isnull=True)
    for item in qs.iterator():
        net = item.net_content
        if not net or net <= 0 or not item.net_content_unit:
            continue
        if item.unit == item.net_content_unit:
            continue  # already stored as an exact base quantity
        old_qty = item.quantity or Decimal("0")
        new_qty = old_qty * net
        delta = new_qty - old_qty
        item.quantity = new_qty
        item.unit = item.net_content_unit
        item.save(update_fields=["quantity", "unit", "updated_at"])
        if delta != 0:
            InventoryTransaction.objects.create(
                pantry_item=item,
                delta_quantity=delta,
                source="manual",
                notes="container-truth: convert remaining to exact base quantity",
            )


def noop_reverse(apps, schema_editor):
    # Not cleanly reversible (the container/base distinction is lost once merged); the
    # base quantity is the canonical truth going forward. Leave data as-is.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("meals", "0016_seed_ingredient_container_truth"),
    ]

    operations = [
        migrations.RunPython(to_base_quantity, noop_reverse),
    ]
