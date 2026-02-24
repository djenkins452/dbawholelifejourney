"""
CoS v2 — Phase 1 Tests: Action Contract + Registry

Tests:
1. CosActionContract: cannot instantiate directly, subclass enforcement
2. CosActionRegistry: register, get, list, duplicate rejection, type checking
3. Contract defaults: default implementations return expected values
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.cos.contracts import (
    ActionResult,
    ConflictCheck,
    CosActionContract,
    DuplicateCheck,
)
from apps.cos.registry import CosActionRegistry

User = get_user_model()


# ──────────────────────────────────────────────────────────
# Concrete test implementation
# ──────────────────────────────────────────────────────────


class FakeCosActions(CosActionContract):
    """Minimal concrete implementation for testing."""

    @property
    def module_name(self) -> str:
        return "fake"

    def create(self, **kwargs):
        return ActionResult(success=True, metadata={"created": True})

    def retrieve(self, entity_id: int):
        return ActionResult(success=True, entity_id=entity_id)

    def summarise(self, **kwargs):
        return ActionResult(success=True, metadata={"summary": "test"})


class AnotherFakeCosActions(CosActionContract):
    """Second concrete implementation for registry tests."""

    @property
    def module_name(self) -> str:
        return "another_fake"

    def create(self, **kwargs):
        return ActionResult(success=True)

    def retrieve(self, entity_id: int):
        return ActionResult(success=True, entity_id=entity_id)

    def summarise(self, **kwargs):
        return ActionResult(success=True)


# ──────────────────────────────────────────────────────────
# Contract Tests
# ──────────────────────────────────────────────────────────


class CosActionContractTests(TestCase):
    """Test the abstract contract and its default behaviors."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="contract@example.com", password="testpass123"
        )
        self.actions = FakeCosActions(user=self.user)

    def test_cannot_instantiate_abstract(self):
        """CosActionContract cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            CosActionContract(user=self.user)

    def test_module_name(self):
        """Concrete implementation returns correct module name."""
        self.assertEqual(self.actions.module_name, "fake")

    def test_create_returns_action_result(self):
        """create() returns ActionResult."""
        result = self.actions.create()
        self.assertIsInstance(result, ActionResult)
        self.assertTrue(result.success)

    def test_retrieve_returns_action_result(self):
        """retrieve() returns ActionResult with entity_id."""
        result = self.actions.retrieve(entity_id=42)
        self.assertEqual(result.entity_id, 42)

    def test_summarise_returns_action_result(self):
        """summarise() returns ActionResult."""
        result = self.actions.summarise()
        self.assertTrue(result.success)

    def test_default_update_not_supported(self):
        """Default update() returns failure."""
        result = self.actions.update(entity_id=1)
        self.assertFalse(result.success)
        self.assertIn("does not support update", result.error)

    def test_default_delete_not_supported(self):
        """Default delete() returns failure."""
        result = self.actions.delete(entity_id=1)
        self.assertFalse(result.success)
        self.assertIn("does not support delete", result.error)

    def test_default_check_duplicate_no_dup(self):
        """Default check_duplicate() returns no duplicate."""
        result = self.actions.check_duplicate()
        self.assertIsInstance(result, DuplicateCheck)
        self.assertFalse(result.is_duplicate)

    def test_default_check_conflicts_no_conflict(self):
        """Default check_conflicts() returns no conflict."""
        result = self.actions.check_conflicts()
        self.assertIsInstance(result, ConflictCheck)
        self.assertFalse(result.has_conflict)

    def test_default_reflection_hook_returns_false(self):
        """Default capture_reflection_hook() returns False."""
        self.assertFalse(
            self.actions.capture_reflection_hook(entity_id=1, reflection_text="test")
        )

    def test_default_supports_reflections_false(self):
        """Default supports_reflections() is False."""
        self.assertFalse(self.actions.supports_reflections())

    def test_default_supports_proactive_prompts_false(self):
        """Default supports_proactive_prompts() is False."""
        self.assertFalse(self.actions.supports_proactive_prompts())

    def test_user_stored_on_instance(self):
        """User is accessible on the contract instance."""
        self.assertEqual(self.actions.user, self.user)


# ──────────────────────────────────────────────────────────
# Result Dataclass Tests
# ──────────────────────────────────────────────────────────


class ActionResultTests(TestCase):
    """Test ActionResult defaults and field access."""

    def test_defaults(self):
        result = ActionResult(success=True)
        self.assertTrue(result.success)
        self.assertIsNone(result.entity)
        self.assertIsNone(result.entity_id)
        self.assertFalse(result.reused)
        self.assertIsNone(result.error)
        self.assertFalse(result.requires_decision)
        self.assertIsNone(result.decision_options)
        self.assertEqual(result.metadata, {})

    def test_with_decision_options(self):
        options = [{"action": "shift_15min"}, {"action": "next_slot"}]
        result = ActionResult(
            success=False,
            requires_decision=True,
            decision_options=options,
        )
        self.assertTrue(result.requires_decision)
        self.assertEqual(len(result.decision_options), 2)


class DuplicateCheckTests(TestCase):
    """Test DuplicateCheck defaults."""

    def test_no_duplicate(self):
        check = DuplicateCheck(is_duplicate=False)
        self.assertFalse(check.is_duplicate)
        self.assertIsNone(check.existing_entity)

    def test_duplicate_found(self):
        check = DuplicateCheck(
            is_duplicate=True,
            existing_entity_id=99,
            match_type="semantic",
            message="Same title and time",
        )
        self.assertTrue(check.is_duplicate)
        self.assertEqual(check.match_type, "semantic")


class ConflictCheckTests(TestCase):
    """Test ConflictCheck defaults."""

    def test_no_conflict(self):
        check = ConflictCheck(has_conflict=False)
        self.assertFalse(check.has_conflict)
        self.assertEqual(check.conflicts, [])
        self.assertEqual(check.suggested_resolutions, [])


# ──────────────────────────────────────────────────────────
# Registry Tests
# ──────────────────────────────────────────────────────────


class CosActionRegistryTests(TestCase):
    """Test the action registry register/get/list/clear."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="registry@example.com", password="testpass123"
        )
        # Use a fresh registry for each test
        self.registry = CosActionRegistry()

    def test_register_and_get(self):
        """Register a contract and retrieve it."""
        self.registry.register("fake", FakeCosActions)
        actions = self.registry.get("fake", user=self.user)
        self.assertIsNotNone(actions)
        self.assertIsInstance(actions, FakeCosActions)
        self.assertEqual(actions.module_name, "fake")
        self.assertEqual(actions.user, self.user)

    def test_get_unregistered_returns_none(self):
        """get() returns None for unregistered module."""
        self.assertIsNone(self.registry.get("nonexistent", user=self.user))

    def test_get_or_raise_raises_for_unregistered(self):
        """get_or_raise() raises KeyError for unregistered module."""
        with self.assertRaises(KeyError):
            self.registry.get_or_raise("nonexistent", user=self.user)

    def test_duplicate_registration_raises(self):
        """Registering the same module twice raises ValueError."""
        self.registry.register("fake", FakeCosActions)
        with self.assertRaises(ValueError):
            self.registry.register("fake", AnotherFakeCosActions)

    def test_non_contract_class_raises(self):
        """Registering a non-CosActionContract class raises TypeError."""
        with self.assertRaises(TypeError):
            self.registry.register("bad", dict)

    def test_instance_not_class_raises(self):
        """Registering an instance (not a class) raises TypeError."""
        instance = FakeCosActions(user=self.user)
        with self.assertRaises(TypeError):
            self.registry.register("bad", instance)

    def test_list_modules(self):
        """list_modules() returns sorted list of registered names."""
        self.registry.register("zebra", FakeCosActions)
        self.registry.register("alpha", AnotherFakeCosActions)
        self.assertEqual(self.registry.list_modules(), ["alpha", "zebra"])

    def test_is_registered(self):
        """is_registered() returns correct boolean."""
        self.assertFalse(self.registry.is_registered("fake"))
        self.registry.register("fake", FakeCosActions)
        self.assertTrue(self.registry.is_registered("fake"))

    def test_unregister(self):
        """unregister() removes a module."""
        self.registry.register("fake", FakeCosActions)
        self.registry.unregister("fake")
        self.assertFalse(self.registry.is_registered("fake"))

    def test_unregister_nonexistent_no_error(self):
        """unregister() on nonexistent module does not raise."""
        self.registry.unregister("nonexistent")  # Should not raise

    def test_clear(self):
        """clear() removes all registrations."""
        self.registry.register("a", FakeCosActions)
        self.registry.register("b", AnotherFakeCosActions)
        self.registry.clear()
        self.assertEqual(self.registry.list_modules(), [])

    def test_each_get_returns_new_instance(self):
        """Each get() call returns a fresh instance (not shared state)."""
        self.registry.register("fake", FakeCosActions)
        a1 = self.registry.get("fake", user=self.user)
        a2 = self.registry.get("fake", user=self.user)
        self.assertIsNot(a1, a2)
