# ==============================================================================
# File: apps/users/migrations/0097_faith_journey_module_mapping.py
# Description: The `faith.journey` domain belongs to the Faith module.
# ==============================================================================
"""Every behavioural domain must be owned by exactly one module.

`faith.journey` ("Walking With God Through Scripture") lives under `apps/faith/journey/`
and is registered as a behavioural domain, but the Faith module's `mapped_domain_keys`
only listed `faith` — so the registry-alignment validator has been reporting
"Behavioral domain 'faith.journey' has no module mapping" since the domain was created.

It is a sub-domain of Faith by construction, so Faith owns it. Idempotent: the key is
added only when absent, and the migration is a no-op if the Faith module row does not
exist (fresh installs seed the catalog elsewhere).
"""
from django.db import migrations

FAITH_SLUG = "faith"
JOURNEY_DOMAIN = "faith.journey"


def add_mapping(apps, schema_editor):
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    module = ModuleDefinition.objects.filter(slug=FAITH_SLUG).first()
    if module is None:
        return
    keys = list(module.mapped_domain_keys or [])
    if JOURNEY_DOMAIN in keys:
        return
    keys.append(JOURNEY_DOMAIN)
    module.mapped_domain_keys = keys
    module.save(update_fields=["mapped_domain_keys"])


def remove_mapping(apps, schema_editor):
    ModuleDefinition = apps.get_model("users", "ModuleDefinition")
    module = ModuleDefinition.objects.filter(slug=FAITH_SLUG).first()
    if module is None:
        return
    keys = [k for k in (module.mapped_domain_keys or []) if k != JOURNEY_DOMAIN]
    module.mapped_domain_keys = keys
    module.save(update_fields=["mapped_domain_keys"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0096_proactive_assistance_enabled"),
    ]

    operations = [
        migrations.RunPython(add_mapping, remove_mapping),
    ]
