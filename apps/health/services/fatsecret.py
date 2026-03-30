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
FATSECRET_BARCODE_URL = 'https://platform.fatsecret.com/rest/food/barcode/find-by-id/v2'
FATSECRET_IMAGE_URL = 'https://platform.fatsecret.com/rest/image-recognition/v2'
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

    def _safe_json(self, response, context: str = "FatSecret"):
        """Parse JSON from response, handling empty/malformed bodies."""
        if not response.content:
            logger.warning("%s returned empty response body (status=%s)", context, response.status_code)
            return None
        try:
            return response.json()
        except ValueError as e:
            logger.error(
                "%s JSON decode error (status=%s, body=%s): %s",
                context, response.status_code, response.text[:200], e,
            )
            return None

    def _get_access_token(self, scope: str = 'basic') -> Optional[str]:
        """
        Get OAuth 2.0 access token with caching.

        Token is cached for ~24 hours (token lifetime minus buffer).
        Different scopes require different tokens.

        Args:
            scope: OAuth scope ('basic', 'barcode', 'image-recognition')
        """
        if not self.is_available:
            logger.warning("FatSecret API credentials not configured")
            return None

        # Use scope-specific cache key
        cache_key = f"{FATSECRET_TOKEN_CACHE_KEY}_{scope}"

        # Check cache first
        token = cache.get(cache_key)
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
                    'scope': scope
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = self._safe_json(response, "FatSecret token")
            if data is None:
                return None
            token = data.get('access_token')

            if token:
                # Cache the token
                cache.set(
                    cache_key,
                    token,
                    FATSECRET_TOKEN_CACHE_TIMEOUT
                )
                logger.debug(f"FatSecret access token ({scope}) obtained and cached")
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

            data = self._safe_json(response, "FatSecret foods.search")
            if data is None:
                return []
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

            data = self._safe_json(response, "FatSecret food.get")
            if data is None:
                return None
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
        # Get the default serving (matches nutrition label serving size)
        servings = food.get('servings', {}).get('serving', [])
        if isinstance(servings, dict):
            servings = [servings]

        # Prefer the serving flagged as default by FatSecret (is_default=1),
        # which typically matches the nutrition label's serving size.
        # Fall back to first serving if no default is flagged.
        serving = {}
        if servings:
            for s in servings:
                if str(s.get('is_default', '0')) == '1':
                    serving = s
                    break
            if not serving:
                serving = servings[0]

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

    def lookup_barcode(self, barcode: str) -> Optional[FatSecretFood]:
        """
        Look up a food product by barcode (UPC/EAN).

        Args:
            barcode: 13-digit GTIN-13 barcode string

        Returns:
            FatSecretFood with nutrition data, or None if not found
        """
        token = self._get_access_token(scope='barcode')
        if not token:
            return None

        try:
            # Convert to GTIN-13 format for FatSecret API.
            # UPC-A (12 digits) → prepend '0' to make EAN-13 (standard conversion).
            # EAN-13 (13 digits) → already correct, pass as-is.
            # Other lengths (8, 14, etc.) → send as-is; blind zero-padding
            # creates wrong barcodes that match different products.
            if len(barcode) == 12:
                barcode = '0' + barcode

            response = requests.get(
                FATSECRET_BARCODE_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                },
                params={
                    'barcode': barcode,
                    'format': 'json',
                    'flag_default_serving': 'true',
                    'include_food_attributes': 'true'
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            data = self._safe_json(response, "FatSecret barcode")
            if data is None:
                return None
            food_data = data.get('food')

            if not food_data:
                logger.debug(f"Barcode {barcode} not found in FatSecret")
                return None

            return self._parse_food_detail(food_data)

        except requests.exceptions.RequestException as e:
            logger.error(f"FatSecret barcode lookup failed: {e}")
        except Exception as e:
            logger.error(f"Error parsing FatSecret barcode response: {e}")

        return None

    def recognize_food_image(
        self,
        image_base64: str,
        include_food_data: bool = True
    ) -> List[FatSecretFood]:
        """
        Identify foods in an image using FatSecret's AI.

        Args:
            image_base64: Base64-encoded image (jpg, png, webp)
            include_food_data: Include full nutrition data in response

        Returns:
            List of FatSecretFood objects for identified foods
        """
        token = self._get_access_token(scope='image-recognition')
        if not token:
            return []

        try:
            response = requests.post(
                FATSECRET_IMAGE_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                json={
                    'image_b64': image_base64,
                    'include_food_data': include_food_data,
                    'region': 'US'
                },
                timeout=30  # Image recognition may take longer
            )
            response.raise_for_status()

            data = self._safe_json(response, "FatSecret image-recognition")
            if data is None:
                return []
            food_responses = data.get('food_response', [])

            if not food_responses:
                logger.debug("No foods identified in image by FatSecret")
                return []

            results = []
            for item in food_responses:
                eaten = item.get('eaten', {})
                food = item.get('food', {})
                suggested = item.get('suggested_serving', {})

                # Get nutrition from eaten data or suggested serving
                nutrition = eaten if eaten else suggested

                results.append(FatSecretFood(
                    food_id=str(food.get('food_id', '')),
                    name=food.get('food_name', item.get('food_entry_name', '')),
                    brand=food.get('brand_name', ''),
                    food_type=food.get('food_type', 'Generic'),
                    description=food.get('food_description', ''),
                    calories=self._safe_float(nutrition.get('calories')),
                    protein_g=self._safe_float(nutrition.get('protein')),
                    carbohydrates_g=self._safe_float(nutrition.get('carbohydrate')),
                    fat_g=self._safe_float(nutrition.get('fat')),
                    fiber_g=self._safe_float(nutrition.get('fiber')),
                    sugar_g=self._safe_float(nutrition.get('sugar')),
                    saturated_fat_g=self._safe_float(nutrition.get('saturated_fat')),
                    serving_size=self._safe_float(
                        nutrition.get('metric_serving_amount') or
                        nutrition.get('serving_amount')
                    ),
                    serving_unit=nutrition.get('metric_serving_unit', 'g'),
                ))

            logger.info(f"FatSecret identified {len(results)} food(s) in image")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"FatSecret image recognition failed: {e}")
        except Exception as e:
            logger.error(f"Error parsing FatSecret image response: {e}")

        return []


# Singleton instance
fatsecret_service = FatSecretService()
