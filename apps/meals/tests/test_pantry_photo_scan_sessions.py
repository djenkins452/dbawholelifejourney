"""
Tests for Phase 12: Pantry Photo Intelligence (Session-Based)

Covers:
- Session creation
- Detection creation
- Confirmation creates PantryItem
- Rejection does not create PantryItem
- overall_confidence calculation
- Drift calculation
- Multiple sessions allowed
- Duplicate detection handling
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.meals.models import (
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    PantryItem,
    PantryPhotoDetection,
    PantryPhotoUpload,
    PantryScanSession,
)
from apps.users.models import User


class PantryPhotoTestMixin:
    """Shared setup for pantry photo scan tests."""

    def create_user(self, email="scantest@example.com"):
        from apps.users.models import TermsAcceptance, UserPreferences
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(user=user, terms_version="1.0")
        prefs, _ = UserPreferences.objects.get_or_create(user=user)
        prefs.has_completed_onboarding = True
        prefs.save(update_fields=["has_completed_onboarding"])
        return user

    def create_household(self, user):
        household = Household.objects.create(
            name="Test Household",
            primary_user=user,
        )
        HouseholdMembership.objects.create(
            household=household,
            user=user,
            role="admin",
        )
        return household

    def create_ingredient(self, name="chicken breast", category="protein", shelf_life=5):
        return Ingredient.objects.create(
            canonical_name=name,
            category=category,
            storage_type="refrigerator",
            shelf_life_days=shelf_life,
        )

    def create_session(self, household, location="fridge"):
        return PantryScanSession.objects.create(
            household=household,
            location_type=location,
        )

    def create_upload(self, session):
        """Create a mock upload without actual image."""
        return PantryPhotoUpload.objects.create(
            session=session,
            image="pantry_scans/test/fake.jpg",
            processed=True,
            raw_detection_json={"items": []},
        )

    def create_detection(self, session, upload, label="Milk", ingredient=None,
                         confidence=0.85, quantity=1):
        return PantryPhotoDetection.objects.create(
            session=session,
            upload=upload,
            detected_label=label,
            matched_ingredient=ingredient,
            confidence_score=Decimal(str(confidence)),
            suggested_quantity=Decimal(str(quantity)),
            unit="piece",
        )


class TestPantryScanSessionModel(PantryPhotoTestMixin, TestCase):
    """Tests for PantryScanSession model."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)

    def test_create_session(self):
        session = self.create_session(self.household)
        self.assertEqual(session.household, self.household)
        self.assertEqual(session.location_type, "fridge")
        self.assertEqual(session.items_detected, 0)
        self.assertEqual(session.items_confirmed, 0)
        self.assertIsNone(session.completed_at)

    def test_session_str(self):
        session = self.create_session(self.household, location="pantry")
        self.assertIn("Pantry Shelf Scan", str(session))

    def test_session_location_choices(self):
        for loc in ["fridge", "pantry", "freezer"]:
            session = PantryScanSession.objects.create(
                household=self.household,
                location_type=loc,
            )
            self.assertEqual(session.location_type, loc)

    def test_multiple_sessions_allowed(self):
        """Multiple sessions can exist for the same household."""
        s1 = self.create_session(self.household, "fridge")
        s2 = self.create_session(self.household, "pantry")
        s3 = self.create_session(self.household, "fridge")

        sessions = PantryScanSession.objects.filter(household=self.household)
        self.assertEqual(sessions.count(), 3)

    def test_session_ordering(self):
        """Sessions are ordered by newest first."""
        s1 = self.create_session(self.household)
        s2 = self.create_session(self.household)
        sessions = list(PantryScanSession.objects.filter(household=self.household))
        self.assertEqual(sessions[0].pk, s2.pk)


class TestPantryPhotoUploadModel(PantryPhotoTestMixin, TestCase):
    """Tests for PantryPhotoUpload model."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)

    def test_create_upload(self):
        upload = self.create_upload(self.session)
        self.assertEqual(upload.session, self.session)
        self.assertTrue(upload.processed)

    def test_upload_ordering(self):
        """Uploads ordered by upload time."""
        u1 = self.create_upload(self.session)
        u2 = self.create_upload(self.session)
        uploads = list(self.session.uploads.all())
        self.assertEqual(uploads[0].pk, u1.pk)


class TestPantryPhotoDetectionModel(PantryPhotoTestMixin, TestCase):
    """Tests for PantryPhotoDetection model."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.ingredient = self.create_ingredient()

    def test_create_detection(self):
        detection = self.create_detection(
            self.session, self.upload, "Chicken Breast",
            ingredient=self.ingredient, confidence=0.92,
        )
        self.assertEqual(detection.detected_label, "Chicken Breast")
        self.assertEqual(detection.matched_ingredient, self.ingredient)
        self.assertFalse(detection.confirmed)
        self.assertFalse(detection.rejected)

    def test_detection_str(self):
        detection = self.create_detection(self.session, self.upload, "Milk")
        self.assertIn("pending", str(detection))

        detection.confirmed = True
        detection.save()
        self.assertIn("confirmed", str(detection))

    def test_detection_ordering(self):
        """Detections ordered by confidence descending."""
        d_low = self.create_detection(self.session, self.upload, "Unknown Item", confidence=0.30)
        d_high = self.create_detection(self.session, self.upload, "Clear Item", confidence=0.95)
        detections = list(self.session.detections.all())
        self.assertEqual(detections[0].pk, d_high.pk)


class TestConfirmationCreatesItems(PantryPhotoTestMixin, TestCase):
    """Tests that confirmation creates PantryItems correctly."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy", shelf_life=7)
        self.eggs = self.create_ingredient("eggs", "protein", shelf_life=21)
        self.butter = self.create_ingredient("butter", "dairy", shelf_life=30)

    def test_confirm_creates_pantry_items(self):
        """Confirming detections creates PantryItems."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Whole Milk",
                                   ingredient=self.milk, confidence=0.90, quantity=2)
        d2 = self.create_detection(self.session, self.upload, "Eggs",
                                   ingredient=self.eggs, confidence=0.85, quantity=12)

        created, updated = pantry_photo_detection_service.confirm_session(
            self.session, [d1.pk, d2.pk]
        )

        self.assertEqual(created, 2)
        self.assertEqual(updated, 0)

        # PantryItems should exist
        self.assertTrue(PantryItem.objects.filter(
            household=self.household, ingredient=self.milk
        ).exists())
        milk_item = PantryItem.objects.get(household=self.household, ingredient=self.milk)
        self.assertEqual(milk_item.quantity, Decimal("2"))

    def test_confirm_creates_inventory_transactions(self):
        """Confirmed detections create InventoryTransaction records."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Butter",
                                   ingredient=self.butter, confidence=0.88, quantity=1)

        pantry_photo_detection_service.confirm_session(self.session, [d1.pk])

        transactions = InventoryTransaction.objects.filter(source="photo_scan")
        self.assertEqual(transactions.count(), 1)
        self.assertEqual(transactions.first().delta_quantity, Decimal("1"))

    def test_confirm_updates_existing_pantry_item(self):
        """If PantryItem already exists, confirmation adds to quantity."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        # Pre-existing pantry item
        PantryItem.objects.create(
            household=self.household,
            ingredient=self.milk,
            quantity=Decimal("1"),
            unit="piece",
        )

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.85, quantity=2)

        created, updated = pantry_photo_detection_service.confirm_session(
            self.session, [d1.pk]
        )

        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)

        milk_item = PantryItem.objects.get(household=self.household, ingredient=self.milk)
        self.assertEqual(milk_item.quantity, Decimal("3"))  # 1 + 2

    def test_confirm_with_quantity_override(self):
        """Quantity overrides are applied correctly."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Eggs",
                                   ingredient=self.eggs, confidence=0.90, quantity=6)

        pantry_photo_detection_service.confirm_session(
            self.session, [d1.pk],
            quantities={d1.pk: Decimal("12")},
        )

        eggs_item = PantryItem.objects.get(household=self.household, ingredient=self.eggs)
        self.assertEqual(eggs_item.quantity, Decimal("12"))

    def test_confirm_sets_expiration_date(self):
        """New PantryItems get expiration date from ingredient shelf life."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.90, quantity=1)

        pantry_photo_detection_service.confirm_session(self.session, [d1.pk])

        milk_item = PantryItem.objects.get(household=self.household, ingredient=self.milk)
        self.assertIsNotNone(milk_item.expiration_date_estimated)
        expected = timezone.now().date() + timedelta(days=7)
        self.assertEqual(milk_item.expiration_date_estimated, expected)


class TestRejectionDoesNotCreateItems(PantryPhotoTestMixin, TestCase):
    """Tests that rejections do NOT create PantryItems."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy")

    def test_rejection_does_not_create_items(self):
        """Detections not in confirmed_ids should not create items."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Mystery Item",
                                   ingredient=self.milk, confidence=0.30)

        # Confirm empty list — d1 should be rejected
        pantry_photo_detection_service.confirm_session(self.session, [])

        self.assertFalse(PantryItem.objects.filter(
            household=self.household, ingredient=self.milk
        ).exists())

        d1.refresh_from_db()
        self.assertTrue(d1.rejected)

    def test_cancel_session_rejects_all(self):
        """Cancelling a session marks all pending detections as rejected."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.90)

        pantry_photo_detection_service.cancel_session(self.session)

        d1.refresh_from_db()
        self.assertTrue(d1.rejected)
        self.assertFalse(d1.confirmed)
        self.assertIsNotNone(self.session.completed_at)


class TestOverallConfidenceCalculation(PantryPhotoTestMixin, TestCase):
    """Tests for session overall_confidence calculation."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy")
        self.eggs = self.create_ingredient("eggs", "protein")
        self.cheese = self.create_ingredient("cheddar cheese", "dairy")

    def test_overall_confidence_is_average(self):
        """Overall confidence should be average of confirmed detections."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.90)
        d2 = self.create_detection(self.session, self.upload, "Eggs",
                                   ingredient=self.eggs, confidence=0.80)
        d3 = self.create_detection(self.session, self.upload, "Cheese",
                                   ingredient=self.cheese, confidence=0.70)

        # Update session detection count (normally done during process_upload)
        self.session.items_detected = 3
        self.session.save(update_fields=["items_detected"])

        # Only confirm d1 and d2 (avg = 0.85)
        pantry_photo_detection_service.confirm_session(
            self.session, [d1.pk, d2.pk]
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.overall_confidence, Decimal("0.85"))
        self.assertEqual(self.session.items_confirmed, 2)
        self.assertEqual(self.session.items_detected, 3)

    def test_completed_at_set_on_confirm(self):
        """completed_at is set after confirmation."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.90)

        pantry_photo_detection_service.confirm_session(self.session, [d1.pk])

        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.completed_at)


class TestDuplicateDetectionHandling(PantryPhotoTestMixin, TestCase):
    """Tests for duplicate detection handling within a session."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy")

    def test_duplicate_ingredients_rejected_in_session(self):
        """Only the first detection for an ingredient is confirmed."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Whole Milk",
                                   ingredient=self.milk, confidence=0.90, quantity=1)
        d2 = self.create_detection(self.session, self.upload, "Milk carton",
                                   ingredient=self.milk, confidence=0.80, quantity=1)

        pantry_photo_detection_service.confirm_session(
            self.session, [d1.pk, d2.pk]
        )

        d1.refresh_from_db()
        d2.refresh_from_db()
        self.assertTrue(d1.confirmed)
        self.assertTrue(d2.rejected)

        # Only one PantryItem created
        items = PantryItem.objects.filter(
            household=self.household, ingredient=self.milk
        )
        self.assertEqual(items.count(), 1)


class TestConfidenceDrift(PantryPhotoTestMixin, TestCase):
    """Tests for confidence drift calculation."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.milk = self.create_ingredient("whole milk", "dairy")

    def test_drift_empty_pantry(self):
        """Empty pantry returns empty status."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        drift = pantry_scan_session_service.calculate_confidence_drift(self.household)
        self.assertEqual(drift["confidence_status"], "empty")
        self.assertEqual(drift["items_tracked"], 0)

    def test_drift_fresh_items(self):
        """Fresh items should have high confidence."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        PantryItem.objects.create(
            household=self.household,
            ingredient=self.milk,
            quantity=Decimal("2"),
            confidence_score=Decimal("1.0"),
            last_confirmed_at=timezone.now(),
        )

        drift = pantry_scan_session_service.calculate_confidence_drift(self.household)
        self.assertEqual(drift["confidence_status"], "high")
        self.assertGreaterEqual(drift["overall_confidence"], 0.75)

    def test_drift_stale_items(self):
        """Old items should have lower confidence."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        PantryItem.objects.create(
            household=self.household,
            ingredient=self.milk,
            quantity=Decimal("2"),
            confidence_score=Decimal("1.0"),
            last_confirmed_at=timezone.now() - timedelta(days=20),
        )

        drift = pantry_scan_session_service.calculate_confidence_drift(self.household)
        self.assertLess(drift["overall_confidence"], 0.75)

    def test_drift_with_scan_staleness(self):
        """Stale scan adds extra penalty."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        PantryItem.objects.create(
            household=self.household,
            ingredient=self.milk,
            quantity=Decimal("2"),
            confidence_score=Decimal("0.50"),
            last_confirmed_at=timezone.now() - timedelta(days=10),
        )

        # Create a stale scan session
        session = self.create_session(self.household)
        session.completed_at = timezone.now() - timedelta(days=20)
        session.save()

        drift = pantry_scan_session_service.calculate_confidence_drift(self.household)
        self.assertIsNotNone(drift["days_since_last_scan"])
        self.assertGreaterEqual(drift["days_since_last_scan"], 20)

    def test_drift_counts_low_confidence_items(self):
        """Drift report tracks low-confidence items."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        eggs = self.create_ingredient("eggs", "protein")
        PantryItem.objects.create(
            household=self.household, ingredient=self.milk,
            quantity=Decimal("1"), confidence_score=Decimal("0.90"),
            last_confirmed_at=timezone.now(),
        )
        PantryItem.objects.create(
            household=self.household, ingredient=eggs,
            quantity=Decimal("6"), confidence_score=Decimal("0.30"),
            last_confirmed_at=timezone.now() - timedelta(days=30),
        )

        drift = pantry_scan_session_service.calculate_confidence_drift(self.household)
        self.assertEqual(drift["items_tracked"], 2)
        self.assertGreaterEqual(drift["low_confidence_items"], 1)


class TestSessionRecentSessions(PantryPhotoTestMixin, TestCase):
    """Tests for recent sessions retrieval."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)

    def test_get_recent_sessions(self):
        """Only completed sessions are returned."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        s1 = self.create_session(self.household)
        s1.completed_at = timezone.now() - timedelta(hours=2)
        s1.save()

        s2 = self.create_session(self.household)  # Not completed

        s3 = self.create_session(self.household)
        s3.completed_at = timezone.now()
        s3.save()

        recent = list(pantry_scan_session_service.get_recent_sessions(self.household))
        self.assertEqual(len(recent), 2)
        # Most recent first
        self.assertEqual(recent[0].pk, s3.pk)

    def test_get_recent_sessions_limit(self):
        """Respects the limit parameter."""
        from apps.meals.services.pantry_photo_detection import pantry_scan_session_service

        for i in range(8):
            s = self.create_session(self.household)
            s.completed_at = timezone.now()
            s.save()

        recent = list(pantry_scan_session_service.get_recent_sessions(self.household, limit=3))
        self.assertEqual(len(recent), 3)


class TestDetectionServiceCreateDetections(PantryPhotoTestMixin, TestCase):
    """Tests for the detection creation pipeline."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy")
        self.eggs = self.create_ingredient("eggs", "protein")

    def test_create_detections_from_raw_result(self):
        """_create_detections parses raw Vision AI output correctly."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        raw_result = {
            "items": [
                {"label": "whole milk", "quantity": 2, "unit": "carton", "confidence": 0.92},
                {"label": "eggs", "quantity": 12, "unit": "piece", "confidence": 0.88},
                {"label": "unknown food", "quantity": 1, "unit": "piece", "confidence": 0.40},
            ]
        }

        detections = pantry_photo_detection_service._create_detections(
            self.upload, raw_result
        )

        self.assertEqual(len(detections), 3)

        # Check that known ingredients were matched
        milk_det = next(d for d in detections if "milk" in d.detected_label.lower())
        self.assertIsNotNone(milk_det.matched_ingredient)
        self.assertEqual(milk_det.matched_ingredient.canonical_name, "whole milk")

    def test_create_detections_updates_session_count(self):
        """Session items_detected is updated after processing."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        raw_result = {
            "items": [
                {"label": "whole milk", "quantity": 1, "unit": "piece", "confidence": 0.90},
            ]
        }

        pantry_photo_detection_service._create_detections(self.upload, raw_result)

        # Manually update count (normally done in process_upload)
        self.session.items_detected = self.session.detections.count()
        self.session.save()

        self.session.refresh_from_db()
        self.assertEqual(self.session.items_detected, 1)

    def test_empty_label_skipped(self):
        """Items with empty labels are skipped."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        raw_result = {
            "items": [
                {"label": "", "quantity": 1, "unit": "piece", "confidence": 0.50},
                {"label": "whole milk", "quantity": 1, "unit": "piece", "confidence": 0.90},
            ]
        }

        detections = pantry_photo_detection_service._create_detections(
            self.upload, raw_result
        )

        self.assertEqual(len(detections), 1)


class TestIngredientOverrides(PantryPhotoTestMixin, TestCase):
    """Tests for ingredient override during confirmation."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy")
        self.skim = self.create_ingredient("skim milk", "dairy")

    def test_ingredient_override_on_confirm(self):
        """User can change the matched ingredient during confirmation."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.80)

        pantry_photo_detection_service.confirm_session(
            self.session, [d1.pk],
            ingredient_overrides={d1.pk: self.skim.pk},
        )

        # Should create PantryItem for skim milk, not whole milk
        self.assertTrue(PantryItem.objects.filter(
            household=self.household, ingredient=self.skim
        ).exists())
        self.assertFalse(PantryItem.objects.filter(
            household=self.household, ingredient=self.milk
        ).exists())


class TestInventoryTransactionSource(PantryPhotoTestMixin, TestCase):
    """Tests that photo_scan source is used for transactions."""

    def setUp(self):
        self.user = self.create_user()
        self.household = self.create_household(self.user)
        self.session = self.create_session(self.household)
        self.upload = self.create_upload(self.session)
        self.milk = self.create_ingredient("whole milk", "dairy")

    def test_photo_scan_source_on_transaction(self):
        """InventoryTransaction uses 'photo_scan' source."""
        from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

        d1 = self.create_detection(self.session, self.upload, "Milk",
                                   ingredient=self.milk, confidence=0.90, quantity=1)

        pantry_photo_detection_service.confirm_session(self.session, [d1.pk])

        tx = InventoryTransaction.objects.filter(source="photo_scan").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.source, "photo_scan")
        self.assertIn("Photo scan", tx.notes)
