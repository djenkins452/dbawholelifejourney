"""
Backfill the stored `relationship_category` for existing relationships from their
type, via the ONE canonical classifier. O(N): load, classify in memory, one
bulk_update. Non-atomic and idempotent so it can never stall a deploy.
"""

from django.db import migrations


def _backfill(apps, schema_editor):
    from apps.legacy.models import classify_category
    Relationship = apps.get_model("legacy", "Relationship")
    qs = Relationship.objects.all().only("pk", "relationship_type", "relationship_category")
    changed, total = [], 0
    for r in qs.iterator(chunk_size=2000):
        total += 1
        cat = classify_category(r.relationship_type)
        if r.relationship_category != cat:
            r.relationship_category = cat
            changed.append(r)
            if len(changed) >= 2000:
                Relationship.objects.bulk_update(changed, ["relationship_category"], batch_size=2000)
                print("[migration 0022] categorized %d/%d relationships" % (total, total), flush=True)
                changed = []
    if changed:
        Relationship.objects.bulk_update(changed, ["relationship_category"], batch_size=2000)
    print("[migration 0022] done — %d relationships processed" % total, flush=True)


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("legacy", "0021_relationship_relationship_category")]
    operations = [migrations.RunPython(_backfill, _noop)]
