"""
Diagnostics Console — Staff-only views for engine tracing.

Layer 1 (Truth Layer): Trace search, waterfall detail, live feed.
Consumed by the Diagnostics Console page and deep-linked from
the Operations Wall.

Project: Whole Life Journey
Path: apps/core/ai_observability/diagnostics_views.py
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


class DiagnosticsConsoleView(AdminRequiredMixin, TemplateView):
    """Main diagnostics console page."""

    template_name = "admin_console/diagnostics_console.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.ai_observability.models import DecisionRecord, EngineRun

        context["recent_runs"] = list(
            EngineRun.objects.order_by("-started_at")[:50].values(
                "id",
                "trace_id",
                "engine_name",
                "phase",
                "started_at",
                "duration_ms",
                "status",
                "error_type",
                "user_id",
            )
        )
        context["recent_decisions"] = list(
            DecisionRecord.objects.order_by("-created_at")[:20].values(
                "id",
                "trace_id",
                "engine_name",
                "decision_type",
                "decision",
                "rationale",
                "user_id",
                "confidence",
                "created_at",
            )
        )
        context["page_title"] = "Diagnostics Console"
        context["app_name"] = "admin_console"
        return context


class DiagnosticsStreamView(View):
    """
    Polling endpoint — returns engine runs/decisions since a timestamp.

    GET /admin-console/diagnostics/stream/?since=<iso-timestamp>
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import DecisionRecord, EngineRun

        since_str = request.GET.get("since", "")
        engine_filter = request.GET.get("engine", "")
        status_filter = request.GET.get("status", "")

        try:
            since = timezone.datetime.fromisoformat(since_str)
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
        except (ValueError, TypeError):
            since = timezone.now() - timedelta(minutes=5)

        runs_qs = EngineRun.objects.filter(started_at__gt=since).order_by("-started_at")
        decisions_qs = DecisionRecord.objects.filter(created_at__gt=since).order_by(
            "-created_at"
        )

        if engine_filter:
            runs_qs = runs_qs.filter(engine_name=engine_filter)
            decisions_qs = decisions_qs.filter(engine_name=engine_filter)
        if status_filter:
            runs_qs = runs_qs.filter(status=status_filter)

        runs = list(
            runs_qs[:100].values(
                "id",
                "trace_id",
                "engine_name",
                "phase",
                "started_at",
                "duration_ms",
                "status",
                "error_type",
                "error_message",
                "user_id",
            )
        )
        decisions = list(
            decisions_qs[:50].values(
                "id",
                "trace_id",
                "engine_name",
                "decision_type",
                "decision",
                "rationale",
                "user_id",
                "confidence",
                "created_at",
            )
        )

        # Serialize datetimes
        for r in runs:
            r["started_at"] = r["started_at"].isoformat() if r["started_at"] else None
        for d in decisions:
            d["created_at"] = d["created_at"].isoformat() if d["created_at"] else None

        return JsonResponse(
            {
                "runs": runs,
                "decisions": decisions,
                "server_time": timezone.now().isoformat(),
            }
        )


class DiagnosticsTraceDetailView(View):
    """
    Trace detail — all runs, spans, decisions for a trace_id.

    GET /admin-console/diagnostics/trace/<trace_id>/
    """

    def get(self, request, trace_id):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import (
            DecisionRecord,
            EngineRun,
            EngineSpan,
        )

        runs = list(
            EngineRun.objects.filter(trace_id=trace_id)
            .order_by("started_at")
            .values(
                "id",
                "engine_name",
                "phase",
                "started_at",
                "ended_at",
                "duration_ms",
                "status",
                "error_type",
                "error_message",
                "user_id",
                "metadata",
            )
        )
        spans = list(
            EngineSpan.objects.filter(trace_id=trace_id)
            .order_by("started_at")
            .values(
                "id",
                "engine_name",
                "span_name",
                "started_at",
                "ended_at",
                "duration_ms",
                "status",
                "metadata",
            )
        )
        decisions = list(
            DecisionRecord.objects.filter(trace_id=trace_id)
            .order_by("created_at")
            .values(
                "id",
                "engine_name",
                "decision_type",
                "decision",
                "rationale",
                "inputs_summary",
                "affected_items",
                "user_id",
                "confidence",
                "created_at",
            )
        )

        # Serialize datetimes
        for item_list in [runs, spans]:
            for item in item_list:
                for key in ["started_at", "ended_at"]:
                    if item.get(key):
                        item[key] = item[key].isoformat()
        for d in decisions:
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()

        # Compute trace timeline info
        trace_start = None
        trace_end = None
        if runs:
            trace_start = runs[0].get("started_at")
            ends = [r.get("ended_at") for r in runs if r.get("ended_at")]
            if ends:
                trace_end = max(ends)

        return JsonResponse(
            {
                "trace_id": trace_id,
                "trace_start": trace_start,
                "trace_end": trace_end,
                "runs": runs,
                "spans": spans,
                "decisions": decisions,
            }
        )


class DiagnosticsSearchView(View):
    """
    Search engine runs by user_id, engine, status, time range.

    GET /admin-console/diagnostics/search/?q=...&engine=...&status=...&since=...
    """

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "forbidden"}, status=403)

        from apps.core.ai_observability.models import EngineRun

        q = request.GET.get("q", "").strip()
        engine = request.GET.get("engine", "")
        status = request.GET.get("status", "")
        since = request.GET.get("since", "")
        user_id = request.GET.get("user_id", "")

        qs = EngineRun.objects.all()

        if engine:
            qs = qs.filter(engine_name=engine)
        if status:
            qs = qs.filter(status=status)
        if user_id:
            try:
                qs = qs.filter(user_id=int(user_id))
            except (ValueError, TypeError):
                pass
        if since:
            try:
                since_dt = timezone.datetime.fromisoformat(since)
                if timezone.is_naive(since_dt):
                    since_dt = timezone.make_aware(since_dt)
                qs = qs.filter(started_at__gte=since_dt)
            except (ValueError, TypeError):
                pass
        if q:
            # Search by trace_id prefix or error message
            from django.db.models import Q

            qs = qs.filter(
                Q(trace_id__startswith=q)
                | Q(error_message__icontains=q)
                | Q(error_type__icontains=q)
            )

        results = list(
            qs.order_by("-started_at")[:100].values(
                "id",
                "trace_id",
                "engine_name",
                "phase",
                "started_at",
                "duration_ms",
                "status",
                "error_type",
                "user_id",
            )
        )

        for r in results:
            r["started_at"] = r["started_at"].isoformat() if r["started_at"] else None

        return JsonResponse({"results": results, "count": len(results)})
