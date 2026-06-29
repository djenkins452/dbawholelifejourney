"""
Executive Briefing Engine (transition capability — consumer, not retriever).

A human Chief of Staff reads a morning briefing BEFORE the conversation: what's
critical, what changed, what's normal, what's stale. This deterministic composer
produces that briefing so Beth consumes judgment instead of inventing it.

It is a pure CONSUMER of the truth platform — it enumerates `registered_domains()`,
asks each `DomainTruth` for its current metrics, and reads the value + freshness +
confidence already attached to every `CurrentTruth`. It performs NO raw DB queries
and computes no truth of its own. Clinical safety ranks FIRST (a dangerous glucose
outranks every optimization), then stale/low-confidence attention, then normal.

Output is a structured `ExecutiveBriefing`; Beth narrates over it. WLJ decides what
matters; Beth decides how to say it.
"""
from dataclasses import dataclass, field
from typing import Any, List, Tuple

from apps.core.truth import freshness as F

# Attention tiers (ranked best-first for output).
ACUTE = "acute"          # clinical-safety danger — surface FIRST, never bury
ATTENTION = "attention"  # caution / stale / low-confidence — worth a mention
NORMAL = "normal"        # present, current, trustworthy — reassure briefly
STALE = "stale"          # no value / not synced — name the gap honestly

_TIER_RANK = {ACUTE: 0, ATTENTION: 1, NORMAL: 2, STALE: 3}

# One representative current metric per concept (avoid double-reporting today+yesterday).
_PREFERRED_METRICS = {
    "glucose_yesterday", "sleep_last_night", "weight_yesterday", "steps_today",
    "calories_yesterday", "net_worth", "month_spending",
}


@dataclass(frozen=True)
class BriefingItem:
    domain: str
    metric: str
    present: bool
    value: Any
    unit: str
    freshness: str
    confidence: str
    as_of: str
    tier: str
    note: str = ""

    def label(self):
        return self.metric.replace("_yesterday", "").replace("_today", "").replace("_last_night", "").replace("_", " ")


@dataclass(frozen=True)
class ExecutiveBriefing:
    items: Tuple[BriefingItem, ...] = field(default_factory=tuple)

    def _tier(self, t):
        return [i for i in self.items if i.tier == t]

    def acute(self):
        return self._tier(ACUTE)

    def attention(self):
        return self._tier(ATTENTION)

    def normal(self):
        return self._tier(NORMAL)

    def stale(self):
        return self._tier(STALE)

    def domains_contributing(self):
        return sorted({i.domain for i in self.items if i.present})

    def headline(self):
        """The single most important item to open with (acute > attention > normal)."""
        return self.items[0] if self.items else None

    def to_dict(self):
        return {
            "headline": _item_dict(self.headline()) if self.items else None,
            "acute": [_item_dict(i) for i in self.acute()],
            "attention": [_item_dict(i) for i in self.attention()],
            "normal": [_item_dict(i) for i in self.normal()],
            "stale": [_item_dict(i) for i in self.stale()],
            "domains_contributing": self.domains_contributing(),
        }


def _item_dict(i):
    if i is None:
        return None
    return {"domain": i.domain, "metric": i.metric, "value": i.value, "unit": i.unit,
            "freshness": i.freshness, "confidence": i.confidence, "as_of": i.as_of,
            "tier": i.tier, "note": i.note}


def build_executive_briefing(user, *, metrics_filter=_PREFERRED_METRICS):
    """Compose the deterministic cross-domain briefing for `user`."""
    from apps.core.truth.domain import get_domain_truth, registered_domains
    items: List[BriefingItem] = []
    for domain in registered_domains():
        try:
            truth = get_domain_truth(user, domain)
            supported = truth.supports().get("current", ())
        except Exception:
            continue
        for metric in supported:
            if metrics_filter and metric not in metrics_filter:
                continue
            try:
                ct = truth.current(metric)
            except Exception:
                continue
            items.append(_classify(domain, metric, ct))
    items.sort(key=lambda i: (_TIER_RANK.get(i.tier, 9), i.domain, i.metric))
    return ExecutiveBriefing(tuple(items))


def _classify(domain, metric, ct):
    """Assign an attention tier — clinical safety FIRST, then freshness/confidence."""
    base = dict(domain=domain, metric=metric, present=ct.present, value=ct.value,
                unit=ct.unit or "", freshness=ct.freshness,
                confidence=ct.confidence, as_of=ct.as_of or "")
    if not ct.present:
        return BriefingItem(tier=STALE, note="no recent data", **base)

    # 1) Clinical safety (reuse the canonical interpreter; never re-derive bands).
    if "glucose" in metric and ct.value is not None:
        from apps.health.services.glucose_interpretation import interpret
        gi = interpret(ct.value, ct.unit or "mg/dL")
        if gi and gi["safety"] == "danger":
            return BriefingItem(tier=ACUTE, note=gi["advice"], **base)
        if gi and gi["safety"] == "caution":
            return BriefingItem(tier=ATTENTION, note=gi["display"], **base)

    # 2) Freshness / confidence attention.
    if ct.freshness == F.STALE:
        return BriefingItem(tier=ATTENTION, note="reading is stale", **base)
    from apps.core.truth import confidence as C
    if ct.confidence in (C.NONE, C.LOW):
        return BriefingItem(tier=ATTENTION, note="low confidence", **base)

    return BriefingItem(tier=NORMAL, note="", **base)


def narrate_briefing(briefing):
    """Deterministic narration shaped like a MORNING EXECUTIVE BRIEFING, not a health
    report: lead with the single most important thing, then what's worth a look, then
    a one-line all-clear, then what we can't see. Beth narrates over this order."""
    if not briefing.items:
        return "I don't have enough recent data to brief you yet."
    parts = []
    acute = briefing.acute()
    if acute:
        for i in acute:
            parts.append(
                f"Top priority — ⚠ {i.label().title()} is {i.value} {i.unit}: "
                f"{i.note}".strip())
    watch = briefing.attention()
    if watch:
        bits = [f"{i.label()} ({i.note})" if i.note else i.label() for i in watch]
        parts.append("Worth a look: " + ", ".join(bits) + ".")
    well = briefing.normal()
    if well:
        parts.append("On track: " + ", ".join(i.label() for i in well) + ".")
    stale = briefing.stale()
    if stale:
        parts.append("No fresh data on: " + ", ".join(i.label() for i in stale) + ".")
    return " ".join(p for p in parts if p)
