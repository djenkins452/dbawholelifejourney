"""Chief-of-Staff recommendation tracking + effectiveness (2026-06-21).

Turns Beth from a recommendation engine into an OUTCOME engine: records the
executive layer's current top constraint as a GuidanceItem with a baseline
metric snapshot, and later evaluates whether the metric actually moved —
"three weeks ago I flagged sleep (5.8h); it's now 6.6h, and your weight is down
4.2 lb. This appears to be working."

Reuses the existing GuidanceItem model — NO schema change. Everything the
tracker needs (domain, baseline metric, baseline date) lives in the `evidence`
JSON field. Grounded + plausibility-guarded; never fabricates a delta.
"""
import logging
from datetime import date, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

REC_TYPE = "cos_constraint"
_FLAT = {"sleep": 0.3, "weight": 1.0, "glucose": 5.0}


def _current_metric(user, domain):
    """(value, unit, lower_is_better) for the domain's headline metric, or None.
    Plausibility-guarded (e.g. sub-3h sleep fragments excluded)."""
    try:
        now = timezone.now()
        if domain == "sleep":
            from apps.health.models import SleepEntry
            qs = SleepEntry.objects.filter(
                user=user, sleep_date__gt=(now - timedelta(days=7)).date())
            vals = [e.total_duration_minutes / 60 for e in qs
                    if e.total_duration_minutes
                    and 3.0 <= e.total_duration_minutes / 60 <= 12.0]
            return (round(sum(vals) / len(vals), 1), "h", False) if vals else None
        if domain == "weight":
            from apps.health.models import WeightEntry
            last = WeightEntry.objects.filter(
                user=user, status="active").order_by("recorded_at").last()
            return (round(float(last.value_in_lb), 1), " lb", True) if last else None
        if domain == "glucose":
            from django.db.models import Avg
            from apps.health.models import GlucoseEntry
            a = GlucoseEntry.objects.filter(
                user=user, recorded_at__gte=now - timedelta(days=7)
            ).aggregate(a=Avg("value"))["a"]
            return (round(float(a)), " mg/dL", True) if a is not None else None
    except Exception:
        logger.warning("cos_rec: current metric failed (%s)", domain, exc_info=True)
    return None


def _weight_lb_on_or_before(user, the_date):
    from apps.health.models import WeightEntry
    e = (WeightEntry.objects.filter(user=user, status="active",
                                    recorded_at__date__lte=the_date)
         .order_by("recorded_at").last())
    return round(float(e.value_in_lb), 1) if e else None


def record_top_recommendation(user):
    """Idempotently record the current top constraint as an active CoS
    recommendation (one per domain). Keeps the ORIGINAL baseline if one already
    exists — so effectiveness is measured from when the focus first started.
    Read-only-safe to call from a coaching answer; never raises."""
    try:
        from apps.core.cos_briefing.executive_state import (
            build_executive_state_signals, select_executive_lenses)
        from apps.core.ai_guidance.models import GuidanceItem
        picks = select_executive_lenses(build_executive_state_signals(user))
        opp = picks.get("biggest_opportunity") or picks.get("biggest_decline")
        if not opp:
            return None
        domain = opp.domain
        existing = GuidanceItem.objects.filter(
            user=user, guidance_type=REC_TYPE, module=domain,
            is_active=True).first()
        if existing:
            return existing  # preserve original baseline
        metric = _current_metric(user, domain)
        ev = {"domain": domain,
              "baseline_date": timezone.now().date().isoformat()}
        if metric:
            ev["baseline_value"], ev["unit"] = metric[0], metric[1]
            ev["lower_better"] = metric[2]
        return GuidanceItem.objects.create(
            user=user, title=f"Focus: {domain}",
            message=(opp.message or opp.title or f"Focus on {domain}."),
            guidance_type=REC_TYPE, source="composite", module=domain,
            priority=2, evidence=ev)
    except Exception:
        logger.warning("cos_rec: record failed", exc_info=True)
        return None


def _days_since(iso):
    try:
        return (timezone.now().date() - date.fromisoformat(iso)).days
    except Exception:
        return None


def evaluate_active_recommendations(user):
    """Did the focus work? Compares each active recommendation's target metric
    now vs its baseline, plus the cross-domain weight outcome. Returns a coaching
    string, or None when nothing has been recorded yet."""
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        recs = list(GuidanceItem.objects.filter(
            user=user, guidance_type=REC_TYPE, is_active=True).order_by("id"))
    except Exception:
        return None
    if not recs:
        return None
    lines = []
    for rec in recs[:2]:
        ev = rec.evidence or {}
        domain = ev.get("domain") or rec.module
        days = _days_since(ev.get("baseline_date", ""))
        when = f"{days} days ago" if days else "recently"
        bval = ev.get("baseline_value")
        unit = ev.get("unit", "")
        lower_better = ev.get("lower_better", False)
        cur = _current_metric(user, domain)
        if bval is None or cur is None:
            lines.append(f"{when.capitalize()} I flagged {domain} as your "
                         f"constraint, but I don't have a clean before/after "
                         f"metric for it yet.")
            continue
        now_val = cur[0]
        delta = round(now_val - bval, 1)
        flat = abs(delta) < _FLAT.get(domain, 0.3)
        improved = (delta < 0) if lower_better else (delta > 0)
        verdict = ("this appears to be working — keep it up" if improved and not flat
                   else "it hasn't moved — time for a different approach" if flat
                   else "it's gone the wrong way — let's change tack")
        s = (f"{when.capitalize()} I flagged {domain} as your constraint "
             f"({bval}{unit}); it's now {now_val}{unit}")
        # Cross-domain outcome: weight movement since the baseline date.
        if domain != "weight":
            w_then = _weight_lb_on_or_before(user, ev.get("baseline_date"))
            w_now = _current_metric(user, "weight")
            if w_then is not None and w_now is not None:
                wd = round(w_now[0] - w_then, 1)
                if abs(wd) >= 1.0:
                    s += (f", and your weight is "
                          f"{'down' if wd < 0 else 'up'} {abs(wd)} lb")
        lines.append(s + f". {verdict.capitalize()}.")
    return " ".join(lines)


def list_recommendations(user):
    """What has Beth been steering Danny toward lately?"""
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        recs = list(GuidanceItem.objects.filter(
            user=user, guidance_type=REC_TYPE, is_active=True).order_by("id"))
    except Exception:
        recs = []
    if not recs:
        return ("I haven't locked in a standing recommendation yet — ask me for "
                "a read ('what's the highest-leverage thing I can do?') and I'll "
                "set the focus and track whether it works.")
    bits = []
    for r in recs:
        ev = r.evidence or {}
        d = ev.get("domain") or r.module
        bd = ev.get("baseline_date")
        bits.append(d + (f" (since {bd})" if bd else ""))
    return "Lately I've been steering you toward: " + "; ".join(bits) + "."
