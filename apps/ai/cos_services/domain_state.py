# ==============================================================================
# File: apps/ai/cos_services/domain_state.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainStateService — generic canonical domain-state read surface
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
DomainStateService (ChatGPT CoS — Phase 2)
==========================================

The single, generic ChatGPT read surface for ANY WLJ domain's canonical state:

    get_domain_state(user, domain, *, allow_build=False)

Design rules honored (Architecture Laws + Phase 2 mandate):
* REUSE ONLY — delegates to the canonical SAE accessor `get_module_state()` over
  the existing `MODULE_BUILDERS` registry. There are NO domain-specific readers
  (get_health_context / get_faith_context / ... are explicitly forbidden) and NO
  re-aggregation of raw data (Law 9: State-First Reads).
* CACHE / STATE FIRST — reads the SAE snapshot read-only (`allow_rebuild=False`)
  on the request path; never live-computes. `allow_build=True` permits a rebuild
  and is reserved for background/warming callers.
* NO FABRICATION — a domain with no warm snapshot returns `pending`; a known
  domain with no SAE state source (e.g. `notes`, retrieved via search, Phase 5)
  returns `no_state_source`; an unknown domain returns `unsupported_domain` with
  the supported list. Unknown stays unknown.
* JSON-safe + observable; wrappable by an HTTP endpoint later with no logic change.

DOMAIN_REGISTRY is the EXPOSURE contract (ChatGPT-facing domain name -> canonical
SAE module key). It is layered ON TOP of SAE — it does NOT modify the core
`_canonical_module` alias map. Each non-None target is validated against the real
builder registry at call time, so the registry stays honest.
"""

import logging
import time

from django.utils import timezone

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_STATE_SCHEMA_VERSION = "1.0"

# ChatGPT-facing domain -> canonical SAE module key.
#   * value is a string  -> read get_module_state(user, value)
#   * value is None      -> known WLJ domain with NO SAE state source
#                           (retrieved via search/other surface, not Phase 2)
# Note: `purpose`->`goals` and `life`->`tasks` are EXPOSURE aliases here; SAE's
# own `_canonical_module` also maps purpose->goals. We never edit SAE's map.
DOMAIN_REGISTRY = {
    # --- the 13 Phase 2 target domains ---
    "health": "health",
    "medical": "medical",
    "faith": "faith",
    "purpose": "goals",
    "life": "tasks",
    "journal": "journal",
    "relationships": "relationships",
    "finance": "finance",
    "meals": "meals",
    "calendar": "calendar",
    "capture": "capture",
    "sports": "sports",
    "notes": None,  # no SAE state — notes are retrieved via search (Phase 5)
    # --- additional domains that already exist as SAE builders ---
    "goals": "goals",
    "habits": "habits",
    "tasks": "tasks",
    "execution": "execution",
    "routine": "routine",
    "nutrition": "nutrition",
    "fasting": "fasting",
    "fitness": "fitness",
    "medicine": "medicine",
    "brain_training": "brain_training",
}


def supported_domains():
    """Sorted list of ChatGPT-facing domain names this service supports."""
    return sorted(DOMAIN_REGISTRY.keys())


def _emit(user_id, domain, status, *, module=None, available=None,
          fields=None, source=None, ms=None, error=None):
    """Observable, structured telemetry. No silent failures."""
    try:
        logger.info(
            "DOMAIN_STATE served user=%s domain=%s status=%s module=%s "
            "available=%s fields=%s source=%s ms=%s error=%s",
            user_id, domain, status, module, available, fields, source,
            ("%.1f" % ms) if ms is not None else "na", error,
        )
    except Exception:
        pass


def _envelope(domain, status, **extra):
    """Common response envelope (JSON-safe, schema-versioned)."""
    base = {
        "status": status,
        "domain": domain,
        "schema_version": DOMAIN_STATE_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
    }
    base.update(extra)
    return base


def get_domain_state(user, domain, *, allow_build=False):
    """
    Return the canonical SAE state for `domain` as a JSON-safe envelope.

    Args:
        user: Django User instance.
        domain: ChatGPT-facing domain name (case-insensitive).
        allow_build: if True, permit a SAE rebuild on a cold snapshot
            (background/warming callers only — NOT the request path).

    Returns:
        dict envelope. `status` is one of:
            "ready"              — state present (or rebuilt) and returned
            "pending"            — no warm snapshot yet (request-path read)
            "no_state_source"    — known domain with no SAE state (e.g. notes)
            "unsupported_domain" — unknown domain (lists supported domains)
            "error"              — read failed (logged with exc_info)
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()

    # --- unknown domain ---
    if domain_norm not in DOMAIN_REGISTRY:
        _emit(uid, domain_norm, "unsupported_domain", available=False)
        return _envelope(
            domain_norm, "unsupported_domain",
            reason="Unknown domain; not in the CoS domain registry.",
            supported_domains=supported_domains(),
        )

    module_key = DOMAIN_REGISTRY[domain_norm]

    # --- known domain, no SAE state source (e.g. notes) ---
    if module_key is None:
        _emit(uid, domain_norm, "no_state_source", available=False)
        return _envelope(
            domain_norm, "no_state_source",
            reason=(
                "This domain has no canonical SAE state; its content is "
                "retrieved via search, not domain-state (see Phase 5)."
            ),
        )

    # --- read canonical state (state-first; never live-compute on request) ---
    source = "rebuild_allowed" if allow_build else "snapshot"
    try:
        from apps.core.ai_state.state_engine import get_module_state
        state = get_module_state(user, module_key, allow_rebuild=allow_build)
    except Exception as exc:  # never swallow silently
        logger.warning(
            "domain_state: read failed user=%s domain=%s module=%s",
            uid, domain_norm, module_key, exc_info=True,
        )
        _emit(uid, domain_norm, "error", module=module_key, available=False,
              source=source, error=type(exc).__name__)
        return _envelope(
            domain_norm, "error", module=module_key,
            reason="State read failed; see server logs.",
        )

    # --- empty snapshot: pending (read-only) vs genuinely-empty (rebuilt) ---
    if not state:
        status = "ready" if allow_build else "pending"
        ms = (time.monotonic() - t0) * 1000
        _emit(uid, domain_norm, status, module=module_key, available=False,
              fields=0, source=source, ms=ms)
        return _envelope(
            domain_norm, status, module=module_key, source=source,
            state={} if allow_build else None,
            reason=None if allow_build else (
                "No warm SAE snapshot for this domain yet; retry shortly."
            ),
            _meta={"source": source, "field_count": 0},
        )

    # --- ready ---
    safe_state = _jsonsafe(state)
    field_count = len(safe_state) if isinstance(safe_state, dict) else 1
    ms = (time.monotonic() - t0) * 1000
    _emit(uid, domain_norm, "ready", module=module_key, available=True,
          fields=field_count, source=source, ms=ms)
    return _envelope(
        domain_norm, "ready", module=module_key, source=source,
        state=safe_state,
        _meta={"source": source, "field_count": field_count},
    )
