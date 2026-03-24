# ==============================================================================
# Data migration: Populate ModuleDefinition catalog fields (Phase 1)
#
# Updates existing rows with new catalog fields and adds new entries
# for documents, travel, and system.
# Removes the 'notes' entry which is not in the canonical module list.
# ==============================================================================

from django.db import migrations


# Canonical module catalog — the single source of truth
MODULE_CATALOG = [
    # ── Layer 1: Ingestion ──
    {
        'slug': 'capture',
        'name': 'Capture',
        'display_name': 'Capture',
        'description': 'Quick voice and text capture',
        'icon_svg': (
            '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>'
            '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
            '<line x1="12" y1="19" x2="12" y2="23"/>'
            '<line x1="8" y1="23" x2="16" y2="23"/>'
        ),
        'status': 'active',
        'catalog_type': 'system',
        'layer': 1,
        'mapped_domain_keys': [],
        'route_name': 'capture:list',
        'url_namespace': 'capture',
        'app_names': ['capture'],
        'default_order': 7,
        'is_active': True,
        'always_available': True,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'capture_enabled',
    },
    # ── Layer 2: Knowledge ──
    {
        'slug': 'documents',
        'name': 'Documents',
        'display_name': 'Documents',
        'description': 'Your important files and records',
        'icon_svg': (
            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<polyline points="14 2 14 8 20 8"/>'
            '<line x1="16" y1="13" x2="8" y2="13"/>'
            '<line x1="16" y1="17" x2="8" y2="17"/>'
            '<polyline points="10 9 9 9 8 9"/>'
        ),
        'status': 'active',
        'catalog_type': 'system',
        'layer': 2,
        'mapped_domain_keys': ['documents'],
        'route_name': 'life:document_list',
        'url_namespace': 'life',
        'app_names': [],
        'default_order': 50,
        'is_active': True,
        'always_available': True,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': '',
    },
    # ── Layer 3: Domains (User Modules) ──
    {
        'slug': 'journal',
        'name': 'Journal',
        'display_name': 'Journal & Reflections',
        'description': 'Daily reflections and journal entries',
        'icon_svg': '<path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['journal', 'emotional'],
        'route_name': 'journal:home',
        'url_namespace': 'journal',
        'app_names': ['journal'],
        'default_order': 1,
        'is_active': True,
        'always_available': False,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'journal_enabled',
    },
    {
        'slug': 'health',
        'name': 'Health',
        'display_name': 'Health & Vitals',
        'description': 'Track weight, fitness, nutrition, and wellness',
        'icon_svg': '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['health', 'medical', 'brain_training'],
        'route_name': 'health:landing',
        'url_namespace': 'health',
        'app_names': ['health', 'medical'],
        'default_order': 2,
        'is_active': True,
        'always_available': False,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'health_enabled',
    },
    {
        'slug': 'faith',
        'name': 'Faith',
        'display_name': 'Faith & Spiritual',
        'description': 'Scripture, prayers, and spiritual growth',
        'icon_svg': '<path d="M12 2v20M7 7h10"/>',
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['faith'],
        'route_name': 'faith:home',
        'url_namespace': 'faith',
        'app_names': ['faith'],
        'default_order': 3,
        'is_active': True,
        'always_available': False,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'faith_enabled',
    },
    {
        'slug': 'life',
        'name': 'Organize',
        'display_name': 'Tasks & Calendar',
        'description': 'Projects, tasks, calendar, and home management',
        'icon_svg': '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['life'],
        'route_name': 'life:home',
        'url_namespace': 'life',
        'app_names': ['life'],
        'default_order': 4,
        'is_active': True,
        'always_available': True,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'life_enabled',
    },
    {
        'slug': 'purpose',
        'name': 'Goals',
        'display_name': 'Goals & Purpose',
        'description': 'Life goals, intentions, and yearly focus',
        'icon_svg': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['purpose'],
        'route_name': 'purpose:home',
        'url_namespace': 'purpose',
        'app_names': ['purpose'],
        'default_order': 5,
        'is_active': True,
        'always_available': False,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'purpose_enabled',
    },
    {
        'slug': 'meals',
        'name': 'Meals',
        'display_name': 'Meals & Nutrition',
        'description': 'Meal planning, pantry, and recipes',
        'icon_svg': (
            '<path d="M18 8h1a4 4 0 0 1 0 8h-1"/>'
            '<path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/>'
            '<line x1="6" y1="1" x2="6" y2="4"/>'
            '<line x1="10" y1="1" x2="10" y2="4"/>'
            '<line x1="14" y1="1" x2="14" y2="4"/>'
        ),
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['meals'],
        'route_name': 'meals:dashboard',
        'url_namespace': 'meals',
        'app_names': ['meals'],
        'default_order': 8,
        'is_active': True,
        'always_available': False,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': '',
    },
    {
        'slug': 'relationships',
        'name': 'People',
        'display_name': 'People & Relationships',
        'description': 'Track connections and meaningful interactions',
        'icon_svg': (
            '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
            '<circle cx="9" cy="7" r="4"/>'
            '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
            '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
        ),
        'status': 'active',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['relationships'],
        'route_name': 'relationships:person_list',
        'url_namespace': 'relationships',
        'app_names': ['relationships'],
        'default_order': 9,
        'is_active': True,
        'always_available': False,
        'default_enabled': True,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': True,
        'sub_features': {},
        'preference_field': 'relationships_enabled',
    },
    {
        'slug': 'finance',
        'name': 'Finance',
        'display_name': 'Finance',
        'description': 'Budget tracking and financial goals',
        'icon_svg': '<path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
        'status': 'coming_soon',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': ['finance'],
        'route_name': 'finance:dashboard',
        'url_namespace': 'finance',
        'app_names': ['finance'],
        'default_order': 20,
        'is_active': True,
        'always_available': False,
        'default_enabled': False,
        'show_in_navigation': True,
        'show_in_preferences': True,
        'cos_participation': False,
        'sub_features': {},
        'preference_field': 'finances_enabled',
    },
    {
        'slug': 'travel',
        'name': 'Travel',
        'display_name': 'Travel',
        'description': 'Trip planning and logistics',
        'icon_svg': (
            '<path d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3'
            'c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5'
            'l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3'
            ' 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>'
        ),
        'status': 'coming_soon',
        'catalog_type': 'module',
        'layer': 3,
        'mapped_domain_keys': [],
        'route_name': '',
        'url_namespace': '',
        'app_names': [],
        'default_order': 21,
        'is_active': True,
        'always_available': False,
        'default_enabled': False,
        'show_in_navigation': False,
        'show_in_preferences': True,
        'cos_participation': False,
        'sub_features': {},
        'preference_field': '',
    },
    # ── Internal ──
    {
        'slug': 'system',
        'name': 'System',
        'display_name': 'System',
        'description': 'Internal system services',
        'icon_svg': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
        'status': 'internal',
        'catalog_type': 'internal',
        'layer': 3,
        'mapped_domain_keys': [],
        'route_name': '',
        'url_namespace': '',
        'app_names': [],
        'default_order': 99,
        'is_active': True,
        'always_available': True,
        'default_enabled': False,
        'show_in_navigation': False,
        'show_in_preferences': False,
        'cos_participation': False,
        'sub_features': {},
        'preference_field': '',
    },
]


def populate_module_catalog(apps, schema_editor):
    """Populate the canonical module catalog."""
    ModuleDefinition = apps.get_model('users', 'ModuleDefinition')

    for module_data in MODULE_CATALOG:
        slug = module_data['slug']
        ModuleDefinition.objects.update_or_create(
            slug=slug,
            defaults=module_data,
        )

    # NOTE: Previously deleted 'notes' module here, but Notes is now
    # part of the canonical catalog (added in fixture + UI Alignment Phase).
    # Deletion removed to prevent fixture/migration conflict.


def reverse_migration(apps, schema_editor):
    # Don't delete catalog data on reverse — too risky
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0076_module_catalog_phase1'),
    ]

    operations = [
        migrations.RunPython(populate_module_catalog, reverse_migration),
    ]
