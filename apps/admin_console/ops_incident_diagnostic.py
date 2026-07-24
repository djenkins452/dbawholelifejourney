"""
TEMPORARY investigative instrument — 2026-07-23 Operations truth-divergence.

READ-ONLY, SELECT-only reconstruction of the production Operations timeline for a
single incident window. This is an investigation tool, NOT a product feature; it
is removed immediately after evidence collection (see the removal commit).

Guardrails (enforced by construction):
  * Existing X-Claude-API-Key auth (operator-only), reuses APIRateLimitMixin.
  * SELECT-only: only `.filter().values()` reads — no create/update/delete/save.
  * Scoped to an incident window (query params, bounded defaults) + per-model caps.
  * Minimum fields only; NO secrets; AssistantMessage restricted to the
    `operations_alert` system-notification type (no arbitrary user content).

Path: apps/admin_console/ops_incident_diagnostic.py  (temporary — remove after use)
"""
from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views import View

from apps.core.rate_limiting import APIRateLimitMixin, secure_compare_api_key

# Default incident window (UTC) — the 2026-07-23 morning incident (US Eastern).
_DEFAULT_START = "2026-07-23T00:00:00+00:00"
_DEFAULT_END = "2026-07-24T06:00:00+00:00"
_CAP = 500  # per-model row cap — prevents any broad table dump


def _dt(raw, fallback):
    return parse_datetime(raw) if raw else parse_datetime(fallback)


class OpsIncidentDiagnosticAPIView(APIRateLimitMixin, View):
    rate_limit_requests_per_minute = 20
    rate_limit_requests_per_hour = 200
    rate_limit_key_prefix = "admin_api_ops_incident_diag"

    def get(self, request):
        if not settings.CLAUDE_API_KEY or not secure_compare_api_key(
            request.headers.get("X-Claude-API-Key", ""), settings.CLAUDE_API_KEY
        ):
            return JsonResponse({"error": "Invalid or missing API key."}, status=401)

        w0 = _dt(request.GET.get("start"), _DEFAULT_START)
        w1 = _dt(request.GET.get("end"), _DEFAULT_END)

        from apps.core.ai_observability.models import (
            COASHealthSnapshot,
            OperationalAlert,
            OpsAnomaly,
            SystemIntegritySnapshot,
        )
        from apps.ai.models import AssistantMessage

        # 2. Integrity history (the Wall's score/posture). Bounded + minimal.
        integrity = list(
            SystemIntegritySnapshot.objects.filter(created_at__range=(w0, w1))
            .order_by("created_at")
            .values("created_at", "score", "posture", "components")[:_CAP]
        )
        # Trim components to the operationally-relevant summary (drop bulky detail).
        for row in integrity:
            comp = row.get("components") or {}
            row["components"] = {
                k: (v.get("penalty") if isinstance(v, dict) else v)
                for k, v in comp.items()
            } if isinstance(comp, dict) else {}

        # 3. OpsAnomaly lifecycle — any incident overlapping the window.
        anomalies = list(
            OpsAnomaly.objects.filter(
                Q(created_at__lte=w1) & (Q(resolved_at__gte=w0) | Q(resolved_at__isnull=True))
            )
            .order_by("created_at")
            .values(
                "id", "anomaly_type", "engine_name", "severity", "original_severity",
                "created_at", "updated_at", "resolved_at", "is_active",
                "escalation_count", "summary",
            )[:_CAP]
        )

        # 4. COAS snapshot — SINGLE ROW (pk=1), CURRENT value only (no history).
        coas_now = list(
            COASHealthSnapshot.objects.filter(pk=1).values(
                "scheduler_score", "engine_score", "freshness_score",
                "overall_score", "updated_at",
            )
        )

        # 5. OperationalAlert lifecycle (COAS) — created or resolved in the window.
        alerts = list(
            OperationalAlert.objects.filter(
                Q(created_at__range=(w0, w1)) | Q(resolved_at__range=(w0, w1))
            )
            .order_by("created_at")
            .values(
                "id", "subsystem", "severity", "status", "health_score",
                "dedupe_key", "created_at", "resolved_at", "last_notified_at",
            )[:_CAP]
        )

        # 6. Notifications — ONLY operations_alert system notes (no user content).
        notifications = list(
            AssistantMessage.objects.filter(
                message_type="operations_alert", created_at__range=(w0, w1)
            )
            .order_by("created_at")
            .values("id", "conversation__user_id", "created_at", "content", "metadata")[:_CAP]
        )

        return JsonResponse(
            {
                "window": {"start": w0.isoformat() if w0 else None,
                           "end": w1.isoformat() if w1 else None},
                "counts": {
                    "integrity": len(integrity), "anomalies": len(anomalies),
                    "alerts": len(alerts), "notifications": len(notifications),
                },
                "note": ("READ-ONLY diagnostic. COAS is a single overwritten row "
                         "(pk=1) — coas_now is the CURRENT value, NOT the incident "
                         "value. Alignment badge is cache-only (not queryable)."),
                "system_integrity": integrity,
                "ops_anomalies": anomalies,
                "coas_now": coas_now,
                "operational_alerts": alerts,
                "notifications": notifications,
            },
            json_dumps_params={"indent": 2, "default": str},
        )
