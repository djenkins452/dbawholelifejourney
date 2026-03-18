"""
Diagnostic command: audit 7-day workout minutes.

Produces a record-level evidence report showing exactly which WorkoutSession
rows contribute to the canonical 7-day total, detects overlaps, and flags
potential double-counts.
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger("wlj.health.audit")


class Command(BaseCommand):
    help = "Audit 7-day workout minutes for a user (evidence report)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="User email. If omitted, audits all users with recent workouts.",
        )

    def handle(self, *args, **options):
        from apps.health.models import WorkoutSession
        from apps.users.models import User

        now = timezone.now()
        cutoff_7d = now - timedelta(days=7)

        if options["email"]:
            users = User.objects.filter(email=options["email"])
        else:
            # All users with workouts in last 7 days
            user_ids = (
                WorkoutSession.objects.filter(date__gte=cutoff_7d.date())
                .values_list("user_id", flat=True)
                .distinct()
            )
            users = User.objects.filter(id__in=user_ids)

        for user in users:
            self._audit_user(user, cutoff_7d)

    def _audit_user(self, user, cutoff_7d):
        from apps.health.models import WorkoutSession

        self.stdout.write(f"\n{'='*72}")
        self.stdout.write(f"WORKOUT MINUTES AUDIT — {user.email}")
        self.stdout.write(f"7-day window: {cutoff_7d.date()} → {timezone.localdate()}")
        self.stdout.write(f"{'='*72}")

        # Canonical query (matches SAE state_builder exactly)
        canonical_qs = WorkoutSession.objects.filter(
            user=user,
            date__gte=cutoff_7d.date(),
            status="active",
            completed_at__isnull=False,
        ).order_by("date", "started_at")

        # All sessions (including uncompleted / soft-deleted)
        all_qs = WorkoutSession.all_objects.filter(
            user=user,
            date__gte=cutoff_7d.date(),
        ).order_by("date", "started_at")

        canonical_ids = set(canonical_qs.values_list("id", flat=True))
        all_sessions = list(all_qs)
        canonical_sessions = [s for s in all_sessions if s.id in canonical_ids]

        # Evidence table
        self.stdout.write("\n--- ALL WorkoutSession rows in 7-day window ---")
        self.stdout.write(
            f"{'ID':>6}  {'Date':10}  {'Name':20}  {'Type':15}  "
            f"{'Min':>4}  {'Source':12}  {'sync_id':20}  "
            f"{'started_at':>19}  {'completed_at':>19}  {'Status':8}  "
            f"{'Canonical':>9}"
        )
        self.stdout.write("-" * 170)

        total_canonical_min = 0
        total_all_min = 0
        excluded_rows = []
        overlap_groups = []

        for s in all_sessions:
            is_canonical = s.id in canonical_ids
            source_label = self._classify_source(s)
            started = s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "—"
            completed = s.completed_at.strftime("%Y-%m-%d %H:%M") if s.completed_at else "—"
            dur = s.duration_minutes or 0

            marker = "YES" if is_canonical else "NO"
            self.stdout.write(
                f"{s.id:>6}  {s.date!s:10}  {(s.name or '—')[:20]:20}  "
                f"{(s.workout_type or '—')[:15]:15}  "
                f"{dur:>4}  {source_label:12}  {(s.sync_id or '—')[:20]:20}  "
                f"{started:>19}  {completed:>19}  {s.status:8}  "
                f"{marker:>9}"
            )

            if is_canonical:
                total_canonical_min += dur
            else:
                excluded_rows.append(s)
            total_all_min += dur

        self.stdout.write(f"\n--- SUMMARY ---")
        self.stdout.write(f"Canonical sessions (counted):  {len(canonical_sessions)}")
        self.stdout.write(f"Canonical total minutes:       {total_canonical_min}")
        self.stdout.write(f"All sessions (incl excluded):  {len(all_sessions)}")
        self.stdout.write(f"All-sessions total minutes:    {total_all_min}")
        inflation = total_all_min - total_canonical_min
        if inflation > 0:
            self.stdout.write(
                f"INFLATION (before fix):        {inflation} min "
                f"({len(excluded_rows)} excluded rows)"
            )

        # Excluded rows detail
        if excluded_rows:
            self.stdout.write(f"\n--- EXCLUDED ROWS (would inflate if not filtered) ---")
            for s in excluded_rows:
                reason = []
                if s.status != "active":
                    reason.append(f"status={s.status}")
                if not s.completed_at:
                    reason.append("completed_at=NULL")
                self.stdout.write(
                    f"  ID {s.id}: {s.name or s.workout_type or '—'}, "
                    f"{s.duration_minutes or 0} min — reason: {', '.join(reason)}"
                )

        # Overlap detection
        self.stdout.write(f"\n--- OVERLAP DETECTION ---")
        overlap_found = False
        dated = {}
        for s in canonical_sessions:
            dated.setdefault(s.date, []).append(s)

        for d, sessions in sorted(dated.items()):
            if len(sessions) < 2:
                continue
            timestamped = [s for s in sessions if s.started_at and s.completed_at]
            for i, a in enumerate(timestamped):
                for b in timestamped[i + 1:]:
                    if a.started_at < b.completed_at and a.completed_at > b.started_at:
                        overlap_min = min(
                            (a.completed_at - b.started_at).total_seconds(),
                            (b.completed_at - a.started_at).total_seconds(),
                        ) / 60
                        self.stdout.write(
                            f"  OVERLAP on {d}: "
                            f"ID {a.id} ({a.started_at:%H:%M}-{a.completed_at:%H:%M}) ↔ "
                            f"ID {b.id} ({b.started_at:%H:%M}-{b.completed_at:%H:%M}) — "
                            f"~{overlap_min:.0f} min overlap"
                        )
                        overlap_found = True
                        overlap_groups.append((a, b))

        if not overlap_found:
            self.stdout.write("  No time overlaps detected in canonical sessions.")

        # Double-count analysis (manual + HealthKit on same date)
        self.stdout.write(f"\n--- DOUBLE-COUNT RISK ANALYSIS ---")
        double_risk = False
        for d, sessions in sorted(dated.items()):
            manual = [s for s in sessions if not s.sync_id]
            healthkit = [s for s in sessions if s.sync_id]
            if manual and healthkit:
                double_risk = True
                self.stdout.write(
                    f"  {d}: {len(manual)} manual + {len(healthkit)} HealthKit sessions"
                )
                for m in manual:
                    for h in healthkit:
                        if m.started_at and h.started_at and m.completed_at and h.completed_at:
                            if m.started_at < h.completed_at and m.completed_at > h.started_at:
                                self.stdout.write(
                                    f"    LIKELY DUPLICATE: manual ID {m.id} "
                                    f"({m.duration_minutes}min) ↔ "
                                    f"HealthKit ID {h.id} ({h.duration_minutes}min)"
                                )
        if not double_risk:
            self.stdout.write("  No manual+HealthKit same-day pairs found.")

        self.stdout.write("")

        # Also log for production visibility
        logger.info(
            "Workout minutes audit for %s: canonical=%d min (%d sessions), "
            "all=%d min (%d sessions), inflation=%d min",
            user.email,
            total_canonical_min,
            len(canonical_sessions),
            total_all_min,
            len(all_sessions),
            inflation,
        )

    @staticmethod
    def _classify_source(session):
        """Classify a session's likely source."""
        if session.sync_id:
            if session.source == "manual":
                return "merged"
            return "healthkit"
        if session.source == "apple_health":
            return "healthkit"
        return "manual"
