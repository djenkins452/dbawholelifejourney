"""
Recipe Photo Import Service

Extracts recipe data from a photo using Vision AI (OCR/transcription).
Handles cookbook pages, recipe cards, handwritten notes, and screen captures.

No models are created here — the view handles Recipe creation after user review.
"""

import base64
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


RECIPE_VISION_PROMPT = """You are analyzing a photo that may contain one or MORE recipes. \
This could be from a cookbook, recipe card, magazine, handwritten note, or screen capture.

Your goal is to READ and TRANSCRIBE ALL recipes visible in the image into structured data.

IMPORTANT RULES:
1. Transcribe each recipe exactly as written — do not invent or embellish.
2. If a field is not visible or not present, leave it as null or empty string.
3. For ingredients, list each one on its own line exactly as written (e.g., "2 cups flour").
4. For instructions, preserve the step-by-step order. Number each step.
5. Extract times, servings, and difficulty if mentioned anywhere in the recipe.
6. If the recipe source/attribution is visible (cookbook name, author, website), include it.
7. If the image contains MULTIPLE recipes, return ALL of them in the array.

RESPONSE FORMAT (strict JSON — always return an object with a "recipes" array):
{
  "recipes": [
    {
      "title": "Recipe Title",
      "description": "Brief description if visible, or empty string",
      "ingredients": "2 cups flour\\n1 tsp salt\\n3 eggs",
      "instructions": "1. Preheat oven to 350F.\\n2. Mix dry ingredients.\\n3. ...",
      "prep_time_minutes": null,
      "cook_time_minutes": null,
      "servings": null,
      "difficulty": "",
      "category": "",
      "source": "Cookbook name or author if visible, else empty string",
      "notes": "Any additional notes visible in the recipe",
      "confidence": 0.85
    }
  ]
}

Field notes:
- "difficulty" must be one of: "", "easy", "medium", "hard"
- "category" examples: "Breakfast", "Lunch", "Dinner", "Dessert", "Appetizer", "Snack", "Side Dish"
- "confidence" is your overall confidence (0.0-1.0) that you accurately read that recipe
- Numeric fields (prep_time_minutes, cook_time_minutes, servings) should be integers or null
- The "recipes" array should contain one entry per distinct recipe visible in the image

Respond ONLY with valid JSON. No markdown fences, no explanation."""


class RecipePhotoImportService:
    """
    Extracts recipe data from a photo using Vision AI.

    Usage:
        from apps.life.services.recipe_photo_import import recipe_photo_import_service
        result = recipe_photo_import_service.extract_from_bytes(raw_bytes, "image/jpeg")
        if "error" in result:
            # handle error
        else:
            # result has title, ingredients, instructions, etc.
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
            if not api_key:
                logger.error(
                    "OPENAI_API_KEY not configured — Vision API unavailable. "
                    "Ensure the env var is set on ALL Railway services (web + worker)."
                )
                return None
            try:
                import openai

                self._client = openai.OpenAI(
                    api_key=api_key,
                    timeout=60,
                )
            except ImportError:
                logger.error("openai package not installed")
            except Exception as e:
                logger.error("Failed to init OpenAI client: %s", e, exc_info=True)
        return self._client

    def extract_from_bytes(self, raw_bytes, content_type="image/jpeg"):
        """
        Extract recipe data from in-memory image bytes.

        Args:
            raw_bytes: Raw image file bytes from request.FILES
            content_type: MIME type of the image

        Returns:
            list of dicts (one per recipe found), or a single dict with 'error' key
        """
        from apps.scan.services.image_utils import resize_for_vision

        base64_data = base64.b64encode(raw_bytes).decode("utf-8")

        # Resize for Vision API — use 2048px for recipe text (needs resolution)
        base64_data = resize_for_vision(base64_data, content_type, max_dim=2048)

        return self._call_vision_api(base64_data, content_type)

    def _call_vision_api(self, base64_data, mime_type):
        """Call OpenAI Vision API with recipe extraction prompt."""
        if not self.client:
            return {"error": "Vision API client not available"}

        model = settings.OPENAI_VISION_MODEL

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": RECIPE_VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_data}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=4000,
                temperature=0.1,
            )

            # Telemetry
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    from apps.owner_finance.services.telemetry import log_llm_usage

                    log_llm_usage(
                        feature="RECIPE_PHOTO_IMPORT",
                        model_name=model,
                        input_tokens=getattr(usage, "prompt_tokens", 0),
                        output_tokens=getattr(usage, "completion_tokens", 0),
                    )
            except ImportError:
                pass
            except Exception:
                logger.debug("Telemetry logging failed", exc_info=True)

            content = response.choices[0].message.content.strip()

            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            result = json.loads(content)

            # Handle multi-recipe response: {"recipes": [...]}
            if isinstance(result, dict) and "recipes" in result:
                recipes = result["recipes"]
                if isinstance(recipes, list) and len(recipes) > 0:
                    validated = []
                    for r in recipes:
                        v = self._validate_result(r)
                        if "error" not in v:
                            validated.append(v)
                    if validated:
                        return validated
                    # All recipes had errors — return the first error
                    return self._validate_result(recipes[0])

            # Backward compat: single recipe dict (no "recipes" wrapper)
            if isinstance(result, dict):
                validated = self._validate_result(result)
                if "error" in validated:
                    return validated
                return [validated]

            # Unexpected format
            return {"error": "Unexpected response format from Vision API"}

        except json.JSONDecodeError as e:
            logger.error("Recipe Vision API returned invalid JSON: %s", e)
            return {"error": "Could not parse recipe from image. Try a clearer photo."}
        except Exception as e:
            logger.error("Recipe Vision API call failed: %s", e, exc_info=True)
            return {"error": f"Failed to analyze photo: {e}"}

    def _validate_result(self, result):
        """Validate and clean the extracted recipe data."""
        validated = {
            "title": (result.get("title") or "").strip(),
            "description": (result.get("description") or "").strip(),
            "ingredients": (result.get("ingredients") or "").strip(),
            "instructions": (result.get("instructions") or "").strip(),
            "prep_time_minutes": result.get("prep_time_minutes"),
            "cook_time_minutes": result.get("cook_time_minutes"),
            "servings": result.get("servings"),
            "difficulty": result.get("difficulty") or "",
            "category": (result.get("category") or "").strip(),
            "source": (result.get("source") or "").strip(),
            "notes": (result.get("notes") or "").strip(),
            "confidence": result.get("confidence", 0.5),
        }

        # Validate difficulty
        if validated["difficulty"] not in ("", "easy", "medium", "hard"):
            validated["difficulty"] = ""

        # Validate numeric fields
        for field in ("prep_time_minutes", "cook_time_minutes", "servings"):
            val = validated[field]
            if val is not None:
                try:
                    validated[field] = int(val)
                    if validated[field] <= 0:
                        validated[field] = None
                except (ValueError, TypeError):
                    validated[field] = None

        # Validate confidence
        try:
            validated["confidence"] = max(0.0, min(1.0, float(validated["confidence"])))
        except (ValueError, TypeError):
            validated["confidence"] = 0.5

        # Title is required
        if not validated["title"]:
            validated["error"] = (
                "Could not identify a recipe title in the image. "
                "Please try a clearer photo."
            )

        return validated


# Module-level singleton
recipe_photo_import_service = RecipePhotoImportService()
