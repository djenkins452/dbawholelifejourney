# ==============================================================================
# File: product_lookup.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Product lookup service for general products (electronics, tools,
#              household items). Uses UPC Item DB API and OpenAI fallback.
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Product Lookup Service - Lookup product information for barcodes.

This service handles barcode lookups for general products (electronics, tools,
appliances, household items) in three stages:
1. Query local ProductCache database for known barcodes
2. Query UPC Item DB API (free tier available)
3. Use OpenAI as fallback for products not in UPC database

The service returns structured data that can be used to pre-fill inventory forms.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# UPC Item DB API configuration (free tier: no key required for basic lookups)
UPC_ITEM_DB_API_URL = "https://api.upcitemdb.com/prod/trial/lookup"
UPC_ITEM_DB_TIMEOUT = 10  # seconds

# Cache TTL for product lookups (24 hours)
PRODUCT_CACHE_TTL = 86400


@dataclass
class ProductResult:
    """Result of a product barcode lookup."""
    barcode: str
    found: bool
    source: str  # 'database', 'upcitemdb', 'ai', 'not_found'
    product_name: str = ''
    brand: str = ''
    description: str = ''
    category: str = ''
    model_number: str = ''
    manufacturer: str = ''
    image_url: str = ''
    msrp: Optional[float] = None
    confidence: float = 0.0
    error: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'barcode': self.barcode,
            'found': self.found,
            'source': self.source,
            'product_name': self.product_name,
            'brand': self.brand,
            'description': self.description,
            'category': self.category,
            'model_number': self.model_number,
            'manufacturer': self.manufacturer,
            'image_url': self.image_url,
            'msrp': self.msrp,
            'confidence': self.confidence,
            'error': self.error,
        }


# AI prompt for product barcode lookup
PRODUCT_LOOKUP_PROMPT = """You are a product database assistant. Given a product barcode (UPC/EAN), identify the product and return its information.

IMPORTANT RULES:
1. Only return information for products you are confident about
2. Use your knowledge base of common consumer products (electronics, tools, appliances, household items)
3. If you don't recognize the barcode, say so
4. Focus on product identification, not pricing (prices change frequently)

RESPONSE FORMAT (strict JSON):
{
  "found": true,
  "product_name": "DeWalt 20V MAX Cordless Drill/Driver Kit",
  "brand": "DeWalt",
  "description": "Compact drill/driver with 2 batteries and charger",
  "category": "Power Tools",
  "model_number": "DCD771C2",
  "manufacturer": "Stanley Black & Decker",
  "confidence": 0.95
}

If you don't recognize the barcode:
{
  "found": false,
  "product_name": "",
  "confidence": 0.0
}

The barcode to look up is: {barcode}

Respond ONLY with valid JSON. No markdown, no explanation text."""


class ProductLookupService:
    """
    Service for looking up product barcodes.

    Usage:
        from apps.scan.services import product_lookup_service
        result = product_lookup_service.lookup(barcode_string)
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.timeout = getattr(settings, 'PRODUCT_LOOKUP_TIMEOUT_SECONDS', 15)
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

    def lookup(self, barcode: str, use_ai: bool = True) -> ProductResult:
        """
        Look up a barcode and return product information.

        Lookup order:
        1. Memory cache (fastest)
        2. UPC Item DB API (free tier)
        3. OpenAI fallback (if enabled)

        Args:
            barcode: The product barcode string (UPC, EAN, etc.)
            use_ai: Whether to use AI for unknown barcodes (default True)

        Returns:
            ProductResult with product information or not_found
        """
        # Clean the barcode
        barcode = self._clean_barcode(barcode)

        if not barcode:
            return ProductResult(
                barcode='',
                found=False,
                source='not_found',
                error='Invalid barcode'
            )

        # Step 1: Check cache
        cache_key = f"product_barcode_{barcode}"
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Product barcode {barcode} found in cache")
            return ProductResult(**cached_result)

        # Step 2: Try UPC Item DB API (free tier)
        upc_result = self._lookup_upcitemdb(barcode)
        if upc_result and upc_result.found:
            logger.info(f"Product barcode {barcode} found in UPC Item DB")
            # Cache the result
            cache.set(cache_key, upc_result.to_dict(), timeout=PRODUCT_CACHE_TTL)
            return upc_result

        # Step 3: Try AI lookup if enabled and available
        if use_ai and self.is_available:
            ai_result = self._lookup_ai(barcode)
            if ai_result.found:
                logger.info(f"Product barcode {barcode} found via AI lookup")
                # Cache the result
                cache.set(cache_key, ai_result.to_dict(), timeout=PRODUCT_CACHE_TTL)
                return ai_result

        # Not found anywhere
        logger.info(f"Product barcode {barcode} not found")
        return ProductResult(
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

    def _lookup_upcitemdb(self, barcode: str) -> Optional[ProductResult]:
        """
        Look up barcode in UPC Item DB API.

        UPC Item DB is a free database with millions of products.
        API docs: https://www.upcitemdb.com/wp/docs/main/development/
        """
        try:
            # Use GET request with upc parameter
            url = f"{UPC_ITEM_DB_API_URL}?upc={barcode}"

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'WholeLifeJourney/1.0'
            }

            response = requests.get(url, headers=headers, timeout=UPC_ITEM_DB_TIMEOUT)

            if response.status_code == 429:
                logger.warning("UPC Item DB rate limit exceeded")
                return None

            if response.status_code != 200:
                logger.warning(f"UPC Item DB API error: {response.status_code}")
                return None

            data = response.json()

            # Check if product was found
            if data.get('code') != 'OK' or 'items' not in data or not data['items']:
                logger.debug(f"Barcode {barcode} not found in UPC Item DB")
                return None

            item = data['items'][0]

            # Extract product information
            product_name = item.get('title', '')
            if not product_name:
                return None

            brand = item.get('brand', '')
            description = item.get('description', '')
            category = item.get('category', '')
            model = item.get('model', '')
            manufacturer = item.get('manufacturer', brand)

            # Get first image if available
            images = item.get('images', [])
            image_url = images[0] if images else ''

            # Get MSRP if available
            msrp = None
            offers = item.get('offers', [])
            if offers:
                # Get lowest price as estimate
                prices = [o.get('price') for o in offers if o.get('price')]
                if prices:
                    msrp = min(prices)

            return ProductResult(
                barcode=barcode,
                found=True,
                source='upcitemdb',
                product_name=product_name,
                brand=brand,
                description=description,
                category=category,
                model_number=model,
                manufacturer=manufacturer,
                image_url=image_url,
                msrp=msrp,
                confidence=0.95  # UPC Item DB data is generally reliable
            )

        except requests.Timeout:
            logger.warning(f"UPC Item DB API timeout for barcode {barcode}")
            return None
        except requests.RequestException as e:
            logger.error(f"UPC Item DB API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"UPC Item DB lookup error for barcode {barcode}: {e}")
            return None

    def _lookup_ai(self, barcode: str) -> ProductResult:
        """Look up barcode using OpenAI."""
        if not self.is_available:
            return ProductResult(
                barcode=barcode,
                found=False,
                source='not_found',
                error='AI service not available'
            )

        try:
            prompt = PRODUCT_LOOKUP_PROMPT.replace('{barcode}', barcode)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a product database assistant. Respond only with valid JSON."
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
                return ProductResult(
                    barcode=barcode,
                    found=True,
                    source='ai',
                    product_name=data.get('product_name', ''),
                    brand=data.get('brand', ''),
                    description=data.get('description', ''),
                    category=data.get('category', ''),
                    model_number=data.get('model_number', ''),
                    manufacturer=data.get('manufacturer', ''),
                    confidence=data.get('confidence', 0.8)
                )
            else:
                return ProductResult(
                    barcode=barcode,
                    found=False,
                    source='not_found'
                )

        except json.JSONDecodeError as e:
            logger.error(f"AI product lookup JSON parse error: {e}")
            return ProductResult(
                barcode=barcode,
                found=False,
                source='not_found',
                error='Failed to parse AI response'
            )

        except Exception as e:
            logger.error(f"AI product lookup error for {barcode}: {e}")
            return ProductResult(
                barcode=barcode,
                found=False,
                source='not_found',
                error=str(e)
            )


# Singleton instance
product_lookup_service = ProductLookupService()
