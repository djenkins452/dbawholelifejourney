# ==============================================================================
# File: apps/core/truth/validation/surface.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Resolve a discovery prompt's OBJECT to the deterministic WLJ record it is
#   about, using the SAME read surfaces and business rules the production application uses
#   ("current"/"active"/"latest"/"by name"). The validator must never invent its own
#   interpretation of these words. Object resolution is EXPLICIT and reported to the
#   operator (rule + resolved identity + provider), never a silent first-row guess.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Surface resolution — discovery prompt -> expected deterministic object.

A discovery prompt carries a `surface` (which provider entity its answer is composed from)
and a `selection` contract (HOW the singular object is chosen — the app's own rule):

    selection.rule = "by_name"  -> get_domain_entity(name=...)      (unambiguous)
                     "active"   -> among describe(type), the record whose status matches
                                   the app's active marker (e.g. reading plan plan_status=
                                   'active') — NEVER simply the first described row
                     "current"  -> resolve the current object's NAME via the domain's own
                                   current(metric) accessor, then fetch that record
                     "latest"   -> the most-recent record (provider composes newest-first)

If no `selection` is declared, we infer: entity_one surface -> by_name; else -> latest
(explicitly labelled "most recent (provider order)" so the operator SEES the rule used).

Every resolution returns an ExpectedObject that names the rule, the resolved identity, the
provider, and where it came from — so the operator is never surprised by the expected truth.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ENTITY_ONE = re.compile(r"entity_one\(\s*['\"]?([^'\")]+?)['\"]?\s*\)")
_ENTITY = re.compile(r"entity\(\s*([a-z_][a-z0-9_]*)")
_CURRENT = re.compile(r"current\(")
_DOMAIN = re.compile(r"^([a-z_][a-z0-9_]*)\s*\.")


@dataclass
class ExpectedObject:
    """The deterministic WLJ object a discovery prompt is about — with its provenance."""
    domain: str
    provider: str                       # the surface consulted, e.g. "faith.entity(reading_plan)"
    present: bool
    entity: Dict[str, Any] = field(default_factory=dict)   # the CompleteEntity/state dict
    reason: str = ""                    # why absent / unresolved (operator-facing)
    resolvable: bool = True             # the surface named a machine-resolvable selector
    selection_rule: str = ""            # human label of the rule used
    resolved_identity: str = ""         # the resolved object's name/title
    resolved_from: str = ""             # "Faith → reading_plan"
    object_status: str = ""             # the resolved record's lifecycle status

    # Back-compat: older callers read `.selector`.
    @property
    def selector(self) -> str:
        return self.provider

    @property
    def status(self) -> str:
        if not self.resolvable:
            return "unresolvable"
        return "present" if self.present else "absent"

    def resolution(self) -> Dict[str, str]:
        """The operator-facing resolution card (Resolved Object / From / Rule / Provider)."""
        return {
            "resolved_object": self.resolved_identity,
            "resolved_from": self.resolved_from,
            "selection_rule": self.selection_rule,
            "provider": self.provider,
            "status": self.object_status,
            "present": self.present,
            "reason": self.reason,
        }


def parse_surface(surface: str) -> Dict[str, Optional[str]]:
    """Parse a `surface` string into {domain, name, entity_type, wants_current}."""
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


def _default_selection(parsed) -> Dict[str, str]:
    if parsed["name"]:
        return {"rule": "by_name"}
    return {"rule": "latest"}


def _entity_identity(entity: Dict[str, Any]) -> str:
    return str((entity or {}).get("identity") or "").strip()


def resolve_expected_object(user, prompt: Dict[str, Any]) -> ExpectedObject:
    """Resolve a discovery prompt to its deterministic WLJ object, using the app's own
    selection rule. Never raises — an unresolved surface is an honest ExpectedObject the
    operator can review. Never silently returns describe()[0] for a "current/active" object.
    """
    surface = prompt.get("surface", "") or ""
    parsed = parse_surface(surface)
    domain = parsed["domain"] or (prompt.get("domain") or "").strip().lower()
    entity_type = parsed["entity_type"]
    selection = dict(prompt.get("selection") or _default_selection(parsed))
    rule = selection.get("rule", "latest")
    resolved_from = f"{domain.title()} → {entity_type or ('name' if parsed['name'] else 'current')}"

    if not domain:
        return ExpectedObject(domain="", provider=surface, present=False, resolvable=False,
                              reason="No domain could be parsed from the surface.")

    # ── by name (unambiguous) ────────────────────────────────────────────────
    if rule == "by_name" or parsed["name"]:
        name = selection.get("name") or parsed["name"]
        entity = _describe_one(user, domain, name)
        prov = f"{domain}.entity_one('{name}')"
        if isinstance(entity, dict):
            return ExpectedObject(
                domain=domain, provider=prov, present=True, entity=entity,
                selection_rule=f"By name: '{name}'", resolved_identity=_entity_identity(entity) or name,
                resolved_from=resolved_from, object_status=str(entity.get("status") or ""))
        return ExpectedObject(domain=domain, provider=prov, present=False, resolvable=(entity is not False),
                              selection_rule=f"By name: '{name}'", resolved_from=resolved_from,
                              reason="No record matches that name." if entity is None
                              else "This domain cannot look an entity up by name.")

    # ── current via the domain's own current(metric) accessor ────────────────
    if rule == "current" and selection.get("metric"):
        return _resolve_current(user, domain, entity_type, selection, surface, resolved_from)

    # ── active: the record whose status matches the app's active marker ──────
    if rule == "active":
        return _resolve_from_list(user, domain, entity_type, surface, resolved_from,
                                  active_status=selection.get("status", "active"))

    # ── latest: most recent (provider composes newest-first) ─────────────────
    return _resolve_from_list(user, domain, entity_type, surface, resolved_from,
                              active_status=None)


# ---------------------------------------------------------------------------
def _describe_one(user, domain, name):
    """Return the CompleteEntity dict for `name`, None if not found, False if the domain
    cannot look up by name / surface unavailable."""
    try:
        from apps.ai.cos_services.domain_entity import get_domain_entity
    except Exception:
        logger.warning("validation.surface: domain_entity import failed", exc_info=True)
        return False
    try:
        env = get_domain_entity(user, domain, name=name)
    except Exception:
        logger.warning("validation.surface: describe_one failed domain=%s", domain, exc_info=True)
        return False
    status = (env or {}).get("status")
    if status == "ready" and isinstance(env.get("entity"), dict):
        return env["entity"]
    if status == "empty":
        return None
    return False


def _list_entities(user, domain, entity_type):
    """(entities_list, envelope_status). entities is [] on any non-ready status."""
    try:
        from apps.ai.cos_services.domain_entity import get_domain_entity
    except Exception:
        logger.warning("validation.surface: domain_entity import failed", exc_info=True)
        return [], "error"
    try:
        env = get_domain_entity(user, domain, entity_type=entity_type)
    except Exception:
        logger.warning("validation.surface: describe failed domain=%s type=%s",
                       domain, entity_type, exc_info=True)
        return [], "error"
    status = (env or {}).get("status")
    if status == "ready":
        return list(env.get("entities") or []), status
    return [], status


def _resolve_from_list(user, domain, entity_type, surface, resolved_from, *, active_status):
    """Resolve the singular object from the describe() list.

    active_status is None -> "latest" (first row, provider newest-first). Otherwise pick the
    FIRST record whose status matches active_status (the app's active marker) — matching the
    production pattern `filter(status=active).first()` on the provider's own ordering."""
    prov = f"{domain}.entity({entity_type})"
    entities, status = _list_entities(user, domain, entity_type)
    if status not in ("ready", "empty"):
        return ExpectedObject(domain=domain, provider=prov, present=False, resolvable=False,
                              resolved_from=resolved_from,
                              selection_rule=("Current active" if active_status else "Most recent"),
                              reason=f"Entity surface returned '{status}' — not auto-resolvable yet.")
    if active_status:
        rule_label = f"Current active {entity_type} (status='{active_status}')"
        chosen = next((e for e in entities
                       if str(e.get("status") or "").strip().lower() == active_status.lower()), None)
    else:
        rule_label = f"Most recent {entity_type} (provider order, newest-first)"
        chosen = entities[0] if entities else None
    if not isinstance(chosen, dict):
        return ExpectedObject(
            domain=domain, provider=prov, present=False, resolved_from=resolved_from,
            selection_rule=rule_label,
            reason=(f"No {entity_type} with status='{active_status}' exists (nothing active to surface)."
                    if active_status else "No such record exists for this user."))
    return ExpectedObject(
        domain=domain, provider=prov, present=True, entity=chosen, selection_rule=rule_label,
        resolved_identity=_entity_identity(chosen), resolved_from=resolved_from,
        object_status=str(chosen.get("status") or ""))


def _resolve_current(user, domain, entity_type, selection, surface, resolved_from):
    """Resolve "the current X" by asking the domain provider's OWN current(metric) accessor
    for the current object's name (the exact production rule), then fetching that record —
    by describe_one if the domain supports it, else by matching the describe() list."""
    metric = selection["metric"]
    prov = f"{domain}.current({metric})"
    rule_label = f"Current via {domain}.current({metric})"
    name = None
    try:
        from apps.core.truth.domain import get_domain_truth
        truth = get_domain_truth(user, domain)
        ct = truth.current(metric)
        if getattr(ct, "found", False) or getattr(ct, "status", "") == "found":
            name = str(getattr(ct, "value", "") or "").strip()
    except Exception:
        logger.warning("validation.surface: current(%s) failed domain=%s", metric, domain,
                       exc_info=True)
    if not name:
        return ExpectedObject(domain=domain, provider=prov, present=False,
                              selection_rule=rule_label, resolved_from=resolved_from,
                              reason=f"The domain reports no current {metric}.")
    # fetch the full record for that name
    entity = _describe_one(user, domain, name)
    if not isinstance(entity, dict):
        # domain can't look up by name — match the describe() list by identity
        entities, _ = _list_entities(user, domain, entity_type)
        entity = next((e for e in entities
                       if _entity_identity(e).lower() == name.lower()), None)
    if isinstance(entity, dict):
        return ExpectedObject(
            domain=domain, provider=prov, present=True, entity=entity, selection_rule=rule_label,
            resolved_identity=_entity_identity(entity) or name, resolved_from=resolved_from,
            object_status=str(entity.get("status") or ""))
    return ExpectedObject(domain=domain, provider=prov, present=False, selection_rule=rule_label,
                          resolved_identity=name, resolved_from=resolved_from,
                          reason=f"Current {metric} is '{name}' but its full record could not be composed.")
