"""
Signal Renderer API (Phase 1).

GET /api/signals/

Returns the deterministically rendered top signals for the requesting
user. NO LLM is invoked. Source signals are pulled from the existing
unified_feed (PIE / PRIE / PGE / CDCE) — this endpoint only RENDERS,
it does not produce.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


class SignalsAPIView(LoginRequiredMixin, View):
    """
    GET /api/signals/?max=2

    Response:
        {
            "success": true,
            "signals": [
                {
                    "label": str,
                    "message": str,
                    "action": str,
                    "priority": "foundational"|"important"|"supporting",
                    "domain": str
                },
                ...
            ]
        }

    No extra fields. The renderer's contract is the API contract.
    """

    def get(self, request, *args, **kwargs):
        try:
            max_n = int(request.GET.get("max", 2))
        except (TypeError, ValueError):
            max_n = 2
        max_n = max(1, min(max_n, 5))  # safety clamp

        try:
            from apps.core.ai_orchestrator.cos_context import build_cos_context
            from apps.core.ai_signals.unified_feed import build_signal_buckets
            from apps.core.signals.signal_renderer import select_top_signals

            cos_context = build_cos_context(request.user)
            buckets = build_signal_buckets(cos_context) or {}
            # Pull from top + critical + positive — selector + conflict
            # resolution will pick the right top-N regardless of bucket.
            pool = []
            for key in ("top_signals", "critical_signals", "positive_signals"):
                pool.extend(buckets.get(key) or [])

            selected = select_top_signals(pool, max_n=max_n)

            return JsonResponse({
                "success": True,
                "signals": [item["rendered"] for item in selected],
            })
        except Exception:
            logger.error(
                "[SIGNALS_API] failed user=%s",
                getattr(request.user, "id", None), exc_info=True,
            )
            return JsonResponse({
                "success": False,
                "error": "Failed to render signals.",
            }, status=500)
