# ==============================================================================
# File: apps/ai/tests/test_domain_entity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface Pillar 1 — the ENTITY branch. Verifies the
#   catalog-driven get_entity truth surface re-fronts the canonical Truth
#   Resolution Layer (DomainTruth.describe / describe_one) with honest statuses,
#   returns composed CompleteEntity (never raw rows), and that the Model Interface
#   tool + capability index are wired.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_entity import (
    get_domain_entity,
    entity_capability_index,
    entity_capable_domains,
)

User = get_user_model()


def _person(user, name):
    from apps.legacy.models import Person
    return Person.objects.create(user=user, display_name=name)


class DomainEntityServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="de@test.com", password="x")
        _person(cls.user, "Grandpa Joe")
        _person(cls.user, "Aunt May")

    # --- the core deterministic retrieval: list record-level entities ---
    def test_list_entities_of_a_type_is_ready(self):
        r = get_domain_entity(self.user, "legacy", entity_type="person")
        self.assertEqual(r["status"], "ready")
        self.assertGreaterEqual(r["count"], 2)
        first = r["entities"][0]
        # composed CompleteEntity, NOT a raw DB row
        self.assertIn("kind", first)
        self.assertIn("identity", first)
        self.assertNotIn("user_id", first)
        self.assertNotIn("password", first)

    # --- honest empty: a describable type with no records → empty, never error ---
    def test_type_with_no_records_is_empty(self):
        fresh = User.objects.create_user(email="empty@test.com", password="x")
        r = get_domain_entity(fresh, "legacy", entity_type="place")
        self.assertEqual(r["status"], "empty")
        self.assertEqual(r["count"], 0)

    # --- honest unsupported: bad type lists the describable ones ---
    def test_unsupported_type_lists_supported(self):
        r = get_domain_entity(self.user, "legacy", entity_type="bogus")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("person", r["supported_entity_types"])

    # --- honest unsupported_domain: unknown domain lists entity-capable ones ---
    def test_unknown_domain(self):
        r = get_domain_entity(self.user, "not_a_domain", entity_type="x")
        self.assertEqual(r["status"], "unsupported_domain")
        self.assertIn("legacy", r["entity_capable_domains"])

    # --- a registered domain that exposes no entities (journal) → unsupported ---
    def test_domain_without_entities_is_unsupported(self):
        r = get_domain_entity(self.user, "journal", entity_type="anything")
        self.assertEqual(r["status"], "unsupported")

    # --- no selector at all → honest unsupported asking for one ---
    def test_no_selector_is_unsupported(self):
        r = get_domain_entity(self.user, "legacy")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("person", r["supported_entity_types"])

    # --- name lookup on a provider without describe_one → honest unsupported ---
    def test_name_lookup_without_describe_one_is_unsupported(self):
        r = get_domain_entity(self.user, "legacy", name="Grandpa Joe")
        self.assertEqual(r["status"], "unsupported")


class EntityCatalogTests(TestCase):
    def test_domains_participate_via_the_catalog(self):
        idx = entity_capability_index()
        self.assertIn("legacy", idx)
        for t in ("memory", "person", "place"):
            self.assertIn(t, idx["legacy"])
        # medicine also describes entities (medication/supplement/otc/wellness)
        self.assertIn("medicine", idx)
        self.assertIn("legacy", entity_capable_domains())


class ModelInterfaceWiringTests(TestCase):
    """The get_entity tool is registered, correctly shaped, and dispatched."""

    def test_get_entity_registered_in_truth_tools(self):
        from apps.ai.model_interface.constitution import truth_tools, all_tools
        names = [t["function"]["name"] for t in truth_tools()]
        self.assertIn("get_entity", names)
        self.assertIn("get_entity",
                      [t["function"]["name"] for t in all_tools(writes_enabled=False)])

    def test_get_entity_schema_shape(self):
        from apps.ai.model_interface.constitution import truth_tools
        tool = next(t for t in truth_tools()
                    if t["function"]["name"] == "get_entity")
        params = tool["function"]["parameters"]
        self.assertEqual(set(params["required"]), {"domain"})
        self.assertIn("entity_type", params["properties"])
        self.assertIn("name", params["properties"])
        # domain enum is catalog-driven and includes an entity-capable domain
        self.assertIn("legacy", params["properties"]["domain"].get("enum", []))

    def test_capability_index_advertises_entities(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("truth_entities", caps)
        self.assertIn("person", caps["truth_entities"].get("legacy", []))

    def test_dispatch_wraps_entity_in_truth_envelope(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        user = User.objects.create_user(email="mie@test.com", password="x")
        _person(user, "Cousin Ada")
        svc = ModelInterfaceService(user, ai_service=object())  # AI unused for dispatch
        dispatch = svc._make_dispatch(turn_id="t", surface="chat", tools_called=[])
        out = dispatch("get_entity", {"domain": "legacy", "entity_type": "person"})
        self.assertIsInstance(out, dict)
        # wrapped in the canonical truth envelope (status carried through)
        self.assertNotEqual(out.get("status"), "error")
