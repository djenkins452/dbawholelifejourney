"""
Mobile App Models

Models for iOS/Android app integration:
- MobileDevice: Registered devices with unique identifiers
- MobileAPIToken: Bearer tokens bound to user + device
- HealthIngestionRun: Audit log for HealthKit data submissions
- MobileTokenExchangeCode: One-time codes for web-to-native auth

Security Design:
- Tokens are hashed (only prefix stored for identification)
- Device IDs stored in iOS Keychain (not on server)
- All ingestion runs logged for audit
- Tokens can be revoked per-device or globally
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def generate_api_token():
    """Generate a secure random API token (64 chars)."""
    return secrets.token_urlsafe(48)


def generate_exchange_code():
    """Generate a one-time exchange code (32 chars)."""
    return secrets.token_urlsafe(24)


class MobileDevice(TimeStampedModel):
    """
    A registered mobile device for a user.

    Each device gets a unique identifier (generated client-side and stored
    in iOS Keychain). This allows:
    - Multiple devices per user
    - Per-device token revocation
    - Device-specific audit trails
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_devices",
    )

    # Device identification
    device_id = models.CharField(
        max_length=128,
        help_text="Unique device identifier (UUID from iOS Keychain)",
    )
    device_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="User-friendly device name (e.g., 'Danny's iPhone')",
    )
    device_model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Device model (e.g., 'iPhone 15 Pro')",
    )
    os_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="OS version (e.g., 'iOS 17.2')",
    )
    app_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="WLJ app version (e.g., '1.0.0')",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Set to False to revoke all tokens for this device",
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last API request from this device",
    )

    # Push notifications (scaffold for future)
    push_token = models.CharField(
        max_length=255,
        blank=True,
        help_text="APNs push notification token",
    )
    push_enabled = models.BooleanField(
        default=False,
        help_text="User has enabled push notifications",
    )

    class Meta:
        verbose_name = "Mobile Device"
        verbose_name_plural = "Mobile Devices"
        unique_together = [["user", "device_id"]]
        indexes = [
            models.Index(fields=["device_id"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        name = self.device_name or self.device_model or "Unknown Device"
        return f"{name} ({self.user.email})"

    def update_last_seen(self):
        """Update last_seen_at timestamp."""
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at", "updated_at"])


class MobileAPIToken(TimeStampedModel):
    """
    Bearer token for mobile API authentication.

    Security:
    - Full token only returned once at creation
    - Only token hash and prefix stored
    - Bound to specific user + device
    - Can be revoked individually or by device
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_tokens",
    )
    device = models.ForeignKey(
        MobileDevice,
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    # Token storage (hash only, prefix for identification)
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hash of the token",
    )
    token_prefix = models.CharField(
        max_length=8,
        help_text="First 8 chars of token for identification",
    )

    # Validity
    is_active = models.BooleanField(
        default=True,
        help_text="Set to False to revoke this token",
    )
    expires_at = models.DateTimeField(
        help_text="Token expiration time",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this token was used",
    )

    # Audit
    created_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address when token was created",
    )

    class Meta:
        verbose_name = "Mobile API Token"
        verbose_name_plural = "Mobile API Tokens"
        indexes = [
            models.Index(fields=["token_hash"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"Token {self.token_prefix}... ({self.user.email}, {status})"

    @classmethod
    def create_token(cls, user, device, expires_days=90, ip_address=None):
        """
        Create a new API token for a user/device.

        Returns tuple: (MobileAPIToken instance, raw_token)
        The raw_token is only available at creation time.
        """
        raw_token = generate_api_token()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        token = cls.objects.create(
            user=user,
            device=device,
            token_hash=token_hash,
            token_prefix=raw_token[:8],
            expires_at=timezone.now() + timedelta(days=expires_days),
            created_ip=ip_address,
        )

        return token, raw_token

    @classmethod
    def validate_token(cls, raw_token):
        """
        Validate a raw token and return the token object if valid.
        Returns None if invalid, expired, or revoked.
        """
        if not raw_token or len(raw_token) < 10:
            return None

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            token = cls.objects.select_related("user", "device").get(
                token_hash=token_hash,
                is_active=True,
                device__is_active=True,
            )

            # Check expiration
            if token.expires_at < timezone.now():
                return None

            # Update last used
            token.last_used_at = timezone.now()
            token.save(update_fields=["last_used_at", "updated_at"])

            # Update device last seen
            token.device.update_last_seen()

            return token

        except cls.DoesNotExist:
            return None

    def revoke(self):
        """Revoke this token."""
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])


class MobileTokenExchangeCode(TimeStampedModel):
    """
    One-time code for exchanging web session for API token.

    Flow:
    1. User logs into WLJ via WKWebView
    2. Web JS calls bridge to request native auth
    3. Django generates one-time code, returns to JS
    4. JS passes code to native app via bridge
    5. Native app exchanges code for API token
    6. Code is consumed and deleted

    Security:
    - Codes expire in 5 minutes
    - Single use only
    - Bound to specific user
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_exchange_codes",
    )

    code = models.CharField(
        max_length=64,
        unique=True,
        default=generate_exchange_code,
    )

    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    # Track what device used the code
    used_by_device_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Device ID that consumed this code",
    )

    class Meta:
        verbose_name = "Token Exchange Code"
        verbose_name_plural = "Token Exchange Codes"
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["user", "is_used"]),
        ]

    def __str__(self):
        status = "used" if self.is_used else "pending"
        return f"Exchange code for {self.user.email} ({status})"

    @classmethod
    def create_code(cls, user, expires_minutes=5):
        """Create a new exchange code for a user."""
        return cls.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(minutes=expires_minutes),
        )

    def consume(self, device_id):
        """
        Mark code as used. Returns True if successful, False if invalid.
        """
        if self.is_used:
            return False
        if self.expires_at < timezone.now():
            return False

        self.is_used = True
        self.used_at = timezone.now()
        self.used_by_device_id = device_id
        self.save(update_fields=["is_used", "used_at", "used_by_device_id", "updated_at"])
        return True


class HealthIngestionRun(TimeStampedModel):
    """
    Audit log for HealthKit data ingestion.

    Every health data submission from the iOS app is logged here for:
    - Compliance auditing
    - Debugging sync issues
    - Rate limiting detection
    - Data integrity verification
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("partial", "Partial Success"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="health_ingestion_runs",
    )
    device = models.ForeignKey(
        MobileDevice,
        on_delete=models.SET_NULL,
        null=True,
        related_name="health_ingestion_runs",
    )
    token = models.ForeignKey(
        MobileAPIToken,
        on_delete=models.SET_NULL,
        null=True,
        related_name="health_ingestion_runs",
    )

    # Request metadata
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    request_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
    )
    request_timestamp = models.DateTimeField(
        default=timezone.now,
        help_text="Client-provided timestamp",
    )
    payload_size_bytes = models.PositiveIntegerField(
        default=0,
        help_text="Size of the request payload",
    )

    # Processing results
    metrics_received = models.PositiveIntegerField(
        default=0,
        help_text="Number of health metrics in request",
    )
    metrics_created = models.PositiveIntegerField(
        default=0,
        help_text="New records created",
    )
    metrics_updated = models.PositiveIntegerField(
        default=0,
        help_text="Existing records updated",
    )
    metrics_skipped = models.PositiveIntegerField(
        default=0,
        help_text="Duplicates or invalid records skipped",
    )

    # Timing
    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error details if failed",
    )
    validation_errors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of validation errors for individual metrics",
    )

    class Meta:
        verbose_name = "Health Ingestion Run"
        verbose_name_plural = "Health Ingestion Runs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"Ingestion {self.id} - {self.user.email} ({self.status})"

    def mark_processing(self):
        """Mark run as processing."""
        self.status = "processing"
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])

    def mark_completed(self, created=0, updated=0, skipped=0):
        """Mark run as completed with stats."""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.metrics_created = created
        self.metrics_updated = updated
        self.metrics_skipped = skipped
        self.save(update_fields=[
            "status", "completed_at", "metrics_created",
            "metrics_updated", "metrics_skipped", "updated_at"
        ])

    def mark_partial(self, created=0, updated=0, skipped=0, errors=None):
        """Mark run as partial success."""
        self.status = "partial"
        self.completed_at = timezone.now()
        self.metrics_created = created
        self.metrics_updated = updated
        self.metrics_skipped = skipped
        if errors:
            self.validation_errors = errors
        self.save(update_fields=[
            "status", "completed_at", "metrics_created",
            "metrics_updated", "metrics_skipped", "validation_errors", "updated_at"
        ])

    def mark_failed(self, error_message):
        """Mark run as failed."""
        self.status = "failed"
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
