"""
Whole Life Journey — CoS Documentation System Tests

Project: Whole Life Journey
Path: apps/core/ai_docs/tests.py
Purpose: Tests for documentation registry, generator, and sync

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.test import TestCase, override_settings

from .cos_doc_registry import (
    ENGINE_DEPENDENCIES,
    BLUEPRINT_MODEL_FIELDS,
    get_cos_registry,
    validate_registry,
)
from .cos_doc_generator import (
    generate_cos_admin_guide,
    _compute_dependency_checksum,
    COS_VERSION,
)


# =============================================================================
# REGISTRY TESTS
# =============================================================================

class CosDocRegistryTests(TestCase):
    """Tests for the CoS documentation registry."""

    def test_engine_dependencies_not_empty(self):
        """ENGINE_DEPENDENCIES should have entries."""
        self.assertGreater(len(ENGINE_DEPENDENCIES), 0)

    def test_all_engines_have_module_and_functions(self):
        """Every engine entry must have module and functions."""
        for key, edef in ENGINE_DEPENDENCIES.items():
            self.assertIn('module', edef, f"Engine {key} missing 'module'")
            self.assertIn('functions', edef, f"Engine {key} missing 'functions'")
            self.assertIsInstance(edef['functions'], list)
            self.assertGreater(len(edef['functions']), 0,
                             f"Engine {key} has empty functions list")

    def test_blueprint_model_fields_not_empty(self):
        """BLUEPRINT_MODEL_FIELDS should have entries."""
        self.assertGreater(len(BLUEPRINT_MODEL_FIELDS), 0)

    def test_all_models_have_module_and_fields(self):
        """Every model entry must have module and expected_fields."""
        for model_name, mdef in BLUEPRINT_MODEL_FIELDS.items():
            self.assertIn('module', mdef, f"Model {model_name} missing 'module'")
            self.assertIn('expected_fields', mdef,
                        f"Model {model_name} missing 'expected_fields'")
            self.assertGreater(len(mdef['expected_fields']), 0,
                             f"Model {model_name} has empty fields list")

    def test_get_cos_registry_returns_list(self):
        """get_cos_registry() should return a non-empty list."""
        registry = get_cos_registry()
        self.assertIsInstance(registry, list)
        self.assertGreater(len(registry), 0)

    def test_registry_entries_have_required_keys(self):
        """Each registry entry must have key, name, description, engines."""
        registry = get_cos_registry()
        for entry in registry:
            self.assertIn('key', entry, f"Entry missing 'key': {entry}")
            self.assertIn('name', entry, f"Entry missing 'name': {entry}")
            self.assertIn('description', entry,
                        f"Entry missing 'description': {entry}")
            self.assertIn('engines', entry, f"Entry missing 'engines': {entry}")

    def test_registry_engine_references_exist(self):
        """All engine references in registry entries must exist in ENGINE_DEPENDENCIES."""
        registry = get_cos_registry()
        for entry in registry:
            for engine_name in entry['engines']:
                self.assertIn(
                    engine_name, ENGINE_DEPENDENCIES,
                    f"Registry entry '{entry['key']}' references unknown "
                    f"engine '{engine_name}'"
                )

    def test_registry_model_references_exist(self):
        """All model references in registry entries must exist in BLUEPRINT_MODEL_FIELDS."""
        registry = get_cos_registry()
        for entry in registry:
            for model_name in entry.get('models', []):
                self.assertIn(
                    model_name, BLUEPRINT_MODEL_FIELDS,
                    f"Registry entry '{entry['key']}' references unknown "
                    f"model '{model_name}'"
                )

    def test_validate_registry_runs(self):
        """validate_registry() should return a tuple."""
        is_valid, errors = validate_registry()
        self.assertIsInstance(is_valid, bool)
        self.assertIsInstance(errors, list)

    def test_validate_registry_blueprint_models(self):
        """Blueprint models should validate (they exist in our codebase)."""
        is_valid, errors = validate_registry()
        # Check that no model-related errors exist
        model_errors = [e for e in errors if "Model" in e]
        self.assertEqual(
            len(model_errors), 0,
            f"Model validation errors: {model_errors}"
        )

    def test_validate_registry_cos_engines(self):
        """Core CoS engines should validate (they exist in our codebase)."""
        is_valid, errors = validate_registry()
        cos_engine_keys = [
            'blueprint_engine', 'priority_engine', 'architecture_engine',
            'drift_engine', 'intervention_engine', 'assistant_triggers',
        ]
        cos_errors = [
            e for e in errors
            if any(k in e for k in cos_engine_keys)
        ]
        self.assertEqual(
            len(cos_errors), 0,
            f"CoS engine validation errors: {cos_errors}"
        )


# =============================================================================
# GENERATOR TESTS
# =============================================================================

class CosDocGeneratorTests(TestCase):
    """Tests for the CoS documentation generator."""

    def test_checksum_is_stable(self):
        """Same registry should produce same checksum."""
        c1 = _compute_dependency_checksum()
        c2 = _compute_dependency_checksum()
        self.assertEqual(c1, c2)

    def test_checksum_is_string(self):
        """Checksum should be a hex string."""
        checksum = _compute_dependency_checksum()
        self.assertIsInstance(checksum, str)
        self.assertEqual(len(checksum), 12)

    def test_generate_returns_expected_structure(self):
        """generate_cos_admin_guide() should return section + articles."""
        guide = generate_cos_admin_guide()
        self.assertIn('section', guide)
        self.assertIn('articles', guide)
        self.assertIn('checksum', guide)
        self.assertIn('validation', guide)
        self.assertIn('generated_at', guide)

    def test_section_has_required_fields(self):
        """Section metadata should have all required fields."""
        guide = generate_cos_admin_guide()
        section = guide['section']
        self.assertIn('section_key', section)
        self.assertIn('title', section)
        self.assertIn('icon', section)
        self.assertIn('description', section)

    def test_articles_are_nonempty(self):
        """Should generate multiple articles."""
        guide = generate_cos_admin_guide()
        articles = guide['articles']
        self.assertGreater(len(articles), 5)

    def test_articles_have_required_fields(self):
        """Each article should have title, slug, content, order."""
        guide = generate_cos_admin_guide()
        for article in guide['articles']:
            self.assertIn('title', article)
            self.assertIn('slug', article)
            self.assertIn('content', article)
            self.assertIn('order', article)
            self.assertIsInstance(article['content'], str)
            self.assertGreater(len(article['content']), 0)

    def test_overview_article_first(self):
        """First article should be the CoS overview."""
        guide = generate_cos_admin_guide()
        first = guide['articles'][0]
        self.assertEqual(first['slug'], 'cos-overview')
        self.assertIn('Chief of Staff', first['content'])

    def test_version_article_present(self):
        """Version stamp article should exist."""
        guide = generate_cos_admin_guide()
        slugs = [a['slug'] for a in guide['articles']]
        self.assertIn('cos-version', slugs)

    def test_version_article_contains_version(self):
        """Version article should contain the COS_VERSION."""
        guide = generate_cos_admin_guide()
        version_article = next(
            a for a in guide['articles'] if a['slug'] == 'cos-version'
        )
        self.assertIn(COS_VERSION, version_article['content'])

    def test_engine_map_article_present(self):
        """Engine map article should exist."""
        guide = generate_cos_admin_guide()
        slugs = [a['slug'] for a in guide['articles']]
        self.assertIn('cos-engine-map', slugs)

    def test_data_model_article_present(self):
        """Data model reference article should exist."""
        guide = generate_cos_admin_guide()
        slugs = [a['slug'] for a in guide['articles']]
        self.assertIn('cos-data-models', slugs)

    def test_scheduled_tasks_article_present(self):
        """Scheduled tasks article should exist."""
        guide = generate_cos_admin_guide()
        slugs = [a['slug'] for a in guide['articles']]
        self.assertIn('cos-scheduled-tasks', slugs)

    def test_component_articles_match_registry(self):
        """Should generate an article for each registry component."""
        registry = get_cos_registry()
        guide = generate_cos_admin_guide()
        slugs = [a['slug'] for a in guide['articles']]

        for component in registry:
            expected_slug = f"cos-{component['key'].replace('_', '-')}"
            self.assertIn(
                expected_slug, slugs,
                f"Missing article for component '{component['key']}'"
            )

    def test_articles_contain_markdown(self):
        """Articles should contain Markdown formatting."""
        guide = generate_cos_admin_guide()
        for article in guide['articles']:
            # Every article should have at least a heading
            self.assertTrue(
                '##' in article['content'] or '#' in article['content'],
                f"Article '{article['slug']}' has no Markdown headings"
            )

    def test_unique_slugs(self):
        """All article slugs must be unique."""
        guide = generate_cos_admin_guide()
        slugs = [a['slug'] for a in guide['articles']]
        self.assertEqual(len(slugs), len(set(slugs)), "Duplicate slugs found")

    def test_unique_orders(self):
        """All article orders must be unique."""
        guide = generate_cos_admin_guide()
        orders = [a['order'] for a in guide['articles']]
        self.assertEqual(len(orders), len(set(orders)), "Duplicate orders found")


# =============================================================================
# SYNC TESTS
# =============================================================================

class CosDocSyncTests(TestCase):
    """Tests for the CoS documentation sync."""

    def test_sync_creates_section(self):
        """sync_cos_admin_guide should create the admin guide section."""
        from .cos_doc_sync import sync_cos_admin_guide
        from apps.admin_console.models import AdminGuideSection

        result = sync_cos_admin_guide(force=True)

        self.assertTrue(result['synced'])
        self.assertTrue(
            AdminGuideSection.objects.filter(
                section_key='cos-architecture'
            ).exists()
        )

    def test_sync_creates_articles(self):
        """sync_cos_admin_guide should create articles."""
        from .cos_doc_sync import sync_cos_admin_guide
        from apps.admin_console.models import AdminGuideArticle, AdminGuideSection

        result = sync_cos_admin_guide(force=True)

        self.assertTrue(result['synced'])
        self.assertGreater(result['articles_created'], 0)

        section = AdminGuideSection.objects.get(section_key='cos-architecture')
        self.assertGreater(
            AdminGuideArticle.objects.filter(section=section).count(), 0
        )

    def test_sync_idempotent(self):
        """Running sync twice should update, not duplicate."""
        from .cos_doc_sync import sync_cos_admin_guide
        from apps.admin_console.models import AdminGuideArticle, AdminGuideSection

        r1 = sync_cos_admin_guide(force=True)
        r2 = sync_cos_admin_guide(force=True)

        self.assertEqual(r2['articles_created'], 0)
        self.assertEqual(r2['articles_updated'], r1['articles_created'])

        section = AdminGuideSection.objects.get(section_key='cos-architecture')
        count = AdminGuideArticle.objects.filter(section=section).count()
        self.assertEqual(count, r1['articles_created'])

    def test_sync_removes_stale(self):
        """Sync should remove articles no longer in generated set."""
        from .cos_doc_sync import sync_cos_admin_guide
        from apps.admin_console.models import AdminGuideArticle, AdminGuideSection

        # First sync
        sync_cos_admin_guide(force=True)

        section = AdminGuideSection.objects.get(section_key='cos-architecture')

        # Add a fake stale article
        AdminGuideArticle.objects.create(
            section=section,
            title='Stale Article',
            slug='cos-stale-test',
            content='Should be removed',
            order=999,
        )

        # Second sync should remove it
        r2 = sync_cos_admin_guide(force=True)
        self.assertEqual(r2['articles_removed'], 1)

        self.assertFalse(
            AdminGuideArticle.objects.filter(slug='cos-stale-test').exists()
        )

    def test_needs_sync_after_initial(self):
        """needs_sync should return True before first sync."""
        from .cos_doc_sync import needs_sync
        self.assertTrue(needs_sync())

    def test_needs_sync_false_after_sync(self):
        """needs_sync should return False after sync."""
        from .cos_doc_sync import sync_cos_admin_guide, needs_sync

        sync_cos_admin_guide(force=True)
        self.assertFalse(needs_sync())

    def test_sync_skips_when_unchanged(self):
        """sync without force should skip if checksum unchanged."""
        from .cos_doc_sync import sync_cos_admin_guide

        sync_cos_admin_guide(force=True)
        r2 = sync_cos_admin_guide(force=False)

        self.assertFalse(r2['synced'])
        self.assertIn('unchanged', r2['reason'].lower())

    def test_sync_stores_checksum_in_dataloadconfig(self):
        """Sync should store checksum in DataLoadConfig."""
        from .cos_doc_sync import sync_cos_admin_guide, SYNC_CONFIG_NAME
        from apps.admin_console.models import DataLoadConfig

        sync_cos_admin_guide(force=True)

        config = DataLoadConfig.objects.filter(
            loader_name=SYNC_CONFIG_NAME
        ).first()
        self.assertIsNotNone(config)
        self.assertTrue(config.is_loaded)
        self.assertEqual(config.display_name, 'CoS Documentation Sync')

    def test_sync_articles_not_editable(self):
        """Auto-generated articles should not be editable."""
        from .cos_doc_sync import sync_cos_admin_guide
        from apps.admin_console.models import AdminGuideArticle, AdminGuideSection

        sync_cos_admin_guide(force=True)

        section = AdminGuideSection.objects.get(section_key='cos-architecture')
        editable = AdminGuideArticle.objects.filter(
            section=section, is_editable=True
        ).count()
        self.assertEqual(editable, 0)

    def test_sync_returns_validation_info(self):
        """Sync result should include validation info."""
        from .cos_doc_sync import sync_cos_admin_guide

        result = sync_cos_admin_guide(force=True)
        self.assertIn('validation', result)
        self.assertIn('is_valid', result['validation'])
        self.assertIn('errors', result['validation'])


# =============================================================================
# MANAGEMENT COMMAND TESTS
# =============================================================================

class SyncCosDocsCommandTests(TestCase):
    """Tests for the sync_cos_docs management command."""

    def test_command_runs(self):
        """Management command should run without errors."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command('sync_cos_docs', '--force', stdout=out)
        output = out.getvalue()
        self.assertIn('synced', output.lower())

    def test_command_validate_only(self):
        """--validate flag should only validate, not sync."""
        from django.core.management import call_command
        from io import StringIO
        from apps.admin_console.models import AdminGuideSection

        out = StringIO()
        call_command('sync_cos_docs', '--validate', stdout=out)
        output = out.getvalue()
        self.assertIn('validation', output.lower())

        # Should NOT have created the section
        self.assertFalse(
            AdminGuideSection.objects.filter(
                section_key='cos-architecture'
            ).exists()
        )
