"""
Dashboard V3 Views — experimental CoS-first dashboard.

Single page render. The composer is fast (it only reads canonical state +
indexed insight rows), and we cap the request path by relying on every
underlying engine's pre-computed snapshots.
"""

from __future__ import annotations

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View
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
        # Phase 4 step 1 — production GET timing. Same instrumentation
        # surface Phase 1 added for action endpoints; emits
        #   [DASHBOARD_ACTION_TIMING] action=dashboard_v3_get user=... total_ms=...
        # exactly once per dashboard render. Lets us confirm in prod
        # logs whether the Phase 3 server-side win (lab profile: ~60 ms)
        # actually holds for real users.
        from apps.core.timing import action_timing
        with action_timing("dashboard_v3_get", self.request):
            return self._build_context(**kwargs)

    def _build_context(self, **kwargs):
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
        # Phase 2/3 — fetch the execution contract ONCE up front; thread it
        # to complete_wake_up + the composer. Eliminates 2 of the 5 redundant
        # build_today_execution calls on the render path.
        _exec_contract = None
        try:
            from apps.core.execution.today_execution import build_today_execution
            _exec_contract = build_today_execution(self.request.user)
            # Stash on the user so the composer's _load_execution_contract
            # picks it up without an explicit kwarg chain.
            self.request.user._dashboard_exec_contract = _exec_contract
        except Exception:
            logger.debug("v3: pre-fetch execution_contract failed", exc_info=True)

        try:
            from apps.core.execution.verified_completion import complete_wake_up
            complete_wake_up(self.request.user, execution_contract=_exec_contract)
        except Exception:
            logger.debug("v3: wake-up completion skipped", exc_info=True)

        # Also run the broader day-start initializer (ensures today's
        # routine task instances exist). Idempotent / cache-gated.
        try:
            from apps.ai.executive_briefing import handle_day_start
            handle_day_start(self.request.user)
        except Exception:
            logger.debug("v3: day-start init skipped", exc_info=True)

        # Trust convergence: dismiss any stale weight-sync artifact (Insight
        # row OR GuidanceItem row) whose underlying condition has resolved,
        # so the dashboard accountability layer can never diverge from the
        # SAE truth Beth reads. Quiet by default; only logs on anomaly.
        try:
            from apps.health.services.weight_sync import (
                resolve_stale_weight_insight_if_cleared,
            )
            res = resolve_stale_weight_insight_if_cleared(self.request.user)
            stuck = (
                (res.get("insight_active_before") or 0)
                > (res.get("insight_dismissed_count") or 0)
                and (res.get("gap_days") or 99) < 3
            )
            if stuck:
                # Active stale rows survived a fresh-weight resolver pass —
                # the trust contract is at risk. Log so we notice.
                logger.warning(
                    "[DASHBOARD_WEIGHT_WARNING] stale weight insight survived "
                    "resolver user=%s gap_days=%s active_before=%s "
                    "dismissed=%s guidance_active=%s",
                    self.request.user.id,
                    res.get("gap_days"),
                    res.get("insight_active_before"),
                    res.get("insight_dismissed_count"),
                    res.get("guidance_active_before"),
                )
        except Exception:
            logger.error(
                "[DASHBOARD_WEIGHT_ERROR] resolver raised for user=%s",
                self.request.user.id, exc_info=True,
            )

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


class UtilitiesSectionView(LoginRequiredMixin, View):
    """HTMX partial — re-renders ONLY the utilities (hydration) section.

    Used by the Phase 4 hydration POC: after a "+8 oz Water" / "+8 oz
    Coffee" / "+16 oz Electrolytes" POST succeeds, the home.html JS
    dispatches ``dashboard:water-changed`` and the utilities <section>
    self-refreshes via ``hx-get`` to this endpoint — NO full dashboard
    reload, NO 258 KB HTML payload, NO browser teardown.

    Reads canonical state via the same ``_build_utilities`` the full
    composer uses — no optimistic data, no JS-side mutation. Server is
    still the source of truth.

    Trust contract preserved:
      - Same data path as full dashboard (composer._build_utilities)
      - No SAE rebuild on request path (Phase 3 contract held)
      - Cheap (~1.4 ms / 2 queries in profile)
    """

    def get(self, request):
        from apps.core.timing import action_timing
        from apps.dashboard_v3.services.composer import _build_utilities

        with action_timing("dashboard_v3_section_utilities", request):
            try:
                utilities = _build_utilities(request.user) or {}
            except Exception:
                logger.warning(
                    "Phase 4: partial utilities render failed for user=%s",
                    request.user.pk, exc_info=True,
                )
                utilities = {}
            return render(
                request,
                "dashboard_v3/sections/utilities.html",
                {"utilities": utilities},
            )


class SectionLiveView(LoginRequiredMixin, View):
    """HTMX partial — re-renders the dynamic dashboard region (#v3-live) after
    a completion, so the checkbox click never triggers a full
    window.location.reload().

    Flow: toggle POST → 204 (fast) → JS optimistically flips the clicked item →
    JS dispatches ``dashboard:completed`` → this endpoint re-renders every
    section a completion changes (gauges/mission/executive/focus/accountability/
    rhythm) and HTMX swaps it in. Reads canonical state via the SAME composer as
    the full page — no optimistic data server-side, no divergence.
    """

    def get(self, request):
        from apps.core.timing import action_timing
        from apps.dashboard_v3.services import build_dashboard_v3_context

        with action_timing("dashboard_v3_section_live", request):
            try:
                v3 = build_dashboard_v3_context(request.user)
            except Exception:
                logger.warning(
                    "section_live render failed for user=%s",
                    request.user.pk, exc_info=True,
                )
                v3 = {}
            return render(
                request,
                "dashboard_v3/sections/_live.html",
                {"v3": v3},
            )
