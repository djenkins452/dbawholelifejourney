"""
Insight Engine Views - display and refresh health insights.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, View

from apps.help.mixins import HelpContextMixin

from .models import InsightResult
from .services.insight_engine import InsightEngine


class InsightListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """Display recent insights for the user."""

    model = InsightResult
    template_name = "health/insights_list.html"
    context_object_name = "insights"
    paginate_by = 20
    help_context_id = "HEALTH_INSIGHTS"

    def get_queryset(self):
        return InsightResult.objects.filter(
            user=self.request.user,
            is_dismissed=False,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dismissed_count"] = InsightResult.objects.filter(
            user=self.request.user,
            is_dismissed=True,
        ).count()
        return context


class InsightRefreshView(LoginRequiredMixin, View):
    """Regenerate insights for the user."""

    def post(self, request):
        engine = InsightEngine(request.user)
        count = engine.generate_insights()
        messages.success(request, f"{count} insight{'s' if count != 1 else ''} generated.")
        return redirect("health:insights_list")


class InsightDismissView(LoginRequiredMixin, View):
    """Dismiss a single insight."""

    def post(self, request, pk):
        try:
            insight = InsightResult.objects.get(pk=pk, user=request.user)
            insight.is_dismissed = True
            insight.save(update_fields=["is_dismissed", "updated_at"])
        except InsightResult.DoesNotExist:
            pass
        return redirect("health:insights_list")
