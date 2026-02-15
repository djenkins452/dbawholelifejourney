"""
DNE — Delivery & Notification Engine Models.

DeliveredNotification tracks every intelligence notification attempt
(sent, skipped, or failed) with deduplication and throttling metadata.
"""

import hashlib

from django.conf import settings
from django.db import models


class DeliveredNotification(models.Model):
    """
    Tracks intelligence notifications delivered (or skipped) by DNE.

    One record per (user, channel, source object) delivery attempt.
    Used for deduplication, throttling, and audit.
    """

    CHANNEL_INAPP = "in_app"
    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_CHOICES = [
        (CHANNEL_INAPP, "In-App"),
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_FAILED, "Failed"),
    ]

    ENGINE_CHOICES = [
        ("PGE", "Proactive Guidance Engine"),
        ("DBE", "Daily Briefing Engine"),
        ("WIRE", "Weekly Intelligence Report Engine"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delivered_notifications",
    )
    source_engine = models.CharField(
        max_length=10,
        choices=ENGINE_CHOICES,
        help_text="Which engine produced the intelligence output.",
    )
    source_object_type = models.CharField(
        max_length=100,
        help_text="Model name of source object (e.g., GuidanceItem).",
    )
    source_object_id = models.IntegerField(
        help_text="PK of the source object.",
    )

    channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    action_url = models.CharField(max_length=500, blank=True, default="")

    delivered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
    )
    skip_reason = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Why delivery was skipped (quiet hours, throttle, dedupe, etc.).",
    )

    dedupe_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hash for deduplication.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra delivery metadata (notification_id, error details, etc.).",
    )

    class Meta:
        app_label = "core"
        db_table = "core_delivered_notification"
        ordering = ["-delivered_at"]
        verbose_name = "Delivered Notification"
        verbose_name_plural = "Delivered Notifications"
        indexes = [
            models.Index(
                fields=["user", "delivered_at"],
                name="idx_dne_user_delivered",
            ),
            models.Index(
                fields=["user", "channel", "delivered_at"],
                name="idx_dne_user_chan_delivered",
            ),
        ]

    def __str__(self):
        return f"{self.source_engine}→{self.channel} [{self.status}] {self.title[:50]}"

    @staticmethod
    def compute_dedupe_hash(user_id, channel, source_engine, source_object_type,
                            source_object_id):
        """
        Compute SHA-256 deduplication hash.

        Keyed on (user, channel, engine, object) — ensures we deliver
        each intelligence item at most once per channel.
        """
        raw = f"{user_id}:{channel}:{source_engine}:{source_object_type}:{source_object_id}"
        return hashlib.sha256(raw.encode()).hexdigest()
