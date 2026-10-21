#!/usr/bin/env python3
"""
Full logical backup of a WLJ Postgres database + an exact verification manifest.

- pg_dump runs on an EXPORTED SNAPSHOT; the manifest's row counts, max ids and
  sequence values are read in that same snapshot, so a restore can be checked
  for exact equality (not "roughly the same").
- Read-only session. Output directory is created 0700, files 0600, and the
  script refuses to write inside a git work tree (backup data never lands in Git).
- The connection string comes from the WLJ_PG_URL environment variable and is
  never printed; the password is passed to pg_dump via PGPASSWORD, not argv.

Usage:
    WLJ_PG_URL=postgresql://... python3 scripts/ops/wlj_db_backup.py [--out-dir ~/WLJ-Backups]

Requires pg_dump >= the server major version (Homebrew postgresql@18 dumps 17).
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2

DEFAULT_PG_BIN = "/opt/homebrew/opt/postgresql@18/bin"


def pg_env(url: str) -> dict:
    u = urlparse(url)
    env = dict(os.environ)
    env.update(
        PGHOST=u.hostname or "",
        PGPORT=str(u.port or 5432),
        PGUSER=unquote(u.username or ""),
        PGPASSWORD=unquote(u.password or ""),
        PGDATABASE=(u.path or "/").lstrip("/"),
    )
    if u.hostname not in ("localhost", "127.0.0.1", None, ""):
        env.setdefault("PGSSLMODE", "prefer")
    return env


def inside_git(path: Path) -> bool:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
    ).returncode == 0


def build_manifest(cur) -> dict:
    cur.execute("select version(), current_database(), pg_database_size(current_database()), now()")
    version, db, size, now = cur.fetchone()
    cur.execute(
        "select schemaname, relname from pg_stat_user_tables where schemaname = 'public' order by relname"
    )
    tables = {}
    for schema, rel in cur.fetchall():
        ident = f'"{schema}"."{rel}"'
        cur.execute(f"select count(*) from {ident}")
        count = cur.fetchone()[0]
        cur.execute(
            "select 1 from information_schema.columns where table_schema=%s and table_name=%s "
            "and column_name='id' and data_type in ('smallint', 'integer', 'bigint')",
            (schema, rel),
        )
        max_id = None
        if cur.fetchone():
            cur.execute(f"select max(id)::text from {ident}")
            max_id = cur.fetchone()[0]
        tables[rel] = {"rows": count, "max_id": max_id}
    cur.execute("select sequencename, last_value from pg_sequences where schemaname = 'public'")
    sequences = {name: last for name, last in cur.fetchall()}
    return {
        "server_version": version,
        "database": db,
        "database_bytes": size,
        "snapshot_time": now.isoformat(),
        "tables": tables,
        "sequences": sequences,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(Path.home() / "WLJ-Backups"))
    ap.add_argument("--pg-bin", default=DEFAULT_PG_BIN)
    ap.add_argument("--label", default="wlj")
    args = ap.parse_args()

    url = os.environ.get("WLJ_PG_URL")
    if not url:
        print("WLJ_PG_URL is not set", file=sys.stderr)
        return 2

    out = Path(args.out_dir).expanduser().resolve()
    os.umask(0o077)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    if inside_git(out):
        print(f"Refusing: {out} is inside a git work tree", file=sys.stderr)
        return 2

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump_path = out / f"{args.label}-{stamp}.dump"
    manifest_path = out / f"{args.label}-{stamp}.manifest.json"
    env = pg_env(url)

    conn = psycopg2.connect(url)
    conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
    cur = conn.cursor()
    cur.execute("set statement_timeout = '15min'")
    cur.execute("select pg_export_snapshot()")
    snapshot = cur.fetchone()[0]

    started = dt.datetime.now(dt.timezone.utc)
    dump = subprocess.Popen(
        [f"{args.pg_bin}/pg_dump", "--snapshot", snapshot, "--format=custom", "--compress=6",
         "--no-password", "--file", str(dump_path)],
        env=env,
    )
    print(f"pg_dump started (snapshot {snapshot}); building manifest in the same snapshot...")
    try:
        manifest = build_manifest(cur)  # same snapshot as the dump: exact counts
        rc = dump.wait()  # the exporting transaction must stay open until pg_dump finishes
    except BaseException:
        dump.kill()
        dump.wait()
        dump_path.unlink(missing_ok=True)
        raise
    finally:
        conn.rollback()
        conn.close()
    if rc != 0:
        print(f"pg_dump failed with exit code {rc}", file=sys.stderr)
        return rc

    sha = hashlib.sha256()
    with open(dump_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    manifest.update(
        dump_file=dump_path.name,
        dump_bytes=dump_path.stat().st_size,
        dump_sha256=sha.hexdigest(),
        pg_dump_version=subprocess.run([f"{args.pg_bin}/pg_dump", "--version"], capture_output=True, text=True).stdout.strip(),
        started_at=started.isoformat(),
        finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    manifest_path.write_text(json.dumps(manifest, indent=1, default=str))
    os.chmod(dump_path, 0o600)
    os.chmod(manifest_path, 0o600)
    print(f"OK  dump={dump_path} ({manifest['dump_bytes'] / 1e6:.0f} MB) tables={len(manifest['tables'])}")
    print(f"    manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
