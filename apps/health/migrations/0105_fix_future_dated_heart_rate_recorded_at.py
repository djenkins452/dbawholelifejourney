"""Fix future-dated heart-rate rows created by the HealthKit noon-default bug.

Heart-rate sync stored ``recorded_at`` at LOCAL NOON from a date-only daily aggregate,
discarding (or never reading) the real HealthKit sample time. A resting/average HR synced
before noon therefore landed in the FUTURE — which is impossible for a measured record and
surfaced on the Health Sync screen as "Newest data · Today · 12:00 PM" at 6 AM.

This mirrors the weight repair in migration 0098. The true sample time is not recoverable
server-side (it was discarded on ingest), so we do NOT fabricate one. We only correct rows
that are unambiguously wrong — ``recorded_at`` in the FUTURE — by resetting them to the
row's real ``created_at`` (the moment WLJ actually received the sample, always in the past,
≈ the sync time). The exact sample time then self-heals on the next HealthKit re-sync
(the ingest fix now stores the real sample instant). Reverse is a deliberate no-op — we
never re-future-date a row.
"""
from django.db import migrations


def fix_future_dated(apps, schema_editor):
    HeartRateEntry = apps.get_model("health", "HeartRateEntry")
    from django.utils import timezone
    now = timezone.now()
    fixed = 0
    for hr in HeartRateEntry.objects.filter(recorded_at__gt=now).only(
        "id", "recorded_at", "created_at"
    ):
        created = getattr(hr, "created_at", None)
        if created and created <= now:
            hr.recorded_at = created
            hr.save(update_fields=["recorded_at"])
            fixed += 1
    if fixed:
        print(f"  fixed {fixed} future-dated HeartRateEntry row(s) → created_at")


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0104_fooditem_net_content_fooditem_net_content_unit"),
    ]

    operations = [
        migrations.RunPython(fix_future_dated, migrations.RunPython.noop),
    ]
