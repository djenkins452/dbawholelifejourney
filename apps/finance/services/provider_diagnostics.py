# ==============================================================================
# File: apps/finance/services/provider_diagnostics.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Extract only the SAFE fields from a provider error.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Turn a provider exception into something safe to log and to show an operator.

A Plaid SDK exception carries a full HTTP response — headers and body. Logging it whole
is how bank data and identifiers end up in a log aggregator. This extracts a strict
allowlist: **error type, error code, and request id**. Those are exactly what Plaid
support asks for, and none of them is sensitive.

Everything else — request bodies, account data, tokens, institution details, display
messages that may quote a balance — is discarded, not truncated.
"""
from __future__ import annotations

import json
import re

#: The only keys ever surfaced from a provider error body.
SAFE_KEYS = ("error_type", "error_code", "request_id", "causes")
MAX_VALUE_LENGTH = 64

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{0,64}$")


def _clean(value):
    """Provider codes are short machine tokens. Anything else is dropped, not trimmed."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_VALUE_LENGTH or not _SAFE_VALUE.match(value):
        return None
    return value


def safe_provider_diagnostics(exc) -> dict:
    """`{"error_type": ..., "error_code": ..., "request_id": ...}` — never more."""
    diagnostics = {"exception": type(exc).__name__}

    for key in SAFE_KEYS:
        cleaned = _clean(getattr(exc, key, None))
        if cleaned:
            diagnostics[key] = cleaned

    body = getattr(exc, "body", None)
    if isinstance(body, (bytes, bytearray)):
        try:
            body = body.decode("utf-8", "ignore")
        except Exception:
            body = None
    if isinstance(body, str) and body.strip().startswith("{"):
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            for key in SAFE_KEYS:
                if key in diagnostics:
                    continue
                cleaned = _clean(parsed.get(key))
                if cleaned:
                    diagnostics[key] = cleaned

    status = getattr(exc, "status", None)
    if isinstance(status, int):
        diagnostics["status"] = status
    return diagnostics
