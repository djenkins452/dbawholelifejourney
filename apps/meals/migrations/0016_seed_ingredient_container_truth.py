# Foundation 2 — seed canonical Pantry Container Truth for common ingredients.
# base_measure + density are intrinsic substance properties (canonical, deterministic).
# default_quantity/default_unit provide a typical per-ingredient net-content DEFAULT
# (source #3 in resolution) — overridden per-product by Open Food Facts / FoodItem.
# No estimation: these are fixed reference values.
from decimal import Decimal

from django.db import migrations

# (canonical_name, base_measure, density_g_per_ml | None, default_net_qty, default_unit)
# default net content is a typical retail package for that ingredient.
SEED = [
    ("ketchup",         "volume", "1.140", "591",  "ml"),   # 20 fl oz bottle
    ("mustard",         "volume", "1.050", "255",  "ml"),   # ~9 oz bottle
    ("mayo",            "volume", "0.910", "445",  "ml"),   # 15 fl oz jar
    ("mayonnaise",      "volume", "0.910", "445",  "ml"),
    ("relish",          "volume", "1.050", "296",  "ml"),   # 10 oz jar
    ("olive oil",       "volume", "0.915", "500",  "ml"),
    ("vegetable oil",   "volume", "0.920", "946",  "ml"),   # 32 fl oz
    ("milk",            "volume", "1.030", "3785", "ml"),   # 1 gallon
    ("water",           "volume", "1.000", "1000", "ml"),
    ("honey",           "volume", "1.420", "340",  "ml"),   # 12 oz bottle
    ("soy sauce",       "volume", "1.150", "296",  "ml"),
    ("flour",           "mass",   "0.530", "2270", "g"),    # 5 lb bag (culinary volume/mass bridge)
    ("all-purpose flour","mass",  "0.530", "2270", "g"),
    ("sugar",           "mass",   "0.850", "1810", "g"),    # 4 lb bag
    ("granulated sugar","mass",   "0.850", "1810", "g"),
    ("brown sugar",     "mass",   "0.900", "907",  "g"),    # 2 lb
    ("salt",            "mass",   "1.200", "737",  "g"),    # 26 oz canister
    ("butter",          "mass",   "0.911", "454",  "g"),    # 1 lb
    ("rice",            "mass",   "0.850", "907",  "g"),    # 2 lb
    ("protein powder",  "mass",   "0.450", "907",  "g"),    # 2 lb tub
]


def seed(apps, schema_editor):
    # Container Truth is seeded into the REAL ingredient catalog only. Skip the test
    # database: the meal test suite creates ingredients by these same common canonical
    # names ("flour"/"rice"/"salt"/...) and would collide with globally-seeded rows on the
    # unique canonical_name constraint. No test relies on these seeded rows existing (the
    # container-truth suite seeds its own uniquely-named fixtures). Production is unaffected
    # — this migration is already applied there, and a fresh prod DB is not named "test_".
    db_name = str(schema_editor.connection.settings_dict.get("NAME") or "")
    if db_name.startswith("test_"):
        return
    Ingredient = apps.get_model("meals", "Ingredient")
    for name, measure, density, qty, unit in SEED:
        obj, _ = Ingredient.objects.get_or_create(
            canonical_name=name,
            defaults={"category": "other"},
        )
        # Canonical substance truth (base_measure/density) + a typical net-content
        # default (source #3; product-specific OFF/FoodItem truth overrides it).
        obj.base_measure = measure
        obj.density_g_per_ml = Decimal(density) if density else None
        obj.default_quantity = Decimal(qty)
        obj.default_unit = unit
        obj.save(update_fields=["base_measure", "density_g_per_ml",
                                "default_quantity", "default_unit", "updated_at"])


def unseed(apps, schema_editor):
    # Reversible to the field defaults (leave rows; just reset the substance truth).
    Ingredient = apps.get_model("meals", "Ingredient")
    names = [row[0] for row in SEED]
    Ingredient.objects.filter(canonical_name__in=names).update(
        base_measure="count", density_g_per_ml=None)


class Migration(migrations.Migration):

    dependencies = [
        ("meals", "0015_ingredient_base_measure_ingredient_density_g_per_ml_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
