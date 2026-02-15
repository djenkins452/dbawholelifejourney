"""
Intelligence Command Center (ICC) — Unified intelligence dashboard.

Aggregates and displays outputs from all intelligence engines:
SAE (state), PGE (guidance), DBE (briefing), WIRE (weekly reports),
DNE (deliveries), PRIE (predictions), with E3 explainability links.

ICC does NOT generate intelligence — it only presents what engines produce.
"""

import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class IntelligenceCommandCenterView(TemplateView):
    """
    Intelligence Command Center — unified view of all engine outputs.

    Sections:
    1. Current State (SAE snapshot)
    2. Active Guidance (PGE)
    3. Daily Briefing (DBE)
    4. Weekly Report summary (WIRE)
    5. Recent Deliveries (DNE)
    6. Predictions (PRIE)
    """

    template_name = "intelligence/command_center.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Section 1: SAE — Current State
        context["user_state"] = self._get_user_state(user)

        # Section 2: PGE — Active Guidance
        context["guidance_items"] = self._get_active_guidance(user, now)
        context["guidance_count"] = len(context["guidance_items"])

        # Section 3: DBE — Daily Briefing
        context["daily_briefing"] = self._get_daily_briefing(user, now)

        # Section 4: WIRE — Weekly Report
        context["weekly_report"] = self._get_weekly_report(user, now)

        # Section 5: DNE — Recent Deliveries
        context["recent_deliveries"] = self._get_recent_deliveries(user)

        # Section 6: PRIE — Predictions
        context["predictions"] = self._get_predictions(user, now)

        # Page metadata
        context["app_name"] = "intelligence"
        context["help_context_id"] = "INTELLIGENCE_COMMAND_CENTER"
        context["page_title"] = "Intelligence Command Center"

        return context

    def _get_user_state(self, user):
        """Fetch SAE state snapshot."""
        try:
            from apps.core.ai_state.models import UserState
            return UserState.objects.filter(user=user).first()
        except Exception as e:
            logger.debug(f"ICC: SAE unavailable: {e}")
            return None

    def _get_active_guidance(self, user, now):
        """Fetch active PGE guidance items."""
        try:
            from apps.core.ai_guidance.models import GuidanceItem
            return list(
                GuidanceItem.objects.filter(
                    user=user,
                    is_active=True,
                    dismissed_at__isnull=True,
                ).exclude(
                    snoozed_until__gt=now,
                ).order_by("priority", "-created_at")[:10]
            )
        except Exception as e:
            logger.debug(f"ICC: PGE unavailable: {e}")
            return []

    def _get_daily_briefing(self, user, now):
        """Fetch today's DBE briefing."""
        try:
            from apps.core.ai_briefing.models import DailyBriefing
            return DailyBriefing.objects.filter(
                user=user,
                briefing_date=now.date(),
            ).first()
        except Exception as e:
            logger.debug(f"ICC: DBE unavailable: {e}")
            return None

    def _get_weekly_report(self, user, now):
        """Fetch latest WIRE weekly report."""
        try:
            from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
            return WeeklyIntelligenceReport.objects.filter(
                user=user,
            ).order_by("-week_start_date").first()
        except Exception as e:
            logger.debug(f"ICC: WIRE unavailable: {e}")
            return None

    def _get_recent_deliveries(self, user):
        """Fetch recent DNE deliveries."""
        try:
            from apps.core.ai_delivery.models import DeliveredNotification
            return list(
                DeliveredNotification.objects.filter(
                    user=user,
                ).order_by("-delivered_at")[:10]
            )
        except Exception as e:
            logger.debug(f"ICC: DNE unavailable: {e}")
            return []

    def _get_predictions(self, user, now):
        """Fetch active PRIE predictions."""
        try:
            from apps.core.ai_predictions.models import Prediction
            return list(
                Prediction.objects.filter(
                    user=user,
                    status="active",
                    predicted_date__gte=now,
                ).order_by("predicted_date")[:10]
            )
        except Exception as e:
            logger.debug(f"ICC: PRIE unavailable: {e}")
            return []
