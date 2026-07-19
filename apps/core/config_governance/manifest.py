"""
Per-service configuration manifest — the secret-safe Railway-visibility spine.

WLJ cannot inspect Railway's variable-sharing UI. But each running service CAN
observe its own ``os.environ`` and report **presence only** (never values). Each
service publishes a manifest to shared Redis; the Operations monitor (running in
the worker's SAME cycle) aggregates all manifests to see the whole topology.

Hard rule: a manifest contains NO secret values — only a 3-state presence token
per contract variable: ``present`` (set and non-empty), ``empty`` (set but
blank), ``absent``. Nothing here can leak a credential.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from django.utils import timezone

from apps.core.config_governance import contract as _c

logger = logging.getLogger(__name__)

# Redis-backed, long TTL so a manifest survives between (frequent) redeploys; a
# manifest older than the freshness window is treated as UNKNOWN, never Healthy.
_MANIFEST_PREFIX = "wlj:config:manifest:"
_MANIFEST_TTL = 60 * 60 * 26          # 26h — comfortably spans deploy cadence
FRESH_WINDOW_SECONDS = 60 * 60 * 26   # manifests older than this are stale

PRESENT = "present"
EMPTY = "empty"
ABSENT = "absent"


def detect_service() -> str:
    """Deterministically identify which Railway service this process is.

    Prefers Railway's injected ``RAILWAY_SERVICE_NAME``; falls back to argv
    heuristics (Celery worker/beat vs gunicorn vs manage.py). Never raises.
    """
    name = (os.environ.get("RAILWAY_SERVICE_NAME", "") or "").lower()
    if name:
        if "beat" in name:
            return _c.SERVICE_BEAT
        if "chat" in name and "worker" in name:
            return _c.SERVICE_CHATWORKER
        if "worker" in name:
            return _c.SERVICE_WORKER
        if "build" in name:
            return _c.SERVICE_BUILD
        if "db" in name or "admin" in name:
            return _c.SERVICE_DB_ADMIN
        if "web" in name or "app" in name:
            return _c.SERVICE_WEB
    argv = " ".join(sys.argv).lower()
    if "celery" in argv:
        if "beat" in argv:
            return _c.SERVICE_BEAT
        if "-q chat" in argv or "chat" in argv:
            return _c.SERVICE_CHATWORKER
        return _c.SERVICE_WORKER
    if "gunicorn" in argv or "runserver" in argv:
        return _c.SERVICE_WEB
    if "manage.py" in argv:
        return _c.SERVICE_BUILD
    return _c.SERVICE_WEB


def _presence(var_name: str) -> str:
    if var_name not in os.environ:
        return ABSENT
    return PRESENT if (os.environ.get(var_name) or "").strip() != "" else EMPTY


def build_local_manifest(service: Optional[str] = None) -> dict:
    """Compute this process's secret-safe presence manifest for the contract."""
    service = service or detect_service()
    presence = {v.name: _presence(v.name) for v in _c.CONTRACT}
    return {
        "service": service,
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "") or "local",
        "commit": (os.environ.get("RAILWAY_GIT_COMMIT_SHA", "") or "development")[:12],
        "is_railway": bool(os.environ.get("RAILWAY_GIT_COMMIT_SHA")),
        "presence": presence,           # {var: present|empty|absent} — NO values
        "published_at": timezone.now().isoformat(),
    }


def _redis():
    """Shared Redis client (broker/cache), or None in dev/degraded."""
    from django.conf import settings
    url = (getattr(settings, "CELERY_BROKER_URL", None)
           or getattr(settings, "REDIS_URL", None))
    if not url or str(url).startswith("memory://"):
        return None
    try:
        import redis
        return redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    except Exception as e:
        logger.debug("config manifest: redis unavailable: %s", e)
        return None


def publish_manifest(service: Optional[str] = None) -> bool:
    """Publish this process's manifest to shared Redis. Never raises.

    Fire-and-forget with short timeouts so it can never block or break startup,
    even if Redis is in a post-deploy circuit-open cooldown.
    """
    try:
        import json
        manifest = build_local_manifest(service)
        client = _redis()
        if client is None:
            return False
        client.set(
            _MANIFEST_PREFIX + manifest["service"],
            json.dumps(manifest),
            ex=_MANIFEST_TTL,
        )
        return True
    except Exception as e:
        logger.debug("config manifest publish failed: %s", e)
        return False


def read_all_manifests() -> dict:
    """Read every published service manifest. Returns {service: manifest}.

    Read-only, request-path-safe (a handful of small Redis GETs). Missing Redis
    or missing manifests yield an empty dict — the evaluator turns that into an
    honest UNKNOWN, never a false Healthy.
    """
    out = {}
    try:
        import json
        client = _redis()
        if client is None:
            return out
        for key in client.scan_iter(match=_MANIFEST_PREFIX + "*", count=50):
            try:
                raw = client.get(key)
                if not raw:
                    continue
                m = json.loads(raw)
                if isinstance(m, dict) and m.get("service"):
                    out[m["service"]] = m
            except Exception:
                continue
    except Exception as e:
        logger.debug("config manifest read failed: %s", e)
    return out
