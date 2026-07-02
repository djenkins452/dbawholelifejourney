"""
Register Legacy in the canonical Module Catalog and enable it for the owner.

Production has no CLI, so seeding runs here (migrate runs on every deploy).
Idempotent: safe to run repeatedly. Legacy defaults OFF for everyone (early
access) and is enabled explicitly for the account driving development.
"""

from django.db import migrations

LEGACY_SLUG = "legacy"
OWNER_EMAIL = "dannyjenkins71@gmail.com"

# Inner SVG for the WLJ nav rail (rendered inside a 24x24 viewBox) — a small tree.
LEGACY_ICON_SVG = (
    '<path d="M12 22v-6"/>'
    '<path d="M12 16c-3 0-5-2-5-5 0-1 .4-2 1-3-1-.6-1.5-1.6-1.5-2.7C6.5 3.5 8 2 10 2c.9 0 '
    '1.6.3 2 .8.4-.5 1.1-.8 2-.8 2 0 3.5 1.5 3.5 3.3 0 1.1-.5 2.1-1.5 2.7.6 1 1 2 1 3 0 3-2 5-5 5z"/>'
)


def seed_legacy_module(apps, schema_editor):
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    UserModulePreference = apps.get_model("users", "UserModulePreference")
    User = apps.get_model("users", "User")

    module, _ = ModuleDefinition.objects.update_or_create(
        slug=LEGACY_SLUG,
        defaults=dict(
            name="Legacy",
            display_name="Legacy",
            description="Preserve people, stories, places, and media for future generations.",
            icon_svg=LEGACY_ICON_SVG,
            status="active",
            catalog_type="module",
            layer=3,
            mapped_domain_keys=[LEGACY_SLUG],
            route_name="legacy:home",
            url_namespace="legacy",
            app_names=[LEGACY_SLUG],
            default_order=60,
            is_active=True,
            always_available=False,
            default_enabled=False,          # OFF for everyone (early access)
            show_in_navigation=True,
            show_in_preferences=True,
            cos_participation=False,        # Phase 1: standalone / no assistant
        ),
    )

    # Enable for the development/owner account so it shows in the WLJ rail.
    owner = User.objects.filter(email__iexact=OWNER_EMAIL).first()
    if owner:
        UserModulePreference.objects.update_or_create(
            user=owner, module=module, defaults={"is_enabled": True},
        )

    # Best-effort cache invalidation so nav updates without waiting for TTL.
    try:
        from django.core.cache import cache
        cache.delete("wlj:module_catalog:all")
        if owner:
            cache.delete(f"nav_modules_user_{owner.id}")
    except Exception:
        pass


def remove_legacy_module(apps, schema_editor):
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    ModuleDefinition.objects.filter(slug=LEGACY_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("legacy", "0001_initial"),
        # Depend on the latest users migration so the historical ModuleDefinition
        # model has every field this seed sets (fields were added post-0048).
        ("users", "0086_enable_chatgpt_cos_for_owner"),
    ]

    operations = [
        migrations.RunPython(seed_legacy_module, remove_legacy_module),
    ]
