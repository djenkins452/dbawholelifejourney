# ==============================================================================
# File: apps/core/management/commands/prune_telemetry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Operator entry point for telemetry retention (apps/core/data_retention.py)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-10-21
# ==============================================================================
"""
Delete expired telemetry rows per the policies in ``apps/core/data_retention.py``.

Usage:
    python manage.py prune_telemetry --dry-run              # eligible counts, deletes nothing
    python manage.py prune_telemetry --only engine_heartbeat
    python manage.py prune_telemetry --time-budget 3600     # initial backlog run
    python manage.py prune_telemetry --list                 # show policies + rationale

Exits non-zero if any table failed, so a scheduler records the failure.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.data_retention import (
    DEFAULT_BATCH_SIZE,
    POLICIES_BY_KEY,
    RETENTION_POLICIES,
    run_retention,
)


class Command(BaseCommand):
    help = "Delete expired telemetry rows in bounded batches (see apps/core/data_retention.py)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count eligible rows; delete nothing.")
        parser.add_argument(
            "--only", action="append", choices=sorted(POLICIES_BY_KEY), help="Limit to a policy key (repeatable)."
        )
        parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
        parser.add_argument("--max-batches", type=int, default=None, help="Per-table batch cap.")
        parser.add_argument("--time-budget", type=float, default=None, help="Total seconds before stopping cleanly.")
        parser.add_argument("--pause", type=float, default=0.0, help="Seconds to sleep between batches.")
        parser.add_argument("--list", action="store_true", help="List policies and exit.")

    def handle(self, *args, **opts):
        if opts["list"]:
            for p in RETENTION_POLICIES:
                self.stdout.write(f"{p.key:28} {p.model._meta.db_table:34} {p.days():>3}d  {p.rationale}")
            return

        results = run_retention(
            opts["only"],
            dry_run=opts["dry_run"],
            batch_size=opts["batch_size"],
            max_batches=opts["max_batches"],
            time_budget_seconds=opts["time_budget"],
            pause_seconds=opts["pause"],
        )
        mode = "DRY RUN" if opts["dry_run"] else "LIVE"
        self.stdout.write(f"Telemetry retention ({mode})")
        for r in results:
            if r.error:
                line = f"  {r.table:34} FAILED: {r.error}"
            elif opts["dry_run"]:
                line = f"  {r.table:34} keep {r.retention_days:>3}d  eligible={r.eligible}"
            else:
                state = "complete" if r.complete else "PARTIAL (continues next run)"
                line = f"  {r.table:34} keep {r.retention_days:>3}d  deleted={r.deleted} batches={r.batches} {state}"
            self.stdout.write(line)

        failed = [r.key for r in results if r.error]
        if failed:
            raise CommandError(f"Telemetry retention failed for: {', '.join(failed)}")
