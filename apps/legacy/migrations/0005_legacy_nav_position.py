"""
Position Legacy in the main WLJ left rail: directly under Goals (purpose,
order 5) and above Travel (order 21). Sets the catalog default_order for new
users and the owner's personal sort_order so it lands in the right place.
Idempotent.
"""

from django.db import migrations

LEGACY_SLUG = "legacy"
OWNER_EMAIL = "dannyjenkins71@gmail.com"
NAV_ORDER = 6  # Goals=5, Legacy=6, (…), Travel=21


def position_legacy(apps, schema_editor):
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")
    User = apps.get_model("users", "User")

    module = ModuleDefinition.objects.filter(slug=LEGACY_SLUG).first()
    if not module:
        return
    module.default_order = NAV_ORDER
    module.save(update_fields=["default_order"])

    owner = User.objects.filter(email__iexact=OWNER_EMAIL).first()
    if owner:
        UserModulePreference.objects.update_or_create(
            user=owner, module=module,
            defaults={"is_enabled": True, "sort_order": NAV_ORDER},
        )

    try:
        from django.core.cache import cache
        cache.delete("wlj:module_catalog:all")
        if owner:
            cache.delete(f"nav_modules_user_{owner.id}")
    except Exception:
        pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("legacy", "0004_alter_output_audience"),
        ("users", "0086_enable_chatgpt_cos_for_owner"),
    ]

    operations = [
        migrations.RunPython(position_legacy, noop),
    ]
