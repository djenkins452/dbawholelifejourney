# ==============================================================================
# File: apps/ai/image_retention.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic cleanup of expired chat-image bytes (72h retention)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-12
# ==============================================================================
"""
Expired chat-image cleanup — the missing cleaner surfaced by OPS-8b.

Policy (``docs/WLJ_SECURITY_PRIVACY_RETENTION.md``): chat images are retained
for **72 hours**, then expire. Every image row is stamped with
``image_expires_at = created_at + 72h``, but until now **no task ever purged the
bytes** — expired base64 blobs accumulated in Postgres forever. OPS-8b's
``media_persistence`` monitor exposed the growth (``expired_unpurged``); this is
the deterministic Layer-1 hygiene ACTION that drains it.

Two producers of image bytes (mirrors ``media_persistence_monitor``):

* ``AssistantMessage`` — a conversation turn that ALSO carries text/role. The
  message row is durable conversation history, so we purge ONLY the image bytes
  (``image_data`` / ``image_mime_type``) and clear ``image_expires_at`` to mark
  the row unambiguously purged. The message itself is kept.
* ``MessageImage`` — a dedicated attachment row (the image IS the record). Once
  expired the attachment is gone by policy, so the whole row is deleted; that
  reclaims both the bytes and the row.

Guarantees
----------
* **Idempotent** — the filters only match rows that still hold expired bytes, so
  a second run in the same window is a no-op (0 purged, 0 deleted).
* **Deterministic** — a single bulk ``UPDATE`` + a single bulk ``DELETE``; no
  per-row Python, no ordering dependence, no external state.
* **Observable / audited** — returns a counts dict, logs an INFO line with the
  same counts, and (via Celery Beat registration) is tracked by the OPS-1
  scheduled-task monitor, which records a ``ScheduledTaskRun`` (success/error)
  and fires ``MISSED_RUN`` if the cleaner ever stops running. A cleaner failure
  is ALSO caught independently by OPS-8b's ``expired_unpurged`` growth.
* **Request-path safe** — background-cycle only (never called from a view).

Project: Whole Life Journey
Path: apps/ai/image_retention.py
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def purge_expired_images(now=None):
    """
    Purge expired chat-image bytes past the 72h retention window.

    Args:
        now: optional timezone-aware cutoff (defaults to ``timezone.now()``).
             Injectable for deterministic tests.

    Returns:
        dict: {
            "messages_purged": int,   # AssistantMessage rows whose bytes were cleared
            "images_deleted": int,    # MessageImage rows deleted
            "cutoff": iso8601 str,
        }
    """
    from apps.ai.models import AssistantMessage, MessageImage

    now = now or timezone.now()

    # AssistantMessage: keep the conversation turn, strip only the expired bytes.
    # image_data__gt="" ensures we never touch already-purged rows (idempotent).
    messages_purged = (
        AssistantMessage.objects.filter(
            image_expires_at__lt=now, image_data__gt=""
        ).update(image_data="", image_mime_type="", image_expires_at=None)
    )

    # MessageImage: the attachment IS the record — delete expired rows outright.
    images_deleted, _ = (
        MessageImage.objects.filter(image_expires_at__lt=now).delete()
    )

    result = {
        "messages_purged": messages_purged,
        "images_deleted": images_deleted,
        "cutoff": now.isoformat(),
    }
    logger.info(
        "Expired chat-image cleanup: purged %d message-image blobs, "
        "deleted %d attachment rows (cutoff=%s)",
        messages_purged, images_deleted, result["cutoff"],
    )
    return result
