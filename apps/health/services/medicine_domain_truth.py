"""
MedicineDomainTruth — the canonical interface to Medication truth (Layer 1).

A thin facade over MedicineQueries (the deterministic query layer). Owns NO new
retrieval logic and reads NO SAE snapshot — every consumer (Beth, dashboards, reports,
engines) gets the same deterministic answer, read live from the canonical models, so it
can never go missing or stale.

"Medicine" = PRESCRIPTION medication only. Supplement / OTC / Wellness are separate.
"""
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.current import CurrentTruth
from apps.core.truth.freshness import CURRENT
from apps.health.services.medicine_queries import MedicineQueries

_DOMAIN = "medicine"
_SRC = "MedicineQueries"

# The FOUR canonical Medication-domain entities — SYMMETRIC: every one supports the same
# retrieval surface (inventory · execution · adherence · profile · single-entity). "Medicine"
# = prescription; the others are their own first-class entities and never route to prescription.
from apps.health.medicine_classification import PRESCRIPTION, SUPPLEMENT, OTC, WELLNESS
_ENTITY_CLASS = {"medication": PRESCRIPTION, "supplement": SUPPLEMENT,
                 "otc": OTC, "wellness": WELLNESS}
_NOUN = {PRESCRIPTION: "prescription medication", SUPPLEMENT: "supplement",
         OTC: "over-the-counter medication", WELLNESS: "wellness product"}
_INVENTORY = {"current_medications": PRESCRIPTION, "active_medications": PRESCRIPTION,
              "current_supplements": SUPPLEMENT, "current_otc": OTC,
              "current_wellness": WELLNESS}
_EXECUTION = {"medication_execution_today": PRESCRIPTION,
              "supplement_execution_today": SUPPLEMENT}
_PROFILE = {"medication_profile": PRESCRIPTION, "supplement_profile": SUPPLEMENT}
_ADHERENCE = {
    "adherence_7d": (PRESCRIPTION, 7), "adherence_30d": (PRESCRIPTION, 30),
    "adherence_90d": (PRESCRIPTION, 90),
    "supplement_adherence_7d": (SUPPLEMENT, 7), "supplement_adherence_30d": (SUPPLEMENT, 30),
    "supplement_adherence_90d": (SUPPLEMENT, 90),
}


@register_domain_truth
class MedicineDomainTruth(DomainTruth):
    domain = _DOMAIN
    current_metrics = (tuple(_INVENTORY) + tuple(_EXECUTION) + tuple(_PROFILE)
                       + tuple(_ADHERENCE)
                       + ("current_intake_all", "medications_remaining_today"))
    history_metrics = ("adherence",)
    entity_types = ("medication", "supplement", "otc", "wellness")

    # -- current --------------------------------------------------------------
    def current(self, metric):
        if metric in _INVENTORY:
            return self._inventory(metric, _INVENTORY[metric])
        if metric in _EXECUTION:
            return self._execution(metric, _EXECUTION[metric])
        if metric in _PROFILE:
            return self._profile_truth(metric, _PROFILE[metric])
        if metric in _ADHERENCE:
            return self._adherence(metric, *_ADHERENCE[metric])
        if metric == "current_intake_all":
            return self._everything()
        if metric == "medications_remaining_today":
            return self._remaining()
        raise KeyError(f"medicine current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    # -- Entity Completeness Contract (reusable Layer 1 pattern) --------------
    def describe(self, entity_type="medication"):
        """Each item of `entity_type` as a CompleteEntity (self-describing across the
        contract dimensions). entity_type ∈ medication | supplement | otc | wellness."""
        return MedicineQueries.describe(self.user, _ENTITY_CLASS.get(entity_type, PRESCRIPTION))

    def describe_one(self, name):
        """ONE entity by name (any category) as a CompleteEntity, or None."""
        return MedicineQueries.describe_one(self.user, name)

    # -- per-metric resolvers (symmetric across all entity types) -------------
    def _inventory(self, metric, classification):
        items = MedicineQueries.active(self.user, classification)
        names = [m["name"] for m in items]
        return CurrentTruth.found(  # always PRESENT — empty is a real "0", never unknown
            _DOMAIN, metric, names, CURRENT, source=_SRC,
            detail={"count": len(names), "items": items, "noun": _NOUN[classification]})

    def _execution(self, metric, classification):
        ex = MedicineQueries.today_execution(self.user, classification)
        return CurrentTruth.found(_DOMAIN, metric, ex["taken"], CURRENT, source=_SRC,
                                  detail={"scope": classification, **ex})

    def _profile_truth(self, metric, classification):
        entities = MedicineQueries.describe(self.user, classification)
        summary = MedicineQueries.summary(self.user, classification)
        return CurrentTruth.found(
            _DOMAIN, metric, summary["count"], CURRENT, source=_SRC,
            detail={"medications": [e.to_dict() for e in entities], "scope": classification,
                    "noun": _NOUN[classification], **summary})

    def _adherence(self, metric, classification, days):
        rate = MedicineQueries.adherence_rate(self.user, days, classification)
        if rate is None:
            return CurrentTruth.absent(_DOMAIN, metric, CURRENT, source=_SRC,
                                       reason=f"no expected {classification} doses in window")
        return CurrentTruth.found(_DOMAIN, metric, rate, CURRENT, unit="%", source=_SRC,
                                  detail={"window_days": days, "scope": classification})

    def _everything(self):
        ev = MedicineQueries.everything(self.user)
        total = sum(len(v) for v in ev.values())
        return CurrentTruth.found(_DOMAIN, "current_intake_all", total, CURRENT,
                                  source=_SRC, detail=ev)

    def _remaining(self):
        doses = MedicineQueries.remaining_today(self.user)
        return CurrentTruth.found(_DOMAIN, "medications_remaining_today", len(doses),
                                  CURRENT, source=_SRC, detail={"doses": doses})

    # -- history --------------------------------------------------------------
    def history(self, metric, period="last_7_days", **kwargs):
        raise KeyError(f"medicine history unsupported: {metric!r} "
                       f"(use current() adherence_7d/30d/90d)")
