"""
MedicineQueries — the deterministic query layer for the Medication domain (Layer 1
Canonical Truth). Reads the canonical models (Intake / IntakeLog / IntakeSchedule)
DIRECTLY on the retrieval path. It owns NO precompute and depends on NO SAE snapshot,
so the truth can never go missing or stale.

Business vocabulary is authoritative (apps/health/medicine_classification.py):
"Medicine" = PRESCRIPTION medication only. Supplements, OTC, and Wellness are separate
categories and are never medicine.
"""
from apps.health.models import Intake, IntakeLog
from apps.health.medicine_classification import (
    classify_intake, classification_q, PRESCRIPTION,
)


class MedicineQueries:
    """Canonical, deterministic medication retrieval. No SAE, no inference."""

    # -- inventory ------------------------------------------------------------
    @classmethod
    def _active_qs(cls, user, classification=PRESCRIPTION):
        qs = Intake.objects.filter(user=user, intake_status=Intake.STATUS_ACTIVE)
        if classification:
            qs = qs.filter(classification_q(classification))
        return qs

    @classmethod
    def active(cls, user, classification=PRESCRIPTION):
        """Active items of a category → list of canonical inventory dicts (name, dose,
        frequency, purpose, category, schedule_times, is_prn). Default: prescriptions.

        The classification_q is a COARSE DB pre-filter; classify_intake() is the FINAL
        authority per object — so the supplement-name safety net excludes a mis-tagged
        item (e.g. a "Fish Oil" wrongly tagged category=prescription) even if the DB
        filter returned it. A supplement can never leak into prescription inventory."""
        out = []
        for m in cls._active_qs(user, classification).prefetch_related("schedules"):
            if classify_intake(m) != classification:
                continue
            times = sorted(
                s.scheduled_time.strftime("%-I:%M %p")
                for s in m.schedules.all()
                if getattr(s, "is_active", True) and s.scheduled_time
            )
            out.append({
                "name": m.name,
                "dose": m.dose,
                "frequency": (m.get_frequency_display()
                              if hasattr(m, "get_frequency_display") else m.frequency),
                "purpose": m.purpose or "",
                "category": classify_intake(m),
                "schedule_times": times,
                "is_prn": bool(getattr(m, "is_prn", False)),
            })
        return sorted(out, key=lambda d: d["name"].lower())

    @classmethod
    def active_names(cls, user, classification=PRESCRIPTION):
        return [m["name"] for m in cls.active(user, classification)]

    # -- today execution ------------------------------------------------------
    @classmethod
    def today_execution(cls, user, classification=PRESCRIPTION):
        """Today's expected / taken / late / missed / skipped / pending doses, computed
        live from schedules + IntakeLog (default: prescriptions only)."""
        from apps.core.utils import get_user_now, get_user_today
        from apps.health.medicine_utils import _enumerate_expected_doses
        today = get_user_today(user)
        now_time = get_user_now(user).time()
        qs = cls._active_qs(user, classification).prefetch_related("schedules")
        expected = len(_enumerate_expected_doses(qs, today, today, today, now_time))
        logs = IntakeLog.objects.filter(user=user, intake__in=qs, scheduled_date=today)
        taken = logs.filter(log_status="taken").count()
        late = logs.filter(log_status="late").count()
        missed = logs.filter(log_status="missed").count()
        skipped = logs.filter(log_status="skipped").count()
        pending = max(0, expected - (taken + late + missed + skipped))
        return {
            "expected": expected,
            "taken": taken + late,        # taken at all (on time or late)
            "taken_on_time": taken,
            "late": late,
            "missed": missed,
            "skipped": skipped,
            "pending": pending,
        }

    # -- history / adherence --------------------------------------------------
    @classmethod
    def adherence_rate(cls, user, days, classification=PRESCRIPTION):
        """N-day adherence rate (int 0-100 or None) — reuses the canonical adherence
        utility (no duplicate math). Default: prescription = Medication Adherence."""
        from apps.health.medicine_utils import calculate_medicine_adherence_rate
        return calculate_medicine_adherence_rate(user, days=days, classification=classification)

    @classmethod
    def adherence_trend(cls, user, classification=PRESCRIPTION):
        """Direction of adherence: compares the most recent 30 days to the prior 30."""
        from datetime import timedelta
        from apps.core.utils import get_user_today
        from apps.health.medicine_utils import calculate_medicine_adherence
        today = get_user_today(user)
        recent = calculate_medicine_adherence(user, today - timedelta(days=30), today,
                                              classification=classification)["adherence_rate"]
        prior = calculate_medicine_adherence(user, today - timedelta(days=60),
                                             today - timedelta(days=30),
                                             classification=classification)["adherence_rate"]
        if recent is None or prior is None:
            return "insufficient_data"
        if recent > prior + 2:
            return "improving"
        if recent < prior - 2:
            return "declining"
        return "steady"
