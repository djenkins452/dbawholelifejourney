# Data migration to add Sports module to ModuleDefinition catalog
from django.db import migrations


def add_sports_module(apps, schema_editor):
    ModuleDefinition = apps.get_model('users', 'ModuleDefinition')
    ModuleDefinition.objects.update_or_create(
        slug='sports',
        defaults={
            'name': 'Sports',
            'display_name': 'Sports',
            'description': 'Track followed teams and game-day signals',
            'icon_svg': '<circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/>',
            'status': 'active',
            'catalog_type': 'module',
            'layer': 3,
            'mapped_domain_keys': ['sports'],
            'route_name': 'sports:hub',
            'url_namespace': 'sports',
            'app_names': ['sports'],
            'default_order': 50,
            'is_active': True,
            'always_available': False,
            'default_enabled': False,
            'show_in_navigation': True,
            'show_in_preferences': True,
            'cos_participation': True,
            'preference_field': 'sports_enabled',
        },
    )


def reverse_migration(apps, schema_editor):
    ModuleDefinition = apps.get_model('users', 'ModuleDefinition')
    ModuleDefinition.objects.filter(slug='sports').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0079_userpreferences_sports_enabled'),
    ]

    operations = [
        migrations.RunPython(add_sports_module, reverse_migration),
    ]
