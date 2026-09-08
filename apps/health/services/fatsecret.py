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
from dataclasses import dataclass, field
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


# ── Search outcomes ──────────────────────────────────────────────────────────
#
# `search_foods` used to return `[]` for five unrelated conditions: an HTTP failure,
# FatSecret's XML error envelope arriving with HTTP 200 (its documented behaviour when a
# request is rejected — wrong format, OAuth problem, rate limit, unregistered IP), a missing
# `foods` payload, a genuinely empty result, and any parse exception. Every one of them
# reached the caller as "no such food".
#
# Production, 2026-09-08: authentication succeeded and every live search returned nothing —
# including "banana" and "big mac", which FatSecret certainly holds. Nothing in the system
# could say why, because the five causes had one shape.
OK_WITH_RESULTS = "OK_WITH_RESULTS"
OK_NO_RESULTS = "OK_NO_RESULTS"
AUTH_ERROR = "AUTH_ERROR"
PROVIDER_ERROR = "PROVIDER_ERROR"       # FatSecret answered, and the answer is an error
HTTP_ERROR = "HTTP_ERROR"
INVALID_RESPONSE = "INVALID_RESPONSE"   # 200, parsed, but not the documented shape
PARSE_ERROR = "PARSE_ERROR"             # body could not be read as JSON at all
NOT_CONFIGURED = "NOT_CONFIGURED"

_DETAIL_CAP = 400

# A bearer token appears only in request headers, never in a response — but a provider that
# echoes a request would put one in a body, so anything token-shaped is removed before a
# detail is stored or logged.
_TOKEN_PATTERN = re.compile(r"(?i)(bearer\s+)?[A-Za-z0-9_\-]{40,}")


def _safe_detail(text):
    """A bounded, credential-free fragment of a provider response."""
    return _TOKEN_PATTERN.sub("[redacted]", str(text or ""))[:_DETAIL_CAP]


@dataclass
class FatSecretSearchOutcome:
    """What actually happened on one FatSecret search.

    `foods` is always a list, so a caller that only wants candidates can ignore everything
    else and never break; `status` is what makes an empty list explainable.
    """
    status: str
    foods: list = field(default_factory=list)
    detail: str = ""
    http_status: Optional[int] = None
    provider_code: Optional[str] = None
    body_kind: str = ""          # json | xml | empty | unreadable

    @property
    def ok(self):
        return self.status in (OK_WITH_RESULTS, OK_NO_RESULTS)

    def as_diagnostic(self):
        """Operator-facing shape. Counts, codes and a bounded message — never a payload."""
        return {
            "status": self.status,
            "count": len(self.foods),
            "http_status": self.http_status,
            "provider_code": self.provider_code,
            "body_kind": self.body_kind,
            "detail": self.detail,
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
        """Parse JSON from response, handling empty/malformed bodies.

        When FatSecret returns its XML error envelope (which it does, with
        HTTP 200, whenever the request format is wrong or there is an
        OAuth / rate-limit issue), the JSON parse fails. We log a 500-char
        prefix of the body — wide enough to capture the full <error>
        envelope including <code> and <message> fields so the actual
        FatSecret error reason is visible in the admin email.
        """
        if not response.content:
            logger.warning("%s returned empty response body (status=%s)", context, response.status_code)
            return None
        try:
            return response.json()
        except ValueError as e:
            logger.error(
                "%s JSON decode error (status=%s, body=%s): %s",
                context, response.status_code, response.text[:500], e,
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
        """Search FatSecret. Returns candidates — the list-only contract callers rely on.

        Resilient by design: an empty list on any failure, so no provider problem can break
        a page. `search_foods_outcome` is the same call with the reason attached, for
        diagnostics that need to know WHY the list is empty.
        """
        return self.search_foods_outcome(query, max_results, page_number).foods

    def search_foods_outcome(
        self,
        query: str,
        max_results: int = 10,
        page_number: int = 0
    ) -> "FatSecretSearchOutcome":
        """The same search, with a structured outcome instead of a bare list.

        Every return below names ONE condition. That is the whole point: the previous
        implementation answered five different failures with the same empty list, so a
        provider rejecting our requests and a food genuinely not existing were
        indistinguishable — in the UI, in the logs, and in production forensics.
        """
        if not self.is_available:
            return FatSecretSearchOutcome(
                status=NOT_CONFIGURED,
                detail="FATSECRET_CLIENT_ID / FATSECRET_CLIENT_SECRET are not set on this "
                       "service.")

        token = self._get_access_token()
        if not token:
            return FatSecretSearchOutcome(
                status=AUTH_ERROR,
                detail="No OAuth token could be obtained for these credentials.")

        try:
            # FatSecret /rest/server.api takes form-encoded parameters (or a query string),
            # NOT a JSON body — even when format=json is requested. Sending a JSON body
            # causes its legacy parser to drop our parameters and return the default XML
            # error envelope with HTTP 200, which then fails JSON decoding downstream.
            response = requests.post(
                FATSECRET_API_URL,
                headers={'Authorization': f'Bearer {token}'},
                data={
                    'method': 'foods.search',
                    'search_expression': query,
                    'format': 'json',
                    'max_results': min(max_results, 50),
                    'page_number': page_number
                },
                timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            logger.error("FatSecret API request failed: %s", exc)
            return FatSecretSearchOutcome(status=HTTP_ERROR,
                                          detail=_safe_detail(exc))

        http_status = response.status_code
        if http_status >= 400:
            return FatSecretSearchOutcome(
                status=HTTP_ERROR, http_status=http_status,
                detail=_safe_detail(response.text))

        if not response.content:
            return FatSecretSearchOutcome(
                status=INVALID_RESPONSE, http_status=http_status, body_kind="empty",
                detail="FatSecret returned an empty body.")

        try:
            data = response.json()
        except ValueError as exc:
            # THE case this whole model exists for: FatSecret answers a rejected request
            # with its XML error envelope and HTTP 200. That is an error, not "no results".
            body = response.text or ""
            kind = "xml" if body.lstrip().startswith("<") else "unreadable"
            code = None
            match = re.search(r"<code>(\d+)</code>", body)
            if match:
                code = match.group(1)
            logger.error("FatSecret foods.search non-JSON body (status=%s, kind=%s): %s",
                         http_status, kind, _safe_detail(body))
            return FatSecretSearchOutcome(
                status=PROVIDER_ERROR if kind == "xml" else PARSE_ERROR,
                http_status=http_status, body_kind=kind, provider_code=code,
                detail=_safe_detail(body) or _safe_detail(exc))

        # FatSecret also returns a JSON error object with HTTP 200.
        if isinstance(data, dict) and "error" in data:
            err = data.get("error") or {}
            return FatSecretSearchOutcome(
                status=PROVIDER_ERROR, http_status=http_status, body_kind="json",
                provider_code=str(err.get("code")) if isinstance(err, dict) else None,
                detail=_safe_detail(err.get("message") if isinstance(err, dict) else err))

        if not isinstance(data, dict) or "foods" not in data:
            return FatSecretSearchOutcome(
                status=INVALID_RESPONSE, http_status=http_status, body_kind="json",
                detail="Response did not contain a `foods` object.")

        foods_data = data.get("foods") or {}
        foods_list = foods_data.get("food", []) if isinstance(foods_data, dict) else []
        if isinstance(foods_list, dict):     # a single result arrives as an object
            foods_list = [foods_list]
        if not foods_list:
            return FatSecretSearchOutcome(
                status=OK_NO_RESULTS, http_status=http_status, body_kind="json",
                detail="FatSecret has no match for this search expression.")

        try:
            foods = [self._parse_food(food) for food in foods_list]
        except Exception as exc:
            logger.error("Error parsing FatSecret response: %s", exc)
            return FatSecretSearchOutcome(
                status=PARSE_ERROR, http_status=http_status, body_kind="json",
                detail=_safe_detail(exc))

        return FatSecretSearchOutcome(status=OK_WITH_RESULTS, foods=foods,
                                      http_status=http_status, body_kind="json")

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
            # See search_foods() for the form-encoded vs JSON rationale —
            # /rest/server.api requires form-encoded parameters; sending JSON
            # makes FatSecret return XML and breaks JSON parsing downstream.
            response = requests.post(
                FATSECRET_API_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                },
                data={
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
