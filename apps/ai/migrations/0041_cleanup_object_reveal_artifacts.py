# Data migration: remove ONLY the certification artifacts created by the Object-Level Reveal
# smokes (2026-08-18) — the "Reveal Test" journal entry and the 15-minute mobility workout —
# on the OWNER's account. Identity is PROVEN before deletion (owner email + distinctive fields
# + created on/after the cert day) and each object is SOFT-deleted (recoverable via deleted_at).
# Prints what it removed to the deploy log. Idempotent; best-effort per model. If a queued/slow
# acceptance turn creates one of these AFTER this runs, it won't be caught here (remove manually).
from datetime import datetime
from datetime import timezone as dt_tz  # NOT django.utils.timezone.utc (removed in Django 5.x)

from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"
CERT_START = datetime(2026, 8, 17, 0, 0, tzinfo=dt_tz.utc)


def cleanup(apps, schema_editor):
    from django.db.models import Q
    User = apps.get_model("users", "User")
    try:
        user = User.objects.get(email__iexact=OWNER_EMAIL)
    except Exception:
        print("  [objreveal-cleanup] owner not found — nothing to do")
        return
    now = datetime.now(tz=dt_tz.utc)

    # 1) "Reveal Test" journal entry (unique test title).
    try:
        JournalEntry = apps.get_model("journal", "JournalEntry")
        n = (JournalEntry.objects
             .filter(user=user, title__iexact="Reveal Test", deleted_at__isnull=True,
                     created_at__gte=CERT_START)
             .update(deleted_at=now))
        if n:
            print(f"  [objreveal-cleanup] soft-deleted JournalEntry 'Reveal Test' x{n}")
    except Exception as e:
        print(f"  [objreveal-cleanup] JournalEntry skipped: {e!r}")

    # 2) The 15-minute "mobility" workout (distinctive: duration + name/type + cert-day window).
    try:
        WorkoutSession = apps.get_model("health", "WorkoutSession")
        n = (WorkoutSession.objects
             .filter(Q(name__icontains="mobility") | Q(workout_type__icontains="mobility"),
                     user=user, duration_minutes=15, deleted_at__isnull=True,
                     created_at__gte=CERT_START)
             .update(deleted_at=now))
        if n:
            print(f"  [objreveal-cleanup] soft-deleted WorkoutSession (15-min mobility) x{n}")
    except Exception as e:
        print(f"  [objreveal-cleanup] WorkoutSession skipped: {e!r}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0040_cleanup_reveal_cert_artifact"),
    ]
    operations = [
        migrations.RunPython(cleanup, noop_reverse),
    ]
