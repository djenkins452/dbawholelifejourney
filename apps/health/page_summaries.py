# ==============================================================================
# File: apps/health/page_summaries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context PAGE-SUMMARY providers for Health overview pages.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic page-summary providers for Health overview/dashboard pages.

Registered at app-ready (see HealthConfig.ready). Each provider is user-scoped and
request-path-safe, and returns the uniform {title, content, kind} the assistant consumes
as Current Context focus — the SAME deterministic truth the page renders.
"""
from django.utils import timezone
from django.utils.dateformat import format as _dj_date

from apps.core.current_context import register_page_summary


def _d(dt):
    return _dj_date(timezone.localtime(dt), "M j, Y") if dt else "—"


@register_page_summary("health.home")
def health_home_summary(user, params):
    """The Health Home workspace (physical health overview). Deterministic facts only —
    reads the ONE shared source (build_health_home_summary), the SAME cached SAE health
    snapshot the page renders (`hs`), so the assistant can never contradict the screen.
    WLJ exposes numbers; the model decides what they mean (no verdicts)."""
    from apps.health.services.health_home_summary import build_health_home_summary

    facts = build_health_home_summary(user)

    if facts.get("status") == "pending":
        return {"title": "Health", "kind": "health overview",
                "content": "Your health snapshot — being prepared (up-to-date figures "
                           "load momentarily)."}

    lines = []
    if facts.get("weight_current") is not None:
        line = f"Current weight: {facts['weight_current']:g} lb"
        ch = facts.get("weight_change_30d")
        if ch is not None:
            line += f" ({'+' if ch > 0 else ''}{ch:g} lb over 30 days)"
        lines.append(line)
    if facts.get("sleep_avg_hours_7d") is not None:
        lines.append(f"Sleep (7-day avg): {facts['sleep_avg_hours_7d']:g} hours")
    if facts.get("steps_avg_7d") is not None:
        lines.append(f"Steps (7-day avg): {facts['steps_avg_7d']:g}")
    if facts.get("heart_rate_avg_7d") is not None:
        lines.append(f"Heart rate (7-day avg): {facts['heart_rate_avg_7d']:g} bpm")
    if facts.get("glucose_latest") is not None:
        line = f"Glucose (latest): {facts['glucose_latest']:g}"
        if facts.get("glucose_avg_7d") is not None:
            line += f" (7-day avg {facts['glucose_avg_7d']:g})"
        lines.append(line)
    if facts.get("bp_systolic") is not None and facts.get("bp_diastolic") is not None:
        lines.append(f"Blood pressure (latest): {facts['bp_systolic']:g}/{facts['bp_diastolic']:g}")
    if facts.get("water_today_oz") is not None:
        line = f"Water today: {facts['water_today_oz']:g} oz"
        if facts.get("water_goal_oz"):
            line += f" of {facts['water_goal_oz']:g} oz goal"
        lines.append(line)
    if facts.get("medication_status") and facts["medication_status"] != "no_data":
        lines.append(f"Medication status: {facts['medication_status']}")

    if not lines:
        return {"title": "Health", "kind": "health overview",
                "content": "Health overview — no health metrics logged yet."}

    return {"title": "Health", "kind": "health overview",
            "content": "Health overview\n" + "\n".join(lines)}


@register_page_summary("health.weight")
def weight_page_summary(user, params):
    """The Weight overview page. Deterministic facts only — WLJ exposes the numbers; the
    model decides what they mean (no verdicts, no 'on track').

    Mirrors the SELECTED time range the user is actually looking at: the same range the
    page persisted (or an explicit `range` param) feeds the SAME range summary the page
    renders, so the assistant can never say '2 years' while the graph shows 6 months."""
    from apps.core.trend_range import get_saved_range, normalize_range
    from apps.health.services import weight_queries
    from apps.health.services.weight_summary import build_weight_range_summary

    params = params or {}
    range_key = normalize_range(params.get("range"),
                                default=get_saved_range(user, "health.weight"))
    facts = build_weight_range_summary(user, range_key=range_key)
    if not facts:
        return {"title": "Weight", "kind": "weight overview",
                "content": "Weight overview — no weight entries logged yet."}

    label = facts["range_label"]
    lines = [
        f"Selected range: {label}",
        f"Current weight: {facts['current_lb']} lb (as of {_d(facts['current_at'])})",
    ]
    if facts.get("has_range_data") and facts.get("avg_lb") is not None:
        lines.append(
            f"{label} — average {facts['avg_lb']} lb, "
            f"low {facts['low_lb']} lb, high {facts['high_lb']} lb "
            f"({facts['count']} weigh-in{'s' if facts['count'] != 1 else ''})"
        )
        lines.append(
            f"Range shown: {_d(facts['first_at'])} – {_d(facts['last_at'])} "
            f"({facts['first_lb']} lb → {facts['last_lb']} lb)"
        )
        if facts.get("total_change_lb") is not None:
            tc = facts["total_change_lb"]
            lines.append(f"Total change over {label}: {'+' if tc > 0 else ''}{tc} lb")
    else:
        lines.append(f"No weigh-ins recorded in the selected range ({label}).")
    lines.append(f"Entries logged (all time): {facts['total_count']}")

    # Optional selected chart point — a deterministic lookup of that calendar day.
    point = params.get("point")
    if point:
        from datetime import date as _date
        try:
            pd = _date.fromisoformat(point)
        except (TypeError, ValueError):
            pd = None
        rec = weight_queries.on_date(user, pd) if pd else None
        if rec is not None:
            lines.append(f"Selected point: {rec['value_lb']} lb on {_d(rec['recorded_at'])}")

    return {"title": "Weight", "kind": "weight overview",
            "content": "Weight overview\n" + "\n".join(lines)}


@register_page_summary("health.nutrition")
def nutrition_page_summary(user, params):
    """The Nutrition Home page. Deterministic facts only — the SAME composition the page
    renders (build_nutrition_summary), so the assistant can never contradict the screen.
    WLJ exposes totals/targets/progress numbers; the model decides what they mean."""
    from apps.health.services.nutrition_summary import build_nutrition_summary

    point = (params or {}).get("date")
    target_date = None
    if point:
        try:
            import datetime
            target_date = datetime.date.fromisoformat(point)
        except (ValueError, TypeError):
            target_date = None

    facts = build_nutrition_summary(user, target_date=target_date)
    # facts["date"] is a datetime.date (not a datetime); format it directly — _d()
    # routes through timezone.localtime() which only accepts aware datetimes.
    day = _dj_date(facts["date"], "M j, Y")

    if not facts["has_entries"]:
        return {"title": "Nutrition", "kind": "nutrition overview",
                "content": f"Nutrition overview — no food logged for {day}."}

    t = facts["totals"]
    lines = [
        f"Date: {day}",
        f"Logged: {facts['entry_count']} food {'entry' if facts['entry_count'] == 1 else 'entries'}",
        (f"Totals so far — {t['calories']:g} cal, {t['protein_g']:g} g protein, "
         f"{t['carbs_g']:g} g carbs, {t['fat_g']:g} g fat "
         f"(fiber {t['fiber_g']:g} g, sugar {t['sugar_g']:g} g)"),
    ]

    targets = facts.get("targets")
    progress = facts.get("progress") or {}
    if targets:
        def _line(label, key, unit):
            tgt = targets.get(key)
            if not tgt:
                return None
            pct = progress.get(key)
            return f"{label}: {t[key]:g}{unit} of {tgt}{unit} target" + (
                f" ({pct}%)" if pct is not None else "")
        for text in (
            _line("Calories", "calories", " cal"),
            _line("Protein", "protein_g", " g"),
            _line("Carbs", "carbs_g", " g"),
            _line("Fat", "fat_g", " g"),
        ):
            if text:
                lines.append(text)
    else:
        lines.append("No nutrition targets set.")

    return {"title": "Nutrition", "kind": "nutrition overview",
            "content": "Nutrition overview\n" + "\n".join(lines)}


def _g2(v):
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def _metric_page_summary(user, *, title, kind, history_metric,
                         target_metric=None, window="last_7_days"):
    """Reusable Current Context for a simple health metric overview page — composes the
    SAME deterministic truth the CoS retrieves (history + trend, and adherence when a
    target exists), so 'look at this page' answers without retrieval and can never
    contradict the screen. Facts only; the model interprets. Request-path-safe (a couple
    of indexed grouped reads)."""
    from apps.core.truth.domain import get_domain_truth
    truth = get_domain_truth(user, "health")
    try:
        d = truth.history(history_metric, window).to_dict()
    except Exception:
        d = {"present": False}
    if not d.get("present"):
        return {"title": title, "kind": kind,
                "content": f"{title} — no data logged in the last week."}
    unit = d.get("unit") or ""
    pts = d.get("points") or []
    latest = pts[-1] if pts else None
    lines = []
    if latest:
        lines.append(f"Most recent: {_g2(latest['value'])} {unit} (on {latest['date']}).")
    lines.append(f"Last 7 days: average {_g2(d['average'])} {unit} "
                 f"over {d['count']} day{'s' if d['count'] != 1 else ''}.")
    ch = d.get("change")
    if ch and ch.get("direction"):
        seg = f"Trend: {ch['direction']}"
        if ch.get("delta") is not None:
            seg += f" ({'+' if ch['delta'] > 0 else ''}{_g2(ch['delta'])} {unit} across the window)"
        lines.append(seg + ".")
    if target_metric:
        try:
            from apps.ai.cos_services.domain_adherence import get_domain_adherence
            a = get_domain_adherence(user, "health", target_metric, period=window)
            if a.get("status") == "ready":
                tgt = a["target"]
                lines.append(
                    f"Target {_g2(tgt['value'])} {tgt['unit']}: averaging "
                    f"{_g2(a['actual']['avg_daily'])} ({a['variance']['pct_of_target']}% "
                    f"of target).")
        except Exception:
            pass
    return {"title": title, "kind": kind, "content": f"{title}\n" + "\n".join(lines)}


@register_page_summary("health.steps")
def steps_page_summary(user, params):
    return _metric_page_summary(user, title="Steps", kind="steps overview",
                                history_metric="steps", target_metric="steps")


@register_page_summary("health.heart_rate")
def heart_rate_page_summary(user, params):
    return _metric_page_summary(user, title="Heart Rate", kind="heart rate overview",
                                history_metric="resting_heart_rate")


@register_page_summary("health.water")
def water_page_summary(user, params):
    return _metric_page_summary(user, title="Water", kind="hydration overview",
                                history_metric="water", target_metric="water")


@register_page_summary("health.blood_pressure")
def blood_pressure_page_summary(user, params):
    return _metric_page_summary(user, title="Blood Pressure",
                                kind="blood pressure overview",
                                history_metric="bp_systolic")


@register_page_summary("health.sleep")
def sleep_page_summary(user, params):
    return _metric_page_summary(user, title="Sleep", kind="sleep overview",
                                history_metric="sleep")


@register_page_summary("health.blood_oxygen")
def blood_oxygen_page_summary(user, params):
    return _metric_page_summary(user, title="Blood Oxygen", kind="blood oxygen overview",
                                history_metric="spo2")


@register_page_summary("health.fitness")
def fitness_page_summary(user, params):
    return _metric_page_summary(user, title="Fitness", kind="fitness overview",
                                history_metric="workouts")


@register_page_summary("health.glucose")
def glucose_page_summary(user, params):
    """The Glucose dashboard. Deterministic facts only — reads the ONE producer
    (build_glucose_page_summary → glucose_reading_window), the SAME intra-day reading
    truth the page renders, so the assistant answers 'look at this page' and 'my lows
    overnight' WITHOUT retrieval and can never contradict the screen. WLJ exposes the
    readings/numbers; the model decides what they mean (no verdicts)."""
    from apps.health.services.glucose_readings import build_glucose_page_summary

    return build_glucose_page_summary(user)


@register_page_summary("health.body_intelligence")
def body_intelligence_page_summary(user, params):
    """The Body Intelligence dashboard. Deterministic facts only — the SAME composition
    the page renders (build_body_intelligence), so the assistant can never contradict
    the screen. WLJ exposes numbers; the model decides what they mean."""
    from apps.health.services.body_intelligence import build_body_intelligence

    bi = build_body_intelligence(user)
    if not bi.get("has_any_data"):
        return {"title": "Body Intelligence", "kind": "body intelligence overview",
                "content": "Body Intelligence — no measurements, weigh-ins, or check-ins "
                           "logged yet."}

    lines = [bi["headline"]["primary"]]
    lines.extend(bi["headline"].get("supporting", []))

    snap = bi.get("snapshot") or {}
    if snap.get("latest_date"):
        lines.append(f"Latest measurements logged: {_d(snap['latest_date'])}"
                     + (f" (previous {_d(snap['previous_date'])})" if snap.get("previous_date") else ""))
    sess = bi.get("sessions") or {}
    if sess.get("count"):
        latest_sess = sess.get("latest") or {}
        detail = f"Check-ins recorded: {sess['count']}"
        if latest_sess.get("checked_in_at"):
            detail += f" (latest {_d(latest_sess['checked_in_at'])})"
        lines.append(detail)
        photo_ct = latest_sess.get("photo_count") or 0
        if photo_ct:
            lines.append(f"Progress photos in latest check-in: {photo_ct}")

    # Windowed weight change lenses (facts).
    for w in bi.get("trend_windows") or []:
        ch = w.get("change")
        if ch:
            lines.append(f"{w['label']} weight change: "
                         f"{'+' if ch['delta'] > 0 else ''}{ch['delta']:g} lb")

    # Derived-truth freshness (Truth Presentation Contract, Dimension 2). If the
    # summaries these trends read from are still catching up with a recent sync,
    # state that as a fact so the model never presents them as fully current.
    fresh = bi.get("freshness") or {}
    if fresh.get("is_updating"):
        lines.append("Note: these trends/scores are still updating from a recent "
                     "sync and may not yet reflect the latest data.")

    return {"title": "Body Intelligence", "kind": "body intelligence overview",
            "content": "Body Intelligence overview\n" + "\n".join(lines)}
