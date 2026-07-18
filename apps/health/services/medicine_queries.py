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

    # -- today execution — at the SCHEDULED-DOSE level -------------------------
    # Execution truth is evaluated per scheduled dose, never collapsed to one
    # medication-level result. A dose scheduled later today is reported PENDING (it must
    # be visible in "review my meds for today"); the adherence DENOMINATOR separately
    # excludes not-yet-due doses (fairness) — these are two different truths.
    @classmethod
    def _med_doses_today(cls, med, logs_for_med, dow, now_time):
        """The scheduled doses for ONE medication today, each with a status."""
        times = sorted(s.scheduled_time for s in med.schedules.all()
                       if getattr(s, "is_active", True) and s.scheduled_time
                       and s.applies_to_day(dow))
        # Count-based assignment (robust to logs that don't carry a scheduled_time):
        # earliest scheduled slots are satisfied first.
        taken_n = sum(1 for l in logs_for_med if l.log_status in ("taken", "late"))
        missed_n = sum(1 for l in logs_for_med if l.log_status == "missed")
        skipped_n = sum(1 for l in logs_for_med if l.log_status == "skipped")
        assigned = (["taken"] * taken_n + ["missed"] * missed_n + ["skipped"] * skipped_n)
        doses = []
        for i, t in enumerate(times):
            if i < len(assigned):
                status = assigned[i]
            else:
                status = "pending" if t > now_time else "overdue"
            doses.append({"time": t.strftime("%-I:%M %p"), "status": status})
        return doses

    @classmethod
    def today_doses(cls, user, classification=PRESCRIPTION):
        """Every scheduled dose today across a category → [{medication, time, status}].
        status ∈ taken | missed | skipped | pending (not yet due) | overdue (past due)."""
        from collections import defaultdict
        from apps.core.utils import get_user_now, get_user_today
        from apps.health.medicine_classification import classify_intake
        today = get_user_today(user)
        dow = today.weekday()
        now_time = get_user_now(user).time()
        qs = cls._active_qs(user, classification).prefetch_related("schedules")
        by_med = defaultdict(list)
        for lg in IntakeLog.objects.filter(user=user, intake__in=qs, scheduled_date=today):
            by_med[lg.intake_id].append(lg)
        out = []
        for m in qs:
            if classify_intake(m) != classification:
                continue
            for d in cls._med_doses_today(m, by_med.get(m.id, []), dow, now_time):
                out.append({"medication": m.name, **d})
        return out

    @staticmethod
    def _summarize_doses(doses):
        def c(*ss):
            return sum(1 for d in doses if d["status"] in ss)
        return {
            "expected": len(doses),               # ALL scheduled doses today (incl. pending)
            "taken": c("taken", "late"),
            "missed": c("missed"),
            "overdue": c("overdue"),
            "skipped": c("skipped"),
            "pending": c("pending", "overdue"),    # not yet taken (future or past-due)
        }

    @classmethod
    def today_execution(cls, user, classification=PRESCRIPTION):
        """Overall today execution at the scheduled-dose level (incl. pending doses)."""
        return cls._summarize_doses(cls.today_doses(user, classification))

    # -- ENTITY COMPLETENESS CONTRACT ------------------------------------------
    # The four canonical Medication-domain entities (Prescription / Supplement / OTC /
    # Wellness) are the SAME shape — a CompleteEntity. "kind" carries which one.
    _KIND = {PRESCRIPTION: "medication", "supplement": "supplement",
             "otc": "otc", "wellness": "wellness"}

    @classmethod
    def _last_taken(cls, intake):
        """The most recent date this item was actually TAKEN (taken|late), or None.
        Answers 'when did I last take X' — the audited truth gap surfaced by the live
        Customer Truth run (med.last_take, 2026-07-18). Prefers the precise `taken_at`
        timestamp, falls back to the dose's scheduled_date."""
        lg = (IntakeLog.objects.filter(intake=intake, log_status__in=("taken", "late"))
              .order_by("-scheduled_date", "-taken_at")
              .values_list("scheduled_date", "taken_at").first())
        if not lg:
            return None
        scheduled_date, taken_at = lg
        return (taken_at.date() if taken_at else scheduled_date)

    @classmethod
    def describe(cls, user, classification=PRESCRIPTION):
        """Each active item of `classification` as a CompleteEntity describing itself
        across the contract dimensions (identity / definition / status / plan / standing /
        performance). Read live from the canonical models."""
        from collections import defaultdict
        from datetime import timedelta
        from apps.core.truth.entity import CompleteEntity
        from apps.core.utils import get_user_now, get_user_today
        from apps.health.medicine_classification import classify_intake
        from apps.health.medicine_utils import calculate_single_medicine_adherence
        today = get_user_today(user)
        dow = today.weekday()
        now_time = get_user_now(user).time()
        qs = cls._active_qs(user, classification).prefetch_related("schedules")
        by_med = defaultdict(list)
        for lg in IntakeLog.objects.filter(user=user, intake__in=qs, scheduled_date=today):
            by_med[lg.intake_id].append(lg)
        kind = cls._KIND.get(classification, "medication")
        entities = []
        for m in qs:
            if classify_intake(m) != classification:       # final authority (name safety net)
                continue
            times = sorted(s.scheduled_time.strftime("%-I:%M %p")
                           for s in m.schedules.all()
                           if getattr(s, "is_active", True) and s.scheduled_time)
            # Complete schedule detail → "which DAYS do I take X" (weekly/custom regimens).
            schedule_detail = [
                {"time": (s.scheduled_time.strftime("%-I:%M %p")
                          if s.scheduled_time else None),
                 "time_of_day": getattr(s, "time_of_day", None) or None,
                 "label": getattr(s, "label", None) or None,
                 "days_of_week": getattr(s, "days_of_week", None) or None}
                for s in m.schedules.all() if getattr(s, "is_active", True)]
            doses = cls._med_doses_today(m, by_med.get(m.id, []), dow, now_time)

            def _adh(days):
                return calculate_single_medicine_adherence(
                    user, m, today - timedelta(days=days), today).get("adherence_rate")

            standing = cls._summarize_doses(doses)
            standing["doses"] = doses                       # per-dose detail (not collapsed)
            last_taken = cls._last_taken(m)
            _g = lambda a: getattr(m, a, None)
            entities.append(CompleteEntity(
                kind=kind,
                identity=m.name,
                definition={"dose": m.dose, "dosage_unit": _g("dosage_unit") or None,
                            "category": classify_intake(m),
                            "purpose": m.purpose or "",
                            "frequency": (m.get_frequency_display()
                                          if hasattr(m, "get_frequency_display")
                                          else _g("frequency")),
                            "is_prn": bool(getattr(m, "is_prn", False)),
                            "priority": _g("priority") or None,
                            "intake_subtype": _g("intake_subtype") or None},
                status=m.intake_status,
                plan={"schedule": times,
                      "schedule_detail": schedule_detail,
                      "grace_period_minutes": _g("grace_period_minutes"),
                      "start_date": (m.start_date.isoformat() if _g("start_date") else None),
                      "end_date": (m.end_date.isoformat() if _g("end_date") else None),
                      "instructions": (_g("instructions") or "").strip() or None,
                      "monitoring": (_g("monitoring_requirements") or "").strip() or None},
                standing={"today": standing,
                          "paused_at": (m.paused_at.isoformat() if _g("paused_at") else None),
                          "paused_reason": (_g("paused_reason") or "").strip() or None,
                          "refill": {"current_supply": _g("current_supply"),
                                     "threshold": _g("refill_threshold"),
                                     "needs_refill": bool(_g("needs_refill")),
                                     "requested": bool(_g("refill_requested")),
                                     "requested_at": (m.refill_requested_at.isoformat()
                                                      if _g("refill_requested_at") else None),
                                     "days_until_empty": _g("days_until_empty")}},
                performance={"adherence": {"7d": _adh(7), "30d": _adh(30), "90d": _adh(90)},
                             "last_taken": last_taken.isoformat() if last_taken else None},
                extensions={k: v for k, v in {
                    "notes": (_g("notes") or "").strip() or None,
                    "prescriber": (getattr(m.provider, "name", None) if m.provider_id
                                   else (_g("prescribing_doctor") or None)),
                    "pharmacy": (getattr(m.pharmacy_ref, "name", None) if _g("pharmacy_ref")
                                 else (_g("pharmacy") or None)),
                    "rx_number": (_g("rx_number") or None),
                }.items() if v is not None},
            ))
        entities.sort(key=lambda e: e.identity.lower())
        return entities

    # -- single-entity retrieval (by identity) --------------------------------
    # Generic med-name words that must NOT match on their own (a med "Daily Vitamin" is
    # not matched by "daily routine").
    _NAME_STOPWORDS = frozenset((
        "daily", "tablet", "tablets", "capsule", "capsules", "extended", "release",
        "oral", "once", "twice", "softgel", "chewable", "liquid", "spray", "cream",
        "solution", "injection", "generic", "brand",
    ))

    @classmethod
    def _match_intake(cls, user, text):
        """Resolve ONE active Intake mentioned in `text`. Matches the full stored name OR a
        distinctive name TOKEN (≥4 chars), so a short name ("Metformin") resolves a fuller
        stored name ("Metformin HCL ER"). Most-specific (longest) match wins."""
        import re
        text_l = (text or "").lower()
        text_words = set(re.findall(r"[a-z0-9]+", text_l))
        best, best_score = None, 0
        for m in Intake.objects.filter(user=user, intake_status=Intake.STATUS_ACTIVE):
            mn = (m.name or "").lower()
            if not mn:
                continue
            if mn in text_l:                                     # full-name match — strongest
                score = 100 + len(mn)
            else:
                toks = [w for w in re.findall(r"[a-z0-9]+", mn)
                        if len(w) >= 4 and w not in cls._NAME_STOPWORDS]
                matched = [w for w in toks if w in text_words]
                score = max((len(w) for w in matched), default=0)
            if score > best_score:
                best, best_score = m, score
        return best

    @classmethod
    def describe_one(cls, user, name):
        """Retrieve ONE entity by name across ALL categories as a CompleteEntity, or None.
        A short name resolves a fuller stored name. The entity describes itself completely."""
        from apps.health.medicine_classification import classify_intake
        target = cls._match_intake(user, name)
        if target is None:
            return None
        for e in cls.describe(user, classify_intake(target)):
            if e.identity == target.name:
                return e
        return None

    # -- execution-status slices ----------------------------------------------
    @classmethod
    def remaining_today(cls, user, classification=PRESCRIPTION):
        """Doses still to take today (pending or overdue)."""
        return [d for d in cls.today_doses(user, classification)
                if d["status"] in ("pending", "overdue")]

    @classmethod
    def missed_today(cls, user, classification=PRESCRIPTION):
        return [d for d in cls.today_doses(user, classification) if d["status"] == "missed"]

    # -- cross-entity combined view -------------------------------------------
    @classmethod
    def everything(cls, user):
        """Everything the user is taking, grouped by the four canonical categories."""
        from apps.health.medicine_classification import SUPPLEMENT, OTC, WELLNESS
        return {
            "prescription": cls.active_names(user, PRESCRIPTION),
            "supplement": cls.active_names(user, SUPPLEMENT),
            "otc": cls.active_names(user, OTC),
            "wellness": cls.active_names(user, WELLNESS),
        }

    # -- HISTORY (point-in-time inventory + lifecycle ledger) -----------------
    # Current state is the Intake projection; the MedicationEvent ledger is the canonical
    # HISTORY ("what changed, when, why"). These read both, live — never the SAE.
    @classmethod
    def taking_on(cls, user, on_date):
        """Point-in-time inventory: everything active on `on_date` (start_date on/before it
        and not ended before it). Includes since-discontinued items — that is the point."""
        from django.db.models import Q
        mgr = getattr(Intake, "all_objects", Intake.objects)   # include discontinued/soft-deleted
        qs = (mgr.filter(user=user, start_date__lte=on_date)
                 .filter(Q(end_date__isnull=True) | Q(end_date__gte=on_date)))
        return sorted({m.name for m in qs})

    @classmethod
    def discontinued(cls, user):
        """Medications the user has STOPPED (canonical DISCONTINUED ledger)."""
        from apps.health.models import MedicationEvent
        evs = (MedicationEvent.objects
               .filter(user=user, event_type=MedicationEvent.EVENT_DISCONTINUED)
               .select_related("intake").order_by("-effective_date"))
        return [{"name": e.intake.name, "date": e.effective_date.isoformat()} for e in evs]

    @classmethod
    def dose_changes(cls, user, name=None):
        """Dose-change history from the ledger (name, date, from → to)."""
        from apps.health.models import MedicationEvent
        evs = (MedicationEvent.objects
               .filter(user=user, event_type=MedicationEvent.EVENT_DOSE_CHANGED)
               .select_related("intake").order_by("-effective_date"))
        if name:
            evs = evs.filter(intake__name__icontains=name)
        return [{"name": e.intake.name, "date": e.effective_date.isoformat(),
                 "from": (e.previous_value or {}).get("dose"),
                 "to": (e.new_value or {}).get("dose")} for e in evs]

    @classmethod
    def started_on(cls, user, name):
        """When the user started a named medication (Intake.start_date)."""
        m = (Intake.objects.filter(user=user, name__icontains=name)
             .order_by("start_date").first())
        return m.start_date.isoformat() if (m and m.start_date) else None

    @classmethod
    def program_changes(cls, user, days):
        """Every real treatment change in the last N days (excludes the tracking-began
        backfill marker) — answers 'has my medication program changed?'."""
        from datetime import timedelta
        from apps.core.utils import get_user_today
        from apps.health.models import MedicationEvent
        since = get_user_today(user) - timedelta(days=days)
        evs = (MedicationEvent.objects
               .filter(user=user, effective_date__gte=since)
               .exclude(event_type=MedicationEvent.EVENT_TRACKING_BEGAN)
               .select_related("intake").order_by("-effective_date"))
        return [{"name": e.intake.name, "event": e.get_event_type_display(),
                 "date": e.effective_date.isoformat()} for e in evs]

    # -- CONDITION / PURPOSE mapping ------------------------------------------
    _CONDITION_SYNONYMS = {
        "diabetes": ("diabet", "blood sugar", "glucose", "a1c", "sugar"),
        "blood pressure": ("blood pressure", "hypertension", "bp"),
        "cholesterol": ("cholesterol", "lipid", "statin"),
        "thyroid": ("thyroid",),
        "depression": ("depress", "mood"),
        "anxiety": ("anxiety", "anxious"),
        "pain": ("pain", "analgesic"),
        "allergy": ("allerg",),
        "acid reflux": ("reflux", "heartburn", "gerd", "acid"),
    }

    @classmethod
    def _condition_tokens(cls, condition):
        c = (condition or "").lower()
        for key, toks in cls._CONDITION_SYNONYMS.items():
            if key in c or any(t in c for t in toks):
                return toks
        return (c,)

    @classmethod
    def for_condition(cls, user, condition, classification=PRESCRIPTION):
        """Medications whose purpose matches a condition (synonym-aware). Canonical
        med→condition mapping is the Intake.purpose field."""
        from django.db.models import Q
        from apps.health.medicine_classification import classify_intake
        q = Q()
        for t in cls._condition_tokens(condition):
            q |= Q(purpose__icontains=t)
        qs = cls._active_qs(user, classification).filter(q)
        return sorted(m.name for m in qs if classify_intake(m) == classification)

    @classmethod
    def summary(cls, user, classification=PRESCRIPTION):
        """Domain-level rollup (composed inside Layer 1 so a higher layer still makes ONE
        call): count + overall today (dose-level) + overall adherence."""
        return {
            "count": len(cls.active_names(user, classification)),
            "today": cls.today_execution(user, classification),
            "adherence": {"7d": cls.adherence_rate(user, 7, classification),
                          "30d": cls.adherence_rate(user, 30, classification),
                          "90d": cls.adherence_rate(user, 90, classification)},
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

    @classmethod
    def adherence_history(cls, user, period="last_7_days", classification=PRESCRIPTION,
                          *, today=None, start=None, end=None):
        """Adherence rate over time as a `HistorySeries` — one WEEKLY point across the
        resolved period, each computed by the canonical adherence math (no duplicate
        calculation). Bounded to whole weeks (request-path-safe: ≤ ~13 buckets for a
        quarter). Fulfils the advertised `history_metrics=("adherence",)` contract
        deterministically instead of raising."""
        from datetime import timedelta
        from apps.core.truth.history import series_from_rows
        from apps.core.truth.periods import resolve_period
        from apps.core.utils import get_user_today
        from apps.health.medicine_utils import calculate_medicine_adherence

        p = resolve_period(period, today or get_user_today(user), start=start, end=end)
        rows, wk_start = [], p.start
        while wk_start <= p.end:
            wk_end = min(wk_start + timedelta(days=6), p.end)
            rate = calculate_medicine_adherence(
                user, wk_start, wk_end, classification=classification).get("adherence_rate")
            if rate is not None:
                rows.append({"date": wk_end, "value": int(rate)})
            wk_start = wk_end + timedelta(days=1)
        return series_from_rows("medicine", "adherence", p, rows, unit="%")
