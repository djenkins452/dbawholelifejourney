"""
Database Health / Administration Monitor — OPS-5.

OPS-2 (`storage_monitor`) answers *"how big is Postgres and how fast is it
growing?"* — capacity. OPS-5 answers the operational-health question capacity
can't: *"is the database administratively healthy right now?"* Connection-pool
saturation, long-running/stuck queries, dead-tuple bloat + autovacuum lag, and a
failed/partial migration are all silent, product-degrading conditions that never
showed on the Ops Wall.

What it measures (all cheap `pg_stat_*` system views / Django state)
--------------------------------------------------------------------
* **Connections** — `pg_stat_activity`: total / active / idle / idle-in-transaction
  for the current database, vs `max_connections` (pool saturation → refused
  connections downstream).
* **Long-running queries** — the oldest active client query's age + a count of
  active client queries over a threshold (stuck / runaway queries).
* **Dead tuples / bloat** — `pg_stat_user_tables`: top tables by `n_dead_tup`,
  worst dead-tuple ratio, and autovacuum age (vacuum falling behind).
* **Migrations** — Django `MigrationExecutor`: any unapplied migration means a
  partial/failed deploy — an incident-worthy condition currently invisible.

Architecture (matches OPS-1 / OPS-2 / api_health)
-------------------------------------------------
* All probing runs ONLY in the SAME background cycle via
  `build_ops_stream_payload → _get_db_health_telemetry → this module`. The HTTP
  request path only reads the cached Ops Stream payload — it NEVER calls this
  module. Cache-guarded (`_TELEMETRY_TTL`) so repeat cycles are cheap.
* Every probe is independently wrapped: one unmeasurable probe degrades to
  `UNAVAILABLE` (with a reason) while the others still report. Nothing here ever
  raises into the caller.
* **Telemetry-only** — like OPS-2/3/4, this is a read-only health section. It does
  NOT emit `OpsAnomaly` incidents and has NO recovery (detection stays separate
  from recovery; DB-admin issues are operator/infra fixes, not safe auto-actions).
* **Backup verification is intentionally NOT here** — Railway manages Postgres
  backups and no in-DB query can confirm a backup succeeded. It remains an
  operator-only check (see `WLJ_OPS_WALL_COVERAGE.md`), not a fabricated status.

Project: Whole Life Journey
Path: apps/core/ai_observability/db_health_monitor.py
"""

import logging

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

# Reuse OPS-2's shared status/threshold helpers (Constitution IV.3 — reuse before
# rebuilding). These are generic utilization → status mappers, not storage-specific.
from apps.core.ai_observability.storage_monitor import (
    CRITICAL_UTIL,
    WARN_UTIL,
    _overall_status,
    _pct,
    _status_from_util,
)

logger = logging.getLogger(__name__)

_TELEMETRY_CACHE_KEY = "wlj:ops:db_health"
_TELEMETRY_TTL = 300  # 5 min — DB admin state moves slowly; avoid probing every 60s

# Long-running query thresholds (seconds).
LONG_WARN_SECS = 60
LONG_CRIT_SECS = 300

# Dead-tuple bloat thresholds (ratio of dead/(live+dead), min absolute dead tuples).
DEAD_MIN_TUPLES = 1000
DEAD_WARN_RATIO = 0.20
DEAD_CRIT_RATIO = 0.50


def _pg_only(probe_name):
    """Guard: these probes are Postgres-only; dev SQLite degrades to UNAVAILABLE."""
    vendor = connection.vendor
    if vendor != "postgresql":
        return {
            "status": "UNAVAILABLE",
            "reason": f"{probe_name} not measurable on {vendor} (Postgres only)",
        }
    return None


# =========================================================================
# INDIVIDUAL PROBES — each returns a self-contained dict, never raises
# =========================================================================


def _probe_connections():
    """Connection-pool saturation via pg_stat_activity vs max_connections."""
    guard = _pg_only("connections")
    if guard:
        return guard
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    count(*) AS total,
                    count(*) FILTER (WHERE state = 'active') AS active,
                    count(*) FILTER (WHERE state = 'idle') AS idle,
                    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_txn
                FROM pg_stat_activity
                WHERE datname = current_database();
                """
            )
            total, active, idle, idle_in_txn = cursor.fetchone()
            cursor.execute("SELECT setting::int FROM pg_settings WHERE name = 'max_connections';")
            row = cursor.fetchone()
            max_conn = int(row[0]) if row and row[0] is not None else None

        util = (total / max_conn) if (max_conn and total is not None) else None
        return {
            "status": _status_from_util(util),
            "total": total,
            "active": active,
            "idle": idle,
            "idle_in_transaction": idle_in_txn,
            "max_connections": max_conn,
            "util_pct": _pct(total, max_conn) if max_conn else None,
        }
    except Exception as e:
        logger.debug("OPS-5 connections probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _probe_long_running():
    """Oldest active client query age + count over threshold (stuck/runaway)."""
    guard = _pg_only("long-running queries")
    if guard:
        return guard
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COALESCE(MAX(EXTRACT(EPOCH FROM (now() - query_start))), 0) AS max_secs,
                    count(*) FILTER (
                        WHERE EXTRACT(EPOCH FROM (now() - query_start)) > %s
                    ) AS over_threshold
                FROM pg_stat_activity
                WHERE state = 'active'
                  AND backend_type = 'client backend'
                  AND query NOT ILIKE %s;
                """,
                [LONG_WARN_SECS, "%pg_stat_activity%"],
            )
            max_secs, over_threshold = cursor.fetchone()
        max_secs = float(max_secs or 0)
        if max_secs >= LONG_CRIT_SECS:
            status = "CRITICAL"
        elif max_secs >= LONG_WARN_SECS:
            status = "WARNING"
        else:
            status = "HEALTHY"
        return {
            "status": status,
            "max_secs": round(max_secs, 1),
            "over_threshold": int(over_threshold or 0),
            "threshold_secs": LONG_WARN_SECS,
        }
    except Exception as e:
        logger.debug("OPS-5 long-running probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _probe_dead_tuples():
    """Dead-tuple bloat + autovacuum age from pg_stat_user_tables."""
    guard = _pg_only("dead tuples")
    if guard:
        return guard
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relname, n_dead_tup, n_live_tup, last_autovacuum
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 0
                ORDER BY n_dead_tup DESC
                LIMIT 5;
                """
            )
            rows = cursor.fetchall()

        tables = []
        worst_ratio = 0.0
        status = "HEALTHY"
        for relname, n_dead, n_live, last_autovac in rows:
            n_dead = int(n_dead or 0)
            n_live = int(n_live or 0)
            ratio = (n_dead / (n_dead + n_live)) if (n_dead + n_live) else 0.0
            tables.append({
                "table": relname,
                "dead": n_dead,
                "live": n_live,
                "dead_ratio_pct": round(ratio * 100, 1),
                "last_autovacuum": last_autovac.isoformat() if last_autovac else None,
            })
            if n_dead >= DEAD_MIN_TUPLES and ratio > worst_ratio:
                worst_ratio = ratio
        if worst_ratio >= DEAD_CRIT_RATIO:
            status = "CRITICAL"
        elif worst_ratio >= DEAD_WARN_RATIO:
            status = "WARNING"
        return {
            "status": status,
            "worst_dead_ratio_pct": round(worst_ratio * 100, 1),
            "top_tables": tables,
        }
    except Exception as e:
        logger.debug("OPS-5 dead-tuple probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _probe_migrations():
    """Unapplied migrations = a partial/failed deploy. Works on any DB vendor."""
    try:
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        unapplied = len(plan)
        return {
            "status": "CRITICAL" if unapplied else "HEALTHY",
            "unapplied": unapplied,
            "all_applied": unapplied == 0,
            # A few names to make a partial deploy diagnosable, bounded.
            "pending": [f"{m.app_label}.{m.name}" for m, _ in plan[:5]],
        }
    except Exception as e:
        logger.debug("OPS-5 migrations probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


# =========================================================================
# PUBLIC — telemetry section (called in background only)
# =========================================================================


def get_db_health_telemetry(now=None):
    """
    Build the ``db_health`` Ops Wall section.

    Cache-guarded (``_TELEMETRY_TTL``); runs the probes and returns:
        status, connections{}, long_running{}, dead_tuples{}, migrations{}, measured_at.

    Safe to call only from the background SAME cycle — it performs live probes.
    """
    cached = cache.get(_TELEMETRY_CACHE_KEY)
    if cached is not None:
        return cached

    now = now or timezone.now()
    connections = _probe_connections()
    long_running = _probe_long_running()
    dead_tuples = _probe_dead_tuples()
    migrations = _probe_migrations()

    result = {
        "status": _overall_status([connections, long_running, dead_tuples, migrations]),
        "connections": connections,
        "long_running": long_running,
        "dead_tuples": dead_tuples,
        "migrations": migrations,
        "measured_at": now.isoformat(),
    }
    cache.set(_TELEMETRY_CACHE_KEY, result, timeout=_TELEMETRY_TTL)
    return result
