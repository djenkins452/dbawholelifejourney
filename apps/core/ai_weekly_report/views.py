"""
WIRE — Views.

Provides the history page for weekly intelligence reports.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.views.generic import DetailView, ListView

from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport


class WeeklyReportHistoryView(LoginRequiredMixin, ListView):
    """Display historical weekly intelligence reports."""

    template_name = "ai_weekly_report/history.html"
    context_object_name = "reports"
    paginate_by = 12

    def get_queryset(self):
        return WeeklyIntelligenceReport.objects.filter(
            user=self.request.user,
        ).order_by("-week_start_date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["app_name"] = "intelligence"
        context["help_context_id"] = "WEEKLY_INTELLIGENCE_REPORT"
        return context


class WeeklyReportDetailView(LoginRequiredMixin, DetailView):
    """Display a single weekly intelligence report."""

    template_name = "ai_weekly_report/detail.html"
    context_object_name = "report"

    def get_queryset(self):
        return WeeklyIntelligenceReport.objects.filter(
            user=self.request.user,
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.user != self.request.user:
            raise Http404
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["app_name"] = "intelligence"
        context["help_context_id"] = "WEEKLY_INTELLIGENCE_REPORT"

        # Phase 4: Record detail view for engagement tracking
        try:
            from apps.core.ai_feedback.briefing_tracker import record_briefing_opened
            record_briefing_opened(self.request.user, "weekly_report", self.object.id)
        except Exception:
            pass

        return context
