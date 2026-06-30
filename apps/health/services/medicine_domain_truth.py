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

# Adherence metric → window (days). "Medication Adherence" = prescription only.
_ADHERENCE_DAYS = {"adherence_7d": 7, "adherence_30d": 30, "adherence_90d": 90}


@register_domain_truth
class MedicineDomainTruth(DomainTruth):
    domain = _DOMAIN
    current_metrics = ("current_medications", "active_medications",
                       "medication_execution_today", "medication_profile",
                       "adherence_7d", "adherence_30d", "adherence_90d")
    history_metrics = ("adherence",)
    entity_types = ("medication",)

    # -- current --------------------------------------------------------------
    def current(self, metric):
        if metric in ("current_medications", "active_medications"):
            return self._inventory()
        if metric == "medication_execution_today":
            return self._execution_today()
        if metric == "medication_profile":
            return self._profile_truth()
        if metric in _ADHERENCE_DAYS:
            return self._adherence(metric, _ADHERENCE_DAYS[metric])
        raise KeyError(f"medicine current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    # -- Entity Completeness Contract (reusable Layer 1 pattern) --------------
    def describe(self, entity_type="medication"):
        """Each prescription as a CompleteEntity (self-describing across the contract
        dimensions). Higher layers consume complete entities; they never assemble
        fragmented truth."""
        return MedicineQueries.describe(self.user)

    def _profile_truth(self):
        # Compose the complete entities + the domain summary INSIDE Layer 1 — the higher
        # layer makes ONE call and receives one complete object.
        entities = MedicineQueries.describe(self.user)
        summary = MedicineQueries.summary(self.user)
        return CurrentTruth.found(
            _DOMAIN, "medication_profile", summary["count"], CURRENT, source=_SRC,
            detail={"medications": [e.to_dict() for e in entities],
                    "count": summary["count"], "today": summary["today"],
                    "adherence": summary["adherence"]},
        )

    def _inventory(self):
        meds = MedicineQueries.active(self.user)          # prescription only
        names = [m["name"] for m in meds]
        # Always PRESENT (read live from canonical truth) — an empty list is a real,
        # confident answer ("you have no prescription medications"), never "unknown".
        return CurrentTruth.found(
            _DOMAIN, "current_medications", names, CURRENT, source=_SRC,
            detail={"count": len(names), "medications": meds},
        )

    def _execution_today(self):
        ex = MedicineQueries.today_execution(self.user)   # prescription only
        return CurrentTruth.found(
            _DOMAIN, "medication_execution_today", ex["taken"], CURRENT, source=_SRC,
            detail={"expected": ex["expected"], "taken": ex["taken"],
                    "late": ex["late"], "missed": ex["missed"],
                    "pending": ex["pending"], "skipped": ex["skipped"]},
        )

    def _adherence(self, metric, days):
        rate = MedicineQueries.adherence_rate(self.user, days)   # prescription only
        if rate is None:
            return CurrentTruth.absent(_DOMAIN, metric, CURRENT, source=_SRC,
                                       reason="no expected prescription doses in window")
        return CurrentTruth.found(_DOMAIN, metric, rate, CURRENT, unit="%", source=_SRC,
                                  detail={"window_days": days, "scope": "prescription"})

    # -- history --------------------------------------------------------------
    def history(self, metric, period="last_7_days", **kwargs):
        raise KeyError(f"medicine history unsupported: {metric!r} "
                       f"(use current() adherence_7d/30d/90d)")
