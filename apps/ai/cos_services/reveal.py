# ==============================================================================
# File: apps/ai/cos_services/reveal.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reveal Target (navigate_to_workspace) — the deterministic resolution half of
#   taking the user to the right WLJ workspace. The certified CoS chooses the TARGET (intent,
#   in words); WLJ resolves it to a concrete URL via the ONE existing destination authority
#   (apps/core/action_router.resolve_route → TeachingDestination, 190 rows) — never a
#   model-invented URL, never a parallel route map. It also owns the target↔current relation:
#   if the resolved workspace IS the page the user is already on, it returns `already_here`
#   (no pointless navigation). The client owns the verb (the existing renderNavigation link).
#   Facts only; never raises.
# ==============================================================================
import logging
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def _same_workspace(current_url, target_url):
    """True if two URLs point at the same workspace page — path-only, trailing-slash- and
    query-insensitive (the current URL may carry ?date=… etc.)."""
    if not current_url or not target_url:
        return False
    def _path(u):
        try:
            return urlsplit(u).path.rstrip("/").lower()
        except Exception:
            return (u or "").rstrip("/").lower()
    return _path(current_url) == _path(target_url)


_REVEAL_LEAF_SEGMENTS = {"new", "create", "add", "log", "edit"}


def _object_in_workspace(object_url, workspace_url):
    """True if the created object's detail URL lives INSIDE the workspace the model is
    revealing — so 'log my workout, show me' opens the specific workout, while 'log my
    workout, show me my weight' still opens the Weight workspace. Deterministic path
    containment (a trailing new/create/add/log/edit leaf on the workspace is ignored)."""
    if not object_url or not workspace_url:
        return False
    def _path(u):
        try:
            return urlsplit(u).path.rstrip("/")
        except Exception:
            return (u or "").rstrip("/")
    o = _path(object_url)
    parts = _path(workspace_url).split("/")
    if parts and parts[-1] in _REVEAL_LEAF_SEGMENTS:
        parts = parts[:-1]
    w = "/".join(parts)
    return bool(w) and (o + "/").startswith(w + "/")


def resolve_reveal(user, target, *, current_url=None, created_reveal=None):
    """Resolve a semantic reveal target ('my weight history', 'yesterday's dashboard',
    'medications') to a workspace URL using the existing destination authority. If an object
    was created/updated THIS TURN (created_reveal) and it lives inside the revealed workspace,
    upgrade the reveal to that SPECIFIC object's detail URL (Object-Level Reveal) — a
    deterministic identity from the action result, never fuzzy resolution. Returns a facts-only
    dict: status ∈ {ok, already_here, not_found} plus url/label (+ object:bool). Never raises."""
    target = (target or "").strip()
    if not target:
        return {"status": "not_found", "message": "Where would you like me to take you?"}
    try:
        from apps.core.action_router import ActionType, resolve_route
        route = resolve_route(text=target)
    except Exception:
        logger.warning("resolve_reveal failed target=%r", target, exc_info=True)
        return {"status": "not_found",
                "message": "I couldn't work out which workspace you mean."}

    url = getattr(route, "destination_url", None)
    label = getattr(route, "destination_label", None) or "Open"
    if not url or getattr(route, "action_type", None) != ActionType.OPEN_WORKFLOW:
        return {"status": "not_found",
                "message": f"I couldn't find a WLJ workspace for “{target}”."}

    is_object = False
    obj_url = (created_reveal or {}).get("url")
    if obj_url and _object_in_workspace(obj_url, url):
        # The thing the user just created IS what they want to see — reveal the object itself.
        url = obj_url
        label = (created_reveal or {}).get("label") or label
        is_object = True

    if _same_workspace(current_url, url):
        # Already on that page — do NOT navigate; let the model answer in place.
        return {"status": "already_here", "url": url, "label": label, "object": is_object}

    return {"status": "ok", "url": url, "label": label, "object": is_object,
            "source": getattr(route, "source", None)}
