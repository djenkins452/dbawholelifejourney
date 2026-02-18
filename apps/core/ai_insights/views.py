"""
PIE Views — Insights Inbox for users.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import ListView

from apps.core.ai_insights.models import Insight


class InsightsInboxView(LoginRequiredMixin, ListView):
    """User-facing Insights Inbox."""

    template_name = "ai_insights/inbox.html"
    context_object_name = "insights"
    paginate_by = 20

    def get_queryset(self):
        qs = Insight.objects.filter(user=self.request.user)
        status_filter = self.request.GET.get("status")
        if status_filter in ("new", "read", "dismissed"):
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_filter"] = self.request.GET.get("status", "all")
        ctx["new_count"] = Insight.objects.filter(
            user=self.request.user, status="new"
        ).count()
        ctx["app_name"] = "insights"
        ctx["help_context_id"] = "INSIGHTS_INBOX"
        return ctx


class InsightActionView(LoginRequiredMixin, View):
    """Mark insights as read or dismissed."""

    def post(self, request, pk):
        action = request.POST.get("action", "read")
        try:
            insight = Insight.objects.get(pk=pk, user=request.user)
            if action == "dismiss":
                insight.status = "dismissed"
            else:
                insight.status = "read"
            insight.save(update_fields=["status", "updated_at"])

            # Phase 4: Record engagement for feedback loop
            try:
                from apps.core.ai_feedback.insight_tracker import record_insight_engagement
                event_type = "dismissed" if action == "dismiss" else "viewed"
                record_insight_engagement(request.user, insight, event_type)
            except Exception:
                pass  # Feedback tracking must never break insight actions

            return JsonResponse({"success": True, "status": insight.status})
        except Insight.DoesNotExist:
            return JsonResponse({"success": False, "error": "Not found"}, status=404)
