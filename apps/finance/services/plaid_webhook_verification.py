# ==============================================================================
# File: apps/finance/services/plaid_webhook_verification.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Full cryptographic verification of Plaid webhooks.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Prove a webhook really came from Plaid before acting on it.

Plaid signs each webhook with an **ES256** JWT in the `Plaid-Verification` header. The
key is fetched by `kid` from `/webhook_verification_key/get`. Verification therefore
requires all of:

  1. a well-formed JWT whose header declares **ES256** and a `kid` (no `alg: none`, no
     algorithm substitution — the allowed list is pinned);
  2. a signature that verifies against the JWK Plaid returns for that `kid`;
  3. an `iat` inside a short window (replayed-later webhooks are rejected);
  4. a `request_body_sha256` matching the SHA-256 of the EXACT raw body;
  5. a body hash not already seen inside the replay window.

**Fail closed everywhere.** Missing configuration, an unknown `kid`, an unreachable key
service, a malformed token — every one of them REJECTS. The previous implementation
decoded with `verify_signature: False` and accepted anything whose body hash and `iat`
looked plausible, both of which a forger controls; and it returned True outright when
Plaid was unconfigured.

Nothing sensitive is logged: no header, no token, no signature, no body — only the
verification outcome and the reason code.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Only ES256. Pinning the algorithm is what stops `alg: none` and HS256-substitution.
ALLOWED_ALGORITHMS = ["ES256"]
#: Plaid's documented tolerance for webhook age.
MAX_AGE_SECONDS = 300
#: Verification keys are cached, but never indefinitely — Plaid rotates them.
KEY_CACHE_SECONDS = 24 * 60 * 60
KEY_CACHE_PREFIX = "wlj:plaid:webhook_key:"
#: A body hash may be accepted once inside the freshness window.
REPLAY_CACHE_PREFIX = "wlj:plaid:webhook_seen:"

# Reason codes — safe to log and to return; they describe the failure, never the payload.
REASON_NOT_CONFIGURED = "plaid_not_configured"
REASON_MISSING_HEADER = "missing_verification_header"
REASON_MALFORMED = "malformed_token"
REASON_BAD_ALGORITHM = "unsupported_algorithm"
REASON_MISSING_KID = "missing_kid"
REASON_UNKNOWN_KEY = "unknown_or_unavailable_key"
REASON_BAD_SIGNATURE = "invalid_signature"
REASON_EXPIRED = "stale_or_future_timestamp"
REASON_BODY_MISMATCH = "body_hash_mismatch"
REASON_REPLAY = "replayed_webhook"
REASON_LIBRARY_MISSING = "verification_library_unavailable"
#: The key service raised. Distinct from UNKNOWN_KEY so a WLJ-side defect is never
#: silently reported as "Plaid gave us a kid we do not recognise".
REASON_KEY_FETCH_ERROR = "key_fetch_error"


class KeyFetchError(Exception):
    """Raised when the key service could not be reached or called correctly."""


class WebhookVerificationResult:
    """Outcome of a verification attempt. `reason` is a code, never payload content."""

    __slots__ = ("verified", "reason")

    def __init__(self, verified: bool, reason: str = ""):
        self.verified = verified
        self.reason = reason

    def __bool__(self):
        return self.verified

    def __repr__(self):
        return f"<WebhookVerification verified={self.verified} reason={self.reason!r}>"


def _reject(reason):
    logger.warning("Plaid webhook rejected: %s", reason)
    return WebhookVerificationResult(False, reason)


def fetch_verification_key(key_id: str):
    """Fetch (and cache) Plaid's JWK for a `kid`. Returns a dict or None.

    Cached for a bounded lifetime so a rotated or revoked key cannot be trusted forever.
    A negative result is NOT cached — an outage must not turn into a day of rejections
    after the service recovers.
    """
    cache_key = f"{KEY_CACHE_PREFIX}{key_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from apps.finance.services.plaid_service import get_plaid_service
        service = get_plaid_service()
        # `is_configured` is a PROPERTY. Calling it raised TypeError on every real
        # webhook, which the broad `except` below turned into an ordinary
        # "unknown key" rejection — so a code defect was indistinguishable from a
        # genuinely unrecognised `kid`. See _FETCH_ERROR below.
        if not service.is_configured:
            return None
        jwk = service.get_webhook_verification_key(key_id)
    except Exception as exc:                       # network, auth, SDK — all fail closed
        # Log the MESSAGE, not just the class name. The class name alone
        # ("TypeError") cost a production diagnosis. Plaid error bodies carry an
        # error_code and request_id, never credentials, so this is safe to log.
        logger.warning("Plaid webhook key fetch failed (%s): %s: %s",
                       key_id[:8] if key_id else "?", type(exc).__name__,
                       str(exc)[:200])
        raise KeyFetchError(str(exc)[:200]) from exc

    if not jwk:
        return None
    cache.set(cache_key, jwk, KEY_CACHE_SECONDS)
    return jwk


def verify_webhook(request, *, key_fetcher=None, now=None):
    """Verify a Plaid webhook request end to end.

    `key_fetcher` is injectable purely so the test suite can exercise every branch
    deterministically — production never needs a real Plaid call to be *rejected*.
    """
    fetch = key_fetcher or fetch_verification_key
    now = now or time.time()

    if not (getattr(settings, "PLAID_CLIENT_ID", "")
            and getattr(settings, "PLAID_SECRET", "")):
        # Fail CLOSED. Unconfigured means we cannot prove authenticity, so we do not act.
        return _reject(REASON_NOT_CONFIGURED)

    token = request.headers.get("Plaid-Verification")
    if not token:
        return _reject(REASON_MISSING_HEADER)

    try:
        import jwt
        from jwt.algorithms import ECAlgorithm
    except ImportError:
        logger.error("PyJWT is unavailable; Plaid webhooks cannot be verified.")
        return _reject(REASON_LIBRARY_MISSING)

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return _reject(REASON_MALFORMED)

    if header.get("alg") not in ALLOWED_ALGORITHMS:
        return _reject(REASON_BAD_ALGORITHM)
    key_id = header.get("kid")
    if not key_id:
        return _reject(REASON_MISSING_KID)

    try:
        jwk = fetch(key_id)
    except KeyFetchError:
        return _reject(REASON_KEY_FETCH_ERROR)
    if not jwk:
        return _reject(REASON_UNKNOWN_KEY)

    try:
        public_key = ECAlgorithm.from_jwk(json.dumps(jwk))
    except Exception:
        return _reject(REASON_UNKNOWN_KEY)

    try:
        claims = jwt.decode(
            token, key=public_key, algorithms=ALLOWED_ALGORITHMS,
            options={"verify_exp": False, "verify_aud": False, "require": ["iat"]},
        )
    except Exception:
        return _reject(REASON_BAD_SIGNATURE)

    issued_at = claims.get("iat")
    if not isinstance(issued_at, (int, float)) or abs(now - issued_at) > MAX_AGE_SECONDS:
        return _reject(REASON_EXPIRED)

    body_hash = hashlib.sha256(request.body or b"").hexdigest()
    if not _constant_time_equal(claims.get("request_body_sha256", ""), body_hash):
        return _reject(REASON_BODY_MISMATCH)

    replay_key = f"{REPLAY_CACHE_PREFIX}{key_id}:{body_hash}:{int(issued_at)}"
    if not cache.add(replay_key, 1, MAX_AGE_SECONDS + 60):
        return _reject(REASON_REPLAY)

    return WebhookVerificationResult(True, "")


def _constant_time_equal(a, b):
    from hmac import compare_digest
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
        return False
    return compare_digest(a, b)
