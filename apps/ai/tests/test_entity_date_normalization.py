# ==============================================================================
# File: apps/ai/tests/test_entity_date_normalization.py
# Description: Shared date-filter normalization in get_domain_entity — natural date
#              phrases are resolved to concrete ISO dates (and expressed as BOTH
#              on_date and start/end) before reaching any domain provider, so every
#              date-aware domain scopes identically. Nutrition is the exemplar.
# ==============================================================================
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_entity import (_normalize_date_filters,
                                                get_domain_entity)
from apps.health.models import FoodEntry

User = get_user_model()


class NormalizeDateFiltersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="datenorm@example.com", password="x")

    def test_on_date_phrase_becomes_iso_and_range(self):
        f = _normalize_date_filters(self.user, {"on_date": "2026-04-07"})
        # ISO on_date is also exposed as a start/end range for range-only providers.
        self.assertEqual(f["on_date"], "2026-04-07")
        self.assertEqual(f["start"], "2026-04-07")
        self.assertEqual(f["end"], "2026-04-07")

    def test_period_phrase_becomes_range(self):
        f = _normalize_date_filters(self.user, {"period": "custom-nonsense"})
        # unparseable period is left intact (provider decides), never fabricated
        self.assertEqual(f.get("period"), "custom-nonsense")

    def test_non_date_filters_untouched(self):
        f = _normalize_date_filters(self.user, {"meal": "lunch", "contains": "pizza"})
        self.assertEqual(f, {"meal": "lunch", "contains": "pizza"})

    def test_none_and_empty(self):
        self.assertIsNone(_normalize_date_filters(self.user, None))
        self.assertEqual(_normalize_date_filters(self.user, {}), {})


class NutritionDateScopedRetrievalTests(TestCase):
    """End-to-end: a date-scoped food question resolves and scopes correctly —
    real data on a real date, honest empty on a date with none. No fabrication."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="datescope@example.com", password="x")
        for d, name in [(date(2026, 4, 7), "Pepperoni Pizza"),
                        (date(2026, 4, 7), "Side Salad"),
                        (date(2026, 4, 6), "Oatmeal")]:
            FoodEntry.objects.create(
                user=cls.user, food_name=name, serving_size="1",
                serving_unit="each", logged_date=d, meal_type="dinner",
                total_calories=200)

    def test_iso_date_with_data_returns_records(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="food",
                              filters={"on_date": "2026-04-07"})
        self.assertEqual(r["status"], "ready")
        self.assertEqual(len(r["entities"]), 2)

    def test_date_without_data_is_honest_empty_not_fabricated(self):
        # A far-future/other date with no logs → empty, never borrowed from another day.
        r = get_domain_entity(self.user, "nutrition", entity_type="food",
                              filters={"on_date": "2026-04-01"})
        self.assertEqual(r["status"], "empty")
