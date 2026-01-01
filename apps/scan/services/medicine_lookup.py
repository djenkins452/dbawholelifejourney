# ==============================================================================
# File: medicine_lookup.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Medicine lookup service for OTC drugs and supplements.
#              Uses RxNav API (NIH), FDA OpenData, and OpenAI fallback.
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Medicine Lookup Service - Lookup medicine information for barcodes and names.

This service handles medicine lookups for OTC drugs and supplements using:
1. RxNav API (NIH) - Free, comprehensive drug database
2. FDA OpenData - Official NDC drug database
3. OpenAI fallback for products not in official databases

The service returns structured data that can be used to pre-fill medicine forms.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# API configurations
RXNAV_API_URL = "https://rxnav.nlm.nih.gov/REST"
FDA_API_URL = "https://api.fda.gov/drug"
API_TIMEOUT = 10  # seconds

# Cache TTL for medicine lookups (24 hours)
MEDICINE_CACHE_TTL = 86400


@dataclass
class MedicineResult:
    """Result of a medicine lookup."""
    query: str  # barcode or drug name
    found: bool
    source: str  # 'rxnav', 'fda', 'ai', 'not_found'
    medicine_name: str = ''
    generic_name: str = ''
    brand_name: str = ''
    dosage_form: str = ''  # tablet, capsule, liquid, etc.
    strength: str = ''  # e.g., "500mg", "10mg/5ml"
    manufacturer: str = ''
    purpose: str = ''  # What it's used for
    route: str = ''  # oral, topical, etc.
    ndc_code: str = ''  # National Drug Code
    rxcui: str = ''  # RxNorm Concept Unique Identifier
    warnings: str = ''
    confidence: float = 0.0
    error: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary for JSON response."""
        return {
            'query': self.query,
            'found': self.found,
            'source': self.source,
            'medicine_name': self.medicine_name,
            'generic_name': self.generic_name,
            'brand_name': self.brand_name,
            'dosage_form': self.dosage_form,
            'strength': self.strength,
            'manufacturer': self.manufacturer,
            'purpose': self.purpose,
            'route': self.route,
            'ndc_code': self.ndc_code,
            'rxcui': self.rxcui,
            'warnings': self.warnings,
            'confidence': self.confidence,
            'error': self.error,
        }


# AI prompt for medicine lookup
MEDICINE_LOOKUP_PROMPT = """You are a pharmaceutical database assistant. Given a product barcode (UPC/NDC) or medicine name, identify the medicine and return its information.

IMPORTANT RULES:
1. Only return information for medicines you are confident about
2. Use your knowledge of OTC drugs, supplements, and common medications
3. If you don't recognize the product, say so
4. Include common use cases (purpose)
5. Be accurate about dosage forms and strengths

RESPONSE FORMAT (strict JSON):
{{
  "found": true,
  "medicine_name": "Ibuprofen Tablets",
  "generic_name": "Ibuprofen",
  "brand_name": "Advil",
  "dosage_form": "Tablet",
  "strength": "200mg",
  "manufacturer": "Pfizer Consumer Healthcare",
  "purpose": "Pain reliever and fever reducer",
  "route": "Oral",
  "warnings": "Do not take for more than 10 days unless directed by a doctor",
  "confidence": 0.95
}}

If you don't recognize the product:
{{
  "found": false,
  "medicine_name": "",
  "confidence": 0.0
}}

The barcode/name to look up is: {query}

Respond ONLY with valid JSON. No markdown, no explanation text."""


class MedicineLookupService:
    """
    Service for looking up medicine barcodes and names.

    Usage:
        from apps.scan.services import medicine_lookup_service
        result = medicine_lookup_service.lookup_by_barcode(barcode)
        result = medicine_lookup_service.lookup_by_name(drug_name)
    """

    def __init__(self):
        self.client = None
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.timeout = getattr(settings, 'MEDICINE_LOOKUP_TIMEOUT_SECONDS', 15)
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

    def lookup_by_barcode(self, barcode: str, use_ai: bool = True) -> MedicineResult:
        """
        Look up a medicine by barcode/NDC code.

        Lookup order:
        1. Memory cache (fastest)
        2. FDA OpenData NDC lookup
        3. OpenAI fallback (if enabled)

        Args:
            barcode: The product barcode or NDC code
            use_ai: Whether to use AI for unknown products (default True)

        Returns:
            MedicineResult with medicine information or not_found
        """
        # Clean the barcode
        barcode = self._clean_barcode(barcode)

        if not barcode:
            return MedicineResult(
                query='',
                found=False,
                source='not_found',
                error='Invalid barcode'
            )

        # Step 1: Check cache
        cache_key = f"medicine_barcode_{barcode}"
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Medicine barcode {barcode} found in cache")
            return MedicineResult(**cached_result)

        # Step 2: Try FDA OpenData for NDC lookup
        fda_result = self._lookup_fda_ndc(barcode)
        if fda_result and fda_result.found:
            logger.info(f"Medicine barcode {barcode} found in FDA database")
            cache.set(cache_key, fda_result.to_dict(), timeout=MEDICINE_CACHE_TTL)
            return fda_result

        # Step 3: Try AI lookup if enabled
        if use_ai and self.is_available:
            ai_result = self._lookup_ai(barcode)
            if ai_result.found:
                logger.info(f"Medicine barcode {barcode} found via AI lookup")
                cache.set(cache_key, ai_result.to_dict(), timeout=MEDICINE_CACHE_TTL)
                return ai_result

        # Not found
        logger.info(f"Medicine barcode {barcode} not found")
        return MedicineResult(
            query=barcode,
            found=False,
            source='not_found'
        )

    def lookup_by_name(self, drug_name: str, use_ai: bool = True) -> MedicineResult:
        """
        Look up a medicine by name.

        Lookup order:
        1. Memory cache (fastest)
        2. RxNav API (NIH drug database)
        3. OpenAI fallback (if enabled)

        Args:
            drug_name: The medicine name (brand or generic)
            use_ai: Whether to use AI for unknown products (default True)

        Returns:
            MedicineResult with medicine information or not_found
        """
        if not drug_name or not drug_name.strip():
            return MedicineResult(
                query='',
                found=False,
                source='not_found',
                error='No drug name provided'
            )

        drug_name = drug_name.strip()

        # Step 1: Check cache
        cache_key = f"medicine_name_{drug_name.lower().replace(' ', '_')}"
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Medicine name '{drug_name}' found in cache")
            return MedicineResult(**cached_result)

        # Step 2: Try RxNav API
        rxnav_result = self._lookup_rxnav(drug_name)
        if rxnav_result and rxnav_result.found:
            logger.info(f"Medicine name '{drug_name}' found in RxNav")
            cache.set(cache_key, rxnav_result.to_dict(), timeout=MEDICINE_CACHE_TTL)
            return rxnav_result

        # Step 3: Try AI lookup if enabled
        if use_ai and self.is_available:
            ai_result = self._lookup_ai(drug_name)
            if ai_result.found:
                logger.info(f"Medicine name '{drug_name}' found via AI lookup")
                cache.set(cache_key, ai_result.to_dict(), timeout=MEDICINE_CACHE_TTL)
                return ai_result

        # Not found
        logger.info(f"Medicine name '{drug_name}' not found")
        return MedicineResult(
            query=drug_name,
            found=False,
            source='not_found'
        )

    def _clean_barcode(self, barcode: str) -> str:
        """Clean and validate a barcode/NDC string."""
        if not barcode:
            return ''

        # Remove whitespace
        barcode = barcode.strip()

        # Remove dashes (NDC codes often have dashes: 12345-6789-01)
        barcode_digits = ''.join(c for c in barcode if c.isdigit())

        # NDC codes are typically 10-11 digits, UPCs are 12
        if len(barcode_digits) < 8 or len(barcode_digits) > 14:
            return ''

        return barcode_digits

    def _lookup_fda_ndc(self, barcode: str) -> Optional[MedicineResult]:
        """
        Look up barcode in FDA OpenData NDC database.

        FDA OpenData provides official drug labeling information.
        API docs: https://open.fda.gov/apis/drug/ndc/
        """
        try:
            # Try to format as NDC (5-4-2 or 5-3-2 format)
            # UPC barcodes sometimes have NDC embedded
            ndc_formats = [
                barcode,  # As-is
                f"{barcode[:5]}-{barcode[5:9]}-{barcode[9:11]}" if len(barcode) == 11 else None,
                f"{barcode[:5]}-{barcode[5:8]}-{barcode[8:10]}" if len(barcode) == 10 else None,
            ]

            for ndc in ndc_formats:
                if not ndc:
                    continue

                url = f"{FDA_API_URL}/ndc.json?search=product_ndc:\"{ndc}\"&limit=1"

                response = requests.get(url, timeout=API_TIMEOUT)

                if response.status_code == 404:
                    continue

                if response.status_code != 200:
                    logger.warning(f"FDA API error: {response.status_code}")
                    continue

                data = response.json()

                if 'results' not in data or not data['results']:
                    continue

                result = data['results'][0]

                # Extract product information
                brand_name = result.get('brand_name', '')
                generic_name = result.get('generic_name', '')
                medicine_name = brand_name or generic_name

                if not medicine_name:
                    continue

                # Get dosage form and route
                dosage_form = result.get('dosage_form', '')
                route = ', '.join(result.get('route', []))

                # Get strength from active ingredients
                strength = ''
                active_ingredients = result.get('active_ingredients', [])
                if active_ingredients:
                    strengths = [f"{ai.get('strength', '')}" for ai in active_ingredients]
                    strength = ', '.join(s for s in strengths if s)

                # Get manufacturer
                manufacturer = result.get('labeler_name', '')

                return MedicineResult(
                    query=barcode,
                    found=True,
                    source='fda',
                    medicine_name=medicine_name,
                    generic_name=generic_name,
                    brand_name=brand_name,
                    dosage_form=dosage_form,
                    strength=strength,
                    manufacturer=manufacturer,
                    route=route,
                    ndc_code=ndc,
                    confidence=0.95
                )

            return None

        except requests.Timeout:
            logger.warning(f"FDA API timeout for barcode {barcode}")
            return None
        except requests.RequestException as e:
            logger.error(f"FDA API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"FDA lookup error for barcode {barcode}: {e}")
            return None

    def _lookup_rxnav(self, drug_name: str) -> Optional[MedicineResult]:
        """
        Look up drug name in RxNav API.

        RxNav is the NIH's drug terminology database.
        API docs: https://lhncbc.nlm.nih.gov/RxNav/APIs/
        """
        try:
            # First, search for the drug name to get RXCUI
            search_url = f"{RXNAV_API_URL}/rxcui.json?name={requests.utils.quote(drug_name)}&search=1"

            response = requests.get(search_url, timeout=API_TIMEOUT)

            if response.status_code != 200:
                logger.warning(f"RxNav API error: {response.status_code}")
                return None

            data = response.json()

            # Get RXCUI from response
            rxcui = None
            id_group = data.get('idGroup', {})
            rxnorm_id = id_group.get('rxnormId', [])
            if rxnorm_id:
                rxcui = rxnorm_id[0]
            else:
                # Try approximate match
                approx_url = f"{RXNAV_API_URL}/approximateTerm.json?term={requests.utils.quote(drug_name)}&maxEntries=1"
                approx_response = requests.get(approx_url, timeout=API_TIMEOUT)
                if approx_response.status_code == 200:
                    approx_data = approx_response.json()
                    candidates = approx_data.get('approximateGroup', {}).get('candidate', [])
                    if candidates:
                        rxcui = candidates[0].get('rxcui')

            if not rxcui:
                return None

            # Get drug properties using RXCUI
            props_url = f"{RXNAV_API_URL}/rxcui/{rxcui}/properties.json"
            props_response = requests.get(props_url, timeout=API_TIMEOUT)

            if props_response.status_code != 200:
                return None

            props_data = props_response.json()
            properties = props_data.get('properties', {})

            medicine_name = properties.get('name', drug_name)
            synonym = properties.get('synonym', '')

            # Try to get more details about the drug class/purpose
            purpose = ''
            try:
                class_url = f"{RXNAV_API_URL}/rxclass/class/byRxcui.json?rxcui={rxcui}"
                class_response = requests.get(class_url, timeout=API_TIMEOUT)
                if class_response.status_code == 200:
                    class_data = class_response.json()
                    class_concepts = class_data.get('rxclassDrugInfoList', {}).get('rxclassDrugInfo', [])
                    if class_concepts:
                        # Get first drug class as purpose
                        purpose = class_concepts[0].get('rxclassMinConceptItem', {}).get('className', '')
            except Exception:
                pass  # Purpose is optional

            # Parse strength and form from name if present
            strength = ''
            dosage_form = ''
            name_parts = medicine_name.split()
            for part in name_parts:
                # Check for strength patterns like "500mg", "10mg/5ml"
                if re.match(r'\d+\.?\d*\s*(mg|mcg|g|ml|mg/ml|%)', part, re.IGNORECASE):
                    strength = part
                # Check for dosage forms
                if part.lower() in ['tablet', 'tablets', 'capsule', 'capsules', 'liquid', 'solution', 'cream', 'gel', 'ointment', 'patch', 'injection']:
                    dosage_form = part.title()

            return MedicineResult(
                query=drug_name,
                found=True,
                source='rxnav',
                medicine_name=medicine_name,
                generic_name=medicine_name if not synonym else synonym,
                brand_name=synonym if synonym else '',
                dosage_form=dosage_form,
                strength=strength,
                purpose=purpose,
                rxcui=rxcui,
                confidence=0.90
            )

        except requests.Timeout:
            logger.warning(f"RxNav API timeout for drug '{drug_name}'")
            return None
        except requests.RequestException as e:
            logger.error(f"RxNav API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"RxNav lookup error for drug '{drug_name}': {e}")
            return None

    def _lookup_ai(self, query: str) -> MedicineResult:
        """Look up medicine using OpenAI."""
        if not self.is_available:
            return MedicineResult(
                query=query,
                found=False,
                source='not_found',
                error='AI service not available'
            )

        try:
            prompt = MEDICINE_LOOKUP_PROMPT.replace('{query}', query)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a pharmaceutical database assistant. Respond only with valid JSON."
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
                return MedicineResult(
                    query=query,
                    found=True,
                    source='ai',
                    medicine_name=data.get('medicine_name', ''),
                    generic_name=data.get('generic_name', ''),
                    brand_name=data.get('brand_name', ''),
                    dosage_form=data.get('dosage_form', ''),
                    strength=data.get('strength', ''),
                    manufacturer=data.get('manufacturer', ''),
                    purpose=data.get('purpose', ''),
                    route=data.get('route', ''),
                    warnings=data.get('warnings', ''),
                    confidence=data.get('confidence', 0.8)
                )
            else:
                return MedicineResult(
                    query=query,
                    found=False,
                    source='not_found'
                )

        except json.JSONDecodeError as e:
            logger.error(f"AI medicine lookup JSON parse error: {e}")
            return MedicineResult(
                query=query,
                found=False,
                source='not_found',
                error='Failed to parse AI response'
            )

        except Exception as e:
            logger.error(f"AI medicine lookup error for {query}: {e}")
            return MedicineResult(
                query=query,
                found=False,
                source='not_found',
                error=str(e)
            )


# Singleton instance
medicine_lookup_service = MedicineLookupService()
