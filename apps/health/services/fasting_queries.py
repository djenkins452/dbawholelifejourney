# ==============================================================================
# File: apps/health/services/fasting_queries.py
# Description: Canonical fasting query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical fasting queries.

COMPLETION RULE:
  A fast is "completed" when ended_at is set and status='active'.
  An open fast (ended_at is null) is "in progress".
"""

from apps.health.models import FastingWindow


class FastingQueries:
    """Canonical, deterministic fasting queries. No instance state."""

    @classmethod
    def current_active(cls, user):
        """Currently active (open) fasting window, or None."""
        return FastingWindow.objects.filter(
            user=user, ended_at__isnull=True, status='active',
        ).order_by('-started_at').first()

    @classmethod
    def is_fasting(cls, user):
        """Boolean: is user currently fasting?"""
        return FastingWindow.objects.filter(
            user=user, ended_at__isnull=True, status='active',
        ).exists()

    @classmethod
    def completed_in_range(cls, user, start_dt, end_dt):
        """Completed fasts started in a datetime range."""
        return FastingWindow.objects.filter(
            user=user,
            ended_at__isnull=False,
            started_at__gte=start_dt,
            status='active',
        )

    @classmethod
    def last_completed(cls, user):
        """Most recent completed fast, or None."""
        return FastingWindow.objects.filter(
            user=user, ended_at__isnull=False, status='active',
        ).order_by('-ended_at').first()

    @classmethod
    def compliance_score_7d(cls, user, now):
        """
        Phase 2 canonical fasting compliance score (0-100), or None.

        Returns the same number that ``build_fasting_state`` produces and
        that downstream surfaces (CoS, dashboards, signals) display. Other
        engines (e.g. signal aggregation, CDCE) MUST call this rather than
        re-deriving the score with a different algorithm — historically the
        signal pipeline used a binary "met target / didn't" while SAE used
        a continuous ratio, and the two answers diverged for the same user
        on the same day.

        Algorithm:
            * If there are zero completed fasts in the last 7 days, returns
              ``None`` (insufficient data — explicitly NOT zero, to prevent
              false 'fasting 0%' correlations downstream).
            * If the user has a target_hours set on a recent fast,
              compliance is the inverse-error of avg_duration vs target,
              clamped 0–100.
            * Otherwise compliance is frequency-based:
              ``(fasts_in_7d / 7) * 100``.
        """
        from datetime import timedelta

        cutoff_7d = now - timedelta(days=7)
        fasts_7d = cls.completed_in_range(user, cutoff_7d, now)
        fasts_7d_count = fasts_7d.count()
        if fasts_7d_count == 0:
            return None

        # Aggregate hours
        total_hours = 0.0
        for started_at, ended_at in fasts_7d.values_list('started_at', 'ended_at'):
            total_hours += (ended_at - started_at).total_seconds() / 3600
        avg_duration = total_hours / fasts_7d_count

        recent_with_target = (
            FastingWindow.objects.filter(
                user=user,
                target_hours__isnull=False,
                status='active',
            )
            .order_by('-started_at')
            .values_list('target_hours', flat=True)
            .first()
        )
        if recent_with_target and recent_with_target > 0:
            ratio = min(avg_duration / float(recent_with_target), 1.5)
            return round(max(0.0, 100 - abs(100 - ratio * 100)), 1)

        return round(min(fasts_7d_count / 7 * 100, 100), 1)
