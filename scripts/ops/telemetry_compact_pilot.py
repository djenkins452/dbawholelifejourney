#!/usr/bin/env python3
"""
Compact ONE telemetry table (VACUUM FULL) with hard limits and live monitoring.

VACUUM FULL rewrites the table and its indexes into new files and drops the old
ones, so the space freed by deleted rows goes back to the volume. It holds an
ACCESS EXCLUSIVE lock: every read and write of THAT table waits until it ends.

Two separate limits:
- lock_timeout (default 3s) bounds how long we WAIT to acquire the lock. While
  we wait, later sessions queue behind us, so this is also the most a queued
  session can be held up by our waiting. On expiry nothing has been changed.
- statement_timeout (default 120s) bounds how long the rewrite may RUN while
  holding the lock. On expiry the rewrite is rolled back; the original files
  are untouched and the temporary new files are removed.

Monitor (separate connection, every second): sessions blocked by the VACUUM
(pg_blocking_pids). If any has waited longer than --max-blocked-seconds, or
--health-url fails twice in a row, the VACUUM is cancelled (pg_cancel_backend),
which rolls it back the same way.

Preflight refuses if the estimated temporary space (new heap + toast + indexes
for the LIVE rows, plus the same again as WAL) exceeds a third of
--volume-free-mb.

Usage (dry run prints the plan and estimate; --execute runs it):
    WLJ_PG_URL=... python3 scripts/ops/telemetry_compact_pilot.py --table core_engine_heartbeat \
        --volume-free-mb 41000 --health-url https://wholelifejourney.com/_health/ [--execute]
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.request

import psycopg2

TABLES = {
    "core_engine_heartbeat", "core_system_integrity_snapshot", "core_diag_engine_run", "core_diag_engine_span",
    "core_diag_decision_record", "core_apirequestlog", "core_arbitration_decision_log", "core_healthbriefingsnapshot",
}


def sizes(cur, table):
    cur.execute(
        """select pg_relation_size(c.oid), coalesce(pg_total_relation_size(c.reltoastrelid), 0),
                  pg_indexes_size(c.oid), pg_total_relation_size(c.oid),
                  s.n_live_tup, s.n_dead_tup
           from pg_class c join pg_stat_user_tables s on s.relid = c.oid where c.relname = %s""",
        (table,),
    )
    heap, toast, idx, total, live, dead = cur.fetchone()
    return dict(heap=heap, toast=toast, idx=idx, total=total, live=live, dead=dead)


def estimate_temp_bytes(sz):
    """New files hold only live rows; WAL (wal_level=replica) logs them again."""
    live_fraction = sz["live"] / max(sz["live"] + sz["dead"], 1)
    new_files = (sz["heap"] + sz["toast"] + sz["idx"]) * live_fraction
    return int(new_files * 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, choices=sorted(TABLES))
    ap.add_argument("--lock-timeout", default="3s")
    ap.add_argument("--statement-timeout", default="120s")
    ap.add_argument("--max-blocked-seconds", type=float, default=15.0)
    ap.add_argument("--health-url")
    ap.add_argument("--volume-free-mb", type=float, required=True)
    ap.add_argument("--target-env", default="WLJ_PG_URL")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    url = os.environ.get(args.target_env)
    if not url:
        print(f"{args.target_env} is not set", file=sys.stderr)
        return 2

    conn = psycopg2.connect(url)
    conn.autocommit = True  # VACUUM cannot run inside a transaction block
    cur = conn.cursor()
    cur.execute(f"analyze {args.table}")  # fresh live/dead estimates (no exclusive lock)
    before = sizes(cur, args.table)
    temp = estimate_temp_bytes(before)
    report = {"table": args.table, "before": before, "estimated_temp_bytes": temp,
              "volume_free_mb": args.volume_free_mb, "lock_timeout": args.lock_timeout,
              "statement_timeout": args.statement_timeout, "max_blocked_seconds": args.max_blocked_seconds}
    if temp / 1e6 > args.volume_free_mb / 3:
        report["refused"] = "estimated temporary space exceeds a third of free volume space"
        print(json.dumps(report, indent=1))
        return 2
    if not args.execute:
        report["mode"] = "plan only (pass --execute to run)"
        print(json.dumps(report, indent=1))
        return 0

    cur.execute("select pg_backend_pid()")
    vacuum_pid = cur.fetchone()[0]
    stop = threading.Event()
    watch = {"max_blocked_sessions": 0, "max_blocked_wait_s": 0.0, "health_failures": 0,
             "health_max_ms": 0, "cancelled_reason": None}

    def monitor():
        mon = psycopg2.connect(url)
        mon.autocommit = True
        mcur = mon.cursor()
        consecutive_health_failures = 0
        while not stop.wait(1.0):
            mcur.execute(
                "select count(*), coalesce(max(extract(epoch from now() - query_start)), 0) "
                "from pg_stat_activity where %s = any(pg_blocking_pids(pid))",
                (vacuum_pid,),
            )
            blocked, wait_s = mcur.fetchone()
            watch["max_blocked_sessions"] = max(watch["max_blocked_sessions"], blocked)
            watch["max_blocked_wait_s"] = max(watch["max_blocked_wait_s"], float(wait_s))
            reason = None
            if float(wait_s) > args.max_blocked_seconds:
                reason = f"a session was blocked {float(wait_s):.1f}s (> {args.max_blocked_seconds}s)"
            if args.health_url:
                t0 = time.monotonic()
                try:
                    urllib.request.urlopen(args.health_url, timeout=5).read()
                    consecutive_health_failures = 0
                except Exception:
                    watch["health_failures"] += 1
                    consecutive_health_failures += 1
                watch["health_max_ms"] = max(watch["health_max_ms"], int((time.monotonic() - t0) * 1000))
                if consecutive_health_failures >= 2:
                    reason = "health check failed twice in a row"
            if reason and not watch["cancelled_reason"]:
                watch["cancelled_reason"] = reason
                mcur.execute("select pg_cancel_backend(%s)", (vacuum_pid,))
        mon.close()

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    cur.execute("set lock_timeout = %s", (args.lock_timeout,))
    cur.execute("set statement_timeout = %s", (args.statement_timeout,))
    t0 = time.monotonic()
    outcome = "completed"
    try:
        cur.execute(f"vacuum (full, analyze) {args.table}")
    except psycopg2.errors.LockNotAvailable:
        outcome = "lock not acquired within lock_timeout — nothing changed"
    except psycopg2.errors.QueryCanceled as exc:
        outcome = f"cancelled and rolled back ({watch['cancelled_reason'] or str(exc).strip()})"
    finally:
        stop.set()
        thread.join()
        cur.execute("reset lock_timeout")
        cur.execute("reset statement_timeout")
    report.update(outcome=outcome, held_or_waited_seconds=round(time.monotonic() - t0, 2),
                  after=sizes(cur, args.table), monitor=watch)
    print(json.dumps(report, indent=1, default=str))
    conn.close()
    return 0 if outcome == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
