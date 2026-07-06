"""Fix future-dated weigh-ins created by the HealthKit noon-default bug.

Body-composition sync (weight / body_fat / lean_body_mass) stored `recorded_at` at
LOCAL NOON from a date-only value, discarding the real HealthKit sample time. A morning
weigh-in synced before noon therefore landed in the FUTURE, which breaks temporal
integrity and makes the assistant refuse to answer today's weight.

The true sample time is not recoverable server-side (it was discarded on ingest), so we
do NOT fabricate one. We only correct rows that are unambiguously wrong — recorded_at in
the FUTURE — by resetting them to the row's real `created_at` (the moment WLJ actually
received the sample, always in the past, ~the sync time). The exact sample time then
self-heals on the next HealthKit re-sync (the ingest fix updates recorded_at from the
real sample). Reverse is a deliberate no-op — we never re-future-date a row.
"""
from django.db import migrations


def fix_future_dated(apps, schema_editor):
    WeightEntry = apps.get_model("health", "WeightEntry")
    from django.utils import timezone
    now = timezone.now()
    fixed = 0
    for w in WeightEntry.objects.filter(recorded_at__gt=now).only(
        "id", "recorded_at", "created_at"
    ):
        created = getattr(w, "created_at", None)
        if created and created <= now:
            w.recorded_at = created
            w.save(update_fields=["recorded_at"])
            fixed += 1
    if fixed:
        print(f"  fixed {fixed} future-dated WeightEntry row(s) → created_at")


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0097_reclassify_mistagged_supplements"),
    ]

    operations = [
        migrations.RunPython(fix_future_dated, migrations.RunPython.noop),
    ]
