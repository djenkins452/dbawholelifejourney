# ==============================================================================
# File: apps/finance/services/plaid_oauth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Short-lived, session-bound state for an in-flight Plaid OAuth attempt.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Carry one OAuth attempt across the round trip to the bank — and no further.

An OAuth institution takes the user off WLJ entirely, to their bank, and returns them to
`/finance/plaid/oauth/`. Plaid requires the SAME Link token to be reused on return, so
that token has to survive the trip. Where it survives matters:

  * **Not `localStorage`** — the token would outlive the attempt on a shared machine.
  * **Not the database** — a Link token is a short-lived credential, not a record.
  * **Not a log or a URL** — both get copied, forwarded, and indexed.

It lives in the **server-side session**: bound to the authenticated user, single-use,
and expiring in minutes. If any of those bindings fails on return, the attempt is
refused rather than repaired — a redirect flow that trusts whatever comes back is how
you hand someone else's bank connection to the wrong account.
"""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

SESSION_KEY = "finance_plaid_oauth"
#: A bank login should not take half an hour; a Link token lives ~4 hours. This is the
#: tighter of the two on purpose.
ATTEMPT_TTL_MINUTES = 30


class OAuthStateError(Exception):
    """The returning request cannot be matched to a legitimate attempt."""


def begin(request, *, link_token):
    """Record an attempt and return its opaque state id. Never returns the token."""
    state_id = secrets.token_urlsafe(24)
    request.session[SESSION_KEY] = {
        "state_id": state_id,
        "link_token": link_token,
        "user_id": request.user.id,
        "started_at": timezone.now().isoformat(),
        "consumed": False,
    }
    request.session.modified = True
    logger.info("Plaid OAuth attempt started for user %s", request.user.id)
    return state_id


def peek(request):
    """The stored attempt, or None. Does not validate."""
    return request.session.get(SESSION_KEY)


def started_at(request):
    """When the current attempt began — proof of a recent, deliberate act."""
    attempt = peek(request)
    if not attempt:
        return None
    from django.utils.dateparse import parse_datetime
    try:
        return parse_datetime(attempt.get("started_at") or "")
    except (TypeError, ValueError):
        return None


def is_live(request):
    """True while an unconsumed, unexpired attempt belongs to THIS user."""
    try:
        resolve(request)
        return True
    except OAuthStateError:
        return False


def resolve(request):
    """Validate the returning request and hand back the Link token to resume with.

    Raises `OAuthStateError` — never silently repairs — when the attempt is missing,
    expired, already used, or belongs to a different account.
    """
    attempt = request.session.get(SESSION_KEY)
    if not attempt:
        raise OAuthStateError("no_attempt")
    if attempt.get("consumed"):
        raise OAuthStateError("already_used")
    if attempt.get("user_id") != getattr(request.user, "id", None):
        # A different account is holding this session. Refuse, and destroy the state so
        # it cannot be retried against yet another user.
        clear(request)
        logger.warning("Plaid OAuth state rejected: user mismatch")
        raise OAuthStateError("wrong_user")

    from django.utils.dateparse import parse_datetime
    started = parse_datetime(attempt.get("started_at") or "")
    if not started or timezone.now() - started > timedelta(minutes=ATTEMPT_TTL_MINUTES):
        clear(request)
        raise OAuthStateError("expired")

    token = attempt.get("link_token")
    if not token:
        clear(request)
        raise OAuthStateError("no_token")
    return token


def consume(request):
    """Mark the attempt used so a replayed return cannot resume it."""
    attempt = request.session.get(SESSION_KEY)
    if attempt:
        attempt["consumed"] = True
        request.session[SESSION_KEY] = attempt
        request.session.modified = True


def clear(request):
    """Drop the attempt entirely — completion, abandonment, or refusal."""
    if SESSION_KEY in request.session:
        del request.session[SESSION_KEY]
        request.session.modified = True


#: Reason code -> what to tell the person. Honest, and never blaming them for a timeout.
STATE_ERROR_MESSAGES = {
    "no_attempt": ("We could not find your bank connection attempt. It may have been "
                   "started in another window. Please start again."),
    "already_used": ("That bank connection link has already been used. Please start "
                     "again if you need to connect another account."),
    "wrong_user": ("That bank connection belongs to a different account. Please start "
                   "again while signed in as yourself."),
    "expired": ("Your bank connection attempt timed out. Nothing was connected — please "
                "start again."),
    "no_token": "That bank connection attempt is incomplete. Please start again.",
}


def message_for(reason):
    return STATE_ERROR_MESSAGES.get(
        reason, "We could not finish that bank connection. Please start again.")
