# ==============================================================================
# File: barcode.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Barcode lookup service for food products. Queries local database
#              first, then Open Food Facts API, then uses OpenAI as fallback.
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Barcode Service - Lookup nutritional information for product barcodes.

This service handles barcode lookups in three stages:
1. Query local FoodItem database for known barcodes
2. Query Open Food Facts API (free, open-source database with 4M+ products)
3. Use OpenAI as fallback for products not in Open Food Facts

The service returns structured data that can be used to pre-fill food entry forms.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Open Food Facts API configuration
OPEN_FOOD_FACTS_API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OPEN_FOOD_FACTS_TIMEOUT = 10  # seconds


@dataclass
class BarcodeResult:
    """Result of a barcode lookup."""
    barcode: str
    found: bool
    source: str  # 'database', 'openfoodfacts', 'ai', 'not_found'
    food_name: str = ''
    brand: str = ''
    description: str = ''
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbohydrates_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    sodium_mg: Optional[float] = None
    serving_size: Optional[float] = None
    serving_unit: str = ''
    confidence: float = 0.0
    error: Optional[str] = None
    food_item_id: Optional[int] = None  # If found in database

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'barcode': self.barcode,
            'found': self.found,
            'source': self.source,
            'food_name': self.food_name,
            'brand': self.brand,
            'description': self.description,
            'calories': self.calories,
            'protein_g': self.protein_g,
            'carbohydrates_g': self.carbohydrates_g,
            'fat_g': self.fat_g,
            'fiber_g': self.fiber_g,
            'sugar_g': self.sugar_g,
            'saturated_fat_g': self.saturated_fat_g,
            'sodium_mg': self.sodium_mg,
            'serving_size': self.serving_size,
            'serving_unit': self.serving_unit,
            'confidence': self.confidence,
            'error': self.error,
            'food_item_id': self.food_item_id,
        }


# AI prompt for barcode lookup
BARCODE_LOOKUP_PROMPT = """You are a food product database assistant. Given a product barcode (UPC/EAN), identify the product and return its nutritional information.

IMPORTANT RULES:
1. Only return information for products you are confident about
2. Use your knowledge base of common food products
3. If you don't recognize the barcode, say so
4. Always return values per serving as shown on the nutrition label
5. Include the standard serving size from the nutrition label

RESPONSE FORMAT (strict JSON):
{
  "found": true,
  "food_name": "Product Name",
  "brand": "Brand Name",
  "description": "Brief description of the product",
  "calories": 240,
  "protein_g": 10,
  "carbohydrates_g": 30,
  "fat_g": 8,
  "fiber_g": 3,
  "sugar_g": 12,
  "saturated_fat_g": 2,
  "sodium_mg": 150,
  "serving_size": 40,
  "serving_unit": "g",
  "confidence": 0.95
}

If you don't recognize the barcode:
{
  "found": false,
  "food_name": "",
  "confidence": 0.0
}

The barcode to look up is: {barcode}

Respond ONLY with valid JSON. No markdown, no explanation text."""


class BarcodeService:
    """
    Service for looking up product barcodes.

    Usage:
        from apps.scan.services import barcode_service
        result = barcode_service.lookup(barcode_string)
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.timeout = getattr(settings, 'BARCODE_LOOKUP_TIMEOUT_SECONDS', 15)
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client if API key is available."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key, timeout=self.timeout)
            except ImportError:
                logger.warning("OpenAI package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if AI lookup service is available."""
        return self.client is not None

    def lookup(self, barcode: str, use_ai: bool = True) -> BarcodeResult:
        """
        Look up a barcode and return nutritional information.

        Lookup order:
        1. Local database (fastest, exact match)
        2. Open Food Facts API (free, 4M+ products)
        3. OpenAI fallback (if enabled)

        Args:
            barcode: The product barcode string (UPC, EAN, etc.)
            use_ai: Whether to use AI for unknown barcodes (default True)

        Returns:
            BarcodeResult with product information or not_found
        """
        # Clean the barcode
        barcode = self._clean_barcode(barcode)

        if not barcode:
            return BarcodeResult(
                barcode='',
                found=False,
                source='not_found',
                error='Invalid barcode'
            )

        # Step 1: Check local database
        db_result = self._lookup_database(barcode)
        if db_result and db_result.found:
            logger.info(f"Barcode {barcode} found in database")
            return db_result

        # Step 2: Try Open Food Facts API (free, open database)
        off_result = self._lookup_openfoodfacts(barcode)
        if off_result and off_result.found:
            logger.info(f"Barcode {barcode} found in Open Food Facts")
            # Save to local database for faster future lookups
            self._save_openfoodfacts_result(off_result)
            return off_result

        # Step 3: Try AI lookup if enabled and available
        if use_ai and self.is_available:
            ai_result = self._lookup_ai(barcode)
            if ai_result.found:
                logger.info(f"Barcode {barcode} found via AI lookup")
                return ai_result

        # Not found anywhere
        logger.info(f"Barcode {barcode} not found")
        return BarcodeResult(
            barcode=barcode,
            found=False,
            source='not_found'
        )

    def _clean_barcode(self, barcode: str) -> str:
        """Clean and validate a barcode string."""
        if not barcode:
            return ''

        # Remove whitespace and common prefixes
        barcode = barcode.strip()

        # Remove any non-digit characters (barcodes are numeric)
        barcode = ''.join(c for c in barcode if c.isdigit())

        # Validate length (UPC-A is 12, EAN-13 is 13, etc.)
        if len(barcode) < 8 or len(barcode) > 14:
            return ''

        return barcode

    def _lookup_database(self, barcode: str) -> Optional[BarcodeResult]:
        """Look up barcode in local FoodItem database."""
        try:
            from apps.health.models import FoodItem

            food_item = FoodItem.objects.filter(
                barcode=barcode,
                is_active=True
            ).first()

            if food_item:
                return BarcodeResult(
                    barcode=barcode,
                    found=True,
                    source='database',
                    food_name=food_item.name,
                    brand=food_item.brand or '',
                    description=food_item.description or '',
                    calories=float(food_item.calories),
                    protein_g=float(food_item.protein_g),
                    carbohydrates_g=float(food_item.carbohydrates_g),
                    fat_g=float(food_item.fat_g),
                    fiber_g=float(food_item.fiber_g),
                    sugar_g=float(food_item.sugar_g),
                    saturated_fat_g=float(food_item.saturated_fat_g),
                    sodium_mg=float(food_item.sodium_mg) if food_item.sodium_mg else None,
                    serving_size=float(food_item.serving_size),
                    serving_unit=food_item.serving_unit,
                    confidence=1.0,  # Database matches are exact
                    food_item_id=food_item.id
                )

            return None

        except Exception as e:
            logger.error(f"Database lookup error for barcode {barcode}: {e}")
            return None

    def _lookup_openfoodfacts(self, barcode: str) -> Optional[BarcodeResult]:
        """
        Look up barcode in Open Food Facts API.

        Open Food Facts is a free, open-source database with 4M+ products.
        API docs: https://openfoodfacts.github.io/openfoodfacts-server/api/
        """
        try:
            url = OPEN_FOOD_FACTS_API_URL.format(barcode=barcode)

            # Add User-Agent header as requested by Open Food Facts
            headers = {
                'User-Agent': 'WholeLifeJourney/1.0 (https://wholelifejourney.com)'
            }

            response = requests.get(url, headers=headers, timeout=OPEN_FOOD_FACTS_TIMEOUT)

            if response.status_code != 200:
                logger.warning(f"Open Food Facts API error: {response.status_code}")
                return None

            data = response.json()

            # Check if product was found
            if data.get('status') != 1 or 'product' not in data:
                logger.debug(f"Barcode {barcode} not found in Open Food Facts")
                return None

            product = data['product']

            # Extract product name (try multiple fields)
            food_name = (
                product.get('product_name') or
                product.get('product_name_en') or
                product.get('generic_name') or
                ''
            )

            if not food_name:
                logger.debug(f"Barcode {barcode} found but no product name")
                return None

            # Extract brand
            brand = product.get('brands', '')
            if brand:
                # Clean up brand (often has multiple comma-separated values)
                brand = brand.split(',')[0].strip()

            # Extract nutrition data (per 100g or per serving)
            nutriments = product.get('nutriments', {})

            # Try to get per-serving data first, fall back to per-100g
            serving_size = product.get('serving_quantity')
            serving_unit = 'g'

            if serving_size:
                # Use per-serving values
                calories = nutriments.get('energy-kcal_serving') or nutriments.get('energy_serving')
                protein = nutriments.get('proteins_serving')
                carbs = nutriments.get('carbohydrates_serving')
                fat = nutriments.get('fat_serving')
                fiber = nutriments.get('fiber_serving')
                sugar = nutriments.get('sugars_serving')
                saturated_fat = nutriments.get('saturated-fat_serving')
                sodium = nutriments.get('sodium_serving')

                # Convert sodium from g to mg
                if sodium is not None:
                    sodium = sodium * 1000
            else:
                # Use per-100g values and set serving size to 100g
                serving_size = 100
                calories = nutriments.get('energy-kcal_100g') or nutriments.get('energy_100g')
                protein = nutriments.get('proteins_100g')
                carbs = nutriments.get('carbohydrates_100g')
                fat = nutriments.get('fat_100g')
                fiber = nutriments.get('fiber_100g')
                sugar = nutriments.get('sugars_100g')
                saturated_fat = nutriments.get('saturated-fat_100g')
                sodium = nutriments.get('sodium_100g')

                # Convert sodium from g to mg
                if sodium is not None:
                    sodium = sodium * 1000

            # Handle energy in kJ (convert to kcal if needed)
            if calories and isinstance(calories, (int, float)) and calories > 1000:
                # Likely in kJ, convert to kcal (1 kcal = 4.184 kJ)
                calories = calories / 4.184

            # Build description from categories
            categories = product.get('categories', '')
            description = categories.split(',')[0].strip() if categories else ''

            return BarcodeResult(
                barcode=barcode,
                found=True,
                source='openfoodfacts',
                food_name=food_name,
                brand=brand,
                description=description,
                calories=self._safe_float(calories),
                protein_g=self._safe_float(protein),
                carbohydrates_g=self._safe_float(carbs),
                fat_g=self._safe_float(fat),
                fiber_g=self._safe_float(fiber),
                sugar_g=self._safe_float(sugar),
                saturated_fat_g=self._safe_float(saturated_fat),
                sodium_mg=self._safe_float(sodium),
                serving_size=self._safe_float(serving_size) or 100,
                serving_unit=serving_unit,
                confidence=0.95  # Open Food Facts data is generally reliable
            )

        except requests.Timeout:
            logger.warning(f"Open Food Facts API timeout for barcode {barcode}")
            return None
        except requests.RequestException as e:
            logger.error(f"Open Food Facts API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Open Food Facts lookup error for barcode {barcode}: {e}")
            return None

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float, returning None if not possible."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _save_openfoodfacts_result(self, result: BarcodeResult) -> Optional[int]:
        """Save Open Food Facts result to local database for caching."""
        if not result.found or result.source != 'openfoodfacts':
            return None

        try:
            from apps.health.models import FoodItem

            # Check if barcode already exists
            existing = FoodItem.objects.filter(barcode=result.barcode).first()
            if existing:
                return existing.id

            # Create new FoodItem
            food_item = FoodItem.objects.create(
                name=result.food_name,
                brand=result.brand,
                description=result.description,
                barcode=result.barcode,
                data_source=FoodItem.SOURCE_BARCODE,
                serving_size=result.serving_size or 100,
                serving_unit=result.serving_unit or 'g',
                calories=result.calories or 0,
                protein_g=result.protein_g or 0,
                carbohydrates_g=result.carbohydrates_g or 0,
                fat_g=result.fat_g or 0,
                fiber_g=result.fiber_g or 0,
                sugar_g=result.sugar_g or 0,
                saturated_fat_g=result.saturated_fat_g or 0,
                sodium_mg=result.sodium_mg,
                is_verified=True  # Open Food Facts data is community-verified
            )

            logger.info(f"Cached Open Food Facts barcode {result.barcode} as FoodItem {food_item.id}")
            return food_item.id

        except Exception as e:
            logger.error(f"Failed to cache Open Food Facts barcode {result.barcode}: {e}")
            return None

    def _lookup_ai(self, barcode: str) -> BarcodeResult:
        """Look up barcode using OpenAI."""
        if not self.is_available:
            return BarcodeResult(
                barcode=barcode,
                found=False,
                source='not_found',
                error='AI service not available'
            )

        try:
            prompt = BARCODE_LOOKUP_PROMPT.replace('{barcode}', barcode)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a food product database assistant. Respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            if data.get('found'):
                return BarcodeResult(
                    barcode=barcode,
                    found=True,
                    source='ai',
                    food_name=data.get('food_name', ''),
                    brand=data.get('brand', ''),
                    description=data.get('description', ''),
                    calories=data.get('calories'),
                    protein_g=data.get('protein_g'),
                    carbohydrates_g=data.get('carbohydrates_g'),
                    fat_g=data.get('fat_g'),
                    fiber_g=data.get('fiber_g'),
                    sugar_g=data.get('sugar_g'),
                    saturated_fat_g=data.get('saturated_fat_g'),
                    sodium_mg=data.get('sodium_mg'),
                    serving_size=data.get('serving_size'),
                    serving_unit=data.get('serving_unit', 'serving'),
                    confidence=data.get('confidence', 0.8)
                )
            else:
                return BarcodeResult(
                    barcode=barcode,
                    found=False,
                    source='not_found'
                )

        except json.JSONDecodeError as e:
            logger.error(f"AI barcode lookup JSON parse error: {e}")
            return BarcodeResult(
                barcode=barcode,
                found=False,
                source='not_found',
                error='Failed to parse AI response'
            )

        except Exception as e:
            logger.error(f"AI barcode lookup error for {barcode}: {e}")
            return BarcodeResult(
                barcode=barcode,
                found=False,
                source='not_found',
                error=str(e)
            )

    def save_to_database(self, result: BarcodeResult) -> Optional[int]:
        """
        Save a barcode result to the database for future lookups.

        Args:
            result: BarcodeResult from AI or Open Food Facts lookup

        Returns:
            The FoodItem ID if saved, None otherwise
        """
        if not result.found or result.source not in ('ai', 'openfoodfacts'):
            return None

        try:
            from apps.health.models import FoodItem

            # Check if barcode already exists
            existing = FoodItem.objects.filter(barcode=result.barcode).first()
            if existing:
                return existing.id

            # Create new FoodItem
            food_item = FoodItem.objects.create(
                name=result.food_name,
                brand=result.brand,
                description=result.description,
                barcode=result.barcode,
                data_source=FoodItem.SOURCE_BARCODE,
                serving_size=result.serving_size or 1,
                serving_unit=result.serving_unit or 'serving',
                calories=result.calories or 0,
                protein_g=result.protein_g or 0,
                carbohydrates_g=result.carbohydrates_g or 0,
                fat_g=result.fat_g or 0,
                fiber_g=result.fiber_g or 0,
                sugar_g=result.sugar_g or 0,
                saturated_fat_g=result.saturated_fat_g or 0,
                sodium_mg=result.sodium_mg,
                is_verified=False  # AI-sourced, needs verification
            )

            logger.info(f"Saved barcode {result.barcode} to database as FoodItem {food_item.id}")
            return food_item.id

        except Exception as e:
            logger.error(f"Failed to save barcode {result.barcode} to database: {e}")
            return None


# Singleton instance
barcode_service = BarcodeService()
