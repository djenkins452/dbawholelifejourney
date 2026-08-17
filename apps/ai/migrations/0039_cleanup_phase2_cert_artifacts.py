# Data migration: remove ONLY the Proactive Phase 2 certification/test artifacts created on the
# owner's account during real-model smokes (2026-08-17). Identity is PROVEN before deletion —
# owner email + exact title (case-insensitive) + created within the cert-day UTC window — so no
# legitimate user data is touched. Calendar events + tasks are SOFT-deleted (recoverable via
# deleted_at); ConversationFollowUp rows are removed outright because that model shipped the SAME
# day (migration 0038), so every row is a test artifact. Idempotent + best-effort per model.
from datetime import datetime
from datetime import timezone as dt_tz  # NOT django.utils.timezone.utc (removed in Django 5.x)

from django.db import migrations

OWNER_EMAIL = "dannyjenkins71@gmail.com"
CERT_START = datetime(2026, 8, 17, 0, 0, tzinfo=dt_tz.utc)
CERT_END = datetime(2026, 8, 18, 0, 0, tzinfo=dt_tz.utc)

# Exact titles created by the real-model smokes (case-insensitive match).
EVENT_TITLES = ["Review Cost Audit", "Weekly Review", "Health Metrics Update"]
TASK_TITLES = ["Call the pharmacy"]


def _owner(apps):
    User = apps.get_model("users", "User")
    try:
        return User.objects.get(email__iexact=OWNER_EMAIL)
    except Exception:
        return None


def cleanup(apps, schema_editor):
    user = _owner(apps)
    if user is None:
        print("  [phase2-cleanup] owner not found — nothing to do")
        return

    # 1) Calendar events (SOFT delete — set deleted_at; recoverable).
    try:
        CalendarEvent = apps.get_model("calendar_engine", "CalendarEvent")
        for title in EVENT_TITLES:
            qs = CalendarEvent.objects.filter(
                user=user, title__iexact=title, deleted_at__isnull=True,
                created_at__gte=CERT_START, created_at__lt=CERT_END)
            n = qs.update(deleted_at=datetime.now(tz=dt_tz.utc))
            if n:
                print(f"  [phase2-cleanup] soft-deleted CalendarEvent '{title}' x{n}")
    except Exception as e:
        print(f"  [phase2-cleanup] CalendarEvent skipped: {e!r}")

    # 2) Task (SOFT delete).
    try:
        Task = apps.get_model("life", "Task")
        for title in TASK_TITLES:
            qs = Task.objects.filter(
                user=user, title__iexact=title, deleted_at__isnull=True,
                created_at__gte=CERT_START, created_at__lt=CERT_END)
            n = qs.update(deleted_at=datetime.now(tz=dt_tz.utc))
            if n:
                print(f"  [phase2-cleanup] soft-deleted Task '{title}' x{n}")
    except Exception as e:
        print(f"  [phase2-cleanup] Task skipped: {e!r}")

    # 3) ConversationFollowUp — the model shipped today (0038); every row is a test artifact.
    #    Remove outright so no test follow-up fires on the owner's real chat.
    try:
        FollowUp = apps.get_model("ai", "ConversationFollowUp")
        n, _ = FollowUp.objects.filter(user=user).delete()
        if n:
            print(f"  [phase2-cleanup] deleted ConversationFollowUp x{n}")
    except Exception as e:
        print(f"  [phase2-cleanup] ConversationFollowUp skipped: {e!r}")


def noop_reverse(apps, schema_editor):
    # Soft-deleted events/tasks can be restored by clearing deleted_at manually; the follow-up
    # rows are gone. No automatic reverse (this is a one-way cleanup of test data).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0038_conversationfollowup"),
    ]
    operations = [
        migrations.RunPython(cleanup, noop_reverse),
    ]
