"""
Phase 4 CoS — Briefing Engagement Tracker.

Tracks open rate and time on page for daily briefings and weekly reports.
Adjusts briefing length and tone dynamically.

Public API:
    - record_briefing_opened(user, content_type, content_id) -> BriefingEngagement
    - record_briefing_time(user, engagement_id, seconds) -> None
    - get_briefing_engagement_profile(user) -> BriefingEngagementProfile
    - get_preferred_briefing_length(user) -> str
"""

import logging

from django.db.models import Avg, Count, Q

from apps.core.ai_feedback.models import (
    BriefingEngagement,
    BriefingEngagementProfile,
)

logger = logging.getLogger(__name__)


def record_briefing_opened(user, content_type, content_id):
    """
    Record that a user opened a briefing or report.

    Args:
        user: Django User instance.
        content_type: "daily_briefing" | "weekly_report"
        content_id: PK of the briefing/report.

    Returns:
        BriefingEngagement instance.
    """
    engagement = BriefingEngagement.objects.create(
        user=user,
        content_type=content_type,
        content_id=content_id,
    )

    _update_briefing_profile(user)
    return engagement


def record_briefing_time(user, engagement_id, seconds, scrolled_to_end=False):
    """
    Update time spent on a briefing.

    Called when user leaves the page or after a timer fires.
    """
    try:
        engagement = BriefingEngagement.objects.get(
            id=engagement_id,
            user=user,
        )
        engagement.time_spent_seconds = seconds
        engagement.scrolled_to_end = scrolled_to_end
        engagement.save(update_fields=["time_spent_seconds", "scrolled_to_end"])
        _update_briefing_profile(user)
    except BriefingEngagement.DoesNotExist:
        logger.debug(f"BriefingTracker: Engagement {engagement_id} not found")


def get_briefing_engagement_profile(user):
    """Get or create the user's briefing engagement profile."""
    profile, _ = BriefingEngagementProfile.objects.get_or_create(user=user)
    return profile


def get_preferred_briefing_length(user):
    """
    Determine preferred briefing length based on engagement.

    Returns:
        "concise" | "standard" | "detailed"
    """
    try:
        profile = BriefingEngagementProfile.objects.filter(user=user).first()
        if profile:
            return profile.preferred_length
    except Exception:
        pass
    return "standard"


def _update_briefing_profile(user):
    """Recompute aggregate briefing engagement profile."""
    profile, _ = BriefingEngagementProfile.objects.get_or_create(user=user)

    daily = BriefingEngagement.objects.filter(
        user=user, content_type="daily_briefing"
    )
    weekly = BriefingEngagement.objects.filter(
        user=user, content_type="weekly_report"
    )

    profile.total_briefings_opened = daily.count()
    profile.total_reports_opened = weekly.count()

    # Compute open rate against generated briefings
    try:
        from apps.core.ai_briefing.models import DailyBriefing
        from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport

        total_generated = DailyBriefing.objects.filter(user=user).count()
        total_reports = WeeklyIntelligenceReport.objects.filter(user=user).count()

        profile.total_briefings_generated = total_generated
        profile.total_reports_generated = total_reports

        total_gen = total_generated + total_reports
        total_opened = profile.total_briefings_opened + profile.total_reports_opened
        if total_gen > 0:
            profile.open_rate = round(min(1.0, total_opened / total_gen), 4)
    except Exception:
        pass

    # Average time spent
    all_engagements = BriefingEngagement.objects.filter(
        user=user, time_spent_seconds__gt=0
    )
    avg = all_engagements.aggregate(avg_time=Avg("time_spent_seconds"))
    profile.avg_time_spent_seconds = round(avg["avg_time"] or 0.0, 1)

    # Derive preferred length from behavior
    if profile.avg_time_spent_seconds < 15 or profile.open_rate < 0.3:
        profile.preferred_length = "concise"
    elif profile.avg_time_spent_seconds > 60 and profile.open_rate > 0.6:
        profile.preferred_length = "detailed"
    else:
        profile.preferred_length = "standard"

    profile.save()
