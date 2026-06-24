# ==============================================================================
# File: apps/ai/cos_services/serialization.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Shared JSON-safety helpers for the ChatGPT CoS service layer
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Shared serialization helpers for the ChatGPT CoS internal services.

Single home for JSON-safety so StandingContextService, DomainStateService, and
future services share one coercion path (no duplicate pipelines). CoS service
output is consumed by an external LLM, so it must serialize cleanly — but it must
NEVER raise on the always-loaded path, so unknown objects degrade to their string
form rather than crashing. Truth is preserved (nothing silently dropped); only
the representation is coerced.
"""

import json


def jsonsafe(value):
    """
    Best-effort coercion of `value` to a JSON-serializable form.

    Fast path: if it already serializes, return as-is. Otherwise recurse into
    dicts/lists, ISO-format datetimes, and str() anything else.
    """
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(k): jsonsafe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonsafe(v) for v in value]
    if hasattr(value, "isoformat"):  # datetime / date
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def cap(value, limit):
    """Cap a list-valued field to `limit`; pass through non-lists unchanged."""
    if isinstance(value, (list, tuple)):
        return list(value)[:limit]
    return value
