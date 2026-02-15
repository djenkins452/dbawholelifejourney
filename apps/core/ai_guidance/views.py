"""
PGE -- API Views.

Provides endpoints for retrieving and managing proactive guidance items.
Supports full lifecycle actions: read, acknowledge, dismiss, snooze, acted.
"""

import json
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
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
    """Handle lifecycle actions on guidance items."""

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

        if action == "read":
            item.mark_read()
            return JsonResponse({"success": True, "status": "read"})

        elif action == "acknowledge":
            item.acknowledge()
            return JsonResponse({"success": True, "status": "acknowledged"})

        elif action == "dismiss":
            item.dismiss()
            return JsonResponse({"success": True, "status": "dismissed"})

        elif action == "snooze":
            hours = int(request.POST.get("hours", 24))
            hours = min(hours, 168)  # Cap at 7 days
            snooze_until = timezone.now() + timedelta(hours=hours)
            item.snooze(snooze_until)
            return JsonResponse({
                "success": True,
                "status": "snoozed",
                "snoozed_until": snooze_until.isoformat(),
            })

        elif action == "acted":
            action_type = request.POST.get("action_type", "")
            item.mark_acted_upon(action_type=action_type or None)
            return JsonResponse({"success": True, "status": "acted_upon"})

        elif action == "feedback":
            feedback_text = request.POST.get("feedback", "")
            if not feedback_text:
                return JsonResponse(
                    {"success": False, "error": "Feedback text required"},
                    status=400,
                )
            item.set_feedback(feedback_text)
            return JsonResponse({"success": True, "status": "feedback_saved"})

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
                "is_acknowledged": item.is_acknowledged,
                "is_acted_upon": item.is_acted_upon,
                "acknowledged_at": (
                    item.acknowledged_at.isoformat()
                    if item.acknowledged_at else None
                ),
                "acted_upon_at": (
                    item.acted_upon_at.isoformat()
                    if item.acted_upon_at else None
                ),
                "action_type": item.action_type,
                "created_at": item.created_at.isoformat(),
            })

        return JsonResponse({"guidance": data, "count": len(data)})
