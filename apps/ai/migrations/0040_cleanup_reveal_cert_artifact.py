# Data migration: remove the single "Reveal Cert" calendar event created on the owner's
# account during the Reveal Target create→reveal smoke (2026-08-18). Identity is PROVEN
# before deletion — owner email + exact (unique) title + created on/after the cert day —
# and the event is SOFT-deleted (recoverable via deleted_at). Idempotent; best-effort.
from datetime import datetime
from datetime import timezone as dt_tz  # NOT django.utils.timezone.utc (removed in Django 5.x)

from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"
CERT_START = datetime(2026, 8, 17, 0, 0, tzinfo=dt_tz.utc)
EVENT_TITLE = "Reveal Cert"


def cleanup(apps, schema_editor):
    User = apps.get_model("users", "User")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except Exception:
        print("  [reveal-cleanup] owner not found — nothing to do")
        return
    try:
        CalendarEvent = apps.get_model("calendar_engine", "CalendarEvent")
        n = (CalendarEvent.objects
             .filter(user=user, title__iexact=EVENT_TITLE, deleted_at__isnull=True,
                     created_at__gte=CERT_START)
             .update(deleted_at=datetime.now(tz=dt_tz.utc)))
        if n:
            print(f"  [reveal-cleanup] soft-deleted CalendarEvent '{EVENT_TITLE}' x{n}")
    except Exception as e:
        print(f"  [reveal-cleanup] skipped: {e!r}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0039_cleanup_phase2_cert_artifacts"),
    ]
    operations = [
        migrations.RunPython(cleanup, noop_reverse),
    ]
