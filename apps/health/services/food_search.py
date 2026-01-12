# ==============================================================================
# File: food_search.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: 3-tier food search orchestrator that combines local database,
#              FatSecret API, and AI estimation for comprehensive food lookup.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# Last Updated: 2026-01-12
# ==============================================================================
"""
Food Search Service - Orchestrates food lookup across multiple sources.

Search Priority:
1. Local Database (CustomFood + FoodItem) - Fastest, includes user's custom foods
2. FatSecret API - 1.9M+ foods including restaurant menus
3. OpenAI AI Estimation - Fallback for foods not found elsewhere

Results from FatSecret/AI are cached to local FoodItem database for future lookups.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from django.db.models import Q
from django.utils import timezone

from .fatsecret import fatsecret_service, FatSecretFood
from .ai_nutrition import ai_nutrition_service, AIFoodEstimate

logger = logging.getLogger(__name__)

# Minimum local results before querying external APIs
MIN_LOCAL_RESULTS_THRESHOLD = 3


@dataclass
class FoodSearchResult:
    """Unified food search result from any source."""
    id: str  # 'local_<id>', 'custom_<id>', 'fatsecret_<id>', 'ai_<hash>'
    name: str
    brand: str
    source: str  # 'local', 'custom', 'fatsecret', 'ai'
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbohydrates_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    serving_size: Optional[float] = None
    serving_unit: str = ''
    confidence: float = 1.0
    food_item_id: Optional[int] = None  # If cached in local database
    custom_food_id: Optional[int] = None  # If from CustomFood

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'id': self.id,
            'name': self.name,
            'brand': self.brand,
            'source': self.source,
            'calories': self.calories,
            'protein_g': self.protein_g,
            'carbohydrates_g': self.carbohydrates_g,
            'fat_g': self.fat_g,
            'fiber_g': self.fiber_g,
            'sugar_g': self.sugar_g,
            'saturated_fat_g': self.saturated_fat_g,
            'serving_size': self.serving_size,
            'serving_unit': self.serving_unit,
            'confidence': self.confidence,
            'food_item_id': self.food_item_id,
            'custom_food_id': self.custom_food_id,
        }


class FoodSearchService:
    """
    Unified food search across multiple sources.

    Usage:
        from apps.health.services.food_search import food_search_service
        results = food_search_service.search("McDonald's Big Mac", user=request.user)
    """

    def search(
        self,
        query: str,
        user=None,
        limit: int = 10,
        use_fatsecret: bool = True,
        use_ai: bool = True
    ) -> List[FoodSearchResult]:
        """
        Search for foods across all available sources.

        Args:
            query: Food name to search
            user: User instance (for searching CustomFood)
            limit: Maximum results to return
            use_fatsecret: Whether to query FatSecret API if local results insufficient
            use_ai: Whether to use AI estimation as final fallback

        Returns:
            List of FoodSearchResult objects sorted by relevance
        """
        if not query or len(query.strip()) < 2:
            return []

        query = query.strip()
        results = []

        # Tier 1: Search local database
        local_results = self._search_local(query, user, limit)
        results.extend(local_results)

        # Tier 2: If insufficient local results, query FatSecret
        if use_fatsecret and len(results) < MIN_LOCAL_RESULTS_THRESHOLD:
            remaining = limit - len(results)
            fatsecret_results = self._search_fatsecret(query, remaining)

            # Filter out duplicates (by name similarity)
            existing_names = {r.name.lower() for r in results}
            for fs_result in fatsecret_results:
                if fs_result.name.lower() not in existing_names:
                    results.append(fs_result)
                    existing_names.add(fs_result.name.lower())

        # Tier 3: If still no results, use AI estimation
        if use_ai and len(results) == 0:
            ai_result = self._estimate_with_ai(query)
            if ai_result:
                results.append(ai_result)

        return results[:limit]

    def _search_local(
        self,
        query: str,
        user,
        limit: int
    ) -> List[FoodSearchResult]:
        """Search local CustomFood and FoodItem databases."""
        results = []

        # Search user's CustomFoods first (if user provided)
        if user:
            try:
                from apps.health.models import CustomFood

                custom_foods = CustomFood.objects.filter(
                    user=user,
                    name__icontains=query
                ).order_by('-updated_at')[:limit]

                for food in custom_foods:
                    results.append(FoodSearchResult(
                        id=f'custom_{food.id}',
                        name=food.name,
                        brand='',
                        source='custom',
                        calories=float(food.calories) if food.calories else None,
                        protein_g=float(food.protein_g) if food.protein_g else None,
                        carbohydrates_g=float(food.carbohydrates_g) if food.carbohydrates_g else None,
                        fat_g=float(food.fat_g) if food.fat_g else None,
                        fiber_g=float(food.fiber_g) if food.fiber_g else None,
                        sugar_g=float(food.sugar_g) if food.sugar_g else None,
                        saturated_fat_g=float(food.saturated_fat_g) if food.saturated_fat_g else None,
                        serving_size=float(food.serving_size) if food.serving_size else None,
                        serving_unit=food.serving_unit or '',
                        confidence=1.0,
                        custom_food_id=food.id,
                    ))
            except Exception as e:
                logger.error(f"Error searching CustomFood: {e}")

        # Search global FoodItem database
        remaining = limit - len(results)
        if remaining > 0:
            try:
                from apps.health.models import FoodItem

                food_items = FoodItem.objects.filter(
                    Q(name__icontains=query) | Q(brand__icontains=query),
                    is_active=True
                ).order_by('name')[:remaining]

                for food in food_items:
                    results.append(FoodSearchResult(
                        id=f'local_{food.id}',
                        name=food.name,
                        brand=food.brand or '',
                        source='local',
                        calories=float(food.calories) if food.calories else None,
                        protein_g=float(food.protein_g) if food.protein_g else None,
                        carbohydrates_g=float(food.carbohydrates_g) if food.carbohydrates_g else None,
                        fat_g=float(food.fat_g) if food.fat_g else None,
                        fiber_g=float(food.fiber_g) if food.fiber_g else None,
                        sugar_g=float(food.sugar_g) if food.sugar_g else None,
                        saturated_fat_g=float(food.saturated_fat_g) if food.saturated_fat_g else None,
                        serving_size=float(food.serving_size) if food.serving_size else None,
                        serving_unit=food.serving_unit or '',
                        confidence=1.0,
                        food_item_id=food.id,
                    ))
            except Exception as e:
                logger.error(f"Error searching FoodItem: {e}")

        return results

    def _search_fatsecret(self, query: str, limit: int) -> List[FoodSearchResult]:
        """Search FatSecret API and cache results."""
        results = []

        if not fatsecret_service.is_available:
            logger.debug("FatSecret service not available")
            return results

        try:
            fs_foods = fatsecret_service.search_foods(query, max_results=limit)

            for food in fs_foods:
                result = FoodSearchResult(
                    id=f'fatsecret_{food.food_id}',
                    name=food.name,
                    brand=food.brand or '',
                    source='fatsecret',
                    calories=food.calories,
                    protein_g=food.protein_g,
                    carbohydrates_g=food.carbohydrates_g,
                    fat_g=food.fat_g,
                    fiber_g=food.fiber_g,
                    sugar_g=food.sugar_g,
                    saturated_fat_g=food.saturated_fat_g,
                    serving_size=food.serving_size,
                    serving_unit=food.serving_unit or '',
                    confidence=0.95,  # FatSecret data is generally reliable
                )

                # Cache to local database
                cached_id = self._cache_fatsecret_result(food)
                if cached_id:
                    result.food_item_id = cached_id

                results.append(result)

        except Exception as e:
            logger.error(f"FatSecret search error: {e}")

        return results

    def _cache_fatsecret_result(self, food: FatSecretFood) -> Optional[int]:
        """Cache FatSecret result to local FoodItem database."""
        try:
            from apps.health.models import FoodItem

            # Check if already cached by fatsecret_id
            existing = FoodItem.objects.filter(fatsecret_id=food.food_id).first()
            if existing:
                return existing.id

            # Create new FoodItem
            food_item = FoodItem.objects.create(
                name=food.name,
                brand=food.brand or '',
                description=food.description or '',
                fatsecret_id=food.food_id,
                data_source=FoodItem.SOURCE_FATSECRET,
                serving_size=food.serving_size or 1,
                serving_unit=food.serving_unit or 'serving',
                calories=food.calories or 0,
                protein_g=food.protein_g or 0,
                carbohydrates_g=food.carbohydrates_g or 0,
                fat_g=food.fat_g or 0,
                fiber_g=food.fiber_g or 0,
                sugar_g=food.sugar_g or 0,
                saturated_fat_g=food.saturated_fat_g or 0,
                last_verified_at=timezone.now(),
                is_verified=True,
            )

            logger.info(f"Cached FatSecret food '{food.name}' as FoodItem {food_item.id}")
            return food_item.id

        except Exception as e:
            logger.error(f"Failed to cache FatSecret result: {e}")
            return None

    def _estimate_with_ai(self, query: str) -> Optional[FoodSearchResult]:
        """Use AI to estimate nutrition for unknown food."""
        if not ai_nutrition_service.is_available:
            logger.debug("AI nutrition service not available")
            return None

        try:
            ai_result = ai_nutrition_service.estimate_nutrition(query)

            if ai_result:
                result = FoodSearchResult(
                    id=f'ai_{hash(query)}',
                    name=ai_result.name,
                    brand=ai_result.brand or '',
                    source='ai',
                    calories=ai_result.calories,
                    protein_g=ai_result.protein_g,
                    carbohydrates_g=ai_result.carbohydrates_g,
                    fat_g=ai_result.fat_g,
                    fiber_g=ai_result.fiber_g,
                    sugar_g=ai_result.sugar_g,
                    saturated_fat_g=ai_result.saturated_fat_g,
                    serving_size=ai_result.serving_size,
                    serving_unit=ai_result.serving_unit or '',
                    confidence=ai_result.confidence,
                )

                # Cache AI result to local database
                cached_id = self._cache_ai_result(ai_result, query)
                if cached_id:
                    result.food_item_id = cached_id

                return result

        except Exception as e:
            logger.error(f"AI estimation error: {e}")

        return None

    def _cache_ai_result(self, ai_result: AIFoodEstimate, original_query: str) -> Optional[int]:
        """Cache AI estimation to local FoodItem database."""
        try:
            from apps.health.models import FoodItem

            # Create new FoodItem from AI estimate
            food_item = FoodItem.objects.create(
                name=ai_result.name,
                brand=ai_result.brand or '',
                description=f"AI estimated: {ai_result.notes}" if ai_result.notes else "AI estimated nutrition",
                data_source=FoodItem.SOURCE_AI,
                source_reference=f"AI estimate for: {original_query}",
                serving_size=ai_result.serving_size or 1,
                serving_unit=ai_result.serving_unit or 'serving',
                calories=ai_result.calories or 0,
                protein_g=ai_result.protein_g or 0,
                carbohydrates_g=ai_result.carbohydrates_g or 0,
                fat_g=ai_result.fat_g or 0,
                fiber_g=ai_result.fiber_g or 0,
                sugar_g=ai_result.sugar_g or 0,
                saturated_fat_g=ai_result.saturated_fat_g or 0,
                last_verified_at=timezone.now(),
                is_verified=False,  # AI estimates are not verified
            )

            logger.info(f"Cached AI estimate '{ai_result.name}' as FoodItem {food_item.id}")
            return food_item.id

        except Exception as e:
            logger.error(f"Failed to cache AI result: {e}")
            return None


# Singleton instance
food_search_service = FoodSearchService()
