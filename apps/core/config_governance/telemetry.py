"""
Configuration Integrity telemetry — the Operations section.

Computed in the SAME background cycle (worker) as one more Ops payload section;
the HTTP path only reads the cached payload (request-path-safe). Reads the
published per-service manifests and evaluates them against the canonical
contract. Emits customer-language + operator-detail, never a secret value.
"""
from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


# Customer-language summaries per status (the CoS/operator banner consumes these).
_CUSTOMER = {
    "healthy": "All required production configuration is present on every service.",
    "degraded": "A non-blocking configuration inconsistency exists; the platform is operational.",
    "critical": "Required production configuration is missing or inconsistent on one or more services.",
    "unknown": "Configuration cannot be fully verified right now (a service is not reporting).",
}


def get_config_integrity_telemetry(now=None) -> dict:
    """Build the ``config_integrity`` Ops section. Deterministic, secret-safe."""
    now = now or timezone.now()
    try:
        from apps.core.config_governance import evaluator, manifest
        manifests = manifest.read_all_manifests()
        result = evaluator.evaluate(manifests, now=now)
    except Exception as e:
        logger.debug("config_integrity telemetry failed: %s", e)
        # Fail to UNKNOWN — never Healthy — when we cannot evaluate.
        return {
            "status": "unknown",
            "customer_summary": _CUSTOMER["unknown"],
            "reason": "evaluation_unavailable",
            "computed_at": now.isoformat(),
        }

    result["customer_summary"] = _CUSTOMER.get(result["status"], _CUSTOMER["unknown"])
    result["computed_at"] = now.isoformat()
    return result
