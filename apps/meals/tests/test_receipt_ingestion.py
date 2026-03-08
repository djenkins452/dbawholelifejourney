"""
Tests for the Receipt Ingestion System.

Covers:
- Receipt model new fields (image, receipt_type, confirmation_status)
- ReceiptVisionService (Vision API parsing, PDF fallback)
- ReceiptUploadView (image upload, text paste, file validation)
- ReceiptConfirmView (confirmation flow, cancel)
- ReceiptRoutingService (grocery->pantry, restaurant->health, all->finance)
"""

import io
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.meals.models import (
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    PantryItem,
    Receipt,
    ReceiptItem,
)
from apps.users.models import User


class TestUserMixin:
    """Mixin to create test users with proper onboarding."""

    def create_user(self, email="test@example.com"):
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(email=email, password="testpass123")
        terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=terms_version)
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user


# =============================================================================
# Model Tests
# =============================================================================


class TestReceiptModelFields(TestUserMixin, TestCase):
    """Test new Receipt model fields."""

    def setUp(self):
        self.user = self.create_user()
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )

    def test_receipt_type_default(self):
        receipt = Receipt.objects.create(
            user=self.user,
            household=self.household,
            raw_text="test",
        )
        self.assertEqual(receipt.receipt_type, Receipt.RECEIPT_TYPE_UNKNOWN)

    def test_confirmation_status_default(self):
        receipt = Receipt.objects.create(
            user=self.user,
            household=self.household,
            raw_text="test",
        )
        self.assertEqual(receipt.confirmation_status, Receipt.CONFIRM_PENDING)

    def test_receipt_type_choices(self):
        for choice_value, _ in Receipt.RECEIPT_TYPE_CHOICES:
            receipt = Receipt.objects.create(
                user=self.user,
                household=self.household,
                raw_text="test",
                receipt_type=choice_value,
            )
            self.assertEqual(receipt.receipt_type, choice_value)

    def test_receipt_item_category(self):
        receipt = Receipt.objects.create(
            user=self.user,
            household=self.household,
            raw_text="test",
        )
        item = ReceiptItem.objects.create(
            receipt=receipt,
            raw_name="Bananas",
            category="produce",
        )
        self.assertEqual(item.category, "produce")


# =============================================================================
# Vision Service Tests
# =============================================================================


class TestReceiptVisionService(TestCase):
    """Test Vision API service for receipt processing."""

    def test_parse_vision_response_grocery(self):
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()
        data = {
            "receipt_type": "grocery",
            "store": "Walmart",
            "date": "2026-03-01",
            "items": [
                {"name": "Bananas", "quantity": 1, "price": 0.68, "category": "produce"},
                {"name": "Chicken Breast", "quantity": 1, "price": 7.99, "category": "meat"},
            ],
            "subtotal": 8.67,
            "tax": 0.0,
            "total": 8.67,
        }
        result = service._parse_vision_response(data)

        self.assertEqual(result.receipt_type, "grocery")
        self.assertEqual(result.store, "Walmart")
        self.assertEqual(result.date, "2026-03-01")
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.total, Decimal("8.67"))
        self.assertEqual(result.source, "vision_api")
        self.assertIsNone(result.error)

    def test_parse_vision_response_restaurant(self):
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()
        data = {
            "receipt_type": "restaurant",
            "store": "Olive Garden",
            "date": "2026-03-05",
            "items": [
                {"name": "Chicken Alfredo", "price": 18.99},
            ],
            "total": 23.45,
        }
        result = service._parse_vision_response(data)
        self.assertEqual(result.receipt_type, "restaurant")
        self.assertEqual(result.store, "Olive Garden")

    def test_parse_vision_response_empty_items(self):
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()
        result = service._parse_vision_response({"items": [{"name": ""}, {}]})
        self.assertEqual(len(result.items), 0)

    def test_parse_vision_response_missing_fields(self):
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()
        result = service._parse_vision_response({})
        self.assertEqual(result.receipt_type, "unknown")
        self.assertEqual(result.store, "")
        self.assertIsNone(result.total)

    def test_safe_decimal(self):
        from apps.meals.services.receipt_vision import _safe_decimal

        self.assertEqual(_safe_decimal(10.5), Decimal("10.5"))
        self.assertEqual(_safe_decimal("3.99"), Decimal("3.99"))
        self.assertIsNone(_safe_decimal(None))
        self.assertIsNone(_safe_decimal("not a number"))

    def test_process_image_calls_vision_api(self):
        """Test that process_image calls the Vision API."""
        from apps.meals.services.receipt_vision import ReceiptVisionResult, ReceiptVisionService

        # Create a minimal JPEG image
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        service = ReceiptVisionService()

        mock_result = ReceiptVisionResult(
            receipt_type="grocery",
            store="TestMart",
            items=[{"name": "Milk", "price": 3.49}],
            total=Decimal("3.49"),
            raw_text="TestMart\nMilk $3.49",
            source="vision_api",
        )

        with patch.object(service, "_call_vision_api", return_value=mock_result):
            result = service.process_image(raw_bytes, "image/jpeg")

        self.assertEqual(result.receipt_type, "grocery")
        self.assertEqual(result.store, "TestMart")
        self.assertEqual(len(result.items), 1)

    def test_pdf_text_extraction(self):
        """Test PDF text extraction path."""
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()

        # Mock pdfplumber to return text
        with patch("apps.meals.services.receipt_vision.ReceiptVisionService._extract_pdf_text") as mock_extract:
            mock_extract.return_value = (
                "WALMART\n03/01/2026\nBANANAS          $0.68\nTOTAL            $0.68"
            )
            result = service.process_pdf(b"fake pdf bytes")

        self.assertEqual(result.source, "pdf_text")
        self.assertIn("WALMART", result.raw_text)


# =============================================================================
# Upload View Tests
# =============================================================================


class TestReceiptUploadView(TestUserMixin, TestCase):
    """Test multi-mode receipt upload."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )

    def test_upload_page_loads(self):
        response = self.client.get(reverse("meals:receipts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload Image")
        self.assertContains(response, "Take Photo")
        self.assertContains(response, "Paste Text")

    def test_text_paste_creates_pending_receipt(self):
        receipt_text = "WALMART\n03/01/2026\nBANANAS          $0.68\nTOTAL            $0.68"
        response = self.client.post(
            reverse("meals:receipts"),
            {"receipt_text": receipt_text},
        )
        self.assertEqual(response.status_code, 302)
        receipt = Receipt.objects.filter(household=self.household).first()
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.confirmation_status, Receipt.CONFIRM_PENDING)
        self.assertEqual(receipt.receipt_type, Receipt.RECEIPT_TYPE_GROCERY)
        self.assertIn("confirm", response.url)

    def test_empty_submission_redirects_with_error(self):
        response = self.client.post(reverse("meals:receipts"), {})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("meals:receipts"))

    @patch("apps.meals.services.receipt_vision.ReceiptVisionService.process_image")
    def test_image_upload_processes(self, mock_process):
        """Test image upload creates receipt and redirects to confirm."""
        from apps.meals.services.receipt_vision import ReceiptVisionResult

        mock_process.return_value = ReceiptVisionResult(
            receipt_type="grocery",
            store="Kroger",
            date="2026-03-08",
            items=[
                {"name": "Bananas", "price": 0.68, "quantity": 1, "category": "produce"},
            ],
            total=Decimal("0.68"),
            raw_text="Kroger\nBANANAS $0.68",
            source="vision_api",
        )

        # Create a minimal JPEG
        from PIL import Image

        img = Image.new("RGB", (10, 10), "white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        uploaded = SimpleUploadedFile("receipt.jpg", buf.read(), content_type="image/jpeg")

        response = self.client.post(
            reverse("meals:receipts"),
            {"receipt_image": uploaded},
        )
        self.assertEqual(response.status_code, 302)
        receipt = Receipt.objects.filter(household=self.household).first()
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.store, "Kroger")
        self.assertEqual(receipt.receipt_type, "grocery")
        self.assertEqual(receipt.confirmation_status, Receipt.CONFIRM_PENDING)
        self.assertIn("confirm", response.url)

    def test_file_too_large_rejected(self):
        # Create a file larger than 10MB
        large_file = SimpleUploadedFile(
            "big.jpg",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("meals:receipts"),
            {"receipt_image": large_file},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Receipt.objects.filter(household=self.household).exists())

    def test_unsupported_type_rejected(self):
        file = SimpleUploadedFile(
            "doc.docx",
            b"fake content",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(
            reverse("meals:receipts"),
            {"receipt_image": file},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Receipt.objects.filter(household=self.household).exists())


# =============================================================================
# Confirm View Tests
# =============================================================================


class TestReceiptConfirmView(TestUserMixin, TestCase):
    """Test receipt confirmation flow."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )
        self.receipt = Receipt.objects.create(
            user=self.user,
            household=self.household,
            raw_text="WALMART\nBANANAS $0.68",
            store="WALMART",
            total=Decimal("0.68"),
            receipt_date=timezone.now().date(),
            receipt_type=Receipt.RECEIPT_TYPE_GROCERY,
            confirmation_status=Receipt.CONFIRM_PENDING,
        )
        self.ingredient = Ingredient.objects.create(
            canonical_name="banana",
            category="produce",
        )
        self.item = ReceiptItem.objects.create(
            receipt=self.receipt,
            ingredient=self.ingredient,
            raw_name="BANANAS",
            raw_price=Decimal("0.68"),
            quantity=Decimal("1"),
            match_confidence=Decimal("0.95"),
        )

    def test_confirm_page_loads(self):
        response = self.client.get(
            reverse("meals:receipt_confirm", kwargs={"pk": self.receipt.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WALMART")
        self.assertContains(response, "BANANAS")

    def test_confirm_already_confirmed_returns_404(self):
        self.receipt.confirmation_status = Receipt.CONFIRM_CONFIRMED
        self.receipt.save()
        response = self.client.get(
            reverse("meals:receipt_confirm", kwargs={"pk": self.receipt.pk})
        )
        self.assertEqual(response.status_code, 404)

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_confirm_grocery_updates_pantry(self, mock_intel):
        response = self.client.post(
            reverse("meals:receipt_confirm", kwargs={"pk": self.receipt.pk}),
            {
                "action": "confirm",
                "receipt_type": "grocery",
                "confirmed_items": [str(self.item.pk)],
                f"qty_{self.item.pk}": "2",
                f"price_{self.item.pk}": "0.68",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Receipt should be confirmed
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.confirmation_status, Receipt.CONFIRM_CONFIRMED)
        self.assertEqual(self.receipt.receipt_type, "grocery")

        # Pantry should have the item
        pantry_item = PantryItem.objects.filter(
            household=self.household, ingredient=self.ingredient
        ).first()
        self.assertIsNotNone(pantry_item)
        self.assertEqual(pantry_item.quantity, Decimal("2"))

        # Inventory transaction should be logged
        self.assertTrue(
            InventoryTransaction.objects.filter(
                pantry_item=pantry_item, source="receipt"
            ).exists()
        )

    def test_cancel_receipt(self):
        response = self.client.post(
            reverse("meals:receipt_confirm", kwargs={"pk": self.receipt.pk}),
            {"action": "cancel"},
        )
        self.assertEqual(response.status_code, 302)
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.confirmation_status, Receipt.CONFIRM_CANCELLED)


# =============================================================================
# Routing Service Tests
# =============================================================================


class TestReceiptRoutingService(TestUserMixin, TestCase):
    """Test domain routing logic."""

    def setUp(self):
        self.user = self.create_user()
        self.household = Household.objects.create(
            name="Test Household", primary_user=self.user
        )
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin"
        )

    def _create_receipt(self, receipt_type="grocery", store="TestStore", total="10.00"):
        return Receipt.objects.create(
            user=self.user,
            household=self.household,
            raw_text="test",
            store=store,
            total=Decimal(total),
            receipt_date=timezone.now().date(),
            receipt_type=receipt_type,
            confirmation_status=Receipt.CONFIRM_PENDING,
        )

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_grocery_routes_to_pantry(self, mock_intel):
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        receipt = self._create_receipt("grocery")
        ingredient = Ingredient.objects.create(canonical_name="milk")
        item = ReceiptItem.objects.create(
            receipt=receipt,
            ingredient=ingredient,
            raw_name="MILK",
            raw_price=Decimal("3.49"),
            quantity=Decimal("1"),
        )

        service = ReceiptRoutingService()
        result = service.route_receipt(
            receipt=receipt,
            household=self.household,
            receipt_type="grocery",
            confirmed_item_ids=[item.pk],
            quantity_overrides={},
            price_overrides={},
            user=self.user,
        )

        self.assertEqual(result.pantry_created, 1)
        self.assertTrue(
            PantryItem.objects.filter(
                household=self.household, ingredient=ingredient
            ).exists()
        )

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_restaurant_routes_to_health(self, mock_intel):
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        receipt = self._create_receipt("restaurant", "Olive Garden", "45.00")

        service = ReceiptRoutingService()
        result = service.route_receipt(
            receipt=receipt,
            household=self.household,
            receipt_type="restaurant",
            confirmed_item_ids=[],
            quantity_overrides={},
            price_overrides={},
            user=self.user,
        )

        self.assertTrue(result.food_entry_created)

        from apps.health.models import FoodEntry

        entry = FoodEntry.objects.filter(user=self.user).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.location, "restaurant")
        self.assertIn("Olive Garden", entry.food_name)

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_finance_routing_with_account(self, mock_intel):
        from apps.finance.models import FinancialAccount, Transaction
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        account = FinancialAccount.objects.create(
            user=self.user,
            name="Checking",
            account_type="checking",
            current_balance=Decimal("1000.00"),
        )

        receipt = self._create_receipt("grocery", "Walmart", "45.23")

        service = ReceiptRoutingService()
        result = service.route_receipt(
            receipt=receipt,
            household=self.household,
            receipt_type="grocery",
            confirmed_item_ids=[],
            quantity_overrides={},
            price_overrides={},
            user=self.user,
        )

        self.assertTrue(result.finance_transaction_created)
        txn = Transaction.objects.filter(user=self.user).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, Decimal("-45.23"))
        self.assertEqual(txn.payee, "Walmart")

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_finance_routing_without_account(self, mock_intel):
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        receipt = self._create_receipt("retail", "Amazon", "99.99")

        service = ReceiptRoutingService()
        result = service.route_receipt(
            receipt=receipt,
            household=self.household,
            receipt_type="retail",
            confirmed_item_ids=[],
            quantity_overrides={},
            price_overrides={},
            user=self.user,
        )

        # No account — silently skip
        self.assertFalse(result.finance_transaction_created)

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_unknown_type_no_routing(self, mock_intel):
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        receipt = self._create_receipt("unknown")

        service = ReceiptRoutingService()
        result = service.route_receipt(
            receipt=receipt,
            household=self.household,
            receipt_type="unknown",
            confirmed_item_ids=[],
            quantity_overrides={},
            price_overrides={},
            user=self.user,
        )

        self.assertEqual(result.pantry_created, 0)
        self.assertFalse(result.food_entry_created)
        self.assertFalse(result.finance_transaction_created)

    @patch("apps.meals.services.receipt_routing.ReceiptRoutingService._trigger_intelligence_updates")
    def test_quantity_overrides_applied(self, mock_intel):
        from apps.meals.services.receipt_routing import ReceiptRoutingService

        receipt = self._create_receipt("grocery")
        ingredient = Ingredient.objects.create(canonical_name="eggs")
        item = ReceiptItem.objects.create(
            receipt=receipt,
            ingredient=ingredient,
            raw_name="EGGS",
            raw_price=Decimal("4.99"),
            quantity=Decimal("1"),
        )

        service = ReceiptRoutingService()
        service.route_receipt(
            receipt=receipt,
            household=self.household,
            receipt_type="grocery",
            confirmed_item_ids=[item.pk],
            quantity_overrides={item.pk: Decimal("12")},
            price_overrides={},
            user=self.user,
        )

        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("12"))

        pantry_item = PantryItem.objects.filter(ingredient=ingredient).first()
        self.assertEqual(pantry_item.quantity, Decimal("12"))
