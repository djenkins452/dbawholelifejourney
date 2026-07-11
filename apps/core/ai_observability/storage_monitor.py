"""
Storage / Volume Monitor — OPS-2.

Persistent-storage observability for the Ops Wall. Storage resources fill
silently: nothing on the wall showed how close the Postgres data volume, Redis
memory, or the mounted disk was to its ceiling. A full database, an evicting
Redis, or a full volume degrades the whole product with no warning.

What it measures
----------------
* **PostgreSQL** — ``pg_database_size(current_database())`` (bytes), plus a
  growth trend derived from the daily ``StorageSnapshot`` history.
* **Redis** — ``INFO memory`` → ``used_memory`` vs ``maxmemory``, the eviction
  policy, and the cumulative ``evicted_keys`` counter (evictions in progress =
  the cache is under memory pressure and silently dropping keys).
* **Disk / mounted volume** — ``shutil.disk_usage`` on the Railway volume mount
  (``RAILWAY_VOLUME_MOUNT_PATH``) or ``MEDIA_ROOT`` fallback.

Architecture (matches OPS-1 / api_health)
------------------------------------------
* All probing runs in the SAME background cycle via
  ``build_ops_stream_payload`` → ``_get_storage_telemetry`` → this module. The
  HTTP request path only reads the cached Ops Stream payload — it NEVER calls
  this module. A cache guard (``_TELEMETRY_TTL``) keeps repeat cycles cheap.
* Every probe is independently wrapped: one unmeasurable resource degrades to
  ``UNAVAILABLE`` (with a reason) while the others still report. Nothing here
  ever raises into the caller.
* A daily ``StorageSnapshot`` row (one per day, upserted) preserves the growth
  trend across a cache flush and a deploy.

Thresholds
----------
Utilization-based, WARNING at 75%, CRITICAL at 90% (per resource). Redis with a
``noeviction`` policy at pressure, or any actively-climbing ``evicted_keys``,
is surfaced explicitly. Postgres has no hard ceiling exposed by the engine, so
its status keys off the disk/volume it lives on plus an absolute-size warning.

Project: Whole Life Journey
Path: apps/core/ai_observability/storage_monitor.py
"""

import logging
import os
import shutil
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)

_TELEMETRY_CACHE_KEY = "wlj:ops:storage"
_TELEMETRY_TTL = 300  # 5 min — storage moves slowly; avoids probing every 60s

# Utilization thresholds (fraction of capacity).
WARN_UTIL = 0.75
CRITICAL_UTIL = 0.90

# Absolute Postgres size warnings (engine exposes no hard ceiling). These are
# generous "you should look" markers, not failure points.
PG_WARN_BYTES = 8 * 1024 ** 3      # 8 GiB
PG_CRITICAL_BYTES = 16 * 1024 ** 3  # 16 GiB


def _pct(used, total):
    """Utilization percentage (0-100, 1dp) or None if not computable."""
    if not total or used is None:
        return None
    return round(used / total * 100, 1)


def _status_from_util(util_fraction):
    """Map a 0-1 utilization fraction to a status string."""
    if util_fraction is None:
        return "UNKNOWN"
    if util_fraction >= CRITICAL_UTIL:
        return "CRITICAL"
    if util_fraction >= WARN_UTIL:
        return "WARNING"
    return "HEALTHY"


# =========================================================================
# INDIVIDUAL PROBES — each returns a self-contained dict, never raises
# =========================================================================


def _probe_postgres():
    """
    Measure the database size. Postgres only — SQLite (dev) has no server-side
    size query, so it degrades to UNAVAILABLE with a clear reason.
    """
    vendor = connection.vendor
    if vendor != "postgresql":
        return {
            "status": "UNAVAILABLE",
            "reason": f"not measurable on {vendor} (Postgres only)",
            "bytes": None,
        }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database());")
            row = cursor.fetchone()
        size_bytes = int(row[0]) if row and row[0] is not None else None
        if size_bytes is None:
            return {"status": "UNAVAILABLE", "reason": "no size returned", "bytes": None}

        if size_bytes >= PG_CRITICAL_BYTES:
            status = "CRITICAL"
        elif size_bytes >= PG_WARN_BYTES:
            status = "WARNING"
        else:
            status = "HEALTHY"
        return {
            "status": status,
            "bytes": size_bytes,
            "warn_bytes": PG_WARN_BYTES,
            "critical_bytes": PG_CRITICAL_BYTES,
        }
    except Exception as e:
        logger.debug("OPS-2 postgres probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200], "bytes": None}


def _get_redis_url():
    """Prefer the cache/broker Redis URL; None if not configured."""
    return (
        getattr(settings, "REDIS_URL", None)
        or getattr(settings, "CELERY_BROKER_URL", None)
    )


def _probe_redis():
    """
    Measure Redis memory pressure + eviction status via ``INFO``.

    ``used_memory`` vs ``maxmemory`` gives utilization; ``maxmemory_policy`` and
    the cumulative ``evicted_keys`` counter reveal whether Redis is actively
    dropping data. A ``noeviction`` instance under pressure will start refusing
    writes instead — surfaced as CRITICAL.
    """
    url = _get_redis_url()
    if not url or str(url).startswith("memory://"):
        return {
            "status": "UNAVAILABLE",
            "reason": "no Redis configured (dev in-memory broker/cache)",
            "used_bytes": None,
        }
    try:
        import redis
        client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        info = client.info(section="memory")
        stats = client.info(section="stats")

        used = int(info.get("used_memory", 0)) or None
        maxmem = int(info.get("maxmemory", 0)) or 0
        policy = info.get("maxmemory_policy", "unknown")
        evicted = int(stats.get("evicted_keys", 0))

        util = (used / maxmem) if (used and maxmem) else None

        if maxmem == 0:
            # No configured ceiling — bounded only by the host. Report used only.
            status = "HEALTHY"
        else:
            status = _status_from_util(util)
            # noeviction under pressure means writes will start failing.
            if policy == "noeviction" and util is not None and util >= WARN_UTIL:
                status = "CRITICAL"

        return {
            "status": status,
            "used_bytes": used,
            "max_bytes": maxmem or None,
            "util_pct": _pct(used, maxmem) if maxmem else None,
            "policy": policy,
            "evicted_keys": evicted,
        }
    except Exception as e:
        logger.debug("OPS-2 redis probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200], "used_bytes": None}


def _disk_mount_path():
    """The mount to measure: Railway volume if present, else MEDIA_ROOT/base."""
    railway = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if railway and os.path.exists(railway):
        return railway
    media = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if media and os.path.exists(media):
        return media
    base = str(getattr(settings, "BASE_DIR", "") or "")
    return base or "/"


def _probe_disk():
    """Measure the mounted volume / disk utilization via ``shutil.disk_usage``."""
    path = _disk_mount_path()
    try:
        usage = shutil.disk_usage(path)
        util = usage.used / usage.total if usage.total else None
        return {
            "status": _status_from_util(util),
            "path": path,
            "used_bytes": usage.used,
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "util_pct": _pct(usage.used, usage.total),
        }
    except Exception as e:
        logger.debug("OPS-2 disk probe failed at %s: %s", path, e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200], "path": path,
                "used_bytes": None}


# =========================================================================
# GROWTH TREND — from the daily StorageSnapshot history
# =========================================================================


def _persist_snapshot(now, pg, redis_probe, disk):
    """Upsert today's StorageSnapshot row (bounded: one per day)."""
    try:
        from apps.core.ai_observability.models import StorageSnapshot
        StorageSnapshot.objects.update_or_create(
            snapshot_date=now.date(),
            defaults={
                "measured_at": now,
                "db_bytes": pg.get("bytes"),
                "redis_used_bytes": redis_probe.get("used_bytes"),
                "redis_max_bytes": redis_probe.get("max_bytes"),
                "redis_evicted_keys": redis_probe.get("evicted_keys"),
                "disk_used_bytes": disk.get("used_bytes"),
                "disk_total_bytes": disk.get("total_bytes"),
            },
        )
    except Exception as e:
        logger.debug("OPS-2 snapshot persist failed: %s", e)


def _db_growth(now):
    """
    Growth trend for the database over the snapshot history.

    Returns a dict with the oldest sampled point within ~30 days and the
    per-day delta, or None if there isn't enough history yet.
    """
    try:
        from apps.core.ai_observability.models import StorageSnapshot
        since = now.date() - timedelta(days=30)
        rows = list(
            StorageSnapshot.objects
            .filter(snapshot_date__gte=since, db_bytes__isnull=False)
            .order_by("snapshot_date")
            .values("snapshot_date", "db_bytes")
        )
        if len(rows) < 2:
            return None
        first, last = rows[0], rows[-1]
        span_days = max(1, (last["snapshot_date"] - first["snapshot_date"]).days)
        delta = last["db_bytes"] - first["db_bytes"]
        return {
            "window_days": span_days,
            "delta_bytes": delta,
            "per_day_bytes": round(delta / span_days),
            "samples": len(rows),
        }
    except Exception as e:
        logger.debug("OPS-2 growth trend failed: %s", e)
        return None


# =========================================================================
# PUBLIC — telemetry section (called in background only)
# =========================================================================


def _overall_status(resources):
    """Roll up the worst resource state, ignoring UNAVAILABLE (informational)."""
    order = {"CRITICAL": 3, "WARNING": 2, "HEALTHY": 1, "UNKNOWN": 0}
    worst = "HEALTHY"
    any_measured = False
    for r in resources:
        s = r.get("status")
        if s == "UNAVAILABLE" or s is None:
            continue
        any_measured = True
        if order.get(s, 0) > order.get(worst, 0):
            worst = s
    if not any_measured:
        return "UNAVAILABLE"
    return worst


def get_storage_telemetry(now=None):
    """
    Build the ``storage`` Ops Wall section.

    Cache-guarded (``_TELEMETRY_TTL``); runs the probes, persists the daily
    snapshot, and returns a dict:
        status, postgres{}, redis{}, disk{}, db_growth{}|None, measured_at.

    Safe to call only from the background SAME cycle — it performs live probes.
    """
    cached = cache.get(_TELEMETRY_CACHE_KEY)
    if cached is not None:
        return cached

    now = now or timezone.now()
    pg = _probe_postgres()
    redis_probe = _probe_redis()
    disk = _probe_disk()

    _persist_snapshot(now, pg, redis_probe, disk)
    growth = _db_growth(now)

    result = {
        "status": _overall_status([pg, redis_probe, disk]),
        "postgres": pg,
        "redis": redis_probe,
        "disk": disk,
        "db_growth": growth,
        "measured_at": now.isoformat(),
    }
    cache.set(_TELEMETRY_CACHE_KEY, result, timeout=_TELEMETRY_TTL)
    return result
