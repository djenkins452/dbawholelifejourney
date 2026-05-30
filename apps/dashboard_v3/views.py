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

from apps.help.mixins import HelpContextMixin

from apps.dashboard_v3.services import build_dashboard_v3_context, build_weather_tile

logger = logging.getLogger(__name__)


class DashboardV3View(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """The CoS-first dashboard — PRODUCTION default at /dashboard/ (2026-05-28).

    Also reachable at /dashboard-v3/ for validation. The preserved v2
    experience lives at /dashboard/classic/ (rollback target). Reuses the
    DASHBOARD_V2_HOME help context for parity with the help button.
    """

    template_name = "dashboard_v3/home.html"
    help_context_id = "DASHBOARD_V2_HOME"

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

        # TRUST CONVERGENCE — clears any stale 'missing_weight_logging'
        # insight whose underlying condition has resolved. Self-sufficient
        # (reads WeightEntry directly, no SAE dependency). Emits a single
        # [DASHBOARD_WEIGHT_DEBUG] line per load as forensic evidence so
        # production logs answer "did the resolver run, what did it see,
        # what did it dismiss" without ambiguity.
        try:
            from apps.health.services.weight_sync import (
                get_weight_sync_status,
                resolve_stale_weight_insight_if_cleared,
            )
            res = resolve_stale_weight_insight_if_cleared(self.request.user)
            sync = get_weight_sync_status(self.request.user)
            logger.info(
                "[DASHBOARD_WEIGHT_DEBUG] route=/dashboard/ view=DashboardV3View "
                "user=%s resolver_called=True active_before=%s active_after=%s "
                "dismissed_count=%s dismissed_ids=%s latest_recorded_at=%s "
                "gap_days=%s sae_weight_sync_stale=%s sae_last_synced=%s",
                self.request.user.id,
                res.get("active_before"), res.get("active_after"),
                res.get("dismissed_count"), res.get("dismissed_ids"),
                res.get("latest_recorded_at"), res.get("gap_days"),
                sync.get("sync_stale"),
                sync["last_entry_at"].isoformat() if sync.get("last_entry_at") else None,
            )
        except Exception:
            logger.warning("v3: weight insight cleanup failed", exc_info=True)

        ctx["v3"] = build_dashboard_v3_context(self.request.user)
        ctx["weather_tile"] = build_weather_tile(self.request.user)

        # Lightweight load observability (one line) — enough to debug a
        # regression fast without over-logging. Captures gauge count, the
        # focus action + its resolved destination, and rhythm totals.
        try:
            v3 = ctx["v3"]
            focus = v3.get("focus_now") or {}
            rhythm_totals = (v3.get("rhythm") or {}).get("totals", {})
            logger.info(
                "DASHBOARD_V3_LOAD user=%s gauges=%d focus=%r dest=%s "
                "rhythm=%s/%s",
                self.request.user.id,
                len(v3.get("cockpit_domains") or v3.get("gauges") or []),
                focus.get("title"),
                focus.get("destination_url"),
                rhythm_totals.get("completed"), rhythm_totals.get("total"),
            )
        except Exception:
            logger.debug("v3: load log skipped", exc_info=True)

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
