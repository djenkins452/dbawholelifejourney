"""
Signal API Views — Feedback capture + Insight read-only endpoints.

POST /api/signals/feedback/  — Record yes/no feedback on a signal
GET  /api/signals/insights/  — Read-only view of what the system is learning
"""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


class SignalFeedbackView(LoginRequiredMixin, View):
    """Accept yes/no feedback on a presented signal.

    POST payload:
        {"fingerprint": "...", "response": "yes"|"no"}

    Returns:
        {"status": "ok"} on success
        {"status": "error", "detail": "..."} on failure
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {"status": "error", "detail": "Invalid JSON"}, status=400,
            )

        fingerprint = (data.get("fingerprint") or "").strip()
        response = (data.get("response") or "").strip().lower()

        if not fingerprint:
            return JsonResponse(
                {"status": "error", "detail": "Missing fingerprint"}, status=400,
            )

        if response not in ("yes", "no"):
            return JsonResponse(
                {"status": "error", "detail": "Response must be 'yes' or 'no'"},
                status=400,
            )

        # Build a signal dict from the fingerprint + any extra fields
        # The feedback service needs type/domain/item — look them up
        # from the presented signals if possible, otherwise use the
        # fields from the request body as fallback.
        signal = {
            "type": (data.get("type") or "").strip().lower(),
            "domain": (data.get("domain") or "").strip().lower(),
            "item": (data.get("item") or "").strip().lower(),
            "source": (data.get("source") or "").strip().lower(),
            "fingerprint": fingerprint,
        }

        from apps.core.signals.feedback_service import record_signal_feedback

        result = record_signal_feedback(request.user, signal, response)

        if result is None:
            return JsonResponse(
                {"status": "error", "detail": "Invalid response"}, status=400,
            )

        return JsonResponse({"status": "ok", "result": result})


class SignalInsightsView(LoginRequiredMixin, View):
    """Read-only view of what the adaptive system is learning.

    GET /api/signals/insights/

    Returns categorized feedback stats: reinforced, suppressed, neutral.
    """

    def get(self, request):
        from apps.core.signals.insight_service import get_signal_insights

        insights = get_signal_insights(request.user)
        return JsonResponse(insights)
