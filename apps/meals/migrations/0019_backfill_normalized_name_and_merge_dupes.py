# Ingredient Intelligence — backfill the deterministic identity key, fold existing
# duplicates that share it, and seed a small curated set of true-synonym aliases.
#   • backfill + merge run everywhere (no-ops on a fresh DB with no duplicates)
#   • the alias seed skips the test database (like meals/0016) — tests create ingredients
#     by these common names and would collide with globally-seeded canonical rows.
from django.db import migrations

# canonical_name -> explicit synonyms (SAME real-world ingredient, not substitutions).
# Plural/case/punctuation are handled deterministically by normalized_name; these cover
# genuine different-word synonyms that normalization cannot derive.
SEED_ALIASES = {
    "ketchup": ["catsup", "tomato ketchup"],
    "hamburger bun": ["burger bun", "hamburger roll"],
    "mayonnaise": ["mayo"],
    "ground beef": ["minced beef"],
}


def forward(apps, schema_editor):
    from apps.meals.services.ingredient_intelligence import (
        merge_duplicate_ingredients, normalize_name,
    )

    Ingredient = apps.get_model("meals", "Ingredient")

    # 1. Backfill the identity key for every existing row.
    for ing in Ingredient.objects.all().iterator():
        norm = normalize_name(ing.canonical_name)
        if ing.normalized_name != norm:
            ing.normalized_name = norm
            ing.save(update_fields=["normalized_name"])

    # 2. Fold existing duplicates (same key -> one survivor). No-op if none.
    merge_duplicate_ingredients(apps_registry=apps)

    # 3. Seed curated synonym aliases (skip the test database).
    db_name = str(schema_editor.connection.settings_dict.get("NAME") or "")
    if db_name.startswith("test_"):
        return
    for canonical, synonyms in SEED_ALIASES.items():
        norm = normalize_name(canonical)
        ing = (Ingredient.objects.filter(canonical_name__iexact=canonical).first()
               or Ingredient.objects.filter(normalized_name=norm).order_by("id").first())
        if ing is None:
            continue  # only annotate ingredients the catalog already has
        alias_set = {a.lower() for a in (ing.aliases or [])}
        for syn in synonyms:
            alias_set.add(syn.lower())
        ing.aliases = sorted(alias_set)
        ing.save(update_fields=["aliases"])


def backward(apps, schema_editor):
    # Identity backfill/merge is not reversible (rows were folded); leave data as-is.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("meals", "0018_ingredient_normalized_name"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
