"""
Transformation Action Handler tests.

Tests all 3 handlers: transformation protocol, shopping item, complete shopping item.
Validates handlers do domain ORM only — intelligence pipeline triggered by execution engine.
"""

from datetime import date

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import TermsAcceptance, User


def _create_test_user(email="handler_test@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.ai_data_consent = True
    user.preferences.ai_data_consent_date = timezone.now()
    user.preferences.save()
    return user


def _get_handler(user):
    from apps.ai.action_handlers import ActionHandler
    return ActionHandler(user)


# ── log_transformation_protocol ─────────────────────────────────


class TestHandleLogTransformationProtocol(TestCase):
    def setUp(self):
        self.user = _create_test_user("handler_proto@example.com")
        self.handler = _get_handler(self.user)

    def test_creates_protocol_successfully(self):
        result = self.handler.handle_log_transformation_protocol(
            name="12-Week Cut",
            protocol_type="cut",
            start_date=date.today(),
        )
        self.assertTrue(result.success)
        self.assertIn("12-Week Cut", result.message)
        self.assertIsNotNone(result.created_object)
        self.assertIn("id", result.created_object)

    def test_creates_with_defaults(self):
        result = self.handler.handle_log_transformation_protocol()
        self.assertTrue(result.success)
        # Should use default name and type
        self.assertIn("id", result.created_object)

    def test_creates_with_all_fields(self):
        from apps.health.models import TransformationProtocol

        result = self.handler.handle_log_transformation_protocol(
            name="Summer Bulk",
            protocol_type="bulk",
            start_date=date.today(),
            goal_weight=200,
            goal_body_fat=15,
            notes="Gain muscle mass",
        )
        self.assertTrue(result.success)

        protocol = TransformationProtocol.objects.get(id=result.created_object["id"])
        self.assertEqual(protocol.name, "Summer Bulk")
        self.assertEqual(protocol.protocol_type, "bulk")

    def test_handler_does_not_import_intelligence_engines(self):
        """Verify handler source doesn't import SAE/PIE/PRIE/PGE."""
        import inspect
        source = inspect.getsource(self.handler.handle_log_transformation_protocol)
        self.assertNotIn("ai_state", source)
        self.assertNotIn("ai_insights", source)
        self.assertNotIn("ai_predictions", source)
        self.assertNotIn("ai_guidance", source)


# ── log_shopping_item ───────────────────────────────────────────


class TestHandleLogShoppingItem(TestCase):
    def setUp(self):
        self.user = _create_test_user("handler_shop@example.com")
        self.handler = _get_handler(self.user)

    def test_creates_item_successfully(self):
        result = self.handler.handle_log_shopping_item(
            name="Chicken Breast",
            quantity="2 lbs",
            category="protein",
        )
        self.assertTrue(result.success)
        self.assertIn("Chicken Breast", result.message)

    def test_creates_shopping_list_if_needed(self):
        from apps.life.models import ShoppingList

        result = self.handler.handle_log_shopping_item(
            name="Eggs",
            list_name="Meal Prep Week 3",
        )
        self.assertTrue(result.success)

        sl = ShoppingList.objects.get(user=self.user, name="Meal Prep Week 3")
        self.assertIsNotNone(sl)

    def test_fails_without_item_name(self):
        result = self.handler.handle_log_shopping_item()
        self.assertFalse(result.success)

    def test_uses_default_list_name(self):
        from apps.life.models import ShoppingList

        self.handler.handle_log_shopping_item(name="Broccoli")
        sl = ShoppingList.objects.get(user=self.user, name="Shopping List")
        self.assertIsNotNone(sl)


# ── complete_shopping_item ──────────────────────────────────────


class TestHandleCompleteShoppingItem(TestCase):
    def setUp(self):
        self.user = _create_test_user("handler_complete@example.com")
        self.handler = _get_handler(self.user)

    def test_marks_item_purchased(self):
        from apps.life.models import ShoppingItem, ShoppingList

        sl = ShoppingList.objects.create(user=self.user, name="List")
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=sl,
            name="Chicken",
        )

        result = self.handler.handle_complete_shopping_item(name="Chicken")
        self.assertTrue(result.success)

        item.refresh_from_db()
        self.assertTrue(item.is_purchased)
        self.assertIsNotNone(item.purchased_at)

    def test_fails_without_name(self):
        result = self.handler.handle_complete_shopping_item()
        self.assertFalse(result.success)

    def test_fails_item_not_found(self):
        result = self.handler.handle_complete_shopping_item(name="Nonexistent")
        self.assertFalse(result.success)


# ── Intent Routing ──────────────────────────────────────────────


class TestTransformationIntentRouting(TestCase):
    def test_intent_engine_routes_transformation(self):
        from apps.core.ai_orchestrator.intent_engine import get_intent_module

        self.assertEqual(
            get_intent_module("log_transformation_protocol"), "health"
        )

    def test_intent_engine_routes_shopping_item(self):
        from apps.core.ai_orchestrator.intent_engine import get_intent_module

        self.assertEqual(get_intent_module("log_shopping_item"), "life")

    def test_intent_engine_routes_complete_shopping(self):
        from apps.core.ai_orchestrator.intent_engine import get_intent_module

        self.assertEqual(get_intent_module("complete_shopping_item"), "life")
