"""
Phase 9 Diagnostic: Concurrency test for calendar creation.

Spawns 5 threads, each calling handle_create_event() with identical input.
Reports total rows created, all exceptions raised, and idempotency behavior.
"""

import threading
import traceback

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

NUM_THREADS = 5


class Command(BaseCommand):
    help = "Phase 9 diagnostic: concurrency test for calendar creation"

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write("Phase 9 Concurrency Test")
        self.stdout.write(f"Threads: {NUM_THREADS}")
        self.stdout.write("=" * 70)

        # --- Create test user ---
        email = "phase9conc@test.local"
        User.objects.filter(email=email).delete()

        user = User.objects.create_user(
            email=email,
            password="testpass123",
            first_name="Phase9Conc",
        )
        prefs = user.preferences
        prefs.timezone = "America/New_York"
        prefs.has_completed_onboarding = True
        prefs.save()

        from apps.users.models import TermsAcceptance
        terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=terms_version)

        self.stdout.write(f"\nUser: {user.email} (pk={user.pk})")

        # --- Concurrent create ---
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        self.stdout.write(f"User now: {user_now!r}")
        self.stdout.write(f'Input: title="Concurrent Workout", start_date="wednesday", start_time="06:15"')

        results = {}
        barrier = threading.Barrier(NUM_THREADS, timeout=10)

        def create_event(thread_id):
            from django.db import connection as conn
            try:
                from apps.ai.action_handlers import ActionHandler
                handler = ActionHandler(user)

                barrier.wait()

                result = handler.handle_create_event(
                    title="Concurrent Workout",
                    start_date="wednesday",
                    start_time="06:15",
                )
                results[thread_id] = {
                    "status": "success",
                    "success": result.success,
                    "message": result.message,
                    "created_object": getattr(result, "created_object", None),
                    "error": getattr(result, "error", None),
                }
            except Exception as e:
                results[thread_id] = {
                    "status": "exception",
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            finally:
                conn.close()

        threads = []
        for i in range(NUM_THREADS):
            t = threading.Thread(target=create_event, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # --- Report ---
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("THREAD RESULTS")
        self.stdout.write("=" * 70)

        for tid in sorted(results.keys()):
            r = results[tid]
            self.stdout.write(f"\nThread {tid}:")
            self.stdout.write(f"  Status: {r['status']}")
            if r["status"] == "success":
                self.stdout.write(f"  Success: {r['success']}")
                self.stdout.write(f"  Message: {r['message']}")
                if r.get("created_object"):
                    co = r["created_object"]
                    self.stdout.write(f"  Event ID: {co.get('id')}")
                    self.stdout.write(f"  Reused: {co.get('reused')}")
                if r.get("error"):
                    self.stdout.write(f"  Error: {r['error']}")
            else:
                self.stdout.write(f"  Exception type: {r['type']}")
                self.stdout.write(f"  Exception message: {r['message']}")
                self.stdout.write(f"  Traceback:\n{r['traceback']}")

        # --- DB state ---
        from apps.calendar_engine.models import CalendarEvent
        rows = CalendarEvent.objects.filter(user=user, title="Concurrent Workout")
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"DB STATE: {rows.count()} row(s)")
        self.stdout.write("=" * 70)
        for row in rows:
            self.stdout.write(
                f"  pk={row.pk} title={row.title!r} "
                f"start_dt={row.start_dt!r} "
                f"idempotency_key={row.idempotency_key}"
            )

        # --- Summary ---
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 70)

        successes = sum(1 for r in results.values() if r["status"] == "success" and r.get("success"))
        exceptions = sum(1 for r in results.values() if r["status"] == "exception")
        reused_count = sum(
            1 for r in results.values()
            if r["status"] == "success" and r.get("created_object", {}).get("reused")
        )
        integrity_errors = sum(
            1 for r in results.values()
            if r["status"] == "exception" and r.get("type") == "IntegrityError"
        )
        runtime_errors = sum(
            1 for r in results.values()
            if r["status"] == "exception" and r.get("type") == "RuntimeError"
        )

        self.stdout.write(f"Total threads: {NUM_THREADS}")
        self.stdout.write(f"Successful results: {successes}")
        self.stdout.write(f"Reused (idempotent): {reused_count}")
        self.stdout.write(f"Exceptions: {exceptions}")
        self.stdout.write(f"  IntegrityError: {integrity_errors}")
        self.stdout.write(f"  RuntimeError: {runtime_errors}")
        self.stdout.write(f"DB rows: {rows.count()}")

        self.stdout.write(f"\nRow created: {'YES' if rows.count() > 0 else 'NO'}")
        self.stdout.write(f"IntegrityError occurred: {'YES' if integrity_errors > 0 else 'NO'}")
        self.stdout.write(f"RuntimeError occurred: {'YES' if runtime_errors > 0 else 'NO'}")

        # --- Cleanup ---
        rows.delete()
        user.delete()
        self.stdout.write("\nCleanup done.")
