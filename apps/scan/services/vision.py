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
4. If you see medicine or supplements, describe what's visible (name, dosage on label) AND look up the common medical purpose of that medication (e.g., "blood pressure control", "cholesterol management", "pain relief", "allergy relief"). Include this purpose in the details.
5. Be conservative with confidence scores - only use high confidence when clearly visible.
6. Always respond with valid JSON matching the schema exactly.
7. Choose the MOST SPECIFIC category that applies. For example, a power tool is "inventory_item", not "unknown".

CATEGORIES YOU CAN IDENTIFY:
- food: Meals, snacks, ingredients, beverages (cooked food, raw ingredients, drinks)
- medicine: Prescription bottles, pill packages, medical devices
- supplement: Vitamins, supplements, protein powder
- receipt: Store receipts, invoices, bills
- document: Lab reports, appointment cards, medical documents, written notes, letters
- workout_equipment: Gym equipment, exercise gear, fitness trackers, weights, yoga mats
- inventory_item: Household items, electronics, furniture, appliances, tools, power tools,
  collectibles, jewelry, musical instruments, art, clothing, sports equipment, gadgets,
  cameras, computers, TVs, game consoles, kitchen appliances, lawn equipment
- recipe: Recipes (handwritten or printed), cookbook pages, recipe cards, food packaging with recipes
- pet: Animals, pets, pet food, pet supplies, pet toys, pet accessories
- maintenance: Home repair items, HVAC filters, plumbing parts, paint cans, hardware,
  car parts, appliance manuals, warranty cards, service records
- barcode: Product barcodes, QR codes (when nothing else is identifiable)
- unknown: ONLY when you truly cannot identify what the item is

CATEGORY SELECTION GUIDANCE:
- Tools (drills, saws, hammers) → inventory_item with category "Tools"
- Electronics (phones, laptops, TVs) → inventory_item with category "Electronics"
- Furniture (chairs, tables, beds) → inventory_item with category "Furniture"
- Kitchen appliances → inventory_item with category "Appliances"
- Jewelry/watches → inventory_item with category "Jewelry"
- Musical instruments → inventory_item with category "Musical Instruments"
- Sports gear (not gym equipment) → inventory_item with category "Sports Equipment"
- Art/collectibles → inventory_item with category "Art" or "Collectibles"
- Pet food or supplies → pet
- Recipe on paper/screen → recipe
- Filter, part, or repair item → maintenance

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
        "directions": "Take once daily",
        "purpose": "Blood pressure control"
      },
      "confidence": 0.92
    }
  ],
  "safety_notes": ["Always consult your doctor or pharmacist about medications"]
}

Example for a power tool (inventory item):
{
  "top_category": "inventory_item",
  "confidence": 0.95,
  "items": [
    {
      "label": "DeWalt 20V Cordless Drill",
      "details": {
        "brand": "DeWalt",
        "model": "DCD771C2",
        "category": "Tools",
        "condition": "good"
      },
      "confidence": 0.95
    }
  ],
  "safety_notes": []
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

Example for a pet:
{
  "top_category": "pet",
  "confidence": 0.90,
  "items": [
    {
      "label": "Golden Retriever",
      "details": {
        "species": "dog",
        "breed": "Golden Retriever",
        "estimated_age": "adult"
      },
      "confidence": 0.90
    }
  ],
  "safety_notes": []
}

Example for a recipe:
{
  "top_category": "recipe",
  "confidence": 0.85,
  "items": [
    {
      "label": "Chocolate Chip Cookies",
      "details": {
        "cuisine": "American",
        "course": "dessert",
        "servings": "24 cookies"
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

    def _add_source_param(self, url: str) -> str:
        """Add source=ai_camera to URL to track AI-created entries."""
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}source=ai_camera"

    def _build_actions(self, category: str, items: list) -> list:
        """
        Build contextual actions based on the identified category.

        Maps categories to WLJ modules and provides relevant action options.
        All action URLs include source=ai_camera to track AI-created entries.
        """
        from urllib.parse import quote

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
                        'url': self._add_source_param(
                            reverse('journal:entry_create') + f'?prefill_title=Food: {quote(food_label)}'
                        ),
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

            # Build URL with all available fields
            url_params = [f'name={quote(med_name)}']
            if details.get('dosage'):
                url_params.append(f'dose={quote(details["dosage"])}')
            if details.get('directions'):
                url_params.append(f'directions={quote(details["directions"])}')
            if details.get('quantity'):
                url_params.append(f'quantity={quote(details["quantity"])}')
            if details.get('purpose'):
                url_params.append(f'purpose={quote(details["purpose"])}')

            actions.append({
                'module': 'Health.Medicine',
                'question': 'Would you like to add this medicine?',
                'actions': [
                    {
                        'id': 'add_medicine',
                        'label': 'Add to My Medicines',
                        'url': self._add_source_param(
                            reverse('health:medicine_create') + '?' + '&'.join(url_params)
                        ),
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

            # Build URL with all available fields
            url_params = [f'name={quote(supp_name)}', 'type=supplement']
            if details.get('dosage'):
                url_params.append(f'dose={quote(details["dosage"])}')
            if details.get('directions'):
                url_params.append(f'directions={quote(details["directions"])}')
            if details.get('quantity'):
                url_params.append(f'quantity={quote(details["quantity"])}')
            if details.get('purpose'):
                url_params.append(f'purpose={quote(details["purpose"])}')

            actions.append({
                'module': 'Health.Medicine',
                'question': 'Would you like to add this supplement?',
                'actions': [
                    {
                        'id': 'add_supplement',
                        'label': 'Add to My Supplements',
                        'url': self._add_source_param(
                            reverse('health:medicine_create') + '?' + '&'.join(url_params)
                        ),
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
                        'url': self._add_source_param(
                            reverse('journal:entry_create') + f'?prefill_title=Receipt from {quote(merchant)}'
                        ),
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
                'module': 'Life.Documents',
                'question': 'Would you like to save this document?',
                'actions': [
                    {
                        'id': 'save_document',
                        'label': 'Save to Documents',
                        'url': self._add_source_param(
                            reverse('life:document_create') + f'?name={quote(doc_type)}'
                        ),
                        'payload_template': {
                            'name': doc_type
                        }
                    },
                    {
                        'id': 'add_journal',
                        'label': 'Add to Journal',
                        'url': self._add_source_param(
                            reverse('journal:entry_create') + f'?prefill_title={quote(doc_type)}'
                        ),
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
                        'url': self._add_source_param(reverse('health:workout_create')),
                        'payload_template': {}
                    },
                    {
                        'id': 'add_inventory',
                        'label': 'Add to Inventory',
                        'url': self._add_source_param(
                            reverse('life:inventory_create') + f'?name={quote(equipment)}&category=Sports Equipment'
                        ),
                        'payload_template': {
                            'name': equipment,
                            'category': 'Sports Equipment'
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

        elif category == 'inventory_item':
            # Handle household items, electronics, tools, etc.
            item_name = items[0]['label'] if items else 'item'
            details = items[0].get('details', {}) if items else {}
            item_category = details.get('category', 'Electronics')
            brand = details.get('brand', '')
            model = details.get('model', '')

            # Build query params for inventory create
            params = [f'name={quote(item_name)}', f'category={quote(item_category)}']
            if brand:
                params.append(f'brand={quote(brand)}')
            if model:
                params.append(f'model_number={quote(model)}')

            actions.append({
                'module': 'Life.Inventory',
                'question': f'Would you like to add this {item_category.lower()} to your inventory?',
                'actions': [
                    {
                        'id': 'add_inventory',
                        'label': 'Add to Inventory',
                        'url': self._add_source_param(
                            reverse('life:inventory_create') + '?' + '&'.join(params)
                        ),
                        'payload_template': {
                            'name': item_name,
                            'category': item_category,
                            'brand': brand,
                            'model_number': model
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

        elif category == 'recipe':
            # Handle recipes from cookbooks, recipe cards, etc.
            recipe_name = items[0]['label'] if items else 'Recipe'
            details = items[0].get('details', {}) if items else {}
            cuisine = details.get('cuisine', '')
            course = details.get('course', '')

            # Build query params for recipe create
            params = [f'name={quote(recipe_name)}']
            if cuisine:
                params.append(f'cuisine={quote(cuisine)}')
            if course:
                params.append(f'course={quote(course)}')

            actions.append({
                'module': 'Life.Recipes',
                'question': 'Would you like to save this recipe?',
                'actions': [
                    {
                        'id': 'save_recipe',
                        'label': 'Save Recipe',
                        'url': self._add_source_param(
                            reverse('life:recipe_create') + '?' + '&'.join(params)
                        ),
                        'payload_template': {
                            'name': recipe_name,
                            'cuisine': cuisine,
                            'course': course
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

        elif category == 'pet':
            # Handle pets and pet-related items
            pet_label = items[0]['label'] if items else 'Pet'
            details = items[0].get('details', {}) if items else {}
            species = details.get('species', '')
            breed = details.get('breed', '')

            # Build query params for pet create
            params = [f'name={quote(pet_label)}']
            if species:
                params.append(f'species={quote(species)}')
            if breed:
                params.append(f'breed={quote(breed)}')

            actions.append({
                'module': 'Life.Pets',
                'question': 'Would you like to add this pet to your family?',
                'actions': [
                    {
                        'id': 'add_pet',
                        'label': 'Add Pet',
                        'url': self._add_source_param(
                            reverse('life:pet_create') + '?' + '&'.join(params)
                        ),
                        'payload_template': {
                            'name': pet_label,
                            'species': species,
                            'breed': breed
                        }
                    },
                    {
                        'id': 'add_journal',
                        'label': 'Add to Journal',
                        'url': self._add_source_param(
                            reverse('journal:entry_create') + f'?prefill_title=Pet: {quote(pet_label)}'
                        ),
                        'payload_template': {
                            'title': f'Pet: {pet_label}'
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

        elif category == 'maintenance':
            # Handle home/car maintenance items
            item_name = items[0]['label'] if items else 'Maintenance Item'
            details = items[0].get('details', {}) if items else {}

            actions.append({
                'module': 'Life.Maintenance',
                'question': 'Would you like to log this maintenance item?',
                'actions': [
                    {
                        'id': 'add_maintenance',
                        'label': 'Log Maintenance',
                        'url': self._add_source_param(
                            reverse('life:maintenance_create') + f'?title={quote(item_name)}'
                        ),
                        'payload_template': {
                            'title': item_name
                        }
                    },
                    {
                        'id': 'add_inventory',
                        'label': 'Add to Inventory',
                        'url': self._add_source_param(
                            reverse('life:inventory_create') + f'?name={quote(item_name)}'
                        ),
                        'payload_template': {
                            'name': item_name
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
                        'id': 'add_inventory',
                        'label': 'Add to Inventory',
                        'url': self._add_source_param(reverse('life:inventory_create')),
                        'payload_template': {}
                    },
                    {
                        'id': 'add_note',
                        'label': 'Add as Journal Note',
                        'url': self._add_source_param(reverse('journal:entry_create')),
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
