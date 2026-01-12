# ==============================================================================
# File: ai_nutrition.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AI-powered nutrition estimation for foods not found in databases.
#              Uses OpenAI to estimate nutritional values based on food name.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# Last Updated: 2026-01-12
# ==============================================================================
"""
AI Nutrition Estimation Service - Fallback when food not found in databases.

This service uses OpenAI to estimate nutritional values based on a food name.
It's designed as a last resort when the food isn't found in local database
or FatSecret API.

The AI provides reasonable estimates but marks results with lower confidence
since these are not from verified sources.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# AI prompt for nutrition estimation
NUTRITION_ESTIMATION_PROMPT = """You are a nutrition database assistant. Given a food name, estimate its nutritional information based on your knowledge of common foods.

IMPORTANT RULES:
1. Provide reasonable estimates based on typical serving sizes
2. If the food is from a restaurant, use known menu item data if available
3. If the food name is vague, estimate based on a typical portion
4. Always include a confidence score (0.0 to 1.0) reflecting how certain you are
5. Use standard serving sizes (e.g., 1 burger, 1 cup, 1 slice, 100g)

RESPONSE FORMAT (strict JSON):
{
  "food_name": "Food Name (cleaned/standardized)",
  "brand": "Brand Name (if identifiable)",
  "calories": 250,
  "protein_g": 12,
  "carbohydrates_g": 30,
  "fat_g": 8,
  "fiber_g": 3,
  "sugar_g": 5,
  "saturated_fat_g": 2,
  "serving_size": 1,
  "serving_unit": "burger",
  "confidence": 0.75,
  "notes": "Based on typical fast food burger"
}

The food to estimate is: {food_name}

Respond ONLY with valid JSON. No markdown, no explanation text."""


@dataclass
class AIFoodEstimate:
    """Result from AI nutrition estimation."""
    name: str
    brand: str
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbohydrates_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    serving_size: Optional[float] = None
    serving_unit: str = ''
    confidence: float = 0.0
    notes: str = ''
    source: str = 'ai'

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'name': self.name,
            'brand': self.brand,
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
            'notes': self.notes,
            'source': self.source,
        }


class AINutritionService:
    """
    AI-powered nutrition estimation service.

    Usage:
        from apps.health.services.ai_nutrition import ai_nutrition_service
        result = ai_nutrition_service.estimate_nutrition("McDonald's Big Mac")
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.timeout = getattr(settings, 'AI_NUTRITION_TIMEOUT_SECONDS', 15)
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
        """Check if AI service is available."""
        return self.client is not None

    def estimate_nutrition(self, food_name: str) -> Optional[AIFoodEstimate]:
        """
        Estimate nutritional values for a food based on its name.

        Args:
            food_name: The food to estimate (e.g., "McDonald's Big Mac")

        Returns:
            AIFoodEstimate with estimated nutrition data, or None if failed
        """
        if not self.is_available:
            logger.warning("AI nutrition service not available")
            return None

        if not food_name or len(food_name.strip()) < 2:
            logger.debug("Food name too short for AI estimation")
            return None

        try:
            prompt = NUTRITION_ESTIMATION_PROMPT.replace('{food_name}', food_name)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a nutrition database assistant. Respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.2,  # Low temperature for consistency
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            # Build result
            result = AIFoodEstimate(
                name=data.get('food_name', food_name),
                brand=data.get('brand', ''),
                calories=self._safe_float(data.get('calories')),
                protein_g=self._safe_float(data.get('protein_g')),
                carbohydrates_g=self._safe_float(data.get('carbohydrates_g')),
                fat_g=self._safe_float(data.get('fat_g')),
                fiber_g=self._safe_float(data.get('fiber_g')),
                sugar_g=self._safe_float(data.get('sugar_g')),
                saturated_fat_g=self._safe_float(data.get('saturated_fat_g')),
                serving_size=self._safe_float(data.get('serving_size', 1)),
                serving_unit=data.get('serving_unit', 'serving'),
                confidence=min(float(data.get('confidence', 0.5)), 0.8),  # Cap at 0.8 for AI
                notes=data.get('notes', ''),
                source='ai',
            )

            logger.info(f"AI estimated nutrition for '{food_name}' with confidence {result.confidence}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response for '{food_name}': {e}")
        except Exception as e:
            logger.error(f"AI nutrition estimation failed for '{food_name}': {e}")

        return None

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
ai_nutrition_service = AINutritionService()
