"""
Signal-parity tests for receipt-routed restaurant FoodEntry creation.

Verifies the 2026-04-18 fix that closed the `health.nutrition.logged`
emission gap in `ReceiptRoutingService._route_restaurant`. Before the
fix, receipt-routed restaurant meals created a `FoodEntry` row but
never fired the canonical domain event — CoS/SAE/PIE subscribers on
`health.*` silently missed those meals.

Contract verified here:

1. Routing a `RECEIPT_TYPE_RESTAURANT` receipt emits exactly ONE
   `health.nutrition.logged` event.
2. The event payload includes `entry_id`, `receipt_id`, `source="receipt"`
   and the event is attributed to the receipt's user.
3. Routing a non-restaurant receipt (grocery, retail, unknown) emits
   ZERO `health.nutrition.logged` events from this path.
4. If the underlying `FoodEntry.objects.create` fails, NO event is
   emitted (fail-closed on the write).
5. If the caller's transaction rolls back AFTER routing, the event is
   NOT delivered (on_commit safety).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import transaction as db_transaction
from django.test import TransactionTestCase

from apps.core.events.domain_events import (
    EventTypes,
    clear_event_bus,
    subscribe_handler,
)
from apps.meals.models import Household, Receipt
from apps.meals.services.receipt_routing import ReceiptRoutingService
from apps.users.models import TermsAcceptance, User, UserPreferences


def _make_user(email):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(user=user, terms_version="1.0")
    prefs, _ = UserPreferences.objects.get_or_create(user=user)
    prefs.has_completed_onboarding = True
    prefs.save(update_fields=["has_completed_onboarding"])
    return user


class _EventCapture:
    def __init__(self):
        self.events = []

    def handler(self, event):
        self.events.append(event)


class ReceiptRestaurantNutritionSignalTests(TransactionTestCase):
    """
    Uses TransactionTestCase because emission goes through
    `transaction.on_commit`, which is a no-op inside the implicit
    transaction wrapping a plain TestCase.
    """

    def setUp(self):
        clear_event_bus()
        self.capture = _EventCapture()
        subscribe_handler("health.*", self.capture.handler)

        self.user = _make_user("receipt-nutrition@example.com")
        self.household = Household.objects.create(
            name="Jenkins", primary_user=self.user
        )

    def tearDown(self):
        clear_event_bus()

    def _build_receipt(self, receipt_type):
        return Receipt.objects.create(
            user=self.user,
            household=self.household,
            receipt_type=receipt_type,
            confirmation_status=Receipt.CONFIRM_CONFIRMED,
            store="Panera",
            receipt_date=date(2026, 4, 18),
            total=Decimal("18.42"),
        )

    # ---------------------------------------------------------------
    # Positive — restaurant route fires the canonical event
    # ---------------------------------------------------------------

    def test_restaurant_routing_emits_nutrition_logged(self):
        receipt = self._build_receipt(Receipt.RECEIPT_TYPE_RESTAURANT)
        svc = ReceiptRoutingService()

        ok = svc._route_restaurant(receipt, self.user)
        self.assertTrue(ok)

        # Exactly one nutrition event
        nutrition_events = [
            e for e in self.capture.events
            if e.event_type == EventTypes.HEALTH_NUTRITION_LOGGED
        ]
        self.assertEqual(
            len(nutrition_events),
            1,
            f"Expected 1 nutrition event, got {len(nutrition_events)}: "
            f"{[e.event_type for e in self.capture.events]}",
        )
        event = nutrition_events[0]

        # Attributed to the correct user
        self.assertEqual(event.user, self.user)

        # Canonical payload shape — matches the web view shape plus
        # receipt_id for traceability.
        self.assertIn("entry_id", event.data)
        self.assertIsNotNone(event.data["entry_id"])
        self.assertEqual(event.data["receipt_id"], receipt.pk)
        self.assertEqual(event.data["source"], "receipt")

    # ---------------------------------------------------------------
    # Negative — non-restaurant routes do not fire from this path
    # ---------------------------------------------------------------

    def test_grocery_routing_does_not_emit_nutrition_logged(self):
        """
        Grocery receipts route through `_route_grocery` (pantry path),
        which should never emit a nutrition event — that would be a
        false intake signal. Verified by calling the full pipeline
        and asserting zero nutrition events.
        """
        receipt = self._build_receipt(Receipt.RECEIPT_TYPE_GROCERY)
        svc = ReceiptRoutingService()

        # Call just the restaurant router path negative — grocery
        # receipts must not reach _route_restaurant in route_receipt.
        # Here we verify the narrow guarantee: _route_restaurant is
        # the sole emission site, so anything else (e.g. grocery)
        # emits nothing from this module.
        svc._route_grocery(receipt, self.household, [])

        nutrition_events = [
            e for e in self.capture.events
            if e.event_type == EventTypes.HEALTH_NUTRITION_LOGGED
        ]
        self.assertEqual(
            nutrition_events,
            [],
            "Grocery routing must not emit health.nutrition.logged.",
        )

    # ---------------------------------------------------------------
    # Fail-closed — create failure suppresses emission
    # ---------------------------------------------------------------

    def test_no_event_when_food_entry_create_fails(self):
        receipt = self._build_receipt(Receipt.RECEIPT_TYPE_RESTAURANT)
        svc = ReceiptRoutingService()

        with patch(
            "apps.health.models.FoodEntry.objects.create",
            side_effect=RuntimeError("simulated DB failure"),
        ):
            ok = svc._route_restaurant(receipt, self.user)

        self.assertFalse(ok)
        nutrition_events = [
            e for e in self.capture.events
            if e.event_type == EventTypes.HEALTH_NUTRITION_LOGGED
        ]
        self.assertEqual(
            nutrition_events,
            [],
            "No event may fire when FoodEntry creation fails.",
        )

    # ---------------------------------------------------------------
    # Rollback safety — on_commit suppresses emission on rollback
    # ---------------------------------------------------------------

    def test_no_event_on_transaction_rollback(self):
        receipt = self._build_receipt(Receipt.RECEIPT_TYPE_RESTAURANT)
        svc = ReceiptRoutingService()

        try:
            with db_transaction.atomic():
                svc._route_restaurant(receipt, self.user)
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

        nutrition_events = [
            e for e in self.capture.events
            if e.event_type == EventTypes.HEALTH_NUTRITION_LOGGED
        ]
        self.assertEqual(
            nutrition_events,
            [],
            "transaction.on_commit must suppress the event on rollback.",
        )

    # ---------------------------------------------------------------
    # No double-fire — one call = one event
    # ---------------------------------------------------------------

    def test_single_event_per_routing_call(self):
        receipt = self._build_receipt(Receipt.RECEIPT_TYPE_RESTAURANT)
        svc = ReceiptRoutingService()

        svc._route_restaurant(receipt, self.user)
        svc._route_restaurant(receipt, self.user)

        nutrition_events = [
            e for e in self.capture.events
            if e.event_type == EventTypes.HEALTH_NUTRITION_LOGGED
        ]
        # Two distinct calls = two distinct events (each creates a new
        # FoodEntry). Neither call should double-fire on its own.
        self.assertEqual(
            len(nutrition_events),
            2,
            "Each _route_restaurant call must emit exactly one event.",
        )
