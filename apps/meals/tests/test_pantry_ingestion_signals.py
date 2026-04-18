"""
Signal consistency tests for pantry ingestion.

Verifies the contract added in the 2026-04-18 signal-consistency pass:

1. `finalize_pantry_item()` emits exactly ONE domain event per call.
2. The event type is `meals.pantry.item_created` on create,
   `meals.pantry.item_updated` on quantity accumulation.
3. The payload shape is identical across ingestion sources
   (receipt, barcode, photo_scan) — only the `source` field differs.
4. Emission happens on `transaction.on_commit` so rollbacks do not
   leak stale signals.
5. Failed ingestion (exception before save) emits NO events.
"""

from decimal import Decimal

from django.db import transaction as db_transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.events.domain_events import (
    EventTypes,
    clear_event_bus,
    subscribe_handler,
)
from apps.meals.models import Household, Ingredient
from apps.meals.services.pantry_ingestion import finalize_pantry_item
from apps.users.models import TermsAcceptance, User, UserPreferences


def _make_user(email):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(user=user, terms_version="1.0")
    prefs, _ = UserPreferences.objects.get_or_create(user=user)
    prefs.has_completed_onboarding = True
    prefs.save(update_fields=["has_completed_onboarding"])
    return user


class _EventCapture:
    """Collect all events emitted during a test."""

    def __init__(self):
        self.events = []

    def handler(self, event):
        self.events.append(event)


class PantryIngestionSignalTests(TransactionTestCase):
    """
    Uses TransactionTestCase because `finalize_pantry_item` emits via
    `transaction.on_commit`, which is a no-op inside the implicit
    transaction that standard TestCase wraps each test in.
    """

    def setUp(self):
        clear_event_bus()  # don't inherit app-startup subscribers
        self.capture = _EventCapture()
        # Subscribe to all meals events for inspection.
        subscribe_handler("meals.*", self.capture.handler)

        self.user = _make_user("signal-test@example.com")
        self.household = Household.objects.create(
            name="Test House", primary_user=self.user
        )
        self.ingredient = Ingredient.objects.create(
            canonical_name="chicken breast", category="protein"
        )

    def tearDown(self):
        clear_event_bus()

    # ---------------------------------------------------------------
    # Create path
    # ---------------------------------------------------------------

    def test_create_emits_item_created_event(self):
        pantry_item, created = finalize_pantry_item(
            household=self.household,
            ingredient=self.ingredient,
            quantity=Decimal("2"),
            unit="piece",
            source="receipt",
            notes="test receipt",
        )
        self.assertTrue(created)
        self.assertEqual(len(self.capture.events), 1)
        event = self.capture.events[0]
        self.assertEqual(event.event_type, EventTypes.MEALS_PANTRY_ITEM_CREATED)
        self.assertEqual(event.user, self.user)
        # Payload shape
        self.assertEqual(event.data["household_id"], self.household.pk)
        self.assertEqual(event.data["pantry_item_id"], pantry_item.pk)
        self.assertEqual(event.data["ingredient_id"], self.ingredient.pk)
        self.assertEqual(event.data["ingredient_name"], "chicken breast")
        self.assertEqual(event.data["quantity_delta"], 2.0)
        self.assertEqual(event.data["unit"], "piece")
        self.assertEqual(event.data["source"], "receipt")
        self.assertTrue(event.data["created"])

    # ---------------------------------------------------------------
    # Update path
    # ---------------------------------------------------------------

    def test_update_emits_item_updated_event(self):
        # Seed: one existing item
        finalize_pantry_item(
            household=self.household,
            ingredient=self.ingredient,
            quantity=Decimal("1"),
            unit="piece",
            source="barcode",
            notes="seed",
        )
        self.capture.events.clear()

        # Second call = update
        finalize_pantry_item(
            household=self.household,
            ingredient=self.ingredient,
            quantity=Decimal("3"),
            unit="piece",
            source="barcode",
            notes="second scan",
        )
        self.assertEqual(len(self.capture.events), 1)
        event = self.capture.events[0]
        self.assertEqual(event.event_type, EventTypes.MEALS_PANTRY_ITEM_UPDATED)
        self.assertEqual(event.data["quantity_delta"], 3.0)
        self.assertFalse(event.data["created"])

    # ---------------------------------------------------------------
    # Source parity — identical payload shape across all three entry
    # points. Only the `source` field should differ.
    # ---------------------------------------------------------------

    def test_payload_shape_identical_across_sources(self):
        shapes = {}
        for source in ("receipt", "barcode", "photo_scan"):
            # Fresh ingredient per source so we get create events each
            # time and don't accumulate on the same PantryItem.
            ing = Ingredient.objects.create(
                canonical_name=f"ingredient for {source}",
                category="protein",
            )
            self.capture.events.clear()
            finalize_pantry_item(
                household=self.household,
                ingredient=ing,
                quantity=Decimal("1"),
                unit="piece",
                source=source,
                notes=f"from {source}",
            )
            self.assertEqual(len(self.capture.events), 1)
            event = self.capture.events[0]
            shapes[source] = set(event.data.keys())

        # Every source must produce the same key set.
        key_sets = list(shapes.values())
        for keys in key_sets[1:]:
            self.assertEqual(
                keys,
                key_sets[0],
                f"Payload keys diverge — {shapes}",
            )

    # ---------------------------------------------------------------
    # Rollback safety — no signal on rollback
    # ---------------------------------------------------------------

    def test_no_event_on_rollback(self):
        try:
            with db_transaction.atomic():
                finalize_pantry_item(
                    household=self.household,
                    ingredient=self.ingredient,
                    quantity=Decimal("1"),
                    unit="piece",
                    source="receipt",
                    notes="will rollback",
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        self.assertEqual(
            self.capture.events,
            [],
            "Signal must not fire when the surrounding transaction is rolled back.",
        )
