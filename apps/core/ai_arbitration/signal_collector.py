"""
UAL — Signal Collector.

Aggregates signals from all active engines into a structured
ArbitrationInput dict. Every import is guarded — a missing engine
never breaks arbitration.
"""
import logging
from datetime import timedelta

from apps.core.ai_observability.instrumentation import log_engine_span as _instrument_span

logger = logging.getLogger(__name__)


def _now():
    """Get current time via HTIE, fallback to timezone.now()."""
    try:
        from apps.core.time.system_clock import get_current_time
        return get_current_time()
    except Exception:
        from django.utils import timezone
        return timezone.now()


@_instrument_span("UAL", "collect_signals")
def collect_signals(user) -> dict:
    """
    Collect and normalise signals from all engines.

    Returns ArbitrationInput dict with keys:
        time_context, health_signals, mood_signals, schedule_signals,
        drift_signals, relational_signals, upcoming_events,
        energy_indicators, risk_indicators, raw_strengths
    """
    now = _now()
    inp = {
        "time_context": _collect_time_context(user, now),
        "health_signals": _collect_health_signals(user, now),
        "mood_signals": _collect_mood_signals(user, now),
        "schedule_signals": _collect_schedule_signals(user, now),
        "drift_signals": _collect_drift_signals(user),
        "relational_signals": _collect_relational_signals(user, now),
        "upcoming_events": _collect_upcoming_events(user, now),
        "energy_indicators": {},
        "risk_indicators": {},
    }

    # Compute normalised signal strengths (0-1) for classifier/fuser
    strengths = _compute_signal_strengths(inp, now)
    inp["raw_strengths"] = strengths

    # Derive energy and risk indicators from strengths
    inp["energy_indicators"] = {
        "sleep_quality": 1.0 - strengths.get("sleep_deficit", 0),
        "capacity": 1.0 - strengths.get("schedule_overload", 0),
        "mood_energy": 1.0 - strengths.get("mood_decline", 0),
    }
    inp["risk_indicators"] = {
        "health_risk": strengths.get("medication_risk", 0),
        "drift_risk": strengths.get("drift_severity", 0),
        "deadline_risk": strengths.get("deadline_pressure", 0),
        "relationship_risk": strengths.get("relationship_drift", 0),
        "mood_risk": strengths.get("mood_decline", 0),
    }
    return inp


# ── Time Context ─────────────────────────────────────────────────────

def _collect_time_context(user, now):
    hour = now.hour
    if hour < 6:
        tod = "night"
    elif hour < 12:
        tod = "morning"
    elif hour < 17:
        tod = "afternoon"
    else:
        tod = "evening"

    return {
        "current_time": now.isoformat(),
        "time_of_day": tod,
        "day_of_week": now.strftime("%A"),
        "is_weekend": now.weekday() >= 5,
        "hour": hour,
    }


# ── Health Signals ───────────────────────────────────────────────────

def _collect_health_signals(user, now):
    signals = {
        "sleep_last_night": None,
        "sleep_duration_minutes": None,
        "sleep_target_minutes": 480,
        "sleep_quality": None,
        "medications_scheduled": 0,
        "medications_taken": 0,
        "medications_missed": 0,
        "active_fast": None,
        "workout_scheduled": False,
        "injury_keywords": [],
        "weight_trend": None,
    }

    # Sleep
    try:
        from apps.health.models import SleepEntry
        yesterday = (now - timedelta(days=1)).date()
        today = now.date()
        sleep = (
            SleepEntry.objects.filter(
                user=user,
                sleep_date__in=[yesterday, today],
            )
            .order_by("-sleep_date")
            .first()
        )
        if sleep:
            signals["sleep_last_night"] = True
            signals["sleep_duration_minutes"] = (
                sleep.asleep_duration_minutes or sleep.total_duration_minutes
            )
            signals["sleep_quality"] = sleep.quality_rating
    except Exception as e:
        logger.debug("UAL sleep collection skipped: %s", e)

    # Sleep target from blueprint
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.objects.filter(
            user=user, is_active=True
        ).first()
        if bp and hasattr(bp, "sleep_target_minutes") and bp.sleep_target_minutes:
            signals["sleep_target_minutes"] = bp.sleep_target_minutes
    except Exception:
        pass

    # Medication
    try:
        from apps.health.models import MedicineLog, Medicine
        today = now.date()
        active_meds = Medicine.objects.filter(
            user=user, medicine_status="active"
        ).exclude(is_prn=True)

        scheduled_today = MedicineLog.objects.filter(
            medicine__in=active_meds,
            scheduled_date=today,
        )
        signals["medications_scheduled"] = scheduled_today.count()
        signals["medications_taken"] = scheduled_today.filter(
            log_status="taken"
        ).count()
        signals["medications_missed"] = scheduled_today.filter(
            log_status__in=["missed", "late"]
        ).count()
    except Exception as e:
        logger.debug("UAL medication collection skipped: %s", e)

    # Active fast
    try:
        from apps.health.models import FastingWindow
        active_fast = FastingWindow.objects.filter(
            user=user, ended_at__isnull=True
        ).first()
        if active_fast:
            elapsed = (now - active_fast.started_at).total_seconds() / 3600
            signals["active_fast"] = {
                "elapsed_hours": round(elapsed, 1),
                "target_hours": active_fast.target_hours,
            }
    except Exception:
        pass

    # Weight trend from SAE
    try:
        from apps.core.ai_state import get_state_value
        signals["weight_trend"] = get_state_value(
            user, "health.weight_trend"
        )
    except Exception:
        pass

    return signals


# ── Mood Signals ─────────────────────────────────────────────────────

def _collect_mood_signals(user, now):
    signals = {
        "current_mood": None,
        "mood_trend": "stable",
        "recent_moods": [],
        "health_keywords_in_journal": [],
        "energy_level": None,
    }

    # Journal mood from SAE
    try:
        from apps.core.ai_state import get_module_state
        journal_state = get_module_state(user, "journal")
        if journal_state:
            signals["current_mood"] = journal_state.get("last_mood")
            dist = journal_state.get("mood_distribution", {})
            if dist:
                signals["recent_moods"] = list(dist.keys())
    except Exception:
        pass

    # Mood trend calculation from recent journal entries
    try:
        from apps.journal.models import JournalEntry
        cutoff = now - timedelta(days=7)
        recent = list(
            JournalEntry.objects.filter(
                user=user,
                created_at__gte=cutoff,
            )
            .exclude(mood__isnull=True)
            .exclude(mood="")
            .order_by("-created_at")
            .values_list("mood", flat=True)[:7]
        )
        if len(recent) >= 3:
            mood_scores = {
                "great": 5, "good": 4, "okay": 3,
                "bad": 2, "terrible": 1,
            }
            scored = [mood_scores.get(m, 3) for m in recent]
            first_half = sum(scored[len(scored) // 2:]) / max(len(scored) // 2, 1)
            second_half = sum(scored[:len(scored) // 2]) / max(len(scored) // 2, 1)
            diff = second_half - first_half
            if diff > 0.5:
                signals["mood_trend"] = "rising"
            elif diff < -0.5:
                signals["mood_trend"] = "falling"
            else:
                signals["mood_trend"] = "stable"
    except Exception:
        pass

    # Health keywords in recent journal
    try:
        from apps.journal.models import JournalEntry
        cutoff = now - timedelta(days=3)
        recent_entries = JournalEntry.objects.filter(
            user=user, created_at__gte=cutoff
        ).values_list("content", flat=True)[:5]

        keywords = [
            "pain", "fatigue", "tired", "exhausted", "stress",
            "anxiety", "anxious", "hurt", "injury", "injured",
            "sick", "nausea", "headache", "migraine", "insomnia",
        ]
        found = set()
        for content in recent_entries:
            if content:
                lower = content.lower()
                for kw in keywords:
                    if kw in lower:
                        found.add(kw)
        signals["health_keywords_in_journal"] = list(found)
    except Exception:
        pass

    return signals


# ── Schedule Signals ─────────────────────────────────────────────────

def _collect_schedule_signals(user, now):
    signals = {
        "capacity_pct": 0,
        "events_today_count": 0,
        "conflicts_detected": False,
        "opportunity_windows": [],
        "heavy_days_ahead": 0,
        "next_4h_events": [],
    }

    # Weekly pressure
    try:
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        pressure = compute_weekly_pressure(user, start_date=now.date(), days=7)
        if pressure:
            day_loads = pressure.get("day_loads", [])
            if day_loads:
                signals["capacity_pct"] = day_loads[0][1] if day_loads[0] else 0
            signals["heavy_days_ahead"] = len(pressure.get("heavy_days", []))
            signals["opportunity_windows"] = pressure.get(
                "opportunity_windows", []
            )[:3]
    except Exception as e:
        logger.debug("UAL schedule collection skipped: %s", e)

    # Today's calendar events
    try:
        from apps.life.models import LifeEvent
        today = now.date()
        today_events = LifeEvent.objects.filter(
            user=user,
            start_date=today,
        ).order_by("start_time")
        signals["events_today_count"] = today_events.count()

        # Next 4 hours
        four_hours = now + timedelta(hours=4)
        for evt in today_events[:10]:
            if evt.start_time:
                from datetime import datetime as dt
                evt_dt = dt.combine(today, evt.start_time)
                try:
                    from django.utils import timezone as tz
                    evt_dt = tz.make_aware(evt_dt, now.tzinfo)
                except Exception:
                    pass
                if now.replace(tzinfo=None) <= evt_dt.replace(tzinfo=None) <= four_hours.replace(tzinfo=None):
                    signals["next_4h_events"].append({
                        "title": evt.title,
                        "time": evt.start_time.strftime("%I:%M %p") if evt.start_time else "all day",
                    })
    except Exception:
        pass

    # Architecture plan blocks for capacity
    try:
        from apps.core.blueprint.models import ArchitecturePlan
        plan = ArchitecturePlan.get_active_for_date(user, now.date())
        if plan:
            blocks = plan.blocks.all().order_by("start_time")
            total_minutes = sum(
                (b.end_time.hour * 60 + b.end_time.minute)
                - (b.start_time.hour * 60 + b.start_time.minute)
                for b in blocks
                if b.start_time and b.end_time
            )
            waking_minutes = 16 * 60
            signals["capacity_pct"] = max(
                signals["capacity_pct"],
                round((total_minutes / waking_minutes) * 100, 1),
            )
    except Exception:
        pass

    return signals


# ── Drift Signals ────────────────────────────────────────────────────

def _collect_drift_signals(user):
    signals = {
        "drift_score": 0,
        "drift_probability_24h": 0,
        "drift_probability_72h": 0,
        "drift_events_today": 0,
        "non_negotiables_missed": 0,
        "pillar_scores": {},
    }

    try:
        from apps.core.blueprint.drift_engine import (
            get_drift_summary,
            predict_drift_probability,
        )
        summary = get_drift_summary(user, days=1)
        if summary:
            signals["drift_score"] = summary.get("current_score", 0)
            signals["drift_events_today"] = summary.get("event_count", 0)
            signals["pillar_scores"] = summary.get("pillar_scores", {})

        prob = predict_drift_probability(user)
        if prob:
            signals["drift_probability_24h"] = prob.get(
                "drift_probability_24h", 0
            )
            signals["drift_probability_72h"] = prob.get(
                "drift_probability_72h", 0
            )
    except Exception as e:
        logger.debug("UAL drift collection skipped: %s", e)

    # Non-negotiable misses
    try:
        from apps.core.blueprint.models import DriftEvent
        from django.utils import timezone
        today = _now().date()
        nn_types = ["MED_MISSED", "FAST_BREAK_EARLY", "WORKOUT_SKIPPED",
                     "FAITH_BLOCK_MISSED", "BLOCK_MISSED"]
        signals["non_negotiables_missed"] = DriftEvent.objects.filter(
            user=user, date=today, drift_type__in=nn_types
        ).count()
    except Exception:
        pass

    return signals


# ── Relational Signals ───────────────────────────────────────────────

def _collect_relational_signals(user, now):
    signals = {
        "drifting_relationships": [],
        "tier1_drifting": 0,
        "tier2_drifting": 0,
    }

    try:
        from apps.core.ai_relationships.relationship_engine import (
            detect_relational_drift,
        )
        drift_alerts = detect_relational_drift(user)
        for alert in (drift_alerts or []):
            tier = alert.get("importance_tier", 3)
            signals["drifting_relationships"].append({
                "name": alert.get("person_name", "Unknown"),
                "tier": tier,
                "days_since": alert.get("days_since_contact", 0),
                "cadence": alert.get("cadence_target", "unknown"),
            })
            if tier == 1:
                signals["tier1_drifting"] += 1
            elif tier == 2:
                signals["tier2_drifting"] += 1
    except Exception as e:
        logger.debug("UAL relational collection skipped: %s", e)

    return signals


# ── Upcoming Events ──────────────────────────────────────────────────

def _collect_upcoming_events(user, now):
    events = {
        "significant_next_7d": [],
        "overdue_tasks": 0,
        "approaching_deadlines": 0,
    }

    # Significant events (birthdays, anniversaries)
    try:
        from apps.life.models import SignificantEvent
        for evt in SignificantEvent.objects.filter(user=user):
            days = evt.days_until_next()
            if days is not None and 0 <= days <= 7:
                events["significant_next_7d"].append({
                    "title": evt.title,
                    "type": evt.event_type,
                    "person": evt.person_name or "",
                    "days_until": days,
                    "years": evt.get_years_count(),
                })
    except Exception:
        pass

    # Open loops (overdue tasks)
    try:
        from apps.life.models import Task
        today = now.date()
        events["overdue_tasks"] = Task.objects.filter(
            user=user,
            is_completed=False,
            due_date__lt=today,
        ).count()
        events["approaching_deadlines"] = Task.objects.filter(
            user=user,
            is_completed=False,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=3),
        ).count()
    except Exception:
        pass

    return events


# ── Signal Strength Computation ──────────────────────────────────────

def _compute_signal_strengths(inp, now) -> dict:
    """
    Normalise raw signals into 0-1 strengths for the classifier.
    """
    s = {}

    # Calendar urgency
    next_4h = inp["schedule_signals"].get("next_4h_events", [])
    conflicts = inp["schedule_signals"].get("conflicts_detected", False)
    if not next_4h:
        s["calendar_urgency"] = 0.0
    elif conflicts:
        s["calendar_urgency"] = 0.8
    elif len(next_4h) >= 3:
        s["calendar_urgency"] = 0.6
    else:
        s["calendar_urgency"] = 0.3

    # Deadline pressure
    overdue = inp["upcoming_events"].get("overdue_tasks", 0)
    approaching = inp["upcoming_events"].get("approaching_deadlines", 0)
    s["deadline_pressure"] = min(1.0, (overdue * 0.3) + (approaching * 0.15))

    # Medication risk
    health = inp["health_signals"]
    scheduled = health.get("medications_scheduled", 0)
    missed = health.get("medications_missed", 0)
    taken = health.get("medications_taken", 0)
    if scheduled == 0:
        s["medication_risk"] = 0.0
    elif missed > 0:
        s["medication_risk"] = min(1.0, 0.5 + (missed * 0.25))
    elif taken < scheduled:
        s["medication_risk"] = 0.3  # Pending but not yet missed
    else:
        s["medication_risk"] = 0.0

    # Sleep deficit
    duration = health.get("sleep_duration_minutes")
    target = health.get("sleep_target_minutes", 480)
    if duration is None:
        s["sleep_deficit"] = 0.3  # Unknown = mild concern
    elif duration >= target:
        s["sleep_deficit"] = 0.0
    else:
        ratio = duration / max(target, 1)
        s["sleep_deficit"] = min(1.0, max(0.0, 1.0 - ratio))

    # Injury risk
    injury_kw = inp["mood_signals"].get("health_keywords_in_journal", [])
    injury_terms = {"injury", "injured", "hurt", "pain"}
    has_injury = bool(injury_terms & set(injury_kw))
    s["injury_risk"] = 0.7 if has_injury else 0.0

    # Drift severity
    drift = inp["drift_signals"]
    drift_score = drift.get("drift_score", 0)
    drift_24h = drift.get("drift_probability_24h", 0)
    s["drift_severity"] = min(1.0, (drift_score / 60) + (0.2 if drift_24h > 0.7 else 0))

    # Non-negotiable misses
    nn_missed = drift.get("non_negotiables_missed", 0)
    s["non_negotiable_miss"] = min(1.0, nn_missed * 0.4)

    # Mood decline
    mood_trend = inp["mood_signals"].get("mood_trend", "stable")
    emotional_kw = inp["mood_signals"].get("health_keywords_in_journal", [])
    emotional_terms = {"stress", "anxiety", "anxious", "exhausted", "fatigue", "tired"}
    emotional_count = len(emotional_terms & set(emotional_kw))
    if mood_trend == "falling":
        s["mood_decline"] = 0.6 + min(0.4, emotional_count * 0.15)
    elif mood_trend == "stable" and emotional_count > 0:
        s["mood_decline"] = min(0.5, emotional_count * 0.2)
    else:
        s["mood_decline"] = 0.0

    # Emotional load
    s["emotional_load"] = min(1.0, emotional_count * 0.25)

    # Relationship drift
    rel = inp["relational_signals"]
    t1 = rel.get("tier1_drifting", 0)
    t2 = rel.get("tier2_drifting", 0)
    s["relationship_drift"] = min(1.0, t1 * 0.5 + t2 * 0.2)

    # Relationship event
    sig_events = inp["upcoming_events"].get("significant_next_7d", [])
    if not sig_events:
        s["relationship_event"] = 0.0
    else:
        min_days = min(e.get("days_until", 7) for e in sig_events)
        if min_days == 0:
            s["relationship_event"] = 1.0
        elif min_days == 1:
            s["relationship_event"] = 0.8
        elif min_days <= 3:
            s["relationship_event"] = 0.6
        else:
            s["relationship_event"] = 0.3

    # Schedule overload
    cap = inp["schedule_signals"].get("capacity_pct", 0)
    s["schedule_overload"] = max(0.0, min(1.0, (cap - 50) / 50))

    # Open loops
    open_count = inp["upcoming_events"].get("overdue_tasks", 0)
    if open_count == 0:
        s["open_loop_count"] = 0.0
    elif open_count <= 2:
        s["open_loop_count"] = 0.2
    elif open_count <= 5:
        s["open_loop_count"] = 0.4
    elif open_count <= 10:
        s["open_loop_count"] = 0.6
    else:
        s["open_loop_count"] = 0.8

    return s
