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
from apps.health.services.weight_summary import build_weight_summary


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
    model decides what they mean (no verdicts, no 'on track')."""
    facts = build_weight_summary(user, point_date=(params or {}).get("point"))
    if not facts:
        return {"title": "Weight", "kind": "weight overview",
                "content": "Weight overview — no weight entries logged yet."}

    lines = [f"Current weight: {facts['current_lb']} lb (as of {_d(facts['current_at'])})"]
    if facts.get("avg_30d_lb") is not None:
        lines.append(
            f"Last {facts['window_days']} days — average {facts['avg_30d_lb']} lb, "
            f"low {facts['low_30d_lb']} lb, high {facts['high_30d_lb']} lb "
            f"({facts['window_count']} entries)"
        )
    if facts.get("total_change_lb") is not None:
        tc = facts["total_change_lb"]
        lines.append(
            f"Total change (all recorded): {facts['first_lb']} lb on {_d(facts['first_at'])} "
            f"→ {facts['current_lb']} lb on {_d(facts['current_at'])} "
            f"= {'+' if tc > 0 else ''}{tc} lb"
        )
    lines.append(f"Entries logged: {facts['count']}")
    lines.append(f"Chart date range shown: {_d(facts['first_at'])} – {_d(facts['current_at'])}")
    if facts.get("point_lb") is not None:
        lines.append(f"Selected point: {facts['point_lb']} lb on {_d(facts['point_at'])}")

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
