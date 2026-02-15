"""
PGE -- API Views.

Provides endpoints for retrieving and managing proactive guidance items.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView

from apps.core.ai_guidance.guidance_engine import get_active_guidance
from apps.core.ai_guidance.models import GuidanceItem

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class GuidanceInboxView(ListView):
    """Display active guidance items for the current user."""

    template_name = "ai_guidance/inbox.html"
    context_object_name = "guidance_items"
    paginate_by = 10

    def get_queryset(self):
        status_filter = self.request.GET.get("filter", "active")

        qs = GuidanceItem.objects.filter(user=self.request.user)

        if status_filter == "active":
            qs = qs.filter(is_active=True)
        elif status_filter == "read":
            qs = qs.filter(is_read=True)
        elif status_filter == "all":
            pass  # No additional filtering
        else:
            qs = qs.filter(is_active=True)

        return qs.order_by("priority", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_filter"] = self.request.GET.get("filter", "active")
        context["active_count"] = GuidanceItem.objects.filter(
            user=self.request.user, is_active=True
        ).count()
        context["app_name"] = "guidance"
        context["help_context_id"] = "GUIDANCE_INBOX"
        return context


@method_decorator(login_required, name="dispatch")
class GuidanceActionView(View):
    """Handle actions on guidance items (read, dismiss)."""

    def post(self, request, pk):
        try:
            item = GuidanceItem.objects.get(
                pk=pk, user=request.user
            )
        except GuidanceItem.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Not found"}, status=404
            )

        action = request.POST.get("action", "read")

        if action == "dismiss":
            item.deactivate()
            return JsonResponse({"success": True, "status": "dismissed"})
        elif action == "read":
            item.mark_read()
            return JsonResponse({"success": True, "status": "read"})
        else:
            return JsonResponse(
                {"success": False, "error": f"Unknown action: {action}"},
                status=400,
            )


@method_decorator(login_required, name="dispatch")
class GuidanceAPIView(View):
    """JSON API endpoint for retrieving active guidance items."""

    def get(self, request):
        limit = int(request.GET.get("limit", 5))
        limit = min(limit, 10)  # Cap at 10

        items = get_active_guidance(request.user, limit=limit)

        data = []
        for item in items:
            data.append({
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "priority": item.priority,
                "priority_display": item.get_priority_display(),
                "guidance_type": item.guidance_type,
                "source": item.source,
                "module": item.module,
                "confidence_score": item.confidence_score,
                "is_read": item.is_read,
                "created_at": item.created_at.isoformat(),
            })

        return JsonResponse({"guidance": data, "count": len(data)})
