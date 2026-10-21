# WLJ Telemetry Retention — Rollout & Recovery Runbook

Policy and code: `apps/core/data_retention.py` (one registry, one batched purge).
Operator tools: `scripts/ops/` (backup, restore-verify, selective recovery, compaction pilot).
Every stage below is a separate approval. Nothing here runs automatically.

## Outcomes are measured separately

| Outcome | Produced by | Measured by |
|---|---|---|
| Logical deletion (rows gone) | `prune_telemetry` | `prune_telemetry --dry-run` eligible → ~0; `n_live_tup` |
| Disk reclamation (files shrink) | `VACUUM FULL` per table (`telemetry_compact_pilot.py`) | `pg_total_relation_size`, `pg_database_size`, Railway `DISK_USAGE_GB` |
| Billed RAM change | unknown — to be measured | Railway `MEMORY_USAGE_GB` (Postgres service), usage API, invoice |

Deleting rows does not shrink files. Whether compaction (or a restart) lowers billed
memory is a hypothesis under test, not an expected result.

## Stage 0 — Activation is off

`WLJ_TELEMETRY_RETENTION_TABLES` (env, comma list of policy keys, or `all`) is **empty by
default**. With it empty, the nightly task (`core.prune_telemetry`, 03:45 UTC), `prune_telemetry`,
`cleanup_api_logs` and `cleanup_diagnostics` delete nothing and say so. `--dry-run` always works.
Deploying the code changes nothing.

## Stage 1 — Backup (pg_dump) and proven restore

```bash
WLJ_PG_URL=<prod public URL> python3 scripts/ops/wlj_db_backup.py --out-dir ~/WLJ-Backups
python3 scripts/ops/wlj_restore_verify.py ~/WLJ-Backups/wlj-<stamp>.dump
```

- The dump and manifest share one exported snapshot, so verification is exact: every table's
  row count and max(id), and every sequence's last_value.
- The restore goes into a throwaway cluster that listens on a unix socket only. It is deleted
  afterwards.
- `~/WLJ-Backups` is 0700, the files are 0600, and FileVault is on. The script refuses to write
  inside a git work tree. Backup data is never committed and never sent to any external service.
- While the dump runs, production holds one long read-only transaction. That delays vacuum
  cleanup until it ends.

Railway's native backups are whole-volume snapshots: create manually, or schedule DAILY,
WEEKLY or MONTHLY. A restore replaces the whole volume, which loses data written after the
snapshot, so it is a last resort only. As of 2026-10-21 this volume had **no backups and no
schedule**.

## Stage 2 — Activate and delete (one table first)

Set `WLJ_TELEMETRY_RETENTION_TABLES=engine_heartbeat` on **wlj-worker**, which runs the task.
Changing the variable redeploys the worker. Then, from the worker:

```bash
python manage.py prune_telemetry --dry-run
python manage.py prune_telemetry --only engine_heartbeat --time-budget 600 --pause 0.05
```

- Measure the real rows per second from this first run. Local rehearsal timings are **not**
  production timings.
- Widen the variable table by table, and finally set it to `all`. The nightly task then keeps
  the tables trimmed.
- Live runs hold the `telemetry_retention` lock row, so a manual run and the nightly run cannot
  overlap. The nightly run skips with status `busy`; a manual run exits with an error. If the
  lock can't be checked, the run refuses (fail closed). A lock whose holder died goes stale
  after 15 minutes.

## Stage 3 — Compaction pilot: `core_engine_heartbeat` only

```bash
WLJ_PG_URL=... python3 scripts/ops/telemetry_compact_pilot.py --table core_engine_heartbeat \
  --volume-free-mb <from Railway> --health-url https://wholelifejourney.com/_health/ \
  --max-blocked-seconds 10                # plan only; add --execute to run
```

**Limits:**
- `lock_timeout` 3 s: the longest we wait for the lock. Sessions arriving while we wait queue
  behind us for at most that long. If it expires, nothing has changed.
- `statement_timeout` 120 s: the longest the rewrite may hold the lock. If it expires, the
  rewrite rolls back and the original table is untouched.
- Monitor: checks every second for sessions blocked by the compaction. It cancels the run if any
  has waited longer than `--max-blocked-seconds`, or if `/_health/` fails twice in a row. Worst
  case, a blocked session waits about 10 s plus 1–2 s of monitor latency.

**Who touches this table:** the SAME cycle (worker, every 60 s), the recovery handler, and
staff-only Ops Wall reads. End-user requests do not read it directly.

**Abort and do not retry the same day** if the lock isn't acquired, the run is cancelled, or
`/_health/` errors. Report back.

**Temporary space:** the new heap, toast and indexes for the live rows, plus the same amount
again as WAL (`wal_level=replica`). The script refuses if that estimate exceeds a third of
the volume's free space. There is no WAL archiving and no replication slot, so WAL is recycled.

**Afterwards:** watch Railway `MEMORY_USAGE_GB` and `DISK_USAGE_GB` at 1-minute resolution for
60 minutes and record the change. That reading decides whether to compact the other tables.

## Selective recovery of deleted rows

```bash
python3 scripts/ops/wlj_restore_verify.py <dump> --keep        # isolated source copy
WLJ_PG_URL=... python3 scripts/ops/telemetry_recover.py --source "host=<sock> port=55432 dbname=wlj_restore user=postgres" \
  --table <table> --since <ts> --until <ts>                      # dry run; add --apply
```

This does not use `pg_restore --data-only`, which cannot redirect rows into a staging table.
Instead, the rows in the window are COPYed out of the restored copy into a session TEMP table
on the target. Then, in one transaction:
1. Rows whose foreign-key parent was deleted since the backup are dropped and reported.
2. `INSERT ... ON CONFLICT DO NOTHING` adds the rest. Rows that still exist and rows created
   after the backup are left alone.
3. The id sequence is set to the greater of its current value and max(id), so it never moves
   backwards.

Re-running is idempotent. Rehearsed 2026-10-21: overlap, post-backup rows, a deleted user,
an idempotent re-run and a lagging sequence were all handled correctly.

## Rollback of the code

Revert the merge commit and push. There are no migrations. With activation empty, the code is
inert anyway.
