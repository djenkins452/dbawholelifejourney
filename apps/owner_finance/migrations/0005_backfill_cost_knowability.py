# ==============================================================================
# File: apps/owner_finance/migrations/0005_backfill_cost_knowability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Make historical unpriced spend honest instead of a misleading $0.00
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Backfill `cost_is_known` from the evidence already recorded on each row.

Rows written before this field existed defaulted to `cost_is_known=True`, which would keep
claiming that an unpriced call cost exactly $0.00 — the precise confusion that let ~$4 of
local development spend read as free.

Two deterministic passes, no guessing and **no fabricated prices**:

1. Rows flagged `metadata.missing_pricebook` whose model NOW has an authoritative price-book
   entry are priced from that entry — we genuinely know the cost now, so recording it is more
   truthful than leaving a blank.
2. Rows still without a price entry are marked `cost_is_known=False`. Their tokens remain
   recorded; their cost is reported as UNKNOWN, never as zero.
"""

from decimal import Decimal

from django.db import migrations


def backfill(apps, schema_editor):
    LLMUsageEvent = apps.get_model("owner_finance", "LLMUsageEvent")
    LLMPriceBook = apps.get_model("owner_finance", "LLMPriceBook")

    prices = {}
    for p in LLMPriceBook.objects.filter(is_active=True).order_by("effective_start"):
        prices[p.model_name] = (p.input_cost_per_1m_tokens_usd,
                                p.output_cost_per_1m_tokens_usd)

    priced = unknown = 0
    qs = LLMUsageEvent.objects.filter(metadata__missing_pricebook=True).iterator()
    for ev in qs:
        rate = prices.get(ev.model_name)
        if rate:
            ev.cost_usd = (Decimal(ev.input_tokens) * rate[0] / Decimal("1000000")
                           + Decimal(ev.output_tokens) * rate[1] / Decimal("1000000"))
            ev.cost_is_known = True
            meta = dict(ev.metadata or {})
            meta.pop("missing_pricebook", None)
            meta["cost_backfilled"] = True
            ev.metadata = meta
            ev.save(update_fields=["cost_usd", "cost_is_known", "metadata"])
            priced += 1
        else:
            ev.cost_is_known = False
            ev.save(update_fields=["cost_is_known"])
            unknown += 1
    print(f"  cost knowability backfill: {priced} priced from the price book, "
          f"{unknown} left explicitly UNKNOWN")


def noop(apps, schema_editor):
    """Irreversible by intent — restoring a misleading $0.00 is not a desirable state."""


class Migration(migrations.Migration):

    dependencies = [
        ("owner_finance", "0004_unattributed_traffic_and_cost_knowability"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
