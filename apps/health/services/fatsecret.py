# ==============================================================================
# File: fatsecret.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: FatSecret Platform API client for food search and nutrition data.
#              Uses OAuth 2.0 for authentication with token caching.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# Last Updated: 2026-01-12
# ==============================================================================
"""
FatSecret API Service - Search food database for nutrition information.

This service provides access to the FatSecret Platform API which contains
1.9M+ food items including restaurant menu items.

Free tier: 5,000 API calls/day (US data only)

API Documentation: https://platform.fatsecret.com/docs
"""

import base64
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# FatSecret API configuration
FATSECRET_TOKEN_URL = 'https://oauth.fatsecret.com/connect/token'
FATSECRET_API_URL = 'https://platform.fatsecret.com/rest/server.api'
FATSECRET_TOKEN_CACHE_KEY = 'fatsecret_access_token'
FATSECRET_TOKEN_CACHE_TIMEOUT = 86400 - 300  # 24 hours minus 5 minute buffer


@dataclass
class FatSecretFood:
    """Result from FatSecret food search."""
    food_id: str
    name: str
    brand: str
    food_type: str  # 'Generic' or 'Brand'
    description: str
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbohydrates_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    serving_size: Optional[float] = None
    serving_unit: str = ''

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'food_id': self.food_id,
            'name': self.name,
            'brand': self.brand,
            'food_type': self.food_type,
            'description': self.description,
            'calories': self.calories,
            'protein_g': self.protein_g,
            'carbohydrates_g': self.carbohydrates_g,
            'fat_g': self.fat_g,
            'fiber_g': self.fiber_g,
            'sugar_g': self.sugar_g,
            'saturated_fat_g': self.saturated_fat_g,
            'serving_size': self.serving_size,
            'serving_unit': self.serving_unit,
        }


class FatSecretService:
    """
    Client for FatSecret Platform API.

    Usage:
        from apps.health.services.fatsecret import fatsecret_service
        results = fatsecret_service.search_foods("McDonald's Big Mac")
    """

    def __init__(self):
        self.client_id = getattr(settings, 'FATSECRET_CLIENT_ID', None)
        self.client_secret = getattr(settings, 'FATSECRET_CLIENT_SECRET', None)
        self.timeout = getattr(settings, 'FATSECRET_TIMEOUT_SECONDS', 10)

    @property
    def is_available(self) -> bool:
        """Check if FatSecret API credentials are configured."""
        return bool(self.client_id and self.client_secret)

    def _get_access_token(self) -> Optional[str]:
        """
        Get OAuth 2.0 access token with caching.

        Token is cached for ~24 hours (token lifetime minus buffer).
        """
        if not self.is_available:
            logger.warning("FatSecret API credentials not configured")
            return None

        # Check cache first
        token = cache.get(FATSECRET_TOKEN_CACHE_KEY)
        if token:
            return token

        # Request new token
        try:
            auth = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()

            response = requests.post(
                FATSECRET_TOKEN_URL,
                headers={'Authorization': f'Basic {auth}'},
                data={
                    'grant_type': 'client_credentials',
                    'scope': 'basic'
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            token = data.get('access_token')

            if token:
                # Cache the token
                cache.set(
                    FATSECRET_TOKEN_CACHE_KEY,
                    token,
                    FATSECRET_TOKEN_CACHE_TIMEOUT
                )
                logger.debug("FatSecret access token obtained and cached")
                return token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get FatSecret access token: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting FatSecret token: {e}")

        return None

    def search_foods(
        self,
        query: str,
        max_results: int = 10,
        page_number: int = 0
    ) -> List[FatSecretFood]:
        """
        Search for foods in FatSecret database.

        Args:
            query: Food name to search (e.g., "McDonald's Big Mac")
            max_results: Number of results per page (max 50)
            page_number: Zero-based page offset

        Returns:
            List of FatSecretFood objects with nutrition data
        """
        token = self._get_access_token()
        if not token:
            return []

        try:
            response = requests.post(
                FATSECRET_API_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                json={
                    'method': 'foods.search',
                    'search_expression': query,
                    'format': 'json',
                    'max_results': min(max_results, 50),
                    'page_number': page_number
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            foods_data = data.get('foods', {})

            # Handle empty results
            if not foods_data or 'food' not in foods_data:
                return []

            # Handle single result (API returns dict instead of list)
            foods_list = foods_data.get('food', [])
            if isinstance(foods_list, dict):
                foods_list = [foods_list]

            return [self._parse_food(food) for food in foods_list]

        except requests.exceptions.RequestException as e:
            logger.error(f"FatSecret API request failed: {e}")
        except Exception as e:
            logger.error(f"Error parsing FatSecret response: {e}")

        return []

    def get_food_details(self, food_id: str) -> Optional[FatSecretFood]:
        """
        Get detailed nutrition info for a specific food.

        Args:
            food_id: FatSecret food ID from search results

        Returns:
            FatSecretFood with full nutrition data, or None if not found
        """
        token = self._get_access_token()
        if not token:
            return None

        try:
            response = requests.post(
                FATSECRET_API_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                json={
                    'method': 'food.get',
                    'food_id': food_id,
                    'format': 'json'
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            food_data = data.get('food', {})

            if not food_data:
                return None

            return self._parse_food_detail(food_data)

        except requests.exceptions.RequestException as e:
            logger.error(f"FatSecret food.get request failed: {e}")
        except Exception as e:
            logger.error(f"Error parsing FatSecret food detail: {e}")

        return None

    def _parse_food(self, food: dict) -> FatSecretFood:
        """
        Parse food object from foods.search response.

        The search endpoint returns food_description with nutrition summary:
        "Per 100g - Calories: 52kcal | Fat: 0.17g | Carbs: 13.81g | Protein: 0.26g"
        """
        description = food.get('food_description', '')
        nutrition = self._parse_nutrition_string(description)

        return FatSecretFood(
            food_id=str(food.get('food_id', '')),
            name=food.get('food_name', ''),
            brand=food.get('brand_name', ''),
            food_type=food.get('food_type', 'Generic'),
            description=description,
            calories=nutrition.get('calories'),
            protein_g=nutrition.get('protein'),
            carbohydrates_g=nutrition.get('carbs'),
            fat_g=nutrition.get('fat'),
            fiber_g=nutrition.get('fiber'),
            sugar_g=nutrition.get('sugar'),
            serving_size=nutrition.get('serving_size'),
            serving_unit=nutrition.get('serving_unit', ''),
        )

    def _parse_food_detail(self, food: dict) -> FatSecretFood:
        """
        Parse detailed food object from food.get response.

        The detail endpoint returns structured serving data with full nutrition.
        """
        # Get the first serving (usually the default)
        servings = food.get('servings', {}).get('serving', [])
        if isinstance(servings, dict):
            servings = [servings]

        serving = servings[0] if servings else {}

        return FatSecretFood(
            food_id=str(food.get('food_id', '')),
            name=food.get('food_name', ''),
            brand=food.get('brand_name', ''),
            food_type=food.get('food_type', 'Generic'),
            description=food.get('food_description', ''),
            calories=self._safe_float(serving.get('calories')),
            protein_g=self._safe_float(serving.get('protein')),
            carbohydrates_g=self._safe_float(serving.get('carbohydrate')),
            fat_g=self._safe_float(serving.get('fat')),
            fiber_g=self._safe_float(serving.get('fiber')),
            sugar_g=self._safe_float(serving.get('sugar')),
            saturated_fat_g=self._safe_float(serving.get('saturated_fat')),
            serving_size=self._safe_float(serving.get('metric_serving_amount')),
            serving_unit=serving.get('metric_serving_unit', ''),
        )

    def _parse_nutrition_string(self, description: str) -> dict:
        """
        Parse nutrition from food_description string.

        Example format:
        "Per 100g - Calories: 52kcal | Fat: 0.17g | Carbs: 13.81g | Protein: 0.26g"
        "Per 1 serving - Calories: 300kcal | Fat: 13g | Carbs: 32g | Protein: 15g"
        """
        nutrition = {}

        # Extract serving info
        serving_match = re.search(r'Per\s+([\d.]+)\s*(\w+)', description)
        if serving_match:
            nutrition['serving_size'] = float(serving_match.group(1))
            nutrition['serving_unit'] = serving_match.group(2)

        # Extract nutritional values
        patterns = {
            'calories': r'Calories:\s*([\d.]+)',
            'fat': r'Fat:\s*([\d.]+)',
            'carbs': r'Carbs:\s*([\d.]+)',
            'protein': r'Protein:\s*([\d.]+)',
            'fiber': r'Fiber:\s*([\d.]+)',
            'sugar': r'Sugar:\s*([\d.]+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                nutrition[key] = float(match.group(1))

        return nutrition

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Safely convert value to float, returning None if invalid."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# Singleton instance
fatsecret_service = FatSecretService()
