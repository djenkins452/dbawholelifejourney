"""
Shopping List and Shopping Item model tests.

Tests CRUD, properties, and soft delete.
"""

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.life.models import ShoppingItem, ShoppingList
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="shopping_test@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestShoppingListCRUD(TestCase):
    def setUp(self):
        self.user = _create_test_user()

    def test_create_shopping_list(self):
        sl = ShoppingList.objects.create(
            user=self.user,
            name="Weekly Groceries",
        )
        self.assertEqual(sl.name, "Weekly Groceries")
        self.assertFalse(sl.is_completed)
        self.assertIsNone(sl.completed_at)

    def test_str_representation(self):
        sl = ShoppingList.objects.create(
            user=self.user,
            name="Meal Prep",
        )
        self.assertEqual(str(sl), "Meal Prep")

    def test_ordering(self):
        sl1 = ShoppingList.objects.create(user=self.user, name="First")
        sl2 = ShoppingList.objects.create(user=self.user, name="Second")
        lists = list(ShoppingList.objects.filter(user=self.user))
        # Most recent first (ordering = ["-created_at"])
        self.assertEqual(lists[0].name, "Second")


class TestShoppingListProperties(TestCase):
    def setUp(self):
        self.user = _create_test_user("shopping_props@example.com")
        self.sl = ShoppingList.objects.create(
            user=self.user,
            name="Test List",
        )

    def test_item_count_empty(self):
        self.assertEqual(self.sl.item_count, 0)

    def test_item_count_with_items(self):
        for i in range(3):
            ShoppingItem.objects.create(
                user=self.user,
                shopping_list=self.sl,
                name=f"Item {i}",
            )
        self.assertEqual(self.sl.item_count, 3)

    def test_purchased_count(self):
        for i in range(3):
            ShoppingItem.objects.create(
                user=self.user,
                shopping_list=self.sl,
                name=f"Item {i}",
                is_purchased=(i < 2),
            )
        self.assertEqual(self.sl.purchased_count, 2)

    def test_progress_percent_empty(self):
        self.assertEqual(self.sl.progress_percent, 0)

    def test_progress_percent_partial(self):
        for i in range(4):
            ShoppingItem.objects.create(
                user=self.user,
                shopping_list=self.sl,
                name=f"Item {i}",
                is_purchased=(i < 2),
            )
        self.assertEqual(self.sl.progress_percent, 50)

    def test_progress_percent_complete(self):
        for i in range(3):
            ShoppingItem.objects.create(
                user=self.user,
                shopping_list=self.sl,
                name=f"Item {i}",
                is_purchased=True,
            )
        self.assertEqual(self.sl.progress_percent, 100)


class TestShoppingItemCRUD(TestCase):
    def setUp(self):
        self.user = _create_test_user("item_test@example.com")
        self.sl = ShoppingList.objects.create(
            user=self.user,
            name="Test List",
        )

    def test_create_item(self):
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=self.sl,
            name="Chicken Breast",
            quantity="2 lbs",
            category="protein",
        )
        self.assertEqual(item.name, "Chicken Breast")
        self.assertEqual(item.quantity, "2 lbs")
        self.assertEqual(item.category, "protein")
        self.assertFalse(item.is_purchased)

    def test_str_with_quantity(self):
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=self.sl,
            name="Eggs",
            quantity="1 dozen",
        )
        self.assertIn("Eggs", str(item))
        self.assertIn("1 dozen", str(item))

    def test_str_without_quantity(self):
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=self.sl,
            name="Broccoli",
        )
        self.assertEqual(str(item), "Broccoli")

    def test_mark_purchased(self):
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=self.sl,
            name="Test Item",
        )
        item.is_purchased = True
        item.purchased_at = timezone.now()
        item.save()

        item.refresh_from_db()
        self.assertTrue(item.is_purchased)
        self.assertIsNotNone(item.purchased_at)

    def test_category_default(self):
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=self.sl,
            name="Test",
        )
        self.assertEqual(item.category, "other")

    def test_ordering(self):
        """Items ordered by: is_purchased, category, name."""
        ShoppingItem.objects.create(
            user=self.user, shopping_list=self.sl,
            name="Zebra Fruit", category="produce", is_purchased=False,
        )
        ShoppingItem.objects.create(
            user=self.user, shopping_list=self.sl,
            name="Apple", category="produce", is_purchased=True,
        )
        ShoppingItem.objects.create(
            user=self.user, shopping_list=self.sl,
            name="Butter", category="dairy", is_purchased=False,
        )

        items = list(self.sl.items.all())
        # Unpurchased first, then by category, then name
        self.assertFalse(items[0].is_purchased)


class TestShoppingListSoftDelete(TestCase):
    def setUp(self):
        self.user = _create_test_user("shop_delete@example.com")

    def test_soft_delete_list(self):
        sl = ShoppingList.objects.create(
            user=self.user,
            name="To Delete",
        )
        sl.soft_delete()
        self.assertEqual(
            ShoppingList.objects.filter(user=self.user).count(), 0
        )
        self.assertEqual(
            ShoppingList.all_objects.filter(user=self.user).count(), 1
        )

    def test_soft_delete_item(self):
        sl = ShoppingList.objects.create(
            user=self.user,
            name="List",
        )
        item = ShoppingItem.objects.create(
            user=self.user,
            shopping_list=sl,
            name="To Delete",
        )
        item.soft_delete()
        self.assertEqual(
            ShoppingItem.objects.filter(user=self.user).count(), 0
        )
        self.assertEqual(
            ShoppingItem.all_objects.filter(user=self.user).count(), 1
        )
