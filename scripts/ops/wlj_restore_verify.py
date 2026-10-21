#!/usr/bin/env python3
"""
Prove a WLJ backup restores: restore it into an ISOLATED throwaway Postgres
cluster and compare it EXACTLY with the manifest written at backup time.

Isolation: a fresh cluster (initdb) next to the dump, listening on a unix socket
only (listen_addresses=''), so nothing on the network can reach the restored
copy. It is stopped and deleted afterwards unless --keep (needed when the
restored copy is the source for telemetry_recover.py).

Checks: sha256 of the dump; pg_restore exits 0 with --exit-on-error; every
manifest table exists with the same row count and max(id); every sequence has
the restored sequence at least max() of the column it feeds (sequences are not
MVCC, so their exact value on a live database is reported, not compared).

Usage:
    python3 scripts/ops/wlj_restore_verify.py ~/WLJ-Backups/wlj-<stamp>.dump [--keep]
"""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

DEFAULT_PG_BIN = "/opt/homebrew/opt/postgresql@18/bin"


# macOS: the postmaster refuses to start ("became multithreaded") without a valid LC_ALL.
PG_ENV = {**os.environ, "LC_ALL": os.environ.get("LC_ALL") or "en_US.UTF-8"}


def run(cmd, **kw):
    subprocess.run(cmd, check=True, env=PG_ENV, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--manifest")
    ap.add_argument("--pg-bin", default=DEFAULT_PG_BIN)
    ap.add_argument("--port", type=int, default=55432)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--keep", action="store_true", help="Leave the restored cluster running.")
    args = ap.parse_args()

    dump = Path(args.dump).expanduser().resolve()
    manifest_path = Path(args.manifest) if args.manifest else dump.with_suffix("").with_suffix(".manifest.json")
    if not manifest_path.exists():
        manifest_path = Path(str(dump).replace(".dump", ".manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    failures = []

    sha = hashlib.sha256()
    with open(dump, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    if sha.hexdigest() != manifest["dump_sha256"]:
        print("FAIL dump sha256 does not match manifest", file=sys.stderr)
        return 1

    cluster = dump.parent / (dump.stem + ".restore-cluster")
    if cluster.exists():
        print(f"Refusing: {cluster} already exists", file=sys.stderr)
        return 2
    # Unix-socket paths are limited to ~100 bytes; use a short private dir.
    sock = tempfile.mkdtemp(prefix="wljrs-")
    pg = args.pg_bin
    conn_kw = dict(host=sock, port=args.port, user="postgres")
    try:
        run([f"{pg}/initdb", "-D", str(cluster), "-U", "postgres", "-A", "trust", "--no-instructions"],
            stdout=subprocess.DEVNULL)
        cluster.chmod(0o700)
        run([f"{pg}/pg_ctl", "-D", str(cluster), "-l", str(cluster / "server.log"), "-w", "start",
             "-o", f"-p {args.port} -c listen_addresses='' -k {sock}"], stdout=subprocess.DEVNULL)
        run([f"{pg}/createdb", "-h", sock, "-p", str(args.port), "-U", "postgres", "wlj_restore"])
        t0 = time.monotonic()
        run([f"{pg}/pg_restore", "-h", sock, "-p", str(args.port), "-U", "postgres", "-d", "wlj_restore",
             "--no-owner", "--no-acl", "--exit-on-error", "-j", str(args.jobs), str(dump)])
        restore_s = time.monotonic() - t0

        conn = psycopg2.connect(dbname="wlj_restore", **conn_kw)
        cur = conn.cursor()
        for table, expected in manifest["tables"].items():
            cur.execute("select to_regclass(%s)", (f'public."{table}"',))
            if cur.fetchone()[0] is None:
                failures.append(f"missing table {table}")
                continue
            cur.execute(f'select count(*) from public."{table}"')
            rows = cur.fetchone()[0]
            if rows != expected["rows"]:
                failures.append(f"{table}: rows {rows} != {expected['rows']}")
            if expected["max_id"] is not None:
                cur.execute(f'select max(id)::text from public."{table}"')
                got = cur.fetchone()[0]
                if got != expected["max_id"]:
                    failures.append(f"{table}: max(id) {got} != {expected['max_id']}")
        # Sequences are not MVCC: pg_dump records each value when it reaches it,
        # not at the snapshot, so on a live database it can differ from the
        # manifest either way. That difference is reported, not failed. What must
        # hold is "no collision": a restored sequence that has been used is >= the
        # max() of the restored column it feeds; an unused one (NULL) matches prod.
        cur.execute("select sequencename, last_value from pg_sequences where schemaname='public'")
        restored_seq = dict(cur.fetchall())
        drifted = 0
        for name, last in manifest["sequences"].items():
            if name not in restored_seq:
                failures.append(f"sequence {name}: missing")
            elif (last is None) != (restored_seq[name] is None):
                failures.append(f"sequence {name}: used/unused state differs (restored {restored_seq[name]}, prod {last})")
            elif restored_seq[name] != last:
                drifted += 1
        cur.execute(
            """select s.relname, t.relname, a.attname from pg_class s
               join pg_depend d on d.objid = s.oid and d.deptype in ('a', 'i')
               join pg_class t on t.oid = d.refobjid
               join pg_attribute a on a.attrelid = t.oid and a.attnum = d.refobjsubid
               where s.relkind = 'S'"""
        )
        for seq, table, col in cur.fetchall():
            got = restored_seq.get(seq)
            if got is None:
                continue  # unused in production too (checked above)
            cur.execute(f'select max("{col}") from public."{table}"')
            top = cur.fetchone()[0]
            if isinstance(top, int) and got < top:
                failures.append(f"sequence {seq}: restored {got} < max({table}.{col}) {top}")
        print(f"sequences whose value moved between dump and manifest (live writes, expected): {drifted}")
        cur.execute("select pg_database_size('wlj_restore')")
        size = cur.fetchone()[0]
        conn.close()

        print(f"restore took {restore_s:.0f}s; restored size {size / 1e6:.0f} MB; "
              f"tables checked {len(manifest['tables'])}; sequences checked {len(manifest['sequences'])}")
    finally:
        if not args.keep:
            subprocess.run([f"{pg}/pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, env=PG_ENV)
            shutil.rmtree(cluster, ignore_errors=True)
            shutil.rmtree(sock, ignore_errors=True)

    if failures:
        print("FAIL\n  " + "\n  ".join(failures[:50]), file=sys.stderr)
        return 1
    print("PASS rows and max(id) exact for every table; sequences collision-safe")
    if args.keep:
        print(f"restored cluster left running: host={sock} port={args.port} db=wlj_restore user=postgres")
        print(f"stop + delete with: {pg}/pg_ctl -D {cluster} -m fast stop && rm -rf {cluster} {sock}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
