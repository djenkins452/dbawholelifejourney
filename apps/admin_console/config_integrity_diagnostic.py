"""
TEMPORARY production verification endpoint for Configuration Governance.

Returns the deterministic Configuration Integrity evaluation + the raw per-service
presence manifests (presence tokens ONLY — never a secret value) so the config-
governance mechanism can be verified against the real Railway topology after
deploy. Reuses the existing X-Claude-API-Key operator auth. REMOVE after
verification.

Path: apps/admin_console/config_integrity_diagnostic.py (temporary scaffolding)
"""
from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from apps.core.rate_limiting import APIRateLimitMixin, secure_compare_api_key


class ConfigIntegrityDiagnosticAPIView(APIRateLimitMixin, View):
    rate_limit_requests_per_minute = 30
    rate_limit_requests_per_hour = 300
    rate_limit_key_prefix = "admin_api_config_integrity_diag"

    def get(self, request):
        if not settings.CLAUDE_API_KEY or not secure_compare_api_key(
            request.headers.get("X-Claude-API-Key", ""), settings.CLAUDE_API_KEY
        ):
            return JsonResponse({"error": "Invalid or missing API key."}, status=401)

        from apps.core.config_governance import manifest, telemetry

        # Presence-only manifests (defensive: strip anything but the safe fields).
        raw = manifest.read_all_manifests()
        safe_manifests = {
            svc: {
                "service": m.get("service"),
                "commit": m.get("commit"),
                "environment": m.get("environment"),
                "published_at": m.get("published_at"),
                "presence": m.get("presence"),  # present|empty|absent tokens only
            }
            for svc, m in raw.items()
        }
        return JsonResponse(
            {
                "evaluation": telemetry.get_config_integrity_telemetry(),
                "manifests": safe_manifests,
                "manifest_count": len(safe_manifests),
            },
            json_dumps_params={"indent": 2},
        )
