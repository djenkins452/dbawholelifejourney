"""
READ-ONLY diagnostic migration (2026-05-28).

Investigation: dashboard/Beth report "No weight entry in 25 days" while the
weight screen's latest entry is May 3, 2026. The read layer is proven
correct (weight screen, SAE, and the accountability rule all read the same
WeightEntry/recorded_at/status=active query and agree). The proven failing
layer is ingestion (push-only /api/health/ingest/ from the iOS app).

This migration ONLY LOGS evidence to the deploy output so we can confirm
WHY the push stopped — there is no other way to read production data (no
CLI/SSH access; the Procfile runs migrate on every deploy).

STRICTLY READ-ONLY:
  - No rows created, updated, or deleted.
  - No schema changes.
  - Reverse is a no-op.
  - Every section is independently guarded so a missing model/user can
    NEVER fail the deploy.

Targets Danny's account (dannyjenkins71@gmail.com) per project convention.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

TARGET_EMAIL = "dannyjenkins71@gmail.com"
LOG = "[WEIGHT_SYNC_DIAG]"


def _diagnose(apps, schema_editor):
    from django.utils import timezone
    from datetime import timedelta

    User = apps.get_model("users", "User")
    user = None
    try:
        user = User.objects.filter(email=TARGET_EMAIL).first()
    except Exception as e:
        logger.warning("%s user lookup failed: %s", LOG, e)
    if not user:
        logger.warning("%s target user not found (%s) — skipping", LOG, TARGET_EMAIL)
        return

    now = timezone.now()
    cutoff_30d = now - timedelta(days=30)

    # ── WeightEntry: latest, per-source, recency ──
    try:
        WeightEntry = apps.get_model("health", "WeightEntry")
        base = WeightEntry.objects.filter(user=user, status="active")
        total = base.count()
        latest = base.order_by("-recorded_at").first()
        latest_dt = latest.recorded_at if latest else None
        manual = base.filter(source="manual").count()
        apple = base.filter(source="apple_health").count()
        last_apple = (
            base.filter(source="apple_health").order_by("-recorded_at").first()
        )
        last_manual = (
            base.filter(source="manual").order_by("-recorded_at").first()
        )
        after_30d = base.filter(recorded_at__gte=cutoff_30d).count()
        logger.warning(
            "%s WEIGHT total_active=%s latest=%s latest_source=%s "
            "manual=%s apple_health=%s last_apple=%s last_manual=%s "
            "entries_last_30d=%s",
            LOG, total,
            latest_dt.isoformat() if latest_dt else None,
            getattr(latest, "source", None),
            manual, apple,
            last_apple.recorded_at.isoformat() if last_apple else None,
            last_manual.recorded_at.isoformat() if last_manual else None,
            after_30d,
        )
    except Exception as e:
        logger.warning("%s WeightEntry diagnostic failed: %s", LOG, e)

    # ── HealthIngestionRun: recent ingest history ──
    try:
        HealthIngestionRun = apps.get_model("mobile", "HealthIngestionRun")
        runs = list(
            HealthIngestionRun.objects.filter(user=user)
            .order_by("-request_timestamp")[:10]
        )
        logger.warning("%s INGEST_RUNS count_shown=%s", LOG, len(runs))
        for r in runs:
            logger.warning(
                "%s   run ts=%s status=%s received=%s created=%s updated=%s "
                "skipped=%s err=%s",
                LOG,
                getattr(r, "request_timestamp", None),
                getattr(r, "status", None),
                getattr(r, "metrics_received", None),
                getattr(r, "metrics_created", None),
                getattr(r, "metrics_updated", None),
                getattr(r, "metrics_skipped", None),
                (getattr(r, "error_message", "") or "")[:120],
            )
        if not runs:
            logger.warning("%s INGEST_RUNS none — iOS app never POSTed, or all pruned", LOG)
    except Exception as e:
        logger.warning("%s HealthIngestionRun diagnostic failed: %s", LOG, e)

    # ── MobileDevice: is the phone registered/active? ──
    try:
        MobileDevice = apps.get_model("mobile", "MobileDevice")
        for d in MobileDevice.objects.filter(user=user).order_by("-last_seen_at")[:5]:
            logger.warning(
                "%s DEVICE active=%s last_seen=%s push_enabled=%s",
                LOG, getattr(d, "is_active", None),
                getattr(d, "last_seen_at", None),
                getattr(d, "push_enabled", None),
            )
    except Exception as e:
        logger.warning("%s MobileDevice diagnostic failed: %s", LOG, e)

    # ── MobileAuthToken: expired? last used? (likely root cause) ──
    try:
        MobileAuthToken = apps.get_model("mobile", "MobileAuthToken")
        for t in MobileAuthToken.objects.filter(user=user).order_by("-created_at")[:5]:
            expires = getattr(t, "expires_at", None)
            logger.warning(
                "%s TOKEN active=%s expires=%s expired=%s last_used=%s",
                LOG, getattr(t, "is_active", None), expires,
                (expires < now) if expires else None,
                getattr(t, "last_used_at", None),
            )
    except Exception as e:
        logger.warning("%s MobileAuthToken diagnostic failed: %s", LOG, e)

    logger.warning("%s DONE — grep deploy logs for '%s'", LOG, LOG)


def _noop(apps, schema_editor):
    """Reverse is a no-op — this migration only reads + logs."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("mobile", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_diagnose, _noop),
    ]
