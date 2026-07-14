"""
Data migration: Expire all active 'nutrition_transformation' DomainCorrelation
rows.

Background: detect_nutrition_energy() emitted a 'nutrition_transformation'
correlation whenever macro-compliance and the transformation_score were both
high (or both low). But the transformation_score is a composite that ALREADY
contains macro-compliance as its largest weighted component (~0.25, see
build_transformation_state in apps/core/ai_state/state_builder.py). The output —
"Nutrition compliance (89%) is supporting your transformation score (70/100).
Stay consistent." — was therefore a same-domain, circular, metric-to-score
restatement, not a cross-domain discovery. It is the exact class already barred
from the executive-pattern lane (commit b56ce76a) and flagged in the changelog
as something "a Chief of Staff would never say."

The detector has been removed from CORRELATION_DETECTORS, so no new rows will be
created. This migration deactivates any rows that already exist so they can no
longer surface (every consumer filters status='active'). Rows are EXPIRED, not
deleted, preserving history — matching expire_stale_correlations() semantics.
"""

from django.db import migrations


def expire_nutrition_transformation_correlations(apps, schema_editor):
    DomainCorrelation = apps.get_model("core", "DomainCorrelation")

    updated = DomainCorrelation.objects.filter(
        correlation_type="nutrition_transformation",
        status="active",
    ).update(status="expired")

    if updated:
        print(
            f"\n  Expired {updated} circular 'nutrition_transformation' "
            f"correlation(s)."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0134_richtextimage"),
    ]

    operations = [
        migrations.RunPython(
            expire_nutrition_transformation_correlations,
            migrations.RunPython.noop,
        ),
    ]
