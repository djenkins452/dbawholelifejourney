# ==============================================================================
# Data migration — correct supplements mis-tagged as prescription medications.
# Trust failure (2026-06-30): "Fish Oil" and "Magnesium glycinate" appeared in the
# user's PRESCRIPTION medication inventory. Root cause: those Intake rows were tagged
# as medication/prescription. This safely re-tags clearly-supplement items (matched by
# unambiguous ingredient name) to intake_type='supplement' with a supplement category,
# so they classify as Supplement everywhere — never as Medicine.
#
# Targeted + conservative: only rows whose NAME matches a curated supplement-ingredient
# list AND that are not already supplements. Insulin and ordinary prescriptions are
# never touched. Idempotent; safe to re-run.
# ==============================================================================
from django.db import migrations
from django.db.models import Q

# Mirror of apps.health.medicine_classification._SUPPLEMENT_NAME_TOKENS (kept literal so
# the migration is stable even if the constant later changes).
_TOKENS = (
    "fish oil", "fish-oil", "omega-3", "omega 3", "omega3", "magnesium", "glucosamine",
    "chondroitin", "probiotic", "melatonin", "biotin", "turmeric", "curcumin", "collagen",
    "coq10", "co q10", "ashwagandha", "elderberry", "psyllium",
    "milk thistle", "ginkgo", "saw palmetto",
)


def _supplement_category_for(name):
    n = name.lower()
    if "magnesium" in n:
        return "mineral"
    if "probiotic" in n:
        return "probiotic"
    if "turmeric" in n or "curcumin" in n or "ginkgo" in n or "milk thistle" in n \
            or "saw palmetto" in n or "ashwagandha" in n or "elderberry" in n:
        return "herbal"
    return "herbal"   # broad supplement bucket (fish oil/omega/etc.) — still classifies SUPPLEMENT


def reclassify(apps, schema_editor):
    Intake = apps.get_model("health", "Intake")
    name_q = Q()
    for tok in _TOKENS:
        name_q |= Q(name__icontains=tok)
    # Items named like supplements but NOT already tagged supplement.
    candidates = Intake.objects.filter(name_q).exclude(intake_type="supplement")
    for m in candidates:
        # Never touch insulin (a real prescription) — names won't match, but be explicit.
        if getattr(m, "intake_subtype", None):
            continue
        m.intake_type = "supplement"
        if (m.category or "").lower() in ("prescription", "otc", "other", ""):
            m.category = _supplement_category_for(m.name)
        m.save(update_fields=["intake_type", "category"])


def noop(apps, schema_editor):
    # Non-reversible data correction (we do not re-mis-tag supplements as medications).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0096_medicationcapturesession"),
    ]
    operations = [
        migrations.RunPython(reclassify, noop),
    ]
