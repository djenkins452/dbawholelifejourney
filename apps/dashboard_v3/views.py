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

from apps.dashboard_v3.services import build_dashboard_v3_context

logger = logging.getLogger(__name__)


class DashboardV3View(LoginRequiredMixin, TemplateView):
    """The experimental CoS-first dashboard.

    Lives at /dashboard-v3/. Coexists with /dashboard/ (V2 production) and
    /dashboard/legacy/ (V1). No data writes, no model changes.
    """

    template_name = "dashboard_v3/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["v3"] = build_dashboard_v3_context(self.request.user)

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
