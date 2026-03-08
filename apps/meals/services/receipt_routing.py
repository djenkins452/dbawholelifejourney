"""
Receipt Domain Routing Service

Routes confirmed receipt items to the appropriate domain:
- Grocery receipts -> Pantry (meals) + Finance
- Restaurant receipts -> FoodEntry (health) + Finance
- Retail receipts -> Finance only
- Unknown -> Store receipt record only (no domain updates)
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of routing a receipt to domain engines."""

    pantry_created: int = 0
    pantry_updated: int = 0
    food_entry_created: bool = False
    finance_transaction_created: bool = False
    summary_message: str = ""


class ReceiptRoutingService:
    """
    Routes confirmed receipt data to the appropriate WLJ domain models.

    Does NOT bypass intelligence engines — feeds data into domain models
    which then trigger the SAE -> PIE -> PRIE chain via update_user_state.
    """

    def route_receipt(
        self,
        receipt,
        household,
        receipt_type,
        confirmed_item_ids,
        quantity_overrides,
        price_overrides,
        user,
    ):
        """
        Route receipt data to appropriate domain models.

        Args:
            receipt: Receipt model instance
            household: Household instance
            receipt_type: str (grocery/restaurant/retail/unknown)
            confirmed_item_ids: list of ReceiptItem PKs the user confirmed
            quantity_overrides: dict {item_id: Decimal}
            price_overrides: dict {item_id: Decimal}
            user: User instance

        Returns:
            RoutingResult
        """
        result = RoutingResult()

        # Apply overrides to receipt items
        self._apply_overrides(
            receipt, confirmed_item_ids, quantity_overrides, price_overrides
        )

        if receipt_type == "grocery":
            created, updated = self._route_grocery(
                receipt, household, confirmed_item_ids
            )
            result.pantry_created = created
            result.pantry_updated = updated

        elif receipt_type == "restaurant":
            result.food_entry_created = self._route_restaurant(receipt, user)

        # Finance routing for all types except unknown
        if receipt_type != "unknown" and receipt.total:
            result.finance_transaction_created = self._route_to_finance(
                receipt, receipt_type, user
            )

        # Trigger intelligence chain for affected domains
        self._trigger_intelligence_updates(user, receipt_type)

        result.summary_message = self._build_summary(result, receipt_type)
        return result

    def _apply_overrides(
        self, receipt, confirmed_item_ids, quantity_overrides, price_overrides
    ):
        """Apply user quantity/price overrides to confirmed items."""
        from apps.meals.models import ReceiptItem

        for item in ReceiptItem.objects.filter(
            receipt=receipt, pk__in=confirmed_item_ids
        ):
            changed_fields = []
            if item.pk in quantity_overrides:
                item.quantity = quantity_overrides[item.pk]
                changed_fields.append("quantity")
            if item.pk in price_overrides:
                item.raw_price = price_overrides[item.pk]
                changed_fields.append("raw_price")
            if changed_fields:
                changed_fields.append("updated_at")
                item.save(update_fields=changed_fields)

    def _route_grocery(self, receipt, household, confirmed_ids):
        """
        Route grocery items to pantry.

        Reuses the existing pantry update logic but only for confirmed items.
        """
        from apps.meals.models import (
            Ingredient,
            InventoryTransaction,
            PantryItem,
            ReceiptItem,
        )
        from apps.meals.services.ingredient_matching import get_or_create_ingredient
        from apps.meals.services.storage_classifier import determine_storage_location

        confirmed_items = ReceiptItem.objects.filter(
            receipt=receipt, pk__in=confirmed_ids
        ).select_related("ingredient")

        created_count = 0
        updated_count = 0

        for item in confirmed_items:
            # Resolve ingredient
            ingredient = item.ingredient
            if not ingredient:
                ingredient = get_or_create_ingredient(item.raw_name)
                item.ingredient = ingredient
                item.save(update_fields=["ingredient", "updated_at"])

            # Classify storage location
            storage_location = determine_storage_location(
                item.raw_name,
                ingredient.category if ingredient else "",
            )

            # Update or create PantryItem
            pantry_item, created = PantryItem.objects.get_or_create(
                household=household,
                ingredient=ingredient,
                defaults={
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "confidence_score": Decimal("0.95"),
                    "last_confirmed_at": timezone.now(),
                    "storage_location": storage_location,
                },
            )

            if not created:
                pantry_item.quantity += item.quantity
                pantry_item.confidence_score = Decimal("0.95")
                pantry_item.last_confirmed_at = timezone.now()
                update_fields = [
                    "quantity",
                    "confidence_score",
                    "last_confirmed_at",
                    "updated_at",
                ]
                # Upgrade storage_location if still unknown and classifier knows better
                if pantry_item.storage_location == "unknown" and storage_location != "unknown":
                    pantry_item.storage_location = storage_location
                    update_fields.append("storage_location")
                pantry_item.save(update_fields=update_fields)
                updated_count += 1
            else:
                created_count += 1
                # Set estimated expiration
                if ingredient.shelf_life_days:
                    pantry_item.expiration_date_estimated = timezone.now().date() + (
                        timezone.timedelta(days=ingredient.shelf_life_days)
                    )
                    pantry_item.save(update_fields=["expiration_date_estimated"])

            # Log transaction
            InventoryTransaction.objects.create(
                pantry_item=pantry_item,
                delta_quantity=item.quantity,
                source="receipt",
                notes=f"From receipt: {receipt.store or 'Unknown Store'}",
            )

        logger.info(
            "Grocery routing for receipt %d: %d created, %d updated",
            receipt.pk,
            created_count,
            updated_count,
        )
        return created_count, updated_count

    def _route_restaurant(self, receipt, user):
        """
        Create a FoodEntry from restaurant receipt.

        Does not attempt nutritional breakdown — just logs the restaurant
        visit with the store name, date, and total.
        """
        try:
            from apps.health.models import FoodEntry

            FoodEntry.objects.create(
                user=user,
                food_name=f"Meal at {receipt.store}" if receipt.store else "Restaurant meal",
                logged_date=receipt.receipt_date or timezone.now().date(),
                logged_time=timezone.now().time(),
                meal_type="dinner",  # Default, user can edit later
                serving_size=Decimal("1"),
                serving_unit="meal",
                location="restaurant",
                entry_source="manual",
                notes=f"From receipt: {receipt.store or 'Unknown'}"
                + (f" - ${receipt.total}" if receipt.total else ""),
            )
            logger.info("Restaurant routing for receipt %d: FoodEntry created", receipt.pk)
            return True
        except Exception as e:
            logger.error(
                "Failed to create FoodEntry for receipt %d: %s",
                receipt.pk,
                e,
                exc_info=True,
            )
            return False

    def _route_to_finance(self, receipt, receipt_type, user):
        """
        Create a finance Transaction from receipt total.

        Silently skips if user has no financial accounts set up.
        """
        try:
            from apps.finance.models import (
                FinancialAccount,
                Transaction,
                TransactionCategory,
            )

            # Find user's default/first account
            account = FinancialAccount.objects.filter(user=user).first()
            if not account:
                logger.info(
                    "No finance account for user %d, skipping finance routing",
                    user.pk,
                )
                return False

            # Map receipt type to spending category
            category_map = {
                "grocery": "Groceries",
                "restaurant": "Dining",
                "retail": "Shopping",
            }
            category_name = category_map.get(receipt_type, "Other")

            category = (
                TransactionCategory.objects.filter(
                    Q(user=user) | Q(user__isnull=True),
                    name__icontains=category_name,
                    category_type="expense",
                )
                .first()
            )

            Transaction.objects.create(
                user=user,
                account=account,
                date=receipt.receipt_date or timezone.now().date(),
                amount=-abs(receipt.total),
                description=f"{receipt.store or 'Receipt'} purchase",
                payee=receipt.store or "",
                category=category,
                reference=f"receipt:{receipt.pk}",
                notes=f"Auto-created from receipt #{receipt.pk}",
            )
            logger.info("Finance routing for receipt %d: Transaction created", receipt.pk)
            return True

        except Exception as e:
            logger.error(
                "Failed to create finance Transaction for receipt %d: %s",
                receipt.pk,
                e,
                exc_info=True,
            )
            return False

    def _trigger_intelligence_updates(self, user, receipt_type):
        """Trigger SAE state updates for affected domains."""
        try:
            from apps.core.ai_state import update_user_state

            update_user_state(user, "meals")

            if receipt_type == "restaurant":
                update_user_state(user, "health")
            if receipt_type != "unknown":
                update_user_state(user, "finance")

        except ImportError:
            logger.debug("Intelligence chain not available")
        except Exception as e:
            logger.warning("Intelligence update failed: %s", e)

    def _build_summary(self, result, receipt_type):
        """Build a user-friendly summary message."""
        parts = []

        if receipt_type == "grocery":
            if result.pantry_created or result.pantry_updated:
                parts.append(
                    f"Pantry updated: {result.pantry_created} new, "
                    f"{result.pantry_updated} existing items"
                )

        if result.food_entry_created:
            parts.append("Restaurant meal logged to Health")

        if result.finance_transaction_created:
            parts.append("Transaction added to Finance")

        if not parts:
            parts.append("Receipt confirmed and saved")

        return ". ".join(parts) + "."
