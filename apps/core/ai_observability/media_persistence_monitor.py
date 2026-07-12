"""
Media & Capture Persistence Health — OPS-8b (Operational Hardening).

"Are uploaded artifacts being safely persisted, and is anything failing?" — for the
two real upload pipelines: **capture audio** and **conversation/multimodal images**.

Evidence-driven scope (investigated 2026-07-12 — the roadmap was half-wrong)
----------------------------------------------------------------------------
* **No "S3 audio bucket" in use.** Production media = **Cloudinary** (the Django
  default `STORAGES["default"]`). The capture-audio S3 path exists but is env-gated
  (`CAPTURE_AUDIO_BUCKET` empty by default) and Cloudinary is checked first. So the
  roadmap's "S3 bucket availability" item is VOID by default → we expose *which store
  is configured* as a deterministic fact, NOT a fabricated S3 probe, and NOT a
  synthetic Cloudinary ping (consistent with OPS-4's no-synthetic-pings discipline).
* **Fabricated signals we deliberately do NOT build** (no backing evidence exists):
  duplicate-detection *rate* (dedup outcome is never recorded queryably —
  `MultimodalArtifact.status='duplicate'` is never written; message idempotency is
  cache-only), orphaned/missing objects (no `storage_ref` linkage — it is never
  populated — and prod is Cloudinary; would need remote listing), and generic
  persistence/verification failures (image writes are fire-and-forget with swallowed
  exceptions; verification exists only on the dormant S3 path).
* **The cleaner this monitor drove:** OPS-8b surfaced that no cleanup task existed
  for expired images — `AssistantMessage.image_data` / `MessageImage.image_data`
  (base64, 72h `image_expires_at`) were never purged, so expired bytes accumulated
  in Postgres forever. The deterministic cleaner
  `apps.ai.tasks.purge_expired_images` (daily Beat, see `apps/ai/image_retention.py`)
  now drains them. This monitor keeps the "expired-but-unpurged" count as the
  steady-state health signal: it should sit near zero, and a **rising** count is
  honest visibility that the cleaner has stalled (a real DB-growth risk). The
  cleaner's own liveness is ALSO tracked by the OPS-1 scheduled-task monitor.

What IS real, deterministic, queryable
--------------------------------------
* **Capture pipeline** (`CaptureEntry`, `TimeStampedModel`): status lifecycle
  (uploading/transcribing/summarizing/ready/failed), `error_message` +
  `get_error_type()`, `updated_at` (→ stuck detection), plus `PendingCapture`
  (`upload_attempts`, `status='abandoned'`, `last_error`).
* **Persisted-object volume** (facts): recent `MultimodalArtifact` ingestion count.
* **Expired-but-never-purged images** (the missing-cleaner signal).

Architecture (matches OPS-2 / OPS-5 / OPS-8a): background-cycle only, cache-guarded,
deterministic aggregate reads, each block degrades to UNAVAILABLE (never raises).
Telemetry-only — no `OpsAnomaly`, no recovery, no new persistence. Request-path safe.

Project: Whole Life Journey
Path: apps/core/ai_observability/media_persistence_monitor.py
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.core.ai_observability.storage_monitor import _overall_status

logger = logging.getLogger(__name__)

_TELEMETRY_CACHE_KEY = "wlj:ops:media_persistence"
_TELEMETRY_TTL = 300  # 5 min

# A capture in a non-terminal (in-progress) state whose last update is older than
# this is stuck (uploads/transcription/summarization complete in minutes).
STUCK_CAPTURE_S = 900  # 15 min
CAPTURE_FAILED_WARN = 3      # failed captures in 24h
CAPTURE_FAILED_CRIT = 15
PENDING_HIGH_RETRY = 3       # PendingCapture.upload_attempts threshold
# Expired image rows never purged (no cleaner exists) — surfaces the growth risk.
EXPIRED_IMG_WARN = 500
EXPIRED_IMG_CRIT = 5000


def _capture_health(now):
    """Capture-audio pipeline health from CaptureEntry + PendingCapture."""
    try:
        from apps.capture.models import CaptureEntry, PendingCapture

        since = now - timedelta(hours=24)
        recent = CaptureEntry.objects.filter(created_at__gte=since)
        # Status breakdown (24h).
        by_status = {}
        for row in recent.values("status"):
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        failed_24h = by_status.get(CaptureEntry.STATUS_FAILED, 0)

        # Top error type among recent failures (bounded, Python aggregation).
        top_error = None
        if failed_24h:
            counts = {}
            for e in recent.filter(status=CaptureEntry.STATUS_FAILED)[:50]:
                t = e.get_error_type()
                counts[t] = counts.get(t, 0) + 1
            if counts:
                top_error = max(counts, key=counts.get)

        # Stuck: in-progress but not advancing (updated_at old).
        in_progress = (CaptureEntry.STATUS_UPLOADING,
                       CaptureEntry.STATUS_TRANSCRIBING,
                       CaptureEntry.STATUS_SUMMARIZING)
        stuck = CaptureEntry.objects.filter(
            status__in=in_progress, updated_at__lt=now - timedelta(seconds=STUCK_CAPTURE_S)
        ).count()

        # Client-side upload health.
        pending_abandoned = PendingCapture.objects.filter(
            status=PendingCapture.STATUS_ABANDONED, created_at__gte=since
        ).count()
        pending_high_retry = PendingCapture.objects.filter(
            upload_attempts__gte=PENDING_HIGH_RETRY, created_at__gte=since
        ).count()

        if stuck >= 3 or failed_24h >= CAPTURE_FAILED_CRIT:
            status = "CRITICAL"
        elif stuck >= 1 or failed_24h >= CAPTURE_FAILED_WARN or pending_abandoned:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "by_status_24h": by_status,
            "failed_24h": failed_24h,
            "top_error_type": top_error,
            "stuck": stuck,
            "pending_abandoned_24h": pending_abandoned,
            "pending_high_retry": pending_high_retry,
        }
    except Exception as e:
        logger.debug("OPS-8b capture probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _image_retention_health(now):
    """Expired conversation-image bytes never purged (no cleanup task exists)."""
    try:
        from apps.ai.models import AssistantMessage, MessageImage

        expired = (
            AssistantMessage.objects.filter(
                image_expires_at__lt=now, image_data__gt=""
            ).count()
            + MessageImage.objects.filter(
                image_expires_at__lt=now, image_data__gt=""
            ).count()
        )
        if expired >= EXPIRED_IMG_CRIT:
            status = "CRITICAL"
        elif expired >= EXPIRED_IMG_WARN:
            status = "WARNING"
        else:
            status = "HEALTHY"
        return {
            "status": status,
            "expired_unpurged": expired,
            "note": (
                "72h image_data is drained daily by apps.ai.tasks.purge_expired_images "
                "(OPS-11 follow-up); a rising count means that cleaner has stalled"
            ),
        }
    except Exception as e:
        logger.debug("OPS-8b image-retention probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _storage_config(now):
    """Which media store is configured (deterministic facts — no synthetic probe)."""
    try:
        from apps.capture.models import MultimodalArtifact

        cloudinary = s3 = False
        try:
            from apps.capture.cloudinary_storage import is_cloudinary_configured
            cloudinary = bool(is_cloudinary_configured())
        except Exception:
            pass
        try:
            from apps.capture.storage import is_storage_configured
            s3 = bool(is_storage_configured())
        except Exception:
            pass
        artifacts_24h = MultimodalArtifact.objects.filter(
            created_at__gte=now - timedelta(hours=24)
        ).count()
        return {
            "status": "HEALTHY",  # informational facts
            "cloudinary_configured": cloudinary,
            "capture_s3_configured": s3,
            "artifacts_ingested_24h": artifacts_24h,
            "note": "prod media = Cloudinary; local-disk fill is covered by OPS-2 storage",
        }
    except Exception as e:
        logger.debug("OPS-8b storage-config probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def get_media_persistence_telemetry(now=None):
    """Build the ``media_persistence`` Ops Wall section (OPS-8b)."""
    cached = cache.get(_TELEMETRY_CACHE_KEY)
    if cached is not None:
        return cached

    now = now or timezone.now()
    capture = _capture_health(now)
    image_retention = _image_retention_health(now)
    storage = _storage_config(now)

    result = {
        "status": _overall_status([capture, image_retention]),
        "capture": capture,
        "image_retention": image_retention,
        "storage_config": storage,
        "measured_at": now.isoformat(),
    }
    cache.set(_TELEMETRY_CACHE_KEY, result, timeout=_TELEMETRY_TTL)
    return result
