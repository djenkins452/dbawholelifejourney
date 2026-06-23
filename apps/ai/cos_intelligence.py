"""Unified Chief-of-Staff intelligence (2026-06-21).

ONE brain, consumed two ways so there are no silos and no trigger phrases:

  1. Injected into the CoS system context (cos_context.build_cos_context) so
     Beth's NORMAL LLM conversation always carries her standing read — the
     current constraint, whether the recommendation is working, goal pace, and
     the overall assessment. Any phrasing gets Chief-of-Staff reasoning.
  2. Callable directly by deterministic routes for guaranteed-grounded fast
     answers.

Everything here is a thin, grounded composition over existing engines
(executive_summary, cos_recommendations, weight history). No new model.
Goal-pace (Capability 5) is the one genuinely new computation.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def goal_pace(user):
    """Capability 5 — weight-goal trajectory from real history.

    Returns current pace, projected completion, and required pace vs the target
    date, or None if there's no goal / not enough history. Never raises."""
    try:
        from apps.health.models import HealthProfile, WeightEntry
        hp = HealthProfile.objects.filter(user=user).first()
        wp = hp.get_weight_progress() if hp else None
        qs = WeightEntry.objects.filter(
            user=user, status="active").order_by("recorded_at")
        first, last = qs.first(), qs.last()
        if not (first and last):
            return None
        cur = round(float(last.value_in_lb), 1)

        # GOAL SELECTION: pace runs against the NEAREST INCOMPLETE weight
        # MILESTONE (the near-term target), not the ultimate destination. The
        # ultimate goal is kept only as strategic context.
        milestone = _nearest_weight_milestone(user)
        ultimate = round(float(wp["goal"]), 1) if (wp and wp.get("goal")) else None
        if milestone is not None:
            goal = round(float(milestone.objective_target_value), 1)
            target = milestone.target_date
            out_extra = {
                "milestone": True,
                "milestone_title": milestone.title,
                "strategic_objective": (milestone.goal.title
                                        if milestone.goal_id else None),
                "ultimate_goal": ultimate,
            }
        elif ultimate is not None:
            goal = ultimate
            target = wp.get("target_date")
            out_extra = {"milestone": False}
        else:
            return None  # no goal or milestone to pace against

        remaining = round(abs(cur - goal), 1)
        direction = ("lose" if goal < cur else "gain" if goal > cur else "maintain")
        out = {"current": cur, "goal": goal, "remaining": remaining,
               "direction": direction}
        out.update(out_extra)
        out["target_date"] = target.isoformat() if target else None

        days = (last.recorded_at.date() - first.recorded_at.date()).days
        if days < 7:
            out["insufficient"] = True
            return out
        # Positive pace = moving toward goal (loss for a 'lose' goal).
        toward = (float(first.value_in_lb) - cur) if direction != "gain" \
            else (cur - float(first.value_in_lb))
        pace = round(toward / days * 7, 2)
        out["current_pace_lb_wk"] = pace
        if pace > 0 and remaining > 0:
            weeks = remaining / pace
            out["weeks_to_goal"] = round(weeks, 1)
            out["projected_date"] = (
                timezone.now().date() + timedelta(weeks=weeks)).isoformat()
        if target and remaining > 0:
            days_left = (target - timezone.now().date()).days
            if days_left <= 0:
                out["target_passed"] = True
            else:
                req = round(remaining / days_left * 7, 2)
                out["required_pace_lb_wk"] = req
                out["days_to_target"] = days_left
                out["on_pace"] = pace >= req
        return out
    except Exception:
        logger.warning("cos_intel: goal_pace failed", exc_info=True)
        return None


def _nearest_weight_milestone(user):
    """The nearest INCOMPLETE weight milestone (objective_metric='weight_lb'),
    ordered by target_date — the near-term target pace should run against.
    Returns a GoalMilestone or None. Never raises."""
    try:
        from apps.purpose.models import GoalMilestone
        return (GoalMilestone.objects.select_related("goal").filter(
            goal__user=user, completed=False, objective_metric="weight_lb",
            objective_target_value__isnull=False, target_date__isnull=False)
            .order_by("target_date").first())
    except Exception:
        logger.debug("cos_intel: milestone lookup failed", exc_info=True)
        return None


def goal_pace_narrative(p):
    if not p:
        return None
    # Milestone-aware framing: lead with the near-term milestone, keep the
    # ultimate goal as strategic context.
    if p.get("milestone"):
        head = (f"Your nearest milestone is {p['goal']} lb by {p['target_date']} "
                f"— {p['remaining']} lb to go")
        if p.get("days_to_target"):
            head += f" in {p['days_to_target']} days"
        head += ". "
        pace = p.get("current_pace_lb_wk")
        if p.get("insufficient"):
            s = head + "Not enough recent weight history to judge the pace yet."
        elif p.get("target_passed"):
            s = head + f"That date ({p['target_date']}) has passed — worth resetting it."
        elif p.get("on_pace") is True:
            s = head + (f"You're on track (need ~{p.get('required_pace_lb_wk')} "
                        f"lb/week, doing {pace}).")
        elif p.get("on_pace") is False and (p.get("remaining") or 99) <= 3:
            s = head + (f"It needs ~{p.get('required_pace_lb_wk')} lb/week "
                        f"(currently {pace}) — a small push gets you there.")
        elif p.get("on_pace") is False:
            s = head + (f"At {pace} lb/week you're behind the ~"
                        f"{p.get('required_pace_lb_wk')} lb/week needed — lift the "
                        f"rate or move the date.")
        else:
            s = head.strip()
        if p.get("strategic_objective"):
            s += f" This milestone supports your broader goal: {p['strategic_objective']}."
        return s.strip()
    head = f"Weight {p['current']} → goal {p['goal']} lb ({p['remaining']} to go). "
    if p.get("insufficient"):
        return head + "Not enough weight history yet to project a pace."
    pace = p.get("current_pace_lb_wk")
    s = head
    if pace and pace > 0:
        s += f"Current pace ~{pace} lb/week"
        if p.get("projected_date"):
            s += (f"; at that rate you'd reach goal around {p['projected_date']} "
                  f"(~{p['weeks_to_goal']} weeks)")
        s += ". "
    elif pace is not None and pace <= 0:
        s += "Weight isn't trending toward the goal right now. "
    if p.get("target_passed"):
        s += f"Your target date ({p['target_date']}) has already passed — worth resetting it."
    elif p.get("on_pace") is True:
        s += (f"You're ON pace for {p['target_date']} "
              f"(need ~{p['required_pace_lb_wk']} lb/week, doing {pace}).")
    elif p.get("on_pace") is False:
        s += (f"To hit {p['target_date']} you'd need ~{p['required_pace_lb_wk']} "
              f"lb/week (currently {pace}) — behind pace, so either lift the rate "
              f"or move the date.")
    return s.strip()


def build_cos_intelligence(user):
    """The standing Chief-of-Staff read: overall, goal pace, recommendation
    effectiveness. Compact + grounded; safe to embed in the LLM context."""
    intel = {}
    try:
        p = goal_pace(user)
        if p:
            intel["goal_pace"] = p
            intel["goal_pace_narrative"] = goal_pace_narrative(p)
    except Exception:
        logger.debug("cos_intel: pace block failed", exc_info=True)
    try:
        from apps.ai.cos_recommendations import evaluate_active_recommendations
        eff = evaluate_active_recommendations(user)
        if eff:
            intel["recommendation_effectiveness"] = eff
    except Exception:
        logger.debug("cos_intel: rec block failed", exc_info=True)
    try:
        from apps.core.cos_briefing.executive_summary import build_executive_summary
        es = build_executive_summary(user) or {}
        lenses = es.get("executive_lenses", {}) or {}
        if lenses.get("overall"):
            intel["overall"] = lenses["overall"]
        if lenses.get("chief_of_staff_briefing"):
            intel["briefing"] = lenses["chief_of_staff_briefing"]
    except Exception:
        logger.debug("cos_intel: executive block failed", exc_info=True)
    try:
        from apps.ai.cos_event_engine import recent_cos_events
        evs = recent_cos_events(user)
        if evs:
            intel["events"] = evs
    except Exception:
        logger.debug("cos_intel: events block failed", exc_info=True)
    return intel


def cos_intelligence_narrative(intel):
    """Render the standing read as a prompt section (None if nothing grounded)."""
    if not intel:
        return None
    lines = []
    if intel.get("overall"):
        lines.append(f"- Overall read: {intel['overall']}")
    if intel.get("goal_pace_narrative"):
        lines.append(f"- Goal pace: {intel['goal_pace_narrative']}")
    if intel.get("recommendation_effectiveness"):
        lines.append(f"- Recommendation status: {intel['recommendation_effectiveness']}")
    for e in (intel.get("events") or [])[:3]:
        tag = (e.get("category") or "").replace("_", " ")
        recur = ""
        if int(e.get("occurrence_count", 1)) >= 3:
            recur = f" (flagged {e['occurrence_count']}x)"
        lines.append(f"- Event [{tag}]{recur}: {e.get('message') or e.get('title')}")
    if not lines:
        return None
    return ("CHIEF OF STAFF STANDING READ (your own current assessment — use it "
            "to answer naturally; do not wait to be asked):\n" + "\n".join(lines))
