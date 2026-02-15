"""
DNE — Views.

Intelligence notification settings and delivery history.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.ai_delivery.models import DeliveredNotification

logger = logging.getLogger(__name__)


class IntelligenceNotificationSettingsView(LoginRequiredMixin, TemplateView):
    """User-facing intelligence notification preferences page."""

    template_name = "ai_delivery/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prefs = self.request.user.preferences
        context["prefs"] = prefs
        return context


class IntelligenceNotificationSettingsSaveView(LoginRequiredMixin, View):
    """Handle form POST from intelligence notification settings."""

    def post(self, request, *args, **kwargs):
        prefs = request.user.preferences

        # Channel toggles
        prefs.intelligence_inapp_enabled = request.POST.get("intelligence_inapp_enabled") == "on"
        prefs.intelligence_email_enabled = request.POST.get("intelligence_email_enabled") == "on"
        prefs.intelligence_sms_enabled = request.POST.get("intelligence_sms_enabled") == "on"

        # Throttle limits
        try:
            max_per_day = int(request.POST.get("intelligence_max_per_day", 6))
            prefs.intelligence_max_per_day = min(max(max_per_day, 1), 20)
        except (ValueError, TypeError):
            pass

        try:
            max_per_hour = int(request.POST.get("intelligence_max_per_hour", 2))
            prefs.intelligence_max_per_hour = min(max(max_per_hour, 1), 10)
        except (ValueError, TypeError):
            pass

        prefs.save()
        messages.success(request, "Intelligence notification settings saved.")
        return redirect("ai_delivery:settings")


class DeliveryHistoryView(LoginRequiredMixin, ListView):
    """View delivery history for the authenticated user."""

    template_name = "ai_delivery/history.html"
    context_object_name = "deliveries"
    paginate_by = 20

    def get_queryset(self):
        return DeliveredNotification.objects.filter(
            user=self.request.user,
        ).order_by("-delivered_at")
