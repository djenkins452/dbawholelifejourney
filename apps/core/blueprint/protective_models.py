"""
Phase 5 — Protective Action Engine: Models.

Advisory-only protective recommendations, alerts, and audit logs.
No auto-execution of schedule/commitment changes.

Models:
    - ProtectiveRecommendation: User-facing advisory recommendation
    - ProtectiveAlert: Scheduled deadline/capacity alert
    - ProtectiveActionLog: Immutable audit trail

Project: Whole Life Journey
Path: apps/core/blueprint/protective_models.py
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# ProtectiveRecommendation
# ---------------------------------------------------------------------------

class ProtectiveRecommendation(models.Model):
    """
    User-facing protective recommendation generated when risk thresholds
    are crossed. Advisory only — never auto-modifies schedule/commitments.

    Recommendations are append-only by default. If a new recommendation of
    the same type for the same related object is created within 12 hours,
    the older one is marked 'expired' (never deleted).
    """

    # Recommendation types
    TYPE_TIME_BLOCK = 'TIME_BLOCK_SUGGESTION'
    TYPE_RENEGOTIATION = 'EARLY_RENEGOTIATION_PROMPT'
    TYPE_CAPACITY_WARNING = 'CAPACITY_WARNING'
    TYPE_FOCUS_PLAN = 'DEADLINE_FOCUS_PLAN'

    TYPE_CHOICES = [
        (TYPE_TIME_BLOCK, 'Time Block Suggestion'),
        (TYPE_RENEGOTIATION, 'Early Renegotiation Prompt'),
        (TYPE_CAPACITY_WARNING, 'Capacity Warning'),
        (TYPE_FOCUS_PLAN, 'Deadline Focus Plan'),
    ]

    # Status lifecycle
    STATUS_ACTIVE = 'active'
    STATUS_DISMISSED = 'dismissed'
    STATUS_ACCEPTED = 'accepted'
    STATUS_EXECUTED = 'executed_elsewhere'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_DISMISSED, 'Dismissed'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_EXECUTED, 'Executed Elsewhere'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='protective_recommendations',
    )

    recommendation_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
    )

    title = models.CharField(
        max_length=200,
        help_text="Short user-facing title (human language)",
    )

    message = models.TextField(
        help_text="User-facing message (human language, no jargon)",
    )

    call_to_action = models.JSONField(
        default=dict,
        blank=True,
        help_text="Options A/B/C with text and action_key",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )

    priority = models.PositiveSmallIntegerField(
        default=50,
        help_text="Higher = more urgent (0-100)",
    )

    # Related object (generic FK via type + id)
    related_object_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Model name of the related object (e.g. 'Commitment')",
    )
    related_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # Risk window
    risk_window_start = models.DateTimeField(
        null=True, blank=True,
        help_text="Start of the risk window this recommendation covers",
    )
    risk_window_end = models.DateTimeField(
        null=True, blank=True,
        help_text="End of the risk window this recommendation covers",
    )

    # Dismissal tracking
    dismissal_reason = models.CharField(
        max_length=30,
        blank=True,
        help_text="Why dismissed: not_relevant, bad_timing, already_handled",
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw scores/inputs for audit (CPI, density, breach prob, etc.)",
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status', 'created_at']),
            models.Index(fields=['user', 'recommendation_type', '-created_at']),
        ]
        verbose_name = "Protective Recommendation"
        verbose_name_plural = "Protective Recommendations"

    def __str__(self):
        return (
            f"ProtectiveRecommendation user={self.user_id} "
            f"type={self.recommendation_type} status={self.status}"
        )

    @classmethod
    def active_for_user(cls, user, limit=10):
        """Get active recommendations for a user, sorted by priority desc."""
        return cls.objects.filter(
            user=user, status=cls.STATUS_ACTIVE,
        ).order_by('-priority', '-created_at')[:limit]


# ---------------------------------------------------------------------------
# ProtectiveAlert
# ---------------------------------------------------------------------------

class ProtectiveAlert(models.Model):
    """
    Scheduled alert for deadline/capacity notifications.

    Delivered via DNE with throttle respect. If a deadline moves
    (renegotiation), pending alerts for the old deadline are cancelled
    and new ones scheduled.
    """

    # Alert types
    TYPE_DEADLINE_24H = 'DEADLINE_24H'
    TYPE_DEADLINE_4H = 'DEADLINE_4H'
    TYPE_DEADLINE_1H = 'DEADLINE_1H'
    TYPE_CAPACITY = 'CAPACITY'
    TYPE_COLLISION = 'COLLISION'

    TYPE_CHOICES = [
        (TYPE_DEADLINE_24H, 'Deadline 24h'),
        (TYPE_DEADLINE_4H, 'Deadline 4h'),
        (TYPE_DEADLINE_1H, 'Deadline 1h'),
        (TYPE_CAPACITY, 'Capacity'),
        (TYPE_COLLISION, 'Collision'),
    ]

    # Delivery status
    DELIVERY_PENDING = 'pending'
    DELIVERY_DELIVERED = 'delivered'
    DELIVERY_SUPPRESSED = 'suppressed_by_throttle'
    DELIVERY_CANCELLED = 'cancelled'

    DELIVERY_CHOICES = [
        (DELIVERY_PENDING, 'Pending'),
        (DELIVERY_DELIVERED, 'Delivered'),
        (DELIVERY_SUPPRESSED, 'Suppressed by Throttle'),
        (DELIVERY_CANCELLED, 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='protective_alerts',
    )

    alert_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
    )

    message = models.TextField(
        help_text="Human language alert message",
    )

    call_to_action = models.JSONField(
        default=dict,
        blank=True,
        help_text="CTA options for user input when required",
    )

    scheduled_for = models.DateTimeField(
        help_text="When this alert should be delivered",
    )

    delivered_at = models.DateTimeField(
        null=True, blank=True,
    )

    delivery_status = models.CharField(
        max_length=25,
        choices=DELIVERY_CHOICES,
        default=DELIVERY_PENDING,
    )

    # Related object
    related_object_type = models.CharField(
        max_length=50,
        blank=True,
    )
    related_object_id = models.PositiveIntegerField(
        null=True, blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw metrics + throttle info for audit",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['scheduled_for']
        indexes = [
            models.Index(fields=['user', 'scheduled_for', 'delivery_status']),
            models.Index(fields=['user', 'related_object_type', 'related_object_id']),
        ]
        verbose_name = "Protective Alert"
        verbose_name_plural = "Protective Alerts"

    def __str__(self):
        return (
            f"ProtectiveAlert user={self.user_id} "
            f"type={self.alert_type} status={self.delivery_status} "
            f"for={self.scheduled_for}"
        )

    @classmethod
    def pending_due(cls, now=None):
        """Get all pending alerts that are due for delivery."""
        if now is None:
            now = timezone.now()
        return cls.objects.filter(
            delivery_status=cls.DELIVERY_PENDING,
            scheduled_for__lte=now,
        ).select_related('user')

    @classmethod
    def pending_for_object(cls, user, object_type, object_id):
        """Get pending alerts for a specific related object."""
        return cls.objects.filter(
            user=user,
            related_object_type=object_type,
            related_object_id=object_id,
            delivery_status=cls.DELIVERY_PENDING,
        )


# ---------------------------------------------------------------------------
# ProtectiveActionLog (audit trail)
# ---------------------------------------------------------------------------

class ProtectiveActionLog(models.Model):
    """
    Immutable audit trail for all protective engine actions.

    Every recommendation, alert, dismissal, and automatic decision
    is logged here for observability and compliance.
    """

    # Event types
    EVENT_CREATED_RECOMMENDATION = 'CREATED_RECOMMENDATION'
    EVENT_DISMISSED = 'DISMISSED'
    EVENT_ACCEPTED = 'ACCEPTED'
    EVENT_ALERT_DELIVERED = 'ALERT_DELIVERED'
    EVENT_ALERT_SUPPRESSED = 'ALERT_SUPPRESSED'
    EVENT_AUTO_DECISION = 'AUTO_DECISION_MADE'
    EVENT_ALERT_CANCELLED = 'ALERT_CANCELLED'
    EVENT_RECOMMENDATION_EXPIRED = 'RECOMMENDATION_EXPIRED'

    EVENT_CHOICES = [
        (EVENT_CREATED_RECOMMENDATION, 'Created Recommendation'),
        (EVENT_DISMISSED, 'Dismissed'),
        (EVENT_ACCEPTED, 'Accepted'),
        (EVENT_ALERT_DELIVERED, 'Alert Delivered'),
        (EVENT_ALERT_SUPPRESSED, 'Alert Suppressed'),
        (EVENT_AUTO_DECISION, 'Auto Decision Made'),
        (EVENT_ALERT_CANCELLED, 'Alert Cancelled'),
        (EVENT_RECOMMENDATION_EXPIRED, 'Recommendation Expired'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='protective_action_logs',
    )

    event_type = models.CharField(
        max_length=30,
        choices=EVENT_CHOICES,
    )

    object_type = models.CharField(
        max_length=50,
        blank=True,
    )
    object_id = models.PositiveIntegerField(
        null=True, blank=True,
    )

    timestamp = models.DateTimeField(default=timezone.now)

    rationale = models.TextField(
        blank=True,
        help_text="Human-readable reason for this action",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['event_type', '-timestamp']),
        ]
        verbose_name = "Protective Action Log"
        verbose_name_plural = "Protective Action Logs"

    def __str__(self):
        return (
            f"ProtectiveActionLog user={self.user_id} "
            f"event={self.event_type} at {self.timestamp}"
        )
