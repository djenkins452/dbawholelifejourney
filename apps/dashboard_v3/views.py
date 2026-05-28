"""
Dashboard V3 Views — experimental CoS-first dashboard.

Single page render. The composer is fast (it only reads canonical state +
indexed insight rows), and we cap the request path by relying on every
underlying engine's pre-computed snapshots.
"""

from __future__ import annotations

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.dashboard_v3.services import build_dashboard_v3_context, build_weather_tile

logger = logging.getLogger(__name__)


class DashboardV3View(LoginRequiredMixin, TemplateView):
    """The experimental CoS-first dashboard.

    Lives at /dashboard-v3/. Coexists with /dashboard/ (V2 production) and
    /dashboard/legacy/ (V1). No data writes, no model changes.
    """

    template_name = "dashboard_v3/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # VERIFIED AUTO-COMPLETION (Rule 1 — authenticated presence proves
        # wakefulness). Loading the dashboard IS authenticated activity.
        #
        # Run wake-up completion UNCONDITIONALLY here (NOT via the
        # day-start cache) so it reflects on THIS render regardless of
        # whether handle_day_start already ran/short-circuited from a CoS
        # path earlier today. complete_wake_up() is idempotent
        # (first-write-wins) and completes whatever the dashboard actually
        # shows as the Wake Up item, so this is the authoritative trigger
        # for the surface the user is looking at.
        try:
            from apps.core.execution.verified_completion import complete_wake_up
            complete_wake_up(self.request.user)
        except Exception:
            logger.debug("v3: wake-up completion skipped", exc_info=True)

        # Also run the broader day-start initializer (ensures today's
        # routine task instances exist). Idempotent / cache-gated.
        try:
            from apps.ai.executive_briefing import handle_day_start
            handle_day_start(self.request.user)
        except Exception:
            logger.debug("v3: day-start init skipped", exc_info=True)

        ctx["v3"] = build_dashboard_v3_context(self.request.user)
        ctx["weather_tile"] = build_weather_tile(self.request.user)

        # Greeting & time phase — small helpers reused from v2 so the
        # surfaces feel coherent without inventing parallel logic.
        try:
            from apps.dashboard_v2.services.dashboard_service import (
                DashboardV2Service,
            )
            svc = DashboardV2Service(self.request.user)
            ctx["time_phase"] = svc.get_time_phase()
            ctx["greeting"] = svc._get_greeting(ctx["time_phase"])
        except Exception:
            logger.debug("v3: greeting/time_phase fallback", exc_info=True)
            ctx["time_phase"] = "day"
            ctx["greeting"] = "Welcome back"

        return ctx
