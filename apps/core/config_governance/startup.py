"""
Startup governance hook — publish this service's manifest + report-only checks.

Called once from ``apps.core.apps.CoreConfig.ready()`` in every process (web,
worker, beat). It:
  1. Publishes this process's secret-safe presence manifest to shared Redis so
     the Operations monitor can see the whole topology.
  2. Runs a REPORT-ONLY validation of the variables THIS service requires,
     logging a plain-language governance summary (never a secret value).

Rollout posture (Phase 15): report-only by default. Fatal enforcement is gated
behind ``CONFIG_GOVERNANCE_ENFORCE_STARTUP`` (default False) so this can never
add a new startup crash. The genuinely-fatal trio (SECRET_KEY, DATABASE_URL,
CLOUDINARY_*) is ALREADY enforced by settings-import raises; this does not
duplicate or weaken that.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("wlj.config_governance")


def run_startup_governance() -> dict:
    """Publish the manifest and log a report-only config summary. Never raises."""
    try:
        from django.conf import settings
        from apps.core.config_governance import contract as _c
        from apps.core.config_governance import manifest as _m

        service = _m.detect_service()
        published = _m.publish_manifest(service)

        # Report-only: which required-for-this-service vars are missing locally?
        local = _m.build_local_manifest(service)
        presence = local["presence"]
        missing = []
        for spec in _c.required_for(service):
            p = presence.get(spec.name, _m.ABSENT)
            ok = p == _m.PRESENT or (p == _m.EMPTY and spec.empty_valid)
            if not ok:
                missing.append((spec, p))

        if missing:
            names = ", ".join(f"{s.name}[{s.severity}]" for s, _p in missing)
            logger.warning(
                "CONFIG GOVERNANCE (report-only): service=%s missing required "
                "config: %s (manifest_published=%s). No secret values logged.",
                service, names, published,
            )
        else:
            logger.info(
                "CONFIG GOVERNANCE: service=%s all required config present "
                "(manifest_published=%s).", service, published,
            )

        # Deferred, flag-gated fatal enforcement (default OFF → report-only).
        if getattr(settings, "CONFIG_GOVERNANCE_ENFORCE_STARTUP", False):
            fatal = [s for s, _p in missing if s.fail_startup]
            if fatal:
                from django.core.exceptions import ImproperlyConfigured
                raise ImproperlyConfigured(
                    "Configuration governance: service '%s' is missing required "
                    "startup configuration: %s. Affected capability: %s. "
                    "Remediation: %s" % (
                        service,
                        ", ".join(s.name for s in fatal),
                        "; ".join(sorted({s.capability for s in fatal})),
                        " ".join(sorted({s.remediation for s in fatal if s.remediation})),
                    )
                )
        return {"service": service, "published": published,
                "missing": [s.name for s, _p in missing]}
    except Exception as e:
        # Re-raise ONLY a deliberate enforcement failure; never let telemetry
        # plumbing break startup.
        from django.core.exceptions import ImproperlyConfigured
        if isinstance(e, ImproperlyConfigured):
            raise
        logger.debug("config governance startup hook failed softly: %s", e)
        return {"service": "unknown", "published": False, "error": str(e)[:200]}
