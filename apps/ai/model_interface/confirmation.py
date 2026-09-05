# ==============================================================================
# File: apps/ai/model_interface/confirmation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bound confirmation transactions (Blocker 1 — no confused deputy)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Bound confirmation transactions for the model-interface action path.

HARDENING (Slice 7.2 — Blocker 1). Each confirmation is its own bound transaction with an
identity, so `resolve` executes a SPECIFIC confirmation by id — never "whatever is stored."

RICH CONFIRMATION (docs/WLJ_RICH_CONFIRMATION_ARCHITECTURE.md). The bound record now also
carries the presentation-independent `view` (title/summary/preview/actions) and is
CONVERSATION-BOUND, so the SAME record drives the on-screen card, the deterministic button
endpoint, and the typed pre-parser. Resolving leaves a short-lived tombstone (status
resolved/cancelled) so a replay is reported as *already resolved* rather than *expired*.

    { id, action, params, summary, view, conversation_id, source_artifact_id, status, choice }

Storage is a dedicated per-user cache dict, isolated from the legacy `pending_intent_*` key.
"""

import logging
import uuid

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_TTL = 300          # seconds an open confirmation stays resolvable
_MAX_OPEN = 8       # cap concurrent OPEN records per user


def _model():
    from apps.ai.models import ActionConfirmation
    return ActionConfirmation


def _key(user_id):
    return f"wlj:mi:confirm:{user_id}"


def _uid(user):
    return getattr(user, "id", None)


def _bust(user_id):
    """The cache is an ACCELERATOR ONLY. It is invalidated on every write and is never
    consulted to decide whether an action may execute."""
    try:
        cache.delete(_key(user_id))
    except Exception:  # pragma: no cover - cache failure must never affect safety
        pass


def _as_dict(rec):
    """The legacy record shape callers already consume — unchanged public contract."""
    if rec is None:
        return None
    return {"id": rec.id, "action": rec.action, "params": dict(rec.params or {}),
            "summary": rec.summary, "view": rec.view or None,
            "authorization_line": rec.authorization_line,
            "conversation_id": rec.conversation_id,
            "source_artifact_id": rec.source_artifact_id or None,
            "status": rec.status, "choice": rec.choice or None,
            "result": dict(rec.result or {})}


def create(user, action, params, summary, *, view=None, conversation_id=None,
           source_artifact_id=None):
    """Create a bound confirmation; return {confirmation_id, summary, expires_in, view}.

    FAILS CLOSED: without a deterministic `view` (which carries the authorization line
    derived from the bound action+params) there is nothing honest to show the user, so
    no confirmation is minted and the caller must refuse the write.
    """
    uid = _uid(user)
    if uid is None:
        return None
    from apps.ai.confirmation_contract import authorization_line
    auth = (view or {}).get("authorization") if isinstance(view, dict) else None
    auth = auth or authorization_line(action, params)
    if not auth:
        logger.warning("mi.confirmation: refusing to mint an unpresentable confirmation "
                       "action=%s user=%s", action, uid)
        return None

    M = _model()
    cid = uuid.uuid4().hex
    now = timezone.now()
    try:
        with transaction.atomic():
            # Bound the number of OPEN records: cancel the oldest beyond the cap.
            open_ids = list(M.objects.filter(user_id=uid, status=M.STATUS_PENDING)
                            .order_by("-created_at").values_list("id", flat=True))
            if len(open_ids) >= _MAX_OPEN:
                M.objects.filter(id__in=open_ids[_MAX_OPEN - 1:]).update(
                    status=M.STATUS_CANCELLED, resolved_at=now, choice="superseded")
            M.objects.create(
                id=cid, user_id=uid, action=action, params=dict(params or {}),
                summary=summary or "", authorization_line=auth, view=view or None,
                conversation_id=(int(conversation_id) if conversation_id else None),
                source_artifact_id=source_artifact_id or "",
                status=M.STATUS_PENDING,
                expires_at=now + timezone.timedelta(seconds=_TTL))
    except Exception:
        logger.warning("mi.confirmation: create failed action=%s user=%s", action, uid,
                       exc_info=True)
        return None
    _bust(uid)
    return {"confirmation_id": cid, "summary": summary, "expires_in": _TTL,
            "view": view or None, "authorization": auth}


def get(user, cid):
    """Return the PENDING, UNEXPIRED confirmation for this user+id, or None."""
    if not cid:
        return None
    M = _model()
    rec = M.objects.filter(id=cid, user_id=_uid(user),
                           status=M.STATUS_PENDING).first()
    if rec is None or rec.is_expired:
        return None
    return _as_dict(rec)


def peek(user, cid):
    """The record regardless of status — lets the caller distinguish 'already resolved'
    from 'expired' from 'never existed'."""
    if not cid:
        return None
    return _as_dict(_model().objects.filter(id=cid, user_id=_uid(user)).first())


def claim(user, cid):
    """ATOMIC COMPARE-AND-SWAP: `pending → executing`. THE exactly-once gate.

    Returns the bound record to the SINGLE caller that wins, and None to everyone else
    — a second confirm, a concurrent request, a retry after a cache outage. Because the
    transition is one conditional UPDATE evaluated by the database, no two callers can
    both observe `pending`; this is what the previous read-then-write cache `consume()`
    could not guarantee.
    """
    if not cid:
        return None
    M = _model()
    now = timezone.now()
    won = (M.objects
           .filter(id=cid, user_id=_uid(user), status=M.STATUS_PENDING,
                   expires_at__gt=now)
           .update(status=M.STATUS_EXECUTING, claimed_at=now))
    if won != 1:
        return None
    _bust(_uid(user))
    return _as_dict(M.objects.filter(id=cid).first())


def finalize(user, cid, *, status="resolved", choice=None, result=None):
    """Record the outcome of the single claimed execution so a retry can REPLAY it."""
    M = _model()
    try:
        M.objects.filter(id=cid, user_id=_uid(user)).update(
            status=status, choice=(choice or ""), result=(result or {}),
            resolved_at=timezone.now())
    except Exception:  # pragma: no cover
        logger.warning("mi.confirmation: finalize failed cid=%s", cid, exc_info=True)
    _bust(_uid(user))


def consume(user, cid, *, status="resolved", choice=None):
    """Backwards-compatible terminal marker (cancel paths, legacy callers).

    NOTE: this is NOT the exactly-once gate any more — `claim()` is. Marking a record
    terminal after the fact could never prevent a duplicate, which is precisely how one
    authorized write executed twice in production.
    """
    finalize(user, cid, status=status, choice=choice)


def list_open(user):
    """Open confirmations as [{confirmation_id, summary}] — surfaced in standing context."""
    M = _model()
    rows = (M.objects.filter(user_id=_uid(user), status=M.STATUS_PENDING,
                             expires_at__gt=timezone.now())
            .order_by("created_at").values("id", "summary", "authorization_line"))
    return [{"confirmation_id": r["id"],
             "summary": r["authorization_line"] or r["summary"] or ""} for r in rows]


def bind_conversation(user, conversation_id):
    """Bind this turn's freshly-minted confirmations to the conversation and return the
    client payload for the newest one (or None).

    THE NEWEST IS NOT THE ONLY ONE. A request naming two things mints two confirmations,
    and only one of them was ever shown — so only one could be authorized. On 2026-09-05
    "log the sandwich and the mac and cheese" created both at 20:39:21 and 20:39:22; the
    user saw the mac, confirmed it, and the sandwich sat pending until it expired while
    the assistant reported the whole request done.

    The payload now carries `also_pending` — the other open confirmations, by id and
    summary. WLJ states that authorization is incomplete; whether to present them one at a
    time, together, or differently is the model's and the client's call. A partial
    authorization can no longer be invisible.
    """
    if not conversation_id:
        return None
    M = _model()
    uid = _uid(user)
    cid_int = int(conversation_id)
    M.objects.filter(user_id=uid, status=M.STATUS_PENDING,
                     conversation_id__isnull=True).update(conversation_id=cid_int)
    _bust(uid)
    open_rows = list(M.objects.filter(user_id=uid, status=M.STATUS_PENDING,
                                      conversation_id=cid_int,
                                      expires_at__gt=timezone.now())
                     .order_by("-created_at"))
    if not open_rows:
        return None
    payload = client_view(_as_dict(open_rows[0]))
    others = [{"confirmation_id": r.id,
               "summary": (r.authorization_line or r.summary or "")}
              for r in open_rows[1:]]
    if others and isinstance(payload, dict):
        payload["also_pending"] = others
    return payload


def open_for_conversation(user, conversation_id):
    """Pending records bound to THIS conversation, newest first — used by the
    deterministic typed pre-parser."""
    M = _model()
    qs = M.objects.filter(user_id=_uid(user), status=M.STATUS_PENDING,
                          expires_at__gt=timezone.now())
    if conversation_id:
        qs = qs.filter(conversation_id=int(conversation_id))
    return [_as_dict(r) for r in qs.order_by("-created_at")]


def client_view(rec, *, status=None):
    """Shape a stored record into the client confirmation payload (id + view + status)."""
    if not rec:
        return None
    view = rec.get("view") or {}
    return {
        "confirmation_id": rec.get("id"),
        "status": status or rec.get("status", "pending"),
        "expires_in": _TTL,
        "title": view.get("title", ""),
        # The deterministic authorization line travels with the card: what the user sees
        # is rendered from the bound payload, never from model prose.
        "authorization": view.get("authorization") or rec.get("authorization_line", ""),
        "summary": view.get("summary", ""),
        "preview": view.get("preview", []),
        "actions": view.get("actions", {}),
    }


def summarize(action, params):
    """A short, deterministic human summary of what will happen (for the user + audit)."""
    from apps.ai.confirmation_contract import authorization_line
    line = authorization_line(action, params)
    if line:
        return line
    params = params or {}
    if params:
        bits = ", ".join(f"{k}={v}" for k, v in list(params.items())[:6])
        return f"{action} ({bits})"
    return action
