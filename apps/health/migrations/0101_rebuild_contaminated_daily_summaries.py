# ==============================================================================
# Data migration: rebuild DailyHealthSummary rows corrupted by the weight-contamination
# incident (2026-07-12).
#
# DailyHealthSummary.weight is a persisted rollup that picks the day's latest WeightEntry
# (daily_summary_builder). While the contaminated "in"-unit rows existed, the rollup
# captured weight=51.0 and derived fat_mass = 51 * body_fat% = 18.77 etc. Migration 0100
# soft-deleted the contaminated WeightEntry rows and re-homed them as BodyCompositionEntry,
# but the already-persisted DailyHealthSummary rows still hold the bad values — so any
# surface that reads the rollup (Body Intelligence fat/lean cards, HealthCommandCenter,
# HealthIntelligence) stays wrong until the rollup is rebuilt.
#
# This migration rebuilds the rollup (idempotent update_or_create) for exactly the users
# who had contaminated rows, over the affected date window through today. Best-effort:
# any failure is logged and skipped so a deploy can never be blocked — the nightly rollup
# is the backstop. No-op on clean databases (no contaminated rows → nothing to rebuild).
#
# Weight itself is already correct everywhere now (the readers use the canonical Weight
# domain); this repairs the body-composition rollup so fat/lean/quality are correct too.
# ==============================================================================
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


_WEIGHT_UNITS = ("lb", "kg")


def rebuild(apps, schema_editor):
    # Identify users whose weight was contaminated (rows migration 0100 soft-deleted).
    WeightEntry = apps.get_model("health", "WeightEntry")
    contaminated = (
        WeightEntry.objects.filter(status="deleted")
        .exclude(unit__in=_WEIGHT_UNITS)
        .values("user_id", "recorded_at")
    )

    # Map user → earliest contaminated date.
    earliest = {}
    for row in contaminated:
        uid = row["user_id"]
        d = row["recorded_at"].date()
        if uid not in earliest or d < earliest[uid]:
            earliest[uid] = d

    if not earliest:
        return  # clean DB — nothing to repair

    # Rebuild via the real builder (it reads the now-clean WeightEntry rows). Imported
    # lazily and guarded so a builder/import problem can never block the deploy.
    try:
        from django.contrib.auth import get_user_model
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
    except Exception as exc:  # pragma: no cover
        print(f"  [rebuild_dhs] builder unavailable ({exc}); nightly rollup will heal")
        return

    User = get_user_model()
    builder = DailyHealthSummaryBuilder()
    today = timezone.now().date()
    rebuilt_users = 0

    for uid, start in earliest.items():
        try:
            user = User.objects.filter(pk=uid).first()
            if user is None:
                continue
            # A small back-buffer so any delta window that looked back at bad weight is
            # recomputed; end at today.
            window_start = start - timedelta(days=3)
            builder.build_range(user, window_start, today)
            rebuilt_users += 1
        except Exception as exc:  # pragma: no cover
            print(f"  [rebuild_dhs] user={uid} rebuild failed ({exc}); nightly rollup will heal")

    if rebuilt_users:
        print(f"  [rebuild_dhs] rebuilt DailyHealthSummary for {rebuilt_users} affected user(s)")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0100_decontaminate_weight_domain"),
    ]

    operations = [
        migrations.RunPython(rebuild, noop_reverse),
    ]
