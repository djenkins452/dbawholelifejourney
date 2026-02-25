"""
Tests for Dynamic URL Resolution & Action Contracts (Phase 7).

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/tests/test_url_resolver.py
"""

from unittest.mock import MagicMock

from django.test import TestCase


# ---------------------------------------------------------------------------
# URL Resolver Tests
# ---------------------------------------------------------------------------

class ResolveIntentUrlTests(TestCase):
    """Tests for resolve_intent_url()."""

    def test_known_intent_returns_url(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_intent_url

        result = resolve_intent_url("log_weight")
        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "/health/weight/")
        self.assertIn("label", result)

    def test_unknown_intent_returns_none(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_intent_url

        result = resolve_intent_url("nonexistent_intent")
        self.assertIsNone(result)

    def test_all_intents_have_url_and_label(self):
        from apps.core.ai_orchestrator.url_resolver import INTENT_URL_MAP

        for intent_type, meta in INTENT_URL_MAP.items():
            self.assertIn("url", meta, f"Intent {intent_type} missing 'url'")
            self.assertIn("label", meta, f"Intent {intent_type} missing 'label'")
            self.assertTrue(meta["url"].startswith("/"), f"Intent {intent_type} URL must start with /")

    def test_health_intents_mapped(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_intent_url

        for intent in ["log_weight", "log_heart_rate", "log_food", "log_sleep", "log_water"]:
            self.assertIsNotNone(resolve_intent_url(intent), f"Missing URL for {intent}")

    def test_life_intents_mapped(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_intent_url

        for intent in ["create_task", "create_event", "complete_task"]:
            self.assertIsNotNone(resolve_intent_url(intent), f"Missing URL for {intent}")

    def test_faith_intents_mapped(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_intent_url

        for intent in ["log_prayer", "save_verse", "add_faith_milestone"]:
            self.assertIsNotNone(resolve_intent_url(intent), f"Missing URL for {intent}")


class ResolveModuleUrlTests(TestCase):
    """Tests for resolve_module_url()."""

    def test_known_module_returns_url(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_module_url

        result = resolve_module_url("health")
        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "/health/")
        self.assertEqual(result["label"], "Health Dashboard")

    def test_all_key_modules_mapped(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_module_url

        for module in ["health", "journal", "faith", "purpose", "life", "finance", "dashboard"]:
            self.assertIsNotNone(resolve_module_url(module), f"Missing URL for module {module}")

    def test_unknown_module_returns_none(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_module_url

        self.assertIsNone(resolve_module_url("nonexistent_module"))


class ResolveEntityUrlTests(TestCase):
    """Tests for resolve_entity_url()."""

    def test_goal_with_pk(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_entity_url

        url = resolve_entity_url("goal", 42)
        self.assertEqual(url, "/purpose/goals/42/")

    def test_journal_with_pk(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_entity_url

        url = resolve_entity_url("journal_entry", 99)
        self.assertEqual(url, "/journal/99/")

    def test_entity_without_pk_returns_list(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_entity_url

        url = resolve_entity_url("goal")
        self.assertEqual(url, "/purpose/goals/")

    def test_unknown_entity_returns_none(self):
        from apps.core.ai_orchestrator.url_resolver import resolve_entity_url

        url = resolve_entity_url("nonexistent_entity")
        self.assertIsNone(url)


class NavigablePagesTests(TestCase):
    """Tests for navigable pages list."""

    def test_returns_list(self):
        from apps.core.ai_orchestrator.url_resolver import get_navigable_pages

        pages = get_navigable_pages()
        self.assertIsInstance(pages, list)
        self.assertTrue(len(pages) > 10)

    def test_each_page_has_required_fields(self):
        from apps.core.ai_orchestrator.url_resolver import get_navigable_pages

        for page in get_navigable_pages():
            self.assertIn("url", page)
            self.assertIn("name", page)
            self.assertIn("keywords", page)
            self.assertTrue(page["url"].startswith("/"))


class BuildActionUrlMetadataTests(TestCase):
    """Tests for build_action_url_metadata()."""

    def test_basic_intent(self):
        from apps.core.ai_orchestrator.url_resolver import build_action_url_metadata

        meta = build_action_url_metadata("log_weight")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["url"], "/health/weight/")

    def test_with_created_object_detail_url(self):
        from apps.core.ai_orchestrator.url_resolver import build_action_url_metadata

        meta = build_action_url_metadata("create_goal", {"type": "goal", "id": 42})
        self.assertIsNotNone(meta)
        self.assertEqual(meta["detail_url"], "/purpose/goals/42/")

    def test_unknown_intent_returns_none(self):
        from apps.core.ai_orchestrator.url_resolver import build_action_url_metadata

        self.assertIsNone(build_action_url_metadata("nonexistent"))


# ---------------------------------------------------------------------------
# Action Contract Tests
# ---------------------------------------------------------------------------

class ActionContractTests(TestCase):
    """Tests for build_action_contract()."""

    def test_successful_action_has_url(self):
        from apps.core.ai_orchestrator.action_contracts import build_action_contract

        contract = build_action_contract(
            intent_type="log_weight",
            success=True,
            message="Logged 180 lbs",
        )
        self.assertTrue(contract.success)
        self.assertEqual(contract.view_url, "/health/weight/")
        self.assertIn("trends", contract.view_label.lower())

    def test_failed_action_no_url(self):
        from apps.core.ai_orchestrator.action_contracts import build_action_contract

        contract = build_action_contract(
            intent_type="log_weight",
            success=False,
            message="Failed to log",
        )
        self.assertFalse(contract.success)
        self.assertIsNone(contract.view_url)

    def test_contract_has_icon(self):
        from apps.core.ai_orchestrator.action_contracts import build_action_contract

        contract = build_action_contract("log_weight", True, "Logged")
        self.assertEqual(contract.icon, "scale")

    def test_contract_to_dict(self):
        from apps.core.ai_orchestrator.action_contracts import build_action_contract

        contract = build_action_contract("log_weight", True, "Logged 180 lbs")
        d = contract.to_dict()
        self.assertIn("intent_type", d)
        self.assertIn("success", d)
        self.assertIn("message", d)
        self.assertIn("view_url", d)
        self.assertIn("view_label", d)

    def test_follow_up_links(self):
        from apps.core.ai_orchestrator.action_contracts import build_action_contract

        contract = build_action_contract("create_event", True, "Event created")
        d = contract.to_dict()
        # create_event has a view_url of /calendar/ — follow-ups
        # should not duplicate the main URL
        if "follow_up_links" in d:
            for link in d["follow_up_links"]:
                self.assertNotEqual(link["url"], contract.view_url)

    def test_with_created_object_detail(self):
        from apps.core.ai_orchestrator.action_contracts import build_action_contract

        contract = build_action_contract(
            "create_goal", True, "Goal created",
            created_object={"type": "goal", "id": 42},
        )
        self.assertEqual(contract.detail_url, "/purpose/goals/42/")


class ActionLinkTests(TestCase):
    """Tests for ActionLink dataclass."""

    def test_to_dict_minimal(self):
        from apps.core.ai_orchestrator.action_contracts import ActionLink

        link = ActionLink(url="/health/", label="View Health")
        d = link.to_dict()
        self.assertEqual(d["url"], "/health/")
        self.assertEqual(d["label"], "View Health")
        self.assertEqual(d["style"], "link")
        self.assertNotIn("icon", d)  # Empty icon omitted

    def test_to_dict_with_icon(self):
        from apps.core.ai_orchestrator.action_contracts import ActionLink

        link = ActionLink(url="/health/", label="View", icon="chart")
        d = link.to_dict()
        self.assertEqual(d["icon"], "chart")


class EnrichResponseWithContractsTests(TestCase):
    """Tests for enrich_response_with_contracts()."""

    def test_with_action_results(self):
        from apps.core.ai_orchestrator.action_contracts import enrich_response_with_contracts

        result = MagicMock()
        result.success = True
        result.action_type = "log_weight"
        result.message = "Logged 180 lbs"
        result.created_object = None

        contracts = enrich_response_with_contracts([result])
        self.assertEqual(len(contracts), 1)
        self.assertTrue(contracts[0]["success"])
        self.assertIn("view_url", contracts[0])

    def test_with_enriched_actions_fallback(self):
        from apps.core.ai_orchestrator.action_contracts import enrich_response_with_contracts

        result = MagicMock()
        result.success = True
        result.action_type = None  # Not set on result
        result.message = "Logged prayer"
        result.created_object = None

        action = MagicMock()
        action.intent_type = "log_prayer"

        contracts = enrich_response_with_contracts([result], [action])
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["intent_type"], "log_prayer")

    def test_empty_results(self):
        from apps.core.ai_orchestrator.action_contracts import enrich_response_with_contracts

        contracts = enrich_response_with_contracts([])
        self.assertEqual(contracts, [])


# ---------------------------------------------------------------------------
# Response Builder Enhancement Tests
# ---------------------------------------------------------------------------

class ResponseBuilderWithContractsTests(TestCase):
    """Tests for build_response_with_contracts()."""

    def test_returns_tuple(self):
        from apps.core.ai_orchestrator.response_builder import build_response_with_contracts

        orch = MagicMock()
        orch.needs_clarification = False
        orch.action_results = []
        orch.actions_enriched = []

        response, contracts = build_response_with_contracts(orch)
        self.assertIsNone(response)
        self.assertEqual(contracts, [])

    def test_with_successful_action(self):
        from apps.core.ai_orchestrator.response_builder import build_response_with_contracts

        result = MagicMock()
        result.success = True
        result.action_type = "log_weight"
        result.message = "Logged 180 lbs"
        result.error = None
        result.created_object = None

        orch = MagicMock()
        orch.needs_clarification = False
        orch.action_results = [result]
        orch.actions_enriched = []

        response, contracts = build_response_with_contracts(orch)
        self.assertIsNotNone(response)
        self.assertEqual(len(contracts), 1)
        self.assertIn("view_url", contracts[0])


# ---------------------------------------------------------------------------
# CoS Context Integration Tests
# ---------------------------------------------------------------------------

class CosContextNavigablePagesTests(TestCase):
    """Tests for navigable pages injection into CoS context."""

    def test_navigable_pages_in_context(self):
        """build_cos_context includes navigable_pages."""
        from apps.core.ai_orchestrator.url_resolver import get_navigable_pages

        pages = get_navigable_pages()
        self.assertTrue(len(pages) > 0)

        # Check that dashboard is first (or at least present)
        urls = [p["url"] for p in pages]
        self.assertIn("/dashboard/", urls)
        self.assertIn("/health/weight/", urls)
        self.assertIn("/journal/", urls)

    def test_format_injection_includes_navigation(self):
        """format_cos_system_injection includes APP NAVIGATION section."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection
        from apps.core.ai_orchestrator.url_resolver import get_navigable_pages

        # Build a minimal context with navigable_pages
        context = {
            'navigable_pages': get_navigable_pages(),
            # Minimal required fields to avoid KeyErrors
            'blueprint_state': {},
            'calendar_events_today': [],
            'today_blocks_summary': [],
            'protected_tiers': [],
            'capacity_snapshot': {},
            'module_permissions': {},
        }

        injection = format_cos_system_injection(context)
        self.assertIn("APP NAVIGATION", injection)
        self.assertIn("/health/weight/", injection)
        self.assertIn("Weight Tracking", injection)
