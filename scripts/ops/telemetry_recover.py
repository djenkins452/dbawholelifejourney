#!/usr/bin/env python3
"""
Selectively put deleted telemetry rows back from a VERIFIED restored copy.

Source = the isolated cluster left by ``wlj_restore_verify.py --keep``.
Target = the live database. Dry run by default; ``--apply`` commits.

How it works (pg_restore --data-only cannot redirect rows into a staging
table, so this does not use it):
1. Rows in the requested window are COPYed out of the restored copy.
2. They are COPYed into a TEMP table in the target session (``LIKE`` the live
   table, no defaults/constraints) — session-scoped, so nothing is left behind.
3. In ONE transaction:
   - rows whose foreign-key parent no longer exists (e.g. a user deleted after
     the backup) are dropped from the stage and reported;
   - ``INSERT ... SELECT ... ON CONFLICT DO NOTHING`` — any row whose id (or
     other unique key) already exists is skipped, so rows that were never
     deleted and rows created after the backup are untouched;
   - the id sequence is moved to GREATEST(current value, max(id)) — it never
     moves backwards, so new inserts cannot collide.
4. Dry run reports the same counts and rolls back.

Usage:
    python3 scripts/ops/telemetry_recover.py --source "host=... port=55432 dbname=wlj_restore user=postgres" \
        --target-env WLJ_PG_URL --table core_engine_heartbeat --since 2026-09-01 --until 2026-10-01 [--apply]
"""

import argparse
import os
import sys
import tempfile

import psycopg2
from psycopg2 import sql

# Timestamp column per telemetry table (mirrors apps/core/data_retention.py).
TIMESTAMP_COLUMNS = {
    "core_engine_heartbeat": "observed_at",
    "core_system_integrity_snapshot": "created_at",
    "core_diag_engine_run": "started_at",
    "core_diag_engine_span": "started_at",
    "core_diag_decision_record": "created_at",
    "core_apirequestlog": "created_at",
    "core_arbitration_decision_log": "timestamp",
    "core_healthbriefingsnapshot": "generated_at",
}


def columns(cur, table):
    cur.execute(
        "select column_name, is_nullable, column_default from information_schema.columns "
        "where table_schema='public' and table_name=%s order by ordinal_position",
        (table,),
    )
    return cur.fetchall()


def foreign_keys(cur, table):
    """[(local_column, parent_table, parent_column)] for single-column FKs."""
    cur.execute(
        """
        select a.attname, cf.relname, af.attname
        from pg_constraint c
        join pg_class cl on cl.oid = c.conrelid
        join pg_class cf on cf.oid = c.confrelid
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
        join pg_attribute af on af.attrelid = c.confrelid and af.attnum = c.confkey[1]
        where c.contype = 'f' and cl.relname = %s and array_length(c.conkey, 1) = 1
        """,
        (table,),
    )
    return cur.fetchall()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="libpq DSN of the isolated restored copy")
    ap.add_argument("--target-env", default="WLJ_PG_URL", help="env var holding the target URL")
    ap.add_argument("--table", required=True, choices=sorted(TIMESTAMP_COLUMNS))
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    target_url = os.environ.get(args.target_env)
    if not target_url:
        print(f"{args.target_env} is not set", file=sys.stderr)
        return 2
    table, ts = args.table, TIMESTAMP_COLUMNS[args.table]

    src = psycopg2.connect(args.source)
    src.set_session(readonly=True)
    tgt = psycopg2.connect(target_url)
    scur, tcur = src.cursor(), tgt.cursor()

    tcols = columns(tcur, table)
    scol_names = {c[0] for c in columns(scur, table)}
    missing_required = [c for c, nullable, default in tcols if c not in scol_names and nullable == "NO" and default is None]
    if missing_required:
        print(f"Refusing: target requires columns absent from the backup: {missing_required}", file=sys.stderr)
        return 2
    cols = [c for c, _, _ in tcols if c in scol_names]
    col_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)

    with tempfile.TemporaryFile() as buf:  # stays on this machine, deleted on close
        select = sql.SQL("select {cols} from {t} where {ts} >= %s and {ts} < %s").format(
            cols=col_list, t=sql.Identifier(table), ts=sql.Identifier(ts)
        )
        bound = scur.mogrify(select, (args.since, args.until)).decode()
        scur.copy_expert(f"copy ({bound}) to stdout with (format binary)", buf)
        buf.seek(0)
        tcur.execute(sql.SQL("create temp table recovery_stage (like {t})").format(t=sql.Identifier(table)))
        tcur.copy_expert(
            sql.SQL("copy recovery_stage ({cols}) from stdin with (format binary)").format(cols=col_list).as_string(tgt),
            buf,
        )

    tcur.execute("select count(*) from recovery_stage")
    staged = tcur.fetchone()[0]

    orphans = 0
    for local, parent, parent_col in foreign_keys(tcur, table):
        tcur.execute(
            sql.SQL(
                "delete from recovery_stage s where s.{l} is not null and not exists "
                "(select 1 from {p} x where x.{pc} = s.{l})"
            ).format(l=sql.Identifier(local), p=sql.Identifier(parent), pc=sql.Identifier(parent_col))
        )
        orphans += tcur.rowcount

    tcur.execute(
        sql.SQL("select count(*) from recovery_stage s where exists (select 1 from {t} x where x.id = s.id)")
        .format(t=sql.Identifier(table))
    )
    already_present = tcur.fetchone()[0]

    tcur.execute(
        sql.SQL("insert into {t} ({cols}) select {cols} from recovery_stage on conflict do nothing")
        .format(t=sql.Identifier(table), cols=col_list)
    )
    inserted = tcur.rowcount

    tcur.execute("select pg_get_serial_sequence(%s, 'id')", (table,))
    seq = tcur.fetchone()[0]
    seq_before = seq_after = None
    if seq:
        tcur.execute(sql.SQL("select last_value from {s}").format(s=sql.SQL(seq)))
        seq_before = tcur.fetchone()[0]
        tcur.execute(
            sql.SQL("select setval(%s, greatest((select coalesce(max(id), 1) from {t}), (select last_value from {s})))")
            .format(t=sql.Identifier(table), s=sql.SQL(seq)),
            (seq,),
        )
        seq_after = tcur.fetchone()[0]

    mode = "APPLIED" if args.apply else "DRY RUN (rolled back)"
    print(f"{mode} {table} [{args.since}, {args.until}) staged={staged} fk_orphans_skipped={orphans} "
          f"already_present={already_present} inserted={inserted} sequence {seq_before} -> {seq_after}")
    if args.apply:
        tgt.commit()
    else:
        tgt.rollback()
    tgt.close()
    src.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
