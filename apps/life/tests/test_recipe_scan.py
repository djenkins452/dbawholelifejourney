"""
Recipe Photo Import Tests

Tests for the recipe photo scan feature: upload, Vision AI processing,
and recipe creation from scanned data.
"""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.life.models import Recipe

User = get_user_model()


class RecipeScanTestBase(TestCase):
    """Base class with common setup for recipe scan tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="recipescan@example.com",
            password="testpass123",
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)

    def _accept_terms(self, user):
        try:
            from apps.users.models import TermsAcceptance

            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass

    def _login(self):
        self.client.login(email="recipescan@example.com", password="testpass123")

    def _make_test_image(self, content_type="image/jpeg", size=100):
        """Create a minimal test image file."""
        # 1x1 JPEG bytes
        jpeg_bytes = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
            b"\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
            b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"
            b"\x22q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16"
            b"\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz"
            b"\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99"
            b"\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7"
            b"\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5"
            b"\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1"
            b"\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\xae\x8a(\x03\xff\xd9"
        )
        return SimpleUploadedFile(
            "recipe.jpg", jpeg_bytes, content_type=content_type
        )


class RecipeScanViewTest(RecipeScanTestBase):
    """Tests for the recipe scan page."""

    def test_scan_page_requires_login(self):
        response = self.client.get(reverse("life:recipe_scan"))
        self.assertEqual(response.status_code, 302)

    def test_scan_page_loads(self):
        self._login()
        response = self.client.get(reverse("life:recipe_scan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scan a Recipe")
        self.assertTemplateUsed(response, "life/recipe_scan.html")


class RecipeScanProcessViewTest(RecipeScanTestBase):
    """Tests for the AJAX photo processing endpoint."""

    def test_process_requires_login(self):
        response = self.client.post(reverse("life:recipe_scan_process"))
        self.assertEqual(response.status_code, 302)

    def test_process_requires_photo(self):
        self._login()
        response = self.client.post(reverse("life:recipe_scan_process"))
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_process_validates_file_size(self):
        self._login()
        # Create file > 10MB
        big_file = SimpleUploadedFile(
            "big.jpg",
            b"\xff\xd8\xff" + b"\x00" * (11 * 1024 * 1024),
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("life:recipe_scan_process"), {"photo": big_file}
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("10MB", data["error"])

    def test_process_validates_file_type(self):
        self._login()
        text_file = SimpleUploadedFile(
            "recipe.txt", b"some text", content_type="text/plain"
        )
        response = self.client.post(
            reverse("life:recipe_scan_process"), {"photo": text_file}
        )
        self.assertEqual(response.status_code, 400)

    @patch(
        "apps.life.services.recipe_photo_import.RecipePhotoImportService.extract_from_bytes"
    )
    def test_process_returns_extracted_data(self, mock_extract):
        self._login()
        mock_extract.return_value = [{
            "title": "Test Recipe",
            "description": "A tasty dish",
            "ingredients": "2 cups flour\n1 tsp salt",
            "instructions": "1. Mix ingredients.\n2. Bake.",
            "prep_time_minutes": 15,
            "cook_time_minutes": 30,
            "servings": 4,
            "difficulty": "easy",
            "category": "Dinner",
            "source": "Test Cookbook",
            "notes": "",
            "confidence": 0.9,
        }]

        photo = self._make_test_image()
        response = self.client.post(
            reverse("life:recipe_scan_process"), {"photo": photo}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["recipe"]["title"], "Test Recipe")
        self.assertEqual(data["recipe"]["servings"], 4)
        mock_extract.assert_called_once()

    @patch(
        "apps.life.services.recipe_photo_import.RecipePhotoImportService.extract_from_bytes"
    )
    def test_process_handles_service_error(self, mock_extract):
        self._login()
        mock_extract.return_value = {
            "error": "Could not identify a recipe title in the image."
        }

        photo = self._make_test_image()
        response = self.client.post(
            reverse("life:recipe_scan_process"), {"photo": photo}
        )
        self.assertEqual(response.status_code, 422)
        data = json.loads(response.content)
        self.assertIn("error", data)


class RecipeScanConfirmViewTest(RecipeScanTestBase):
    """Tests for recipe creation from scanned data."""

    def test_confirm_requires_login(self):
        response = self.client.post(reverse("life:recipe_scan_confirm"))
        self.assertEqual(response.status_code, 302)

    def test_confirm_requires_title(self):
        self._login()
        response = self.client.post(
            reverse("life:recipe_scan_confirm"),
            {"title": "", "ingredients": "flour", "instructions": "mix"},
        )
        self.assertRedirects(response, reverse("life:recipe_scan"))

    def test_confirm_creates_recipe(self):
        self._login()
        response = self.client.post(
            reverse("life:recipe_scan_confirm"),
            {
                "title": "Scanned Pasta",
                "description": "Italian classic",
                "ingredients": "2 cups pasta\n1 cup sauce",
                "instructions": "1. Boil pasta.\n2. Add sauce.",
                "prep_time_minutes": "10",
                "cook_time_minutes": "20",
                "servings": "4",
                "difficulty": "easy",
                "category": "Dinner",
                "source": "Grandma's Book",
                "notes": "Family recipe",
            },
        )
        self.assertEqual(response.status_code, 302)

        recipe = Recipe.objects.get(title="Scanned Pasta")
        self.assertEqual(recipe.user, self.user)
        self.assertEqual(recipe.prep_time_minutes, 10)
        self.assertEqual(recipe.cook_time_minutes, 20)
        self.assertEqual(recipe.servings, 4)
        self.assertEqual(recipe.difficulty, "easy")
        self.assertEqual(recipe.category, "Dinner")
        self.assertEqual(recipe.source, "Grandma's Book")
        self.assertIn("2 cups pasta", recipe.ingredients)
        self.assertIn("Boil pasta", recipe.instructions)

    def test_confirm_saves_photo(self):
        self._login()
        photo = self._make_test_image()
        response = self.client.post(
            reverse("life:recipe_scan_confirm"),
            {
                "title": "Photo Recipe",
                "ingredients": "flour",
                "instructions": "mix",
                "photo": photo,
            },
        )
        self.assertEqual(response.status_code, 302)

        recipe = Recipe.objects.get(title="Photo Recipe")
        self.assertTrue(recipe.image)

    def test_confirm_handles_invalid_numbers(self):
        self._login()
        response = self.client.post(
            reverse("life:recipe_scan_confirm"),
            {
                "title": "Number Test",
                "ingredients": "flour",
                "instructions": "mix",
                "prep_time_minutes": "not-a-number",
                "servings": "-5",
            },
        )
        self.assertEqual(response.status_code, 302)

        recipe = Recipe.objects.get(title="Number Test")
        self.assertIsNone(recipe.prep_time_minutes)
        self.assertIsNone(recipe.servings)

    def test_confirm_redirects_to_detail(self):
        self._login()
        response = self.client.post(
            reverse("life:recipe_scan_confirm"),
            {
                "title": "Redirect Test",
                "ingredients": "flour",
                "instructions": "mix",
            },
        )
        recipe = Recipe.objects.get(title="Redirect Test")
        self.assertRedirects(response, reverse("life:recipe_detail", kwargs={"pk": recipe.pk}))


class RecipePhotoImportServiceTest(TestCase):
    """Tests for the recipe photo import service."""

    def test_validate_result_valid(self):
        from apps.life.services.recipe_photo_import import RecipePhotoImportService

        service = RecipePhotoImportService()
        result = service._validate_result(
            {
                "title": "Test Recipe",
                "ingredients": "flour\nsugar",
                "instructions": "1. Mix",
                "prep_time_minutes": 10,
                "cook_time_minutes": "30",
                "servings": 4,
                "difficulty": "easy",
                "confidence": 0.85,
            }
        )
        self.assertEqual(result["title"], "Test Recipe")
        self.assertEqual(result["prep_time_minutes"], 10)
        self.assertEqual(result["cook_time_minutes"], 30)
        self.assertEqual(result["servings"], 4)
        self.assertEqual(result["difficulty"], "easy")
        self.assertNotIn("error", result)

    def test_validate_result_missing_title(self):
        from apps.life.services.recipe_photo_import import RecipePhotoImportService

        service = RecipePhotoImportService()
        result = service._validate_result({"title": "", "ingredients": "flour"})
        self.assertIn("error", result)

    def test_validate_result_invalid_difficulty(self):
        from apps.life.services.recipe_photo_import import RecipePhotoImportService

        service = RecipePhotoImportService()
        result = service._validate_result(
            {
                "title": "Test",
                "difficulty": "super-hard",
                "ingredients": "flour",
                "instructions": "mix",
            }
        )
        self.assertEqual(result["difficulty"], "")

    def test_validate_result_invalid_numbers(self):
        from apps.life.services.recipe_photo_import import RecipePhotoImportService

        service = RecipePhotoImportService()
        result = service._validate_result(
            {
                "title": "Test",
                "prep_time_minutes": "abc",
                "cook_time_minutes": -5,
                "servings": 0,
                "ingredients": "flour",
                "instructions": "mix",
            }
        )
        self.assertIsNone(result["prep_time_minutes"])
        self.assertIsNone(result["cook_time_minutes"])
        self.assertIsNone(result["servings"])

    def test_validate_result_confidence_bounds(self):
        from apps.life.services.recipe_photo_import import RecipePhotoImportService

        service = RecipePhotoImportService()
        result = service._validate_result(
            {"title": "Test", "confidence": 1.5, "ingredients": "f", "instructions": "m"}
        )
        self.assertEqual(result["confidence"], 1.0)

        result2 = service._validate_result(
            {"title": "Test", "confidence": -0.5, "ingredients": "f", "instructions": "m"}
        )
        self.assertEqual(result2["confidence"], 0.0)

    @patch(
        "apps.life.services.recipe_photo_import.RecipePhotoImportService._call_vision_api"
    )
    @patch("apps.scan.services.image_utils.resize_for_vision", return_value="fake_base64")
    def test_extract_from_bytes_calls_vision(self, mock_resize, mock_vision):
        from apps.life.services.recipe_photo_import import RecipePhotoImportService

        mock_vision.return_value = {"title": "Vision Result", "confidence": 0.9}

        service = RecipePhotoImportService()
        result = service.extract_from_bytes(b"\xff\xd8\xff", "image/jpeg")

        mock_vision.assert_called_once()
        self.assertEqual(result["title"], "Vision Result")
