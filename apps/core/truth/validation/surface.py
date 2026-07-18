# ==============================================================================
# File: apps/core/truth/validation/surface.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Resolve a discovery prompt's `surface` string to the deterministic WLJ
#   truth object it names, using the SAME read surfaces the model calls
#   (get_domain_entity / get_domain_state). This is how the validator obtains the
#   "expected truth" — WLJ is always the authority; nothing is fabricated.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Surface resolution — discovery `surface` string -> expected deterministic object.

A discovery prompt carries a `surface` field that names the provider entity its answer
should be composed from, e.g.:

    "health.entity(weight)"              -> get_domain_entity(domain="health", entity_type="weight")[0]
    "medicine.entity_one('Metformin')"  -> get_domain_entity(domain="medicine", name="Metformin")
    "relationships.current(most_connected)" -> get_domain_state(domain="relationships")
    "calendar.current(next_event) / entity(event)"  -> first parseable selector wins

We resolve the FIRST parseable `entity_one('X')` or `entity(type)` selector (record-level
truth — the natural target of a "tell me everything about <object>" prompt); if the surface
carries only a `current(...)` selector we fall back to the composed domain state. When no
selector resolves to a present record we return an ABSENT object (honest N/A), never a guess.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# entity_one('Name') / entity_one("Name") / entity_one(yesterday)
_ENTITY_ONE = re.compile(r"entity_one\(\s*['\"]?([^'\")]+?)['\"]?\s*\)")
# entity(type)  or  entity(type, extra...)  -> capture the leading type token
_ENTITY = re.compile(r"entity\(\s*([a-z_][a-z0-9_]*)")
# current(key)
_CURRENT = re.compile(r"current\(")
# leading "domain." — the domain owning the surface
_DOMAIN = re.compile(r"^([a-z_][a-z0-9_]*)\s*\.")


@dataclass
class ExpectedObject:
    """The deterministic WLJ truth object a discovery prompt is about."""
    domain: str
    selector: str                       # human description of how it was resolved
    present: bool                       # a concrete record was found
    entity: Dict[str, Any] = field(default_factory=dict)   # the CompleteEntity dict (or state dict)
    reason: str = ""                    # why absent / unresolved (operator-facing)
    resolvable: bool = True             # the surface named a machine-resolvable selector

    @property
    def status(self) -> str:
        if not self.resolvable:
            return "unresolvable"
        return "present" if self.present else "absent"


def parse_surface(surface: str) -> Dict[str, Optional[str]]:
    """Parse a `surface` string into {domain, name, entity_type, wants_current}.

    Returns the FIRST record-level selector found (name preferred over type), plus a
    `wants_current` flag when a current(...) selector is present. `domain` is the leading
    token before the first dot.
    """
    surface = surface or ""
    domain = None
    m = _DOMAIN.match(surface.strip())
    if m:
        domain = m.group(1).strip().lower()
    name = None
    entity_type = None
    m1 = _ENTITY_ONE.search(surface)
    if m1:
        name = m1.group(1).strip()
    m2 = _ENTITY.search(surface)
    if m2:
        entity_type = m2.group(1).strip().lower()
    wants_current = bool(_CURRENT.search(surface))
    return {"domain": domain, "name": name, "entity_type": entity_type,
            "wants_current": "1" if wants_current else ""}


def resolve_expected_object(user, prompt: Dict[str, Any]) -> ExpectedObject:
    """Resolve a discovery prompt to its deterministic WLJ truth object.

    Uses the model-facing read surfaces so the validator compares against exactly what a
    correct answer would have been composed from. Never raises — a failure to resolve is an
    honest `unresolvable`/`absent` ExpectedObject the operator can review.
    """
    surface = prompt.get("surface", "") or ""
    parsed = parse_surface(surface)
    domain = parsed["domain"] or (prompt.get("domain") or "").strip().lower()

    if not domain:
        return ExpectedObject(domain="", selector=surface, present=False,
                              resolvable=False,
                              reason="No domain could be parsed from the surface.")

    # ── record-level truth (the natural target of an object prompt) ──────────────
    if parsed["name"] or parsed["entity_type"]:
        try:
            from apps.ai.cos_services.domain_entity import get_domain_entity
        except Exception:
            logger.warning("validation.surface: domain_entity import failed", exc_info=True)
            return ExpectedObject(domain=domain, selector=surface, present=False,
                                  resolvable=False, reason="Entity read surface unavailable.")
        try:
            if parsed["name"]:
                env = get_domain_entity(user, domain, name=parsed["name"])
                sel = f"{domain}.entity_one('{parsed['name']}')"
            else:
                env = get_domain_entity(user, domain, entity_type=parsed["entity_type"])
                sel = f"{domain}.entity({parsed['entity_type']})"
        except Exception:
            logger.warning("validation.surface: get_domain_entity failed domain=%s",
                           domain, exc_info=True)
            return ExpectedObject(domain=domain, selector=surface, present=False,
                                  resolvable=False, reason="Entity read raised; see logs.")
        status = (env or {}).get("status")
        if status == "ready":
            entity = env.get("entity")
            if entity is None:
                entities = env.get("entities") or []
                # "most recent <object>" -> the provider composes most-recent-first.
                entity = entities[0] if entities else None
            if isinstance(entity, dict):
                return ExpectedObject(domain=domain, selector=sel, present=True, entity=entity)
            return ExpectedObject(domain=domain, selector=sel, present=False,
                                  reason="Surface ready but exposed no record to compare.")
        if status == "empty":
            return ExpectedObject(domain=domain, selector=sel, present=False,
                                  reason="No such record exists for this user (nothing to surface).")
        # unsupported / unsupported_domain / error
        return ExpectedObject(domain=domain, selector=sel, present=False, resolvable=False,
                              reason=f"Entity surface returned '{status}' — not auto-resolvable yet.")

    # ── composed-state fallback (current(...)-only surfaces) ─────────────────────
    if parsed["wants_current"]:
        try:
            from apps.ai.cos_services.domain_state import get_domain_state
            env = get_domain_state(user, domain)
        except Exception:
            logger.warning("validation.surface: get_domain_state failed domain=%s",
                           domain, exc_info=True)
            return ExpectedObject(domain=domain, selector=surface, present=False,
                                  resolvable=False, reason="State read surface unavailable.")
        state = (env or {}).get("state") if isinstance(env, dict) else None
        if isinstance(state, dict) and state:
            return ExpectedObject(domain=domain, selector=f"{domain}.current",
                                  present=True, entity=state)
        return ExpectedObject(domain=domain, selector=f"{domain}.current", present=False,
                              reason="Composed state carried no comparable values.")

    return ExpectedObject(domain=domain, selector=surface, present=False, resolvable=False,
                          reason="Surface names no machine-resolvable selector (manual review).")
