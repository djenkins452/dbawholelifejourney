"""
Vision Service - OpenAI Vision API integration for WLJ.

This service handles image analysis using OpenAI's Vision capabilities.
It returns structured data about what's in the image and suggests
relevant actions within WLJ.

Security Notes:
- Images are processed in-memory only
- No image data is logged
- Strict JSON schema for responses
- Timeout protection
"""

import base64
import json
import logging
import time
from typing import Optional
from dataclasses import dataclass, asdict

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


# Vision prompt for structured analysis
VISION_SYSTEM_PROMPT = """You are a vision assistant for "Whole Life Journey", a personal wellness app.
Your job is to analyze images and identify what they contain so the user can take action in the app.

IMPORTANT RULES:
1. NEVER identify people or faces. If a person is in the image, ignore them.
2. NEVER make assumptions about the person's health, weight, or medical conditions.
3. NEVER provide medical advice. Only identify what you see.
4. If you see medicine or supplements, just describe what's visible (name, dosage on label).
5. Be conservative with confidence scores - only use high confidence when clearly visible.
6. Always respond with valid JSON matching the schema exactly.

CATEGORIES YOU CAN IDENTIFY:
- food: Meals, snacks, ingredients, beverages
- medicine: Prescription bottles, pill packages, medical devices
- supplement: Vitamins, supplements, protein powder
- receipt: Store receipts, invoices, bills
- document: Lab reports, appointment cards, medical documents, notes
- workout_equipment: Gym equipment, exercise gear, fitness trackers
- barcode: Product barcodes, QR codes
- unknown: When you cannot confidently identify the item

RESPONSE FORMAT (strict JSON):
{
  "top_category": "category_name",
  "confidence": 0.0-1.0,
  "items": [
    {
      "label": "item name",
      "details": {"key": "value pairs relevant to the item"},
      "confidence": 0.0-1.0
    }
  ],
  "safety_notes": ["any warnings or notes for the user"]
}

Example for a medicine bottle:
{
  "top_category": "medicine",
  "confidence": 0.92,
  "items": [
    {
      "label": "Lisinopril 10mg",
      "details": {
        "dosage": "10mg",
        "quantity": "30 tablets",
        "directions": "Take once daily"
      },
      "confidence": 0.92
    }
  ],
  "safety_notes": ["Always consult your doctor or pharmacist about medications"]
}

Example for food:
{
  "top_category": "food",
  "confidence": 0.88,
  "items": [
    {
      "label": "Grilled chicken salad",
      "details": {
        "estimated_calories": "350-450",
        "protein": "high",
        "meal_type": "lunch/dinner"
      },
      "confidence": 0.85
    }
  ],
  "safety_notes": []
}

Respond ONLY with valid JSON. No markdown, no explanation text."""


@dataclass
class ScanItem:
    """Individual item detected in the scan."""
    label: str
    details: dict
    confidence: float


@dataclass
class ScanAction:
    """Suggested action for the user."""
    id: str
    label: str
    url: str
    payload_template: dict


@dataclass
class NextBestAction:
    """Group of actions for a module."""
    module: str
    question: str
    actions: list


@dataclass
class ScanResult:
    """Complete scan result with actions."""
    request_id: str
    top_category: str
    confidence: float
    items: list
    safety_notes: list
    next_best_actions: list
    error: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'request_id': self.request_id,
            'top_category': self.top_category,
            'confidence': self.confidence,
            'items': [asdict(item) if isinstance(item, ScanItem) else item for item in self.items],
            'safety_notes': self.safety_notes,
            'next_best_actions': [
                {
                    'module': nba.module if isinstance(nba, NextBestAction) else nba.get('module'),
                    'question': nba.question if isinstance(nba, NextBestAction) else nba.get('question'),
                    'actions': [
                        asdict(a) if isinstance(a, ScanAction) else a
                        for a in (nba.actions if isinstance(nba, NextBestAction) else nba.get('actions', []))
                    ]
                }
                for nba in self.next_best_actions
            ],
            'error': self.error
        }


class VisionService:
    """
    Service for analyzing images using OpenAI Vision API.

    Usage:
        from apps.scan.services import vision_service
        result = vision_service.analyze_image(image_data, request_id)
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_VISION_MODEL', 'gpt-4o')
        self.timeout = getattr(settings, 'SCAN_REQUEST_TIMEOUT_SECONDS', 30)
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client if API key is available."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key, timeout=self.timeout)
            except ImportError:
                logger.warning("OpenAI package not installed. Run: pip install openai")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if vision service is available."""
        return self.client is not None

    def analyze_image(
        self,
        image_base64: str,
        request_id: str,
        image_format: str = 'jpeg'
    ) -> ScanResult:
        """
        Analyze an image and return structured results.

        Args:
            image_base64: Base64-encoded image data (without data URI prefix)
            request_id: UUID for tracking this request
            image_format: Image format (jpeg, png, webp)

        Returns:
            ScanResult with category, items, and suggested actions
        """
        if not self.is_available:
            logger.error(f"Vision service unavailable for request {request_id}")
            return self._error_result(request_id, "Vision service not configured")

        start_time = time.time()

        try:
            # Build the data URI
            media_type = f"image/{image_format}"
            data_uri = f"data:{media_type};base64,{image_base64}"

            # Call OpenAI Vision API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this image and identify what it contains. Respond with JSON only."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_uri,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.1,  # Low temperature for consistent structured output
                response_format={"type": "json_object"}
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Parse the response
            content = response.choices[0].message.content
            ai_result = json.loads(content)

            # Validate required fields
            if 'top_category' not in ai_result:
                ai_result['top_category'] = 'unknown'
            if 'confidence' not in ai_result:
                ai_result['confidence'] = 0.0
            if 'items' not in ai_result:
                ai_result['items'] = []
            if 'safety_notes' not in ai_result:
                ai_result['safety_notes'] = []

            # Build next best actions based on category
            next_actions = self._build_actions(
                ai_result['top_category'],
                ai_result['items']
            )

            logger.info(
                f"Scan {request_id} completed: {ai_result['top_category']} "
                f"(confidence: {ai_result['confidence']:.2f}) in {processing_time_ms}ms"
            )

            return ScanResult(
                request_id=request_id,
                top_category=ai_result['top_category'],
                confidence=ai_result['confidence'],
                items=ai_result['items'],
                safety_notes=ai_result['safety_notes'],
                next_best_actions=next_actions
            )

        except json.JSONDecodeError as e:
            logger.error(f"Scan {request_id} JSON parse error: {e}")
            return self._error_result(request_id, "Failed to parse AI response")

        except TimeoutError:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Scan {request_id} timed out after {processing_time_ms}ms")
            return self._error_result(request_id, "Request timed out. Please try again.")

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Scan {request_id} error after {processing_time_ms}ms: {e}")
            return self._error_result(request_id, "An error occurred. Please try again.")

    def _build_actions(self, category: str, items: list) -> list:
        """
        Build contextual actions based on the identified category.

        Maps categories to WLJ modules and provides relevant action options.
        """
        actions = []

        if category == 'food':
            # Build prefill data from items
            food_label = items[0]['label'] if items else 'meal'
            calories = items[0].get('details', {}).get('estimated_calories', '') if items else ''

            actions.append({
                'module': 'Health.FoodLog',
                'question': 'Would you like to log this meal?',
                'actions': [
                    {
                        'id': 'log_food',
                        'label': 'Log to Food Journal',
                        'url': reverse('journal:entry_create') + f'?prefill_title=Food: {food_label}',
                        'payload_template': {
                            'category': 'health',
                            'title': f'Food: {food_label}',
                            'body': f'Logged meal: {food_label}' + (f' (~{calories} cal)' if calories else '')
                        }
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

        elif category == 'medicine':
            med_name = items[0]['label'] if items else 'medication'
            details = items[0].get('details', {}) if items else {}

            actions.append({
                'module': 'Health.Medicine',
                'question': 'Would you like to add this medicine?',
                'actions': [
                    {
                        'id': 'add_medicine',
                        'label': 'Add to My Medicines',
                        'url': reverse('health:medicine_create') + f'?name={med_name}',
                        'payload_template': {
                            'name': med_name,
                            'dose': details.get('dosage', ''),
                            'directions': details.get('directions', '')
                        }
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

        elif category == 'supplement':
            supp_name = items[0]['label'] if items else 'supplement'
            details = items[0].get('details', {}) if items else {}

            actions.append({
                'module': 'Health.Medicine',
                'question': 'Would you like to add this supplement?',
                'actions': [
                    {
                        'id': 'add_supplement',
                        'label': 'Add to My Supplements',
                        'url': reverse('health:medicine_create') + f'?name={supp_name}&type=supplement',
                        'payload_template': {
                            'name': supp_name,
                            'dose': details.get('dosage', ''),
                            'is_supplement': True
                        }
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

            # Add safety note for supplements
            actions[0]['safety_notes'] = ['Always consult your doctor or pharmacist about supplements']

        elif category == 'receipt':
            merchant = items[0].get('details', {}).get('merchant', 'Store') if items else 'Store'

            actions.append({
                'module': 'Journal',
                'question': 'Would you like to save this receipt?',
                'actions': [
                    {
                        'id': 'save_receipt',
                        'label': 'Add Journal Note',
                        'url': reverse('journal:entry_create') + f'?prefill_title=Receipt from {merchant}',
                        'payload_template': {
                            'category': 'life',
                            'title': f'Receipt from {merchant}'
                        }
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

        elif category == 'document':
            doc_type = items[0]['label'] if items else 'Document'

            actions.append({
                'module': 'Journal',
                'question': 'Would you like to save this document?',
                'actions': [
                    {
                        'id': 'save_document',
                        'label': 'Add to Journal',
                        'url': reverse('journal:entry_create') + f'?prefill_title={doc_type}',
                        'payload_template': {
                            'title': doc_type
                        }
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

        elif category == 'workout_equipment':
            equipment = items[0]['label'] if items else 'equipment'

            actions.append({
                'module': 'Health.Fitness',
                'question': 'Would you like to log a workout?',
                'actions': [
                    {
                        'id': 'log_workout',
                        'label': 'Start Workout',
                        'url': reverse('health:workout_create'),
                        'payload_template': {}
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

        else:  # unknown or barcode
            actions.append({
                'module': 'Unknown',
                'question': "I couldn't identify this clearly. What would you like to do?",
                'actions': [
                    {
                        'id': 'retry',
                        'label': 'Try Again',
                        'url': reverse('scan:home'),
                        'payload_template': {}
                    },
                    {
                        'id': 'add_note',
                        'label': 'Add as Journal Note',
                        'url': reverse('journal:entry_create'),
                        'payload_template': {}
                    },
                    {
                        'id': 'skip',
                        'label': 'Skip',
                        'url': '',
                        'payload_template': {}
                    }
                ]
            })

        return actions

    def _error_result(self, request_id: str, error_message: str) -> ScanResult:
        """Create an error result."""
        return ScanResult(
            request_id=request_id,
            top_category='unknown',
            confidence=0.0,
            items=[],
            safety_notes=[],
            next_best_actions=[{
                'module': 'Unknown',
                'question': error_message,
                'actions': [
                    {
                        'id': 'retry',
                        'label': 'Try Again',
                        'url': reverse('scan:home'),
                        'payload_template': {}
                    }
                ]
            }],
            error=error_message
        )


# Singleton instance
vision_service = VisionService()
