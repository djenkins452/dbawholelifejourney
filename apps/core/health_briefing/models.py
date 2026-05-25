"""
HealthBriefing persistence — snapshot model.

A single concrete model that records the exact ``HealthBriefing`` payload
the composer produced for a user at a point in time. The snapshot is the
backbone of the Phase 0 observability commitment: every CoS turn that
consumed a briefing can be replayed forensically by retrieving the
snapshot keyed by ``briefing_id`` and re-rendering the inputs the
composer used.

Lives in ``apps.core.health_briefing.models`` but is registered to the
``apps.core`` app (via re-export in ``apps/core/models.py``), so the
migration lands in ``apps/core/migrations/`` and the snapshot table is
created in the ``core`` namespace. This avoids adding a new entry to
``INSTALLED_APPS`` (a Bible Journey collision risk).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class HealthBriefingSnapshot(models.Model):
    """
    Immutable record of one composed HealthBriefing payload.

    The composer writes a row on every successful composition. CoS turns
    reference the snapshot by ``briefing_id`` so we can always answer
    "what did Beth see when she said that?".

    Field rules:

    * ``briefing_id`` is the SHA-256 from
      ``apps.core.health_briefing.contract.compute_briefing_id`` —
      deterministic over (user, generated_at, composer_version,
      evidence_hash). Unique; lookups go through this column.
    * ``payload`` is the full ``HealthBriefing`` serialized to a dict
      (enums collapse to strings, datetimes to ISO-8601 with offset).
      No raw domain rows (per Phase 0 audit rule).
    * ``expires_at`` is set by the composer to ``generated_at +
      ttl_seconds`` (default 1800s / 30 min). Snapshots remain queryable
      after expiry; the field is for cleanup tooling.
    """

    briefing_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 of (user, generated_at, composer_version, evidence_hash).",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="health_briefing_snapshots",
    )
    generated_at = models.DateTimeField(
        help_text="When the composer produced this briefing (UTC).",
    )
    composer_version = models.CharField(
        max_length=20,
        help_text="Semver string of the composer that produced this snapshot.",
    )
    payload = models.JSONField(
        help_text="Full HealthBriefing serialized to dict; never includes raw rows.",
    )
    expires_at = models.DateTimeField(
        help_text="generated_at + ttl_seconds. Snapshots remain queryable past this.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        verbose_name = "health briefing snapshot"
        verbose_name_plural = "health briefing snapshots"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["user", "-generated_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"HealthBriefingSnapshot({self.briefing_id[:12]}… user={self.user_id})"

    @property
    def is_expired(self) -> bool:
        """True when ``expires_at`` is in the past."""
        return timezone.now() > self.expires_at
