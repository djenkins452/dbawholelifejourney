"""
Operations Wall — Staff-only views for live engine monitoring.

Layer 2 (Vegas View): Live pulse tiles, cognitive feed, anomaly alerts,
trend charts. All data derived from EngineRun/DecisionRecord tables.

Project: Whole Life Journey
Path: apps/core/ai_observability/ops_views.py
"""

import logging
from datetime import timedelta

from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class AdminRequiredMixin(UserPassesTestMixin):
    """Restrict to staff users."""

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        from django.shortcuts import redirect

        return redirect("dashboard:home")


class OperationsWallView(AdminRequiredMixin, TemplateView):
    """Main operations wall page."""

    template_name = "admin_console/operations_wall.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Operations Wall"
        context["app_name"] = "admin_console"
        return context


class OperationsWallPollView(View):
    """
    Polling endpoint for the Operations Wall.

    GET /admin-console/ops/poll/?since=<iso-timestamp>

    Returns JSON with engine tiles, feed, anomalies, charts, system status.
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        since_str = request.GET.get("since", "")
        engine_filter = request.GET.get("engine", "")

        try:
            since = timezone.datetime.fromisoformat(since_str)
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
        except (ValueError, TypeError):
            since = timezone.now() - timedelta(minutes=5)

        # Compute all aggregates
        from apps.core.ai_observability.ops_aggregates import (
            get_all_engine_pulses,
            get_confidence_trend,
            get_suppression_stats,
            get_system_latency,
            get_system_status,
            get_ual_scenario_distribution,
        )
        from apps.core.ai_observability.ops_anomalies import detect_anomalies
        from apps.core.ai_observability.ops_feed import get_recent_feed

        pulses = get_all_engine_pulses()

        return JsonResponse(
            {
                "server_time": timezone.now().isoformat(),
                "system_status": get_system_status(pulses),
                "engine_tiles": pulses,
                "ops_feed": get_recent_feed(
                    since=since,
                    limit=50,
                    engine_filter=engine_filter or None,
                ),
                "anomalies": detect_anomalies(),
                "charts": {
                    "ual_scenarios": get_ual_scenario_distribution(),
                    "suppression": get_suppression_stats(),
                    "latency": get_system_latency(),
                    "confidence_trend": get_confidence_trend(),
                },
                "next_since": timezone.now().isoformat(),
            }
        )
