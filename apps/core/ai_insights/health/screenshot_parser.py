# ==============================================================================
# File: screenshot_parser.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Structured health data extraction from screenshots via Vision API.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Health Screenshot Parser — Extracts structured health data from screenshots.

Uses a focused Vision API prompt to convert health app screenshots
(Apple Health, Fitbit, Garmin, etc.) into normalized JSON with
minute-based values for PIE analysis rules.

Supported screenshot types:
  - sleep: Sleep duration, stages (REM/deep/core/awake)
  - heart_rate: Resting, average, max HR readings
  - blood_pressure: Systolic/diastolic readings
  - glucose: Blood sugar readings
  - body_composition: Weight, body fat, muscle mass
  - workout: Exercise summary data
  - unknown: Not a recognized health screenshot
"""

import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Vision API Prompt ────────────────────────────────────────────────

HEALTH_SCREENSHOT_PROMPT = """You are a health data extraction system for Whole Life Journey.

Analyze this screenshot from a health/fitness app (Apple Health, Fitbit, Garmin, Samsung Health, Oura, WHOOP, etc.) and extract structured data.

STEP 1: Determine the screenshot_type from: sleep, heart_rate, blood_pressure, glucose, body_composition, workout, unknown.
If this is NOT a health/fitness screenshot, return {"screenshot_type": "unknown"}.

STEP 2: Extract ALL visible numbers and convert time values to MINUTES.
- "6h 35m" → 395 minutes
- "1h 27m" → 87 minutes
- "45m" → 45 minutes
- "7:22" (as duration) → 442 minutes

STEP 3: Return ONLY valid JSON. No markdown, no explanation.

For SLEEP screenshots, return this schema:
{
  "screenshot_type": "sleep",
  "sleep_summary": {
    "average_sleep_minutes": <int, total sleep time in minutes>,
    "average_rem_minutes": <int or null>,
    "average_core_minutes": <int or null, light/core sleep>,
    "average_deep_minutes": <int or null>,
    "average_awake_minutes": <int or null>
  },
  "recent_sleep": {
    "date": "<YYYY-MM-DD or null>",
    "total_sleep_minutes": <int>,
    "rem_minutes": <int or null>,
    "core_minutes": <int or null>,
    "deep_minutes": <int or null>,
    "awake_minutes": <int or null>
  },
  "time_period": "<e.g., '7 days', '1 month', 'last night'>",
  "raw_text": "<transcribe ALL visible text and numbers>"
}

For HEART_RATE screenshots:
{
  "screenshot_type": "heart_rate",
  "heart_rate": {
    "resting_bpm": <int or null>,
    "average_bpm": <int or null>,
    "max_bpm": <int or null>,
    "min_bpm": <int or null>
  },
  "time_period": "<e.g., '7 days', 'today'>",
  "raw_text": "<ALL visible text>"
}

For BLOOD_PRESSURE screenshots:
{
  "screenshot_type": "blood_pressure",
  "blood_pressure": {
    "systolic": <int>,
    "diastolic": <int>,
    "pulse": <int or null>
  },
  "time_period": "<e.g., 'latest reading'>",
  "raw_text": "<ALL visible text>"
}

For GLUCOSE screenshots:
{
  "screenshot_type": "glucose",
  "glucose": {
    "value_mg_dl": <int or null>,
    "average_mg_dl": <int or null>,
    "fasting": <bool or null>,
    "time_in_range_pct": <int or null>
  },
  "time_period": "<e.g., '14 days'>",
  "raw_text": "<ALL visible text>"
}

For BODY_COMPOSITION screenshots:
{
  "screenshot_type": "body_composition",
  "body_composition": {
    "weight_lbs": <float or null>,
    "weight_kg": <float or null>,
    "body_fat_pct": <float or null>,
    "muscle_mass_lbs": <float or null>,
    "bmi": <float or null>
  },
  "raw_text": "<ALL visible text>"
}

For WORKOUT screenshots:
{
  "screenshot_type": "workout",
  "workout": {
    "type": "<e.g., 'strength', 'running', 'cycling'>",
    "duration_minutes": <int or null>,
    "calories_burned": <int or null>,
    "distance_miles": <float or null>,
    "heart_rate_avg": <int or null>
  },
  "raw_text": "<ALL visible text>"
}

CRITICAL RULES:
- ALL time durations MUST be in minutes (integers)
- Use null for values not visible in the screenshot
- Do NOT invent or estimate values — only extract what is visible
- Return raw JSON only — no markdown fences, no explanation"""


# ── Parser Service ───────────────────────────────────────────────────

_client = None


def _get_client():
    """Lazy-init OpenAI client."""
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def parse_health_screenshot(image_base64, mime_type='image/jpeg'):
    """
    Parse a health screenshot into structured data.

    Args:
        image_base64: Base64-encoded image data (no data URI prefix).
        mime_type: MIME type of the image.

    Returns:
        Dict with structured health data, or None if:
        - Not a health screenshot (screenshot_type == 'unknown')
        - Parsing fails
        - Vision API unavailable
    """
    if not getattr(settings, 'OPENAI_API_KEY', None):
        logger.warning("HEALTH_SCREENSHOT_PARSER: Vision API not available")
        return None

    model = getattr(settings, 'OPENAI_VISION_MODEL', 'gpt-4o')
    media_type = mime_type or 'image/jpeg'
    data_uri = f"data:{media_type};base64,{image_base64}"

    start = time.time()

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": HEALTH_SCREENSHOT_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract structured health data from this screenshot.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_uri,
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=1000,
            temperature=0.0,
        )

        elapsed_ms = int((time.time() - start) * 1000)
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            if raw.endswith('```'):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)

        screenshot_type = parsed.get('screenshot_type', 'unknown')
        if screenshot_type == 'unknown':
            logger.info(
                "HEALTH_SCREENSHOT_PARSER: Not a health screenshot (%dms)",
                elapsed_ms,
            )
            return None

        logger.info(
            "HEALTH_SCREENSHOT_PARSER: Extracted %s data (%dms, %d/%d tokens)",
            screenshot_type,
            elapsed_ms,
            response.usage.prompt_tokens if response.usage else 0,
            response.usage.completion_tokens if response.usage else 0,
        )

        return parsed

    except json.JSONDecodeError as e:
        logger.warning(
            "HEALTH_SCREENSHOT_PARSER: JSON parse error: %s (raw=%s)",
            e, raw[:200] if 'raw' in dir() else 'N/A',
        )
        return None

    except Exception:
        logger.warning(
            "HEALTH_SCREENSHOT_PARSER: Vision API call failed (%dms)",
            int((time.time() - start) * 1000),
            exc_info=True,
        )
        return None
