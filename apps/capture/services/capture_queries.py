# ==============================================================================
# File: apps/capture/services/capture_queries.py
# Description: Canonical capture query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical capture queries.
"""

from apps.capture.models import CaptureEntry, PendingCapture


class CaptureQueries:
    """Canonical, deterministic capture queries. No instance state."""

    @classmethod
    def pending_uploads(cls, user):
        """Pending/uploading captures."""
        return PendingCapture.objects.filter(
            user=user, status__in=['pending', 'uploading'],
        )

    @classmethod
    def ready_recent(cls, user, days=7):
        """Ready captures in last N days, ordered by date desc."""
        from datetime import timedelta

        from django.utils import timezone
        cutoff = timezone.localdate() - timedelta(days=days)
        return CaptureEntry.objects.filter(
            user=user, status='ready',
            created_at__date__gte=cutoff,
        ).order_by('-created_at')

    @classmethod
    def failed_recent(cls, user, days=7):
        """Failed captures in last N days."""
        from datetime import timedelta

        from django.utils import timezone
        cutoff = timezone.localdate() - timedelta(days=days)
        return CaptureEntry.objects.filter(
            user=user, status='failed',
            created_at__date__gte=cutoff,
        )

    @classmethod
    def today(cls, user, as_of=None):
        """Captures created today."""
        if as_of is None:
            from django.utils import timezone
            as_of = timezone.localdate()
        return CaptureEntry.objects.filter(
            user=user, created_at__date=as_of,
        )

    @classmethod
    def volume_recent(cls, user, days=7):
        """All captures in last N days (any status)."""
        from datetime import timedelta

        from django.utils import timezone
        cutoff = timezone.localdate() - timedelta(days=days)
        return CaptureEntry.objects.filter(
            user=user, created_at__date__gte=cutoff,
        )

    @classmethod
    def stale(cls, user, days=14):
        """Ready captures older than N days (not reviewed)."""
        from datetime import timedelta

        from django.utils import timezone
        cutoff = timezone.now() - timedelta(days=days)
        return CaptureEntry.objects.filter(
            user=user, status='ready',
            created_at__lt=cutoff,
        )
