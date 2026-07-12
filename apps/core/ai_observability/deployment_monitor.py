"""
Deployment & Version Health — OPS-9.

Answers, from inside the running process and WITHOUT any external API call:
  * "What version is actually running?"  → the running commit SHA + environment.
  * "Did the last deployment succeed?"   → migrations all applied (the release's
    `migrate` step completed) AND the process is running.
  * "Can I trust production?"            → running SHA + migration status + a
    self-observed deploy-change log.

Evidence-driven scope (investigated 2026-07-12 — the roadmap was partly outside
what a running process can know)
------------------------------------------------------------------------------
A running Django process can deterministically know only:
  * `RAILWAY_GIT_COMMIT_SHA` (the commit this process was built from — the single
    most valuable deployment truth), `RAILWAY_ENVIRONMENT`, runtime versions.
  * Migration status (reuses OPS-5 `db_health._probe_migrations`) — unapplied
    migrations = a partial/failed deploy (the release `migrate` step didn't
    complete). This is the honest, deterministic "deploy fully succeeded?" signal.
  * A **self-observed** deploy history: the SAME cycle records the running SHA; when
    it changes (a new deploy = a new process with a new SHA), we log the transition.
    No GitHub/Railway poll, no external dependency.

**Deliberately NOT built (would fabricate state or require external polling):**
build status / build duration / build failures (Railway build-runner's domain —
invisible to a running process); failed deployments (a failed deploy means the OLD
process keeps running; detecting it needs a GitHub poll for the "expected" SHA —
forbidden); deploy duration; rollback availability/state. These are Railway/operator
truth, not WLJ truth. The card labels them as external where relevant.

Architecture (matches OPS-2 / OPS-5 / OPS-8): background-cycle only, cache-guarded,
deterministic reads, degrades gracefully, never raises. Telemetry-only — no
`OpsAnomaly`, no recovery, no new persistence (the deploy marker is a cache key).
Request-path safe.

Project: Whole Life Journey
Path: apps/core/ai_observability/deployment_monitor.py
"""

import logging
import os
import sys

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

_TELEMETRY_CACHE_KEY = "wlj:ops:deployment"
_TELEMETRY_TTL = 300  # 5 min
# Self-observed deploy marker — long-lived (survives redeploys via Redis).
_DEPLOY_MARKER_KEY = "wlj:ops:deploy_marker"
_DEPLOY_MARKER_TTL = 60 * 60 * 24 * 30  # 30 days


def _running_sha():
    return os.environ.get("RAILWAY_GIT_COMMIT_SHA", "") or "development"


def _running_version():
    """Deterministic facts about the running build (env + runtime)."""
    import django

    sha = _running_sha()
    return {
        "commit_sha": sha,
        "commit_short": sha[:12],
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "") or "local",
        "django_version": django.get_version(),
        "python_version": sys.version.split()[0],
        "is_railway": bool(os.environ.get("RAILWAY_GIT_COMMIT_SHA")),
    }


def _deploy_detection(now, sha):
    """Self-observed deploy history via SHA-change tracking (no external call).

    Records when the current running SHA was first observed and the previous SHA it
    replaced — a lightweight, deterministic deploy log the app builds from its own
    observation.
    """
    try:
        marker = cache.get(_DEPLOY_MARKER_KEY)
        now_iso = now.isoformat()
        if not marker or not isinstance(marker, dict):
            marker = {"sha": sha, "first_seen": now_iso, "prev_sha": None, "prev_seen": None}
            cache.set(_DEPLOY_MARKER_KEY, marker, timeout=_DEPLOY_MARKER_TTL)
        elif marker.get("sha") != sha:
            # A deploy transition just became observable.
            marker = {
                "sha": sha,
                "first_seen": now_iso,
                "prev_sha": marker.get("sha"),
                "prev_seen": marker.get("first_seen"),
            }
            cache.set(_DEPLOY_MARKER_KEY, marker, timeout=_DEPLOY_MARKER_TTL)

        first_seen = marker.get("first_seen")
        observed_for_s = None
        if first_seen:
            try:
                from django.utils.dateparse import parse_datetime
                dt = parse_datetime(first_seen)
                if dt:
                    observed_for_s = int((now - dt).total_seconds())
            except Exception:
                pass
        return {
            "current_first_observed": first_seen,
            "observed_for_s": observed_for_s,
            "previous_sha": (marker.get("prev_sha") or "")[:12] or None,
            "previous_seen": marker.get("prev_seen"),
        }
    except Exception as e:
        logger.debug("OPS-9 deploy detection failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _migration_status():
    """Reuse OPS-5's deterministic unapplied-migration probe (Constitution IV.3)."""
    try:
        from apps.core.ai_observability.db_health_monitor import _probe_migrations
        return _probe_migrations()
    except Exception as e:
        logger.debug("OPS-9 migration status failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def get_deployment_telemetry(now=None):
    """Build the ``deployment`` Ops Wall section (OPS-9)."""
    cached = cache.get(_TELEMETRY_CACHE_KEY)
    if cached is not None:
        return cached

    now = now or timezone.now()
    running = _running_version()
    deploy = _deploy_detection(now, running["commit_sha"])
    migrations = _migration_status()

    # Deterministic "did the deploy fully succeed?": the process is running (so its
    # build+release started this code) AND migrations are applied. Unapplied
    # migrations ⇒ the release `migrate` step didn't complete ⇒ partial deploy.
    mig_status = migrations.get("status", "UNAVAILABLE")
    status = "CRITICAL" if mig_status == "CRITICAL" else "HEALTHY"

    result = {
        "status": status,
        "running": running,
        "deploy": deploy,
        "migrations": migrations,
        # Honest boundary note for operators.
        "external_note": (
            "build status / failed deploys / rollback are Railway-side, not "
            "knowable from a running process; not shown to avoid fabrication"
        ),
        "measured_at": now.isoformat(),
    }
    cache.set(_TELEMETRY_CACHE_KEY, result, timeout=_TELEMETRY_TTL)
    return result
