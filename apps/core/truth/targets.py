"""
Platform capability: TARGET REGISTRY.

The ONE place a (domain, metric) declares its user-scoped target/limit, so a single
reusable ADHERENCE capability (apps.ai.cos_services.domain_adherence) can answer
"am I in line?" for ANY metric — nutrition macros, water, steps, … — without a
per-domain comparison. There is NO nutrition-adherence / steps-adherence; there is ONE
adherence surface reading ONE target registry.

A target provider is `fn(user) -> Target | None`. It reads the CANONICAL stored target
(never invents one) and returns the value + unit + kind. `kind` is a FACT, not a verdict:
  * "target" — a value to REACH or exceed (protein, fiber, steps, water)
  * "limit"  — a value to STAY UNDER (added sugar, sodium)
The model interprets "in line"; WLJ supplies target, actual, and which kind it is.

Registration happens at app-ready (see HealthConfig.ready → import health_targets), the
same lifecycle as page-summary providers.
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Target:
    value: float
    unit: str = ""
    kind: str = "target"          # "target" (reach) | "limit" (stay under)
    basis: str = "daily"          # the period the target applies to
    source: str = ""              # provenance, e.g. "health.NutritionGoals"
    label: str = ""

    def to_dict(self):
        return {"value": self.value, "unit": self.unit, "kind": self.kind,
                "basis": self.basis, "source": self.source, "label": self.label}


# (domain, metric) -> provider fn(user) -> Target | None
_TARGET_PROVIDERS = {}


def register_target(domain, metric):
    """Decorator — register a user-scoped target provider for (domain, metric)."""
    def deco(fn):
        _TARGET_PROVIDERS[(domain.strip().lower(), metric.strip().lower())] = fn
        return fn
    return deco


def resolve_target(user, domain, metric) -> Optional[Target]:
    """The user's canonical target for (domain, metric), or None when none is declared
    or none is set. Never raises — a provider failure logs and returns None."""
    fn = _TARGET_PROVIDERS.get(((domain or "").strip().lower(),
                                (metric or "").strip().lower()))
    if fn is None:
        return None
    try:
        t = fn(user)
    except Exception:
        logger.warning("targets: provider failed for %s.%s", domain, metric,
                       exc_info=True)
        return None
    return t if isinstance(t, Target) else None


def target_capability_index():
    """{domain: (metrics with a registered target provider...)} — the capability index
    the model reads to know which metrics support adherence. Names only, no user data,
    no I/O (declarations only)."""
    _ensure_loaded()
    out = {}
    for (d, m) in _TARGET_PROVIDERS:
        out.setdefault(d, set()).add(m)
    return {d: tuple(sorted(ms)) for d, ms in out.items()}


def target_capable_domains():
    return sorted(target_capability_index().keys())


def _ensure_loaded():
    """Trigger target-provider registration (app-ready normally does this; this guards
    catalog/index reads that can run before ready in tests/management commands)."""
    if _TARGET_PROVIDERS:
        return
    for mod in ("apps.health.services.health_targets",):
        try:
            __import__(mod)
        except Exception:
            logger.warning("targets: could not import provider module %s", mod,
                           exc_info=True)
