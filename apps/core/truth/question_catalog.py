"""
Platform capability: QUESTION CATALOG (data-driven certification).

The certification standard, as a PERMANENT, MACHINE-CHECKED ARTIFACT — not a report a
human re-derives each time. A domain declares the real customer questions it must
answer; each question declares the deterministic truth it REQUIRES; and this module
CHECKS those requirements against the live capability registries. So `certified` is
COMPUTED from the actual wired surfaces, never asserted.

    Certification := "Can the CoS answer every question in the catalog?"
    (NOT "can someone think of more questions?")

Future domain work adds `Question`s here; the certifier tells you, deterministically,
which are answerable and — for the rest — the FIRST failing architectural layer.

Reusable across ALL domains (Health is the first/reference catalog): Finance, Faith,
Relationships, Journal, Goals, Medical, Travel … register their own questions the same
way. No per-domain certification code — one framework, many catalogs.

A `Requirement` is `(capability, domain, target)`. The certifier maps each capability to
the registry that proves it is wired for that (domain, target):

    history / trend / comparison  -> history_capability_index      (any per-day series)
    readings / by_hour            -> readings_capability_index      (intra-day stream)
    event_frequency               -> event_frequency_capability_index (event-count series)
    adherence                     -> target registry                (a stored target)
    analysis                      -> analysis_capability_index       (an analysis subject)
    current                       -> truth_catalog[domain]["current"]
    current_context               -> registered page-summary keys    (target = page key)

A requirement naming a capability NOT in `KNOWN_CAPABILITIES` (e.g. a not-yet-built
`change_point` or `consistency`) is unsatisfiable by construction — the catalog can
express "this question needs a capability WLJ does not have yet", and it auto-certifies
the day that capability ships. WLJ exposes facts; the model renders verdicts — the
catalog certifies TRUTH AVAILABILITY, never answer quality.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Capabilities the platform actually provides, each backed by a live registry the
# certifier can consult. A requirement outside this set is a declared FUTURE capability.
KNOWN_CAPABILITIES = frozenset({
    "current_context", "current", "history", "trend", "comparison",
    "adherence", "analysis", "readings", "by_hour", "event_frequency",
    "consistency", "change_point",
})

# The eight question CATEGORIES a domain is certified across (the dimensions).
CATEGORIES = (
    "current_context", "current", "history", "trend",
    "comparison", "adherence", "analysis", "readings",
)


@dataclass(frozen=True)
class Requirement:
    capability: str
    domain: str
    target: Optional[str] = None      # metric / subject / page-key (capability-dependent)

    def label(self):
        return f"{self.capability}({self.domain}" + (f".{self.target}" if self.target else "") + ")"


@dataclass(frozen=True)
class Question:
    id: str                           # stable, e.g. "health.glucose.time_of_night_lows"
    domain: str                       # the CATALOG domain (certification scope), e.g. "health"
    category: str                     # one of CATEGORIES
    examples: Tuple[str, ...]         # natural-language phrasings the customer uses
    requires: Tuple[Requirement, ...]  # ALL must be satisfied to certify
    note: str = ""                    # rationale, or why a gap exists
    topic: str = ""                   # sub-grouping within the domain, e.g. "glucose"


_REGISTRY = {}                        # id -> Question
_DOMAIN_MODULES = {                   # domain -> catalog module (lazy import at ready)
    "health": "apps.health.health_question_catalog",
}


def register_question(q: Question):
    if q.category not in CATEGORIES:
        raise ValueError(f"{q.id}: unknown category {q.category!r} (have {CATEGORIES})")
    if q.id in _REGISTRY:
        raise ValueError(f"duplicate question id {q.id!r}")
    _REGISTRY[q.id] = q
    return q


def _ensure_loaded(domain=None):
    mods = ([_DOMAIN_MODULES[domain]] if domain and domain in _DOMAIN_MODULES
            else list(_DOMAIN_MODULES.values()))
    for mod in mods:
        try:
            __import__(mod)
        except Exception:
            logger.warning("question_catalog: could not import %s", mod, exc_info=True)


# ── the certifier — the single source of "is this answerable?" ────────────────

def _index(name):
    """Lazily fetch a capability index {domain: (targets...)}. Isolated so a broken
    registry degrades that capability to 'unsatisfiable', never crashes certification."""
    try:
        if name == "history":
            from apps.ai.cos_services.domain_history import history_capability_index
            return history_capability_index()
        if name == "readings":
            from apps.ai.cos_services.domain_readings import readings_capability_index
            return readings_capability_index()
        if name == "event_frequency":
            from apps.ai.cos_services.domain_event_frequency import (
                event_frequency_capability_index,
            )
            return event_frequency_capability_index()
        if name == "consistency":
            from apps.ai.cos_services.domain_consistency import (
                consistency_capability_index,
            )
            return consistency_capability_index()
        if name == "adherence":
            from apps.core.truth.targets import target_capability_index
            return target_capability_index()
        if name == "analysis":
            from apps.ai.cos_services.domain_analysis import analysis_capability_index
            return analysis_capability_index()
        if name == "current":
            from apps.core.truth.catalog import truth_catalog
            return {d: tuple(s.get("current", ()))
                    for d, s in truth_catalog().items() if isinstance(s, dict)}
    except Exception:
        logger.warning("question_catalog: index %s unavailable", name, exc_info=True)
    return {}


def _satisfied(req: Requirement) -> bool:
    cap = req.capability
    if cap not in KNOWN_CAPABILITIES:
        return False                                  # declared future capability
    if cap == "current_context":
        from apps.core.current_context import registered_page_summaries
        return (req.target or "") in registered_page_summaries()
    # history/trend/comparison/change_point all ride the per-day history series.
    index_name = {"trend": "history", "comparison": "history",
                  "change_point": "history", "by_hour": "readings"}.get(cap, cap)
    idx = _index(index_name)
    return req.target in tuple(idx.get(req.domain, ()) or ())


def certify_question(q: Question) -> dict:
    """Compute a question's live certification from the wired registries. Returns
    {id, domain, category, examples, requirements, certified, first_failing_layer}."""
    reqs = []
    first_fail = None
    for r in q.requires:
        ok = _satisfied(r)
        reqs.append({"requirement": r.label(), "capability": r.capability,
                     "satisfied": ok})
        if not ok and first_fail is None:
            # The architectural layer that fails first = the missing capability, named.
            layer = ("Platform Capability" if r.capability not in KNOWN_CAPABILITIES
                     else "Current Context" if r.capability == "current_context"
                     else "Truth Exposure")
            first_fail = {"layer": layer, "capability": r.capability,
                          "needs": r.label()}
    return {
        "id": q.id, "domain": q.domain, "topic": q.topic, "category": q.category,
        "examples": list(q.examples), "requirements": reqs,
        "certified": first_fail is None,
        "first_failing_layer": first_fail, "note": q.note,
    }


def certify(domain=None) -> dict:
    """Certify the whole catalog (or one domain). Returns a report with per-question
    results + a summary — the authoritative, data-driven certification matrix."""
    _ensure_loaded(domain)
    questions = [q for q in _REGISTRY.values()
                 if domain is None or q.domain == domain]
    results = [certify_question(q) for q in sorted(questions, key=lambda q: q.id)]
    total = len(results)
    certified = sum(1 for r in results if r["certified"])
    by_domain = {}
    for r in results:
        b = by_domain.setdefault(r["domain"], {"total": 0, "certified": 0})
        b["total"] += 1
        b["certified"] += 1 if r["certified"] else 0
    return {
        "questions": results,
        "summary": {"total": total, "certified": certified,
                    "uncertified": total - certified,
                    "pct": round((certified / total) * 100, 1) if total else 0.0,
                    "by_domain": by_domain},
    }


def registered_domains():
    _ensure_loaded()
    return sorted({q.domain for q in _REGISTRY.values()})
