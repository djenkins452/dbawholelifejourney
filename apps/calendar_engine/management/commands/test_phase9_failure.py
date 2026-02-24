"""
Phase 9 Diagnostic: Reproduce calendar creation failure.

Creates a test user with America/New_York timezone and calls
handle_create_event() directly with weekday + time inputs.
Reports stored vs intended start_dt, exception type, and outcome.
"""

import traceback

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Phase 9 diagnostic: reproduce calendar creation failure"

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write("Phase 9 Failure Reproduction")
        self.stdout.write("=" * 70)

        # --- Create test user ---
        email = "phase9diag@test.local"
        User.objects.filter(email=email).delete()

        user = User.objects.create_user(
            email=email,
            password="testpass123",
            first_name="Phase9",
        )
        prefs = user.preferences
        prefs.timezone = "America/New_York"
        prefs.has_completed_onboarding = True
        prefs.save()

        # Accept terms
        from apps.users.models import TermsAcceptance
        terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=terms_version)

        self.stdout.write(f"\nUser created: {user.email} (pk={user.pk})")
        self.stdout.write(f"Timezone: {prefs.timezone}")
        self.stdout.write(f"timezone_iana: {prefs.timezone_iana}")

        # --- Print current user time ---
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        self.stdout.write(f"User now: {user_now!r}")
        self.stdout.write(f"User today weekday: {user_now.strftime('%A')} ({user_now.isoweekday()})")

        # --- Call handle_create_event ---
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(user)

        self.stdout.write("\n--- Calling handle_create_event ---")
        self.stdout.write('  title="Workout"')
        self.stdout.write('  start_date="wednesday"')
        self.stdout.write('  start_time="06:15"')

        exception_raised = None
        result = None

        try:
            result = handler.handle_create_event(
                title="Workout",
                start_date="wednesday",
                start_time="06:15",
            )
        except Exception as e:
            exception_raised = e
            self.stderr.write(f"\n!!! EXCEPTION RAISED !!!")
            self.stderr.write(f"Type: {type(e).__name__}")
            self.stderr.write(f"Message: {e}")
            self.stderr.write(f"\nFull traceback:")
            self.stderr.write(traceback.format_exc())

        # --- Report ---
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("RESULTS")
        self.stdout.write("=" * 70)

        if result is not None:
            self.stdout.write(f"Success: {result.success}")
            self.stdout.write(f"Message: {result.message}")
            if hasattr(result, "created_object") and result.created_object:
                self.stdout.write(f"Created object: {result.created_object}")
                event_id = result.created_object.get("id")
                if event_id:
                    from apps.calendar_engine.models import CalendarEvent
                    try:
                        event = CalendarEvent.objects.get(pk=event_id)
                        self.stdout.write(f"\nStored event:")
                        self.stdout.write(f"  pk: {event.pk}")
                        self.stdout.write(f"  title: {event.title!r}")
                        self.stdout.write(f"  start_dt: {event.start_dt!r}")
                        self.stdout.write(f"  start_dt.tzinfo: {event.start_dt.tzinfo!r}")
                        self.stdout.write(f"  end_dt: {event.end_dt!r}")
                        self.stdout.write(f"  idempotency_key: {event.idempotency_key}")
                        self.stdout.write(f"  reused: {result.created_object.get('reused')}")
                    except CalendarEvent.DoesNotExist:
                        self.stdout.write(f"  EVENT NOT FOUND IN DB (pk={event_id})")
            if hasattr(result, "error") and result.error:
                self.stdout.write(f"Error: {result.error}")
        else:
            self.stdout.write("Result: None (exception raised)")

        if exception_raised:
            self.stdout.write(f"\nException type: {type(exception_raised).__name__}")
            self.stdout.write(f"Exception message: {exception_raised}")

        # --- Check DB for any rows ---
        from apps.calendar_engine.models import CalendarEvent
        rows = CalendarEvent.objects.filter(user=user)
        self.stdout.write(f"\nTotal CalendarEvent rows for user: {rows.count()}")
        for row in rows:
            self.stdout.write(f"  pk={row.pk} title={row.title!r} start_dt={row.start_dt!r}")

        # --- Cleanup ---
        rows.delete()
        user.delete()
        self.stdout.write("\nCleanup done.")
