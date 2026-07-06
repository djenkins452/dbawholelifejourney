"""Significant Event Pipeline (v1) — the Chief-of-Staff reflex.

Origin (production capability gap, 2026-07-02): Danny hit the "France 2027
Family 18K Mission" weight milestone (283.1 lb against a 284.9 lb target,
achieved two days after the June 30 due date). The dashboard number updated, but
nothing recognized this as *mission-significant* until the 3-hour CoS Event
Engine scheduler happened to run. A production-ready Chief of Staff must react in
the moment: recognize the event, determine why it matters, update dependent
truth, notify appropriately, and re-evaluate the plan — WITHOUT waiting for a
scheduler.

Design (framework-first, additive — NO new model, NO parallel system):

  1. DEFINE — significance is defined here (which domain events are
     mission-significant): milestone / goal completion.
  2. EVALUATE ON THE BUS — significance is evaluated on the existing domain event
     bus via subscribers in ``apps/core/events/subscribers.py``, which ENQUEUE the
     reaction on a background worker so the request path stays fast (per the
     Observability Performance Law — never compute heavy work on the request
     path).
  3. REACT — the reaction reuses existing substrate:
       • the CoS Event Engine's ``GuidanceItem`` persistence (so the event
         appears in Beth's standing read via ``recent_cos_events`` and in the
         notification center for free),
       • the DNE (``deliver_single``) for delivery through existing channels +
         policies (quiet hours / throttle / dedupe / orchestrator),
       • ``goal_pace`` for the re-plan (the next milestone / next step).

The achievement is persisted as a MAJOR WIN under a STICKY dedupe key
(``cos_event:win:milestone:<id>``) which the CoS Event Engine's re-detection
auto-resolve explicitly exempts (see ``_WIN_PREFIX`` in ``cos_event_engine``): a
one-time achievement is true forever and must not be resolved just because it
isn't "re-detected" on the next scan.

Backstop: if the enqueue fails (broker down), the 3-hour CoS Event Engine still
catches the strategic layer up later — degraded, not broken.
"""
import logging

from apps.core.events.domain_events import EventTypes

logger = logging.getLogger(__name__)


# ── 1. DEFINE mission-significant events ─────────────────────────────────
# v1 scope: milestone / goal completion. A milestone or goal *reaching
# completion* is intrinsically significant — significant by identity, not by a
# threshold. (Threshold-significant events — a metric crossing a risk band — are
# a documented phased follow-on; see docs/SIGNIFICANT_EVENT_PIPELINE.md.)
SIGNIFICANT_EVENT_TYPES = frozenset({
    EventTypes.PURPOSE_MILESTONE_COMPLETED,
    EventTypes.PURPOSE_GOAL_COMPLETED,
})


def is_significant_event_type(event_type):
    """Cheap membership check used by the enqueue gate."""
    return event_type in SIGNIFICANT_EVENT_TYPES


def classify_significance(user, event_type, data):
    """DETERMINE significance. Return a verdict dict, or None if not significant.

    verdict = {kind, is_mission, priority, milestone_id, goal_id}
      kind ∈ {"mission_milestone", "goal_milestone", "goal_completed"}
      is_mission — the affected goal is the user's Primary Mission.
      priority   — 2 for mission events (surfaces first), 3 otherwise.
    Never raises."""
    if event_type not in SIGNIFICANT_EVENT_TYPES:
        return None
    data = data or {}
    goal_id = data.get("goal_id")
    is_mission = _is_mission_goal(user, goal_id)
    if event_type == EventTypes.PURPOSE_GOAL_COMPLETED:
        kind = "goal_completed"
    else:
        kind = "mission_milestone" if is_mission else "goal_milestone"
    return {
        "kind": kind,
        "is_mission": is_mission,
        "priority": 2 if is_mission else 3,
        "milestone_id": data.get("milestone_id"),
        "goal_id": goal_id,
    }


def _is_mission_goal(user, goal_id):
    if not goal_id:
        return False
    try:
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.filter(
            pk=goal_id, user=user, is_primary_mission=True).exists()
    except Exception:
        return False


# ── 2/8. REACT — the Chief-of-Staff reflex ───────────────────────────────

def react_to_significant_event(user, event_type, data=None):
    """Detect → judge → update dependent truth → persist → notify → re-plan.

    Runs in a background worker (``react_to_significant_event_task``). Returns a
    summary dict for observability + acceptance tests. Never raises."""
    data = data or {}
    summary = {"significant": False, "ok": False}
    try:
        verdict = classify_significance(user, event_type, data)
        if verdict is None:
            return summary
        summary.update({"significant": True, "kind": verdict["kind"],
                        "is_mission": verdict["is_mission"]})

        # ── 4. REFRESH dependent truth (generalizes the 3-health-event PIE
        #        pass to mission events; invalidates SAE + CoS caches). ──
        _refresh_dependent_truth(user)

        # Mission / goal context + derived progress count (e.g. 2/12).
        goal = None
        gid = verdict.get("goal_id")
        if gid:
            try:
                from apps.purpose.models import LifeGoal
                goal = LifeGoal.objects.filter(pk=gid).first()
            except Exception:
                goal = None
        done, total = _mission_progress(goal)
        summary["mission_progress"] = {"completed": done, "total": total}

        # ── 8. RE-PLAN — recompute pace + surface the NEXT milestone. ──
        next_ms = _next_planning_step(user)
        summary["next_milestone"] = next_ms

        # ── 2/5. PERSIST the significant event (MAJOR WIN) + run the CoS
        #        Event Engine immediately so the strategic layer is fresh NOW
        #        (not in 3h) and Beth's recent_cos_events reflects reality. ──
        item = _persist_major_win(user, verdict, data, goal, (done, total), next_ms)
        summary["event_persisted"] = bool(item)
        if item is not None:
            summary["event_dedupe_key"] = item.dedupe_key
            summary["acknowledgment"] = item.message

        try:
            from apps.ai.cos_event_engine import run_cos_event_engine
            run_cos_event_engine(user)
        except Exception:
            logger.warning("significant_event: cos_event_engine run failed",
                           exc_info=True)

        # ── 6. NOTIFY through existing delivery infra + policies. ──
        if item is not None:
            summary["notified"] = _notify(user, item)

        summary["ok"] = True
        return summary
    except Exception:
        logger.warning("significant_event: reaction failed (type=%s user=%s)",
                       event_type, getattr(user, "id", "?"), exc_info=True)
        return summary


def _refresh_dependent_truth(user):
    """Invalidate SAE + CoS-context caches and run a real-time PIE pass for the
    goals module — the generalization of the 3-health-event real-time PIE pass to
    mission events (goal/milestone completion previously ran NO intelligence
    pass). Fail-soft throughout."""
    try:
        from django.core.cache import cache
        cache.delete(f"wlj:user_state:{user.id}")
    except Exception:
        pass
    try:
        from apps.core.ai_state.tasks import enqueue_module_warm
        enqueue_module_warm(user, "goals")
        enqueue_module_warm(user, "health")
    except Exception:
        logger.warning("significant_event: SAE warm enqueue failed", exc_info=True)
    try:
        from apps.ai.readiness_cache import invalidate_cos_context
        invalidate_cos_context(user)
    except Exception:
        pass
    try:
        from apps.core.ai_insights.insight_engine import run_insights
        from apps.core.time.system_clock import get_current_time
        run_insights(user, {
            "event_type": "record_created", "module": "goals",
            "action": "milestone_completed",
            "timestamp_utc": get_current_time().isoformat(),
        })
    except Exception:
        logger.warning("significant_event: PIE goals pass failed", exc_info=True)


def _mission_progress(goal):
    """Derived (completed, total) milestone counts for a goal. The mission
    progress count (e.g. 2/12) is derived truth — the milestone.completed flip
    the evaluator already performed updates it; nothing to store."""
    if goal is None:
        return 0, 0
    try:
        total = goal.milestones.count()
        done = goal.milestones.filter(completed=True).count()
        return done, total
    except Exception:
        return 0, 0


def _next_planning_step(user):
    """The next milestone / next planning implication, from goal_pace (the same
    computation Beth's standing read uses). Returns a dict or None."""
    try:
        from apps.ai.cos_intelligence import goal_pace
        gp = goal_pace(user) or {}
    except Exception:
        return None
    if gp.get("milestone"):
        return {"title": gp.get("milestone_title"),
                "target_value": gp.get("goal"),
                "target_date": gp.get("target_date"),
                "kind": "milestone"}
    if gp.get("remaining") is not None and gp.get("remaining") <= 1.0 \
            and not gp.get("insufficient"):
        return {"title": "Ultimate goal reached", "kind": "goal_reached",
                "target_value": gp.get("goal")}
    if gp.get("goal") is not None:
        return {"title": "Ultimate weight goal", "target_value": gp.get("goal"),
                "target_date": gp.get("target_date"), "kind": "ultimate"}
    return None


def _persist_major_win(user, verdict, data, goal, progress, next_ms):
    """Persist the achievement as a MAJOR WIN CoSEvent (GuidanceItem) with a
    CoS-quality three-part acknowledgment (what happened / why it matters / what
    to do next), keyed STICKY so re-detection never resolves it. Returns the
    GuidanceItem or None."""
    from apps.ai.cos_event_engine import CoSEvent, MAJOR_WIN, persist_event
    done, total = progress
    title = (data.get("title") or "Milestone reached").strip()
    mission_name = goal.title if goal is not None else "your goal"
    target = data.get("target_value")
    current = data.get("current_weight")
    late = _lateness(data)

    # WHAT HAPPENED — the milestone, named, with the honest evidence (weight vs
    # target, lateness). The progression count is NOT the headline here; it
    # belongs in WHY (framed as meaning), not as a bare "milestone N of M".
    what = f"You hit the “{title}” milestone on {mission_name}"
    if current is not None and target is not None:
        what += f" — you're at {_num(current)} lb against the {_num(target)} lb target"
    if late:
        what += f" ({late})"
    what += "."

    # WHY IT MATTERS — the SAME canonical meaning-first composition the dashboard
    # card uses: the milestone's own meaning (its description, if any) grounded by
    # progression toward THIS mission's purpose (named). Never generic boilerplate.
    from apps.core.mission_commentary import why_it_matters
    why = why_it_matters(
        mission_title=(goal.title if goal is not None else None),
        milestone_description=_milestone_description(verdict, data),
        completed=done, total=total, milestone_title=title,
    ) or "Real progress on the mission you set."

    # WHAT TO DO NEXT (the re-plan, made actionable)
    wd = _what_next(next_ms)

    ev = CoSEvent(MAJOR_WIN, "goal", title, what, why, wd,
                  priority=verdict.get("priority", 2),
                  key=f"win:milestone:{verdict.get('milestone_id') or _slug(title)}")
    try:
        item, _created = persist_event(user, ev)
        meta = dict(item.metadata or {})
        meta.update({
            "significant_event": True, "one_time": True,
            "kind": verdict.get("kind"),
            "mission_progress": {"completed": done, "total": total},
            "next_milestone": next_ms,
        })
        item.metadata = meta
        item.save(update_fields=["metadata", "updated_at"])
        return item
    except Exception:
        logger.warning("significant_event: persist major win failed", exc_info=True)
        return None


def _milestone_description(verdict, data):
    """The completed milestone's OWN description (the user's stated meaning), if
    any — so WHY IT MATTERS can speak to what the milestone means, not a template.
    Fail-soft: returns None when unavailable."""
    mid = (verdict or {}).get("milestone_id") or (data or {}).get("milestone_id")
    if not mid:
        return None
    try:
        from apps.purpose.models import GoalMilestone
        ms = GoalMilestone.objects.filter(pk=mid).only("description").first()
        return ((ms.description or "").strip() or None) if ms is not None else None
    except Exception:
        return None


def _what_next(next_ms):
    if next_ms and next_ms.get("kind") == "milestone" and next_ms.get("title"):
        wd = f"Next: {next_ms['title']} is now active"
        if next_ms.get("target_value") is not None:
            wd += f" ({_num(next_ms['target_value'])} lb)"
        return wd + "."
    if next_ms and next_ms.get("kind") == "goal_reached":
        return ("You've reached the ultimate target — decide on maintenance or a "
                "new goal so the momentum doesn't stall.")
    if next_ms and next_ms.get("target_value") is not None:
        return (f"Next up is the ultimate target of {_num(next_ms['target_value'])} "
                f"lb — keep the routine that got you here pointed at it.")
    return "Set the next milestone so the mission keeps a concrete next target."


def _notify(user, item):
    """Route the win through the DNE (existing channels + delivery policies:
    quiet hours, throttle, dedupe, MessageOrchestrator). The persisted
    GuidanceItem already guarantees the notification-center/bell + Beth
    awareness; DNE adds push / SMS / email per the user's prefs. Fail-soft."""
    payload = {
        "title": f"Chief of Staff: {(item.title or 'Milestone reached')[:70]}",
        "message": (item.message or item.title or "")[:300],
        "priority": item.priority,
        "message_type": "cos_major_win",
        "action_url": "/assistant/", "icon": "🎉",
    }
    try:
        from django.db import transaction
        from apps.core.ai_delivery.delivery_engine import deliver_single
        # Savepoint: the DNE dedupes a repeat send by letting the
        # DeliveredNotification unique-insert fail (IntegrityError). Isolate it so
        # that dedupe signal can NEVER poison the caller's transaction — e.g. a
        # milestone re-completing (weight bounced up then back down) re-enters the
        # reflex; the win is delivered once and the repeat is silently suppressed.
        with transaction.atomic():
            deliver_single(user, "COS", item, payload=payload)
        return True
    except Exception:
        logger.warning("significant_event: DNE deliver_single failed", exc_info=True)
        return False


# ── enqueue (keeps the request path fast) ────────────────────────────────

def enqueue_significant_event_reaction(user, event_type, data=None):
    """Enqueue the reaction on a background worker so the emitting request path
    stays fast. Fail-soft; in Celery-EAGER/test mode it runs inline. If enqueue
    fails, the 3-hour CoS Event Engine remains the backstop."""
    if not getattr(user, "is_authenticated", False):
        return
    if not is_significant_event_type(event_type):
        return
    try:
        from apps.ai.tasks import react_to_significant_event_task
        react_to_significant_event_task.delay(user.id, event_type, data or {})
    except Exception:
        logger.warning("significant_event: enqueue failed (type=%s user=%s)",
                       event_type, getattr(user, "id", "?"), exc_info=True)


# ── small helpers ─────────────────────────────────────────────────────────

def _lateness(data):
    """Human phrase for achieved-vs-target-date: 'on time', 'N days early',
    'N days late'. Empty when either date is missing."""
    from datetime import date
    td, ad = data.get("target_date"), data.get("achieved_date")
    if not (td and ad):
        return ""
    try:
        d = (date.fromisoformat(ad) - date.fromisoformat(td)).days
    except Exception:
        return ""
    if d == 0:
        return "on time"
    n = abs(d)
    unit = "day" if n == 1 else "days"
    return f"{n} {unit} {'early' if d < 0 else 'late'}"


def _num(v):
    """Trim a trailing .0 so 284.0 → '284' but 284.9 stays '284.9'."""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(round(f, 1))
    except Exception:
        return str(v)


def _slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", (text or "item").lower()).strip("-")[:60] or "item"
