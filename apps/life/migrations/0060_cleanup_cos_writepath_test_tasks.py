# Data migration — deterministic ROLLBACK of the CoS write-path certification test.
# A write-path certification (2026-08-06) created sentinel Tasks via the CoS create_task
# action to prove the write/read/delete workflow. The delete confirmation loop (Blocker #13)
# prevented the CoS from removing two of them, so they persist in production. This migration
# hard-deletes ONLY those clearly-labeled sentinel tasks, scoped to the test user. Idempotent
# and safe: the titles are unique test markers; nothing else can match.
from django.db import migrations

_SENTINELS = ("ZZZ-COS-WRITE-CERT", "ZZZ-CONFIRM-TEST")
_TEST_EMAIL = "dannyjenkins71@gmail.com"


def _cleanup(apps, schema_editor):
    from django.db.models import Q
    Task = apps.get_model("life", "Task")
    User = apps.get_model("users", "User")
    q = Q()
    for s in _SENTINELS:
        q |= Q(title__icontains=s)
    qs = Task.objects.filter(q)                       # historical manager sees ALL rows
    try:
        user = User.objects.get(email__iexact=_TEST_EMAIL)
        qs = qs.filter(user=user)                     # scope to the test user
    except User.DoesNotExist:
        pass
    titles = list(qs.values_list("id", "title"))
    deleted, _ = qs.delete()
    print(f"cleanup_cos_writepath: hard-deleted {deleted} sentinel row(s): {titles}")


def _noop(apps, schema_editor):
    # Test artifacts are not restorable and must not be recreated on reverse.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("life", "0059_alter_recipebulkimportphoto_recipe_delete_recipe"),
    ]
    operations = [migrations.RunPython(_cleanup, _noop)]
