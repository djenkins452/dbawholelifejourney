# ==============================================================================
# File: apps/ai/cos_services/domain_entity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: DomainEntityService — the generic ENTITY (record-level) truth read surface
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-15
# ==============================================================================
"""
DomainEntityService (Model Interface — Pillar 1, entity branch)
===============================================================

The fourth and final generic Model-Interface read surface. Its siblings:

    get_domain_state    → DomainTruth.state()    (composed "now")
    get_foundational_*  → DomainTruth.current()  (current scalars)
    get_domain_history  → DomainTruth.history()  ("back then" series)
    get_domain_entity   → DomainTruth.describe() (RECORD-LEVEL complete entities)

`get_domain_entity(user, domain, entity_type=..., name=...)` answers record-level
questions — "list my medications in full", "show that person", "my last workout's
exercises" — by returning `CompleteEntity` objects (the Entity Completeness Law:
a single deterministic retrieval that fully answers the natural questions about a
record). It is the surface behind "did I do calf raises?" / "show my last InBody
scan" once a domain registers `entity_types` + `describe()`.

Design rules honored (Architecture Laws + Amendment A + Model Interface design):
* REUSE ONLY — delegates to the canonical Truth Resolution Layer
  `DomainTruth(user, domain).describe(entity_type)` / `.describe_one(name)` over
  the existing `truth_catalog()`. NO new retrieval logic, NO parallel entity store,
  NO bespoke per-domain entity tool. The Entity Completeness Law already lives
  INSIDE each domain's provider.
* CATALOG-DRIVEN — every domain that registers `entity_types` participates
  automatically; no per-domain plumbing here.
* NO RAW ROWS — returns composed `CompleteEntity` dicts (identity/definition/
  status/plan/standing/performance + freshness/confidence), never database rows.
* NO FABRICATION — unknown domain → `unsupported_domain`; a domain/type that
  exposes no entities → `unsupported`; a name that matches nothing → `empty`.
  Honest states, never a guess. Mirrors get_domain_history exactly so
  `_wrap_truth` maps `status` → the canonical envelope with no logic change.
"""

import logging
import time

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

DOMAIN_ENTITY_SCHEMA_VERSION = "1.0"


def _emit(user_id, domain, entity_type, status, *, name=None, count=None, ms=None,
          error=None):
    """Observable, structured telemetry. No silent failures."""
    try:
        logger.info(
            "DOMAIN_ENTITY served user=%s domain=%s entity_type=%s name=%s "
            "status=%s count=%s ms=%s error=%s",
            user_id, domain, entity_type, name, status, count,
            ("%.1f" % ms) if ms is not None else "na", error,
        )
    except Exception:
        pass


def _envelope(domain, entity_type, status, **extra):
    from django.utils import timezone
    base = {
        "status": status,
        "domain": domain,
        "entity_type": entity_type,
        "schema_version": DOMAIN_ENTITY_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        # Truthful granularity: this surface carries the DETAILED CONTENTS of individual
        # records (identity, components, child records). For aggregate counts/totals/
        # trends over a period, get_history is the right surface.
        "granularity": "record_detail",
        "scope": ("The detailed contents of individual records (identity, components, "
                  "child records). For aggregate counts, totals, or trends over a period, "
                  "use get_history."),
    }
    base.update(extra)
    return base


def _serialize(item):
    """A CompleteEntity → its canonical dict; anything else passes through jsonsafe."""
    if item is None:
        return None
    to_dict = getattr(item, "to_dict", None)
    return _jsonsafe(to_dict() if callable(to_dict) else item)


def entity_capability_index():
    """{domain: (entity types...)} for every registered domain that describes at least
    one entity type. Small (type NAMES only) — the capability index the model reads to
    know what record-level truth it can pull, never the data itself."""
    try:
        from apps.core.truth.catalog import truth_catalog
        cat = truth_catalog()
    except Exception:
        logger.warning("domain_entity: catalog read failed", exc_info=True)
        return {}
    out = {}
    for domain, supports in (cat or {}).items():
        ents = tuple(supports.get("entities", ()) if isinstance(supports, dict) else ())
        if ents:
            out[domain] = ents
    return out


def entity_capable_domains():
    return sorted(entity_capability_index().keys())


def get_domain_entity(user, domain, *, entity_type=None, name=None, filters=None):
    """
    Return canonical ENTITY (record-level) truth for `domain` as a JSON-safe envelope.
    Delegates to `DomainTruth(user, domain).describe(entity_type)` (a list) or
    `.describe_one(name)` (one), each a composed `CompleteEntity`.

    Args:
        user: Django User instance.
        domain: WLJ domain name (case-insensitive) — must be registered.
        entity_type: the entity type to list (case-insensitive) — must be in the
            domain's `entity_types` (see `entity_capability_index`). List ALL entities
            of that type.
        name: fetch ONE entity by name (any type) instead of listing. Takes precedence
            over entity_type when both are given.

    Returns:
        dict envelope. `status` is one of:
            "ready"              — entity/entities present, returned
            "empty"              — the type has no records, or the name matched nothing
            "unsupported_domain" — unknown domain (lists entity-capable domains)
            "unsupported"        — domain exposes no entities / bad type / no selector
            "error"              — read failed (logged with exc_info)
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    domain_norm = (domain or "").strip().lower()
    type_norm = (entity_type or "").strip().lower() or None
    name_norm = (name or "").strip() or None

    # --- Truth Resolution Layer ---
    try:
        from apps.core.truth.domain import get_domain_truth, registered_domains
    except Exception as exc:
        logger.warning("domain_entity: truth layer unavailable", exc_info=True)
        _emit(uid, domain_norm, type_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, type_norm, "error",
                         reason="Truth layer unavailable; see server logs.")

    # --- unknown domain ---
    if domain_norm not in registered_domains():
        _emit(uid, domain_norm, type_norm, "unsupported_domain")
        return _envelope(
            domain_norm, type_norm, "unsupported_domain",
            reason="Unknown domain; not in the Truth Resolution Layer.",
            entity_capable_domains=entity_capable_domains(),
        )

    try:
        truth = get_domain_truth(user, domain_norm)
    except Exception as exc:
        logger.warning("domain_entity: get_domain_truth failed user=%s domain=%s",
                       uid, domain_norm, exc_info=True)
        _emit(uid, domain_norm, type_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, type_norm, "error",
                         reason="Domain truth read failed; see server logs.")

    supported = tuple(getattr(truth, "entity_types", ()) or ())

    # --- domain exposes no entities ---
    if not supported:
        _emit(uid, domain_norm, type_norm, "unsupported")
        return _envelope(
            domain_norm, type_norm, "unsupported",
            reason=f"'{domain_norm}' exposes no describable entities.",
            supported_entity_types=[],
        )

    # --- need a selector ---
    if not name_norm and not type_norm:
        _emit(uid, domain_norm, type_norm, "unsupported")
        return _envelope(
            domain_norm, type_norm, "unsupported",
            reason=("Provide an entity_type to list, or a name to fetch one."),
            supported_entity_types=sorted(supported),
        )

    # ── fetch ONE by name ──────────────────────────────────────────────────
    if name_norm:
        describe_one = getattr(truth, "describe_one", None)
        if not callable(describe_one):
            _emit(uid, domain_norm, type_norm, "unsupported", name=name_norm)
            return _envelope(
                domain_norm, type_norm, "unsupported",
                reason=f"'{domain_norm}' cannot look an entity up by name.",
                supported_entity_types=sorted(supported),
            )
        try:
            entity = describe_one(name_norm)
        except (KeyError, NotImplementedError) as exc:
            logger.warning("domain_entity: %s.describe_one gap: %s", domain_norm, exc)
            _emit(uid, domain_norm, type_norm, "unsupported", name=name_norm,
                  error=type(exc).__name__)
            return _envelope(domain_norm, type_norm, "unsupported",
                             reason="Name lookup not resolved by this domain yet.")
        except Exception as exc:
            logger.warning("domain_entity: describe_one failed user=%s domain=%s",
                           uid, domain_norm, exc_info=True)
            _emit(uid, domain_norm, type_norm, "error", name=name_norm,
                  error=type(exc).__name__)
            return _envelope(domain_norm, type_norm, "error",
                             reason="Entity read failed; see server logs.")
        ms = (time.monotonic() - t0) * 1000
        if entity is None:
            _emit(uid, domain_norm, type_norm, "empty", name=name_norm, ms=ms)
            return _envelope(domain_norm, type_norm, "empty", name=name_norm,
                             reason=f"No '{name_norm}' found in {domain_norm}.")
        _emit(uid, domain_norm, type_norm, "ready", name=name_norm, count=1, ms=ms)
        return _envelope(domain_norm, type_norm, "ready", name=name_norm,
                         entity=_serialize(entity))

    # ── list ALL of a type ─────────────────────────────────────────────────
    if type_norm not in {t.lower() for t in supported}:
        _emit(uid, domain_norm, type_norm, "unsupported")
        return _envelope(
            domain_norm, type_norm, "unsupported",
            reason=f"'{type_norm}' is not a describable entity type for '{domain_norm}'.",
            supported_entity_types=sorted(supported),
        )
    try:
        # Optional deterministic SCOPING (meal/period/on_date/involves/contains). Passed
        # through to providers that accept it; providers that don't simply ignore it
        # (TypeError → unscoped call), so this stays backward-compatible.
        if filters:
            try:
                entities = truth.describe(type_norm, filters=filters)
            except TypeError:
                entities = truth.describe(type_norm)
        else:
            entities = truth.describe(type_norm)
    except (KeyError, NotImplementedError) as exc:
        # Advertised in entity_types but describe() does not resolve it — a
        # provider-contract gap, not a runtime error. Honest "unsupported".
        logger.warning("domain_entity: provider declares '%s.%s' as an entity but did "
                       "not resolve it: %s", domain_norm, type_norm, exc)
        _emit(uid, domain_norm, type_norm, "unsupported", error=type(exc).__name__)
        return _envelope(
            domain_norm, type_norm, "unsupported",
            reason=(f"'{type_norm}' is advertised for '{domain_norm}' but its provider "
                    f"does not describe it yet."),
        )
    except Exception as exc:
        logger.warning("domain_entity: describe failed user=%s domain=%s type=%s",
                       uid, domain_norm, type_norm, exc_info=True)
        _emit(uid, domain_norm, type_norm, "error", error=type(exc).__name__)
        return _envelope(domain_norm, type_norm, "error",
                         reason="Entity read failed; see server logs.")

    items = [_serialize(e) for e in (entities or [])]
    ms = (time.monotonic() - t0) * 1000
    if not items:
        _emit(uid, domain_norm, type_norm, "empty", count=0, ms=ms)
        return _envelope(domain_norm, type_norm, "empty", count=0,
                         reason=f"No '{type_norm}' records in {domain_norm}.")
    _emit(uid, domain_norm, type_norm, "ready", count=len(items), ms=ms)
    return _envelope(domain_norm, type_norm, "ready", count=len(items), entities=items)
