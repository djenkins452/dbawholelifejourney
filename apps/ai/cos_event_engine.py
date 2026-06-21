"""Chief of Staff Event Engine (2026-06-21).

ONE engine that notices important things and tells Danny before he asks.

Detects Chief-of-Staff events across six categories and PERSISTS each as a
GuidanceItem — the existing notification substrate — so every event appears
*for free* in:
  • Beth's reasoning context (cos_context `active_guidance`)
  • the WLJ notification center / bell / web UI (existing GuidanceItem templates)
  • the unified standing read (build_cos_intelligence -> `events`)
  • push/SMS/email when a device exists (DNE), via the proactive check-in transport

Event creation is decoupled from delivery: the event exists regardless of
channel. Recurrence is first-class — re-detecting the same situation increments
an occurrence count and, after a couple of weeks, escalates the framing
("I've been flagging this for ~3 weeks and it hasn't resolved"). Events that
stop being detected are auto-resolved so the center stays honest.

NO new model — GuidanceItem already carries dedupe_key, created_at, metadata
JSON, and full lifecycle (read/acknowledged/dismissed/resolved). Reuses the
unified brain (build_cos_intelligence) + executive state signals for detection,
so the strategic layer is no longer "only when asked."
"""
import logging
from dataclasses import dataclass

from django.utils import timezone

logger = logging.getLogger(__name__)

# Event categories
APPROACHING = "approaching"
DUE_NOW = "due_now"
PAST_DUE = "past_due"
RECURRING_PROBLEM = "recurring_problem"
STRATEGIC_RISK = "strategic_risk"
STRATEGIC_OPPORTUNITY = "strategic_opportunity"
MAJOR_WIN = "major_win"

CATEGORIES = (APPROACHING, DUE_NOW, PAST_DUE, RECURRING_PROBLEM,
              STRATEGIC_RISK, STRATEGIC_OPPORTUNITY, MAJOR_WIN)

# How many operational events to surface per category (avoid flooding the
# notification center). active_guidance shows the top 5 by priority anyway.
_OP_CAPS = {APPROACHING: 2, DUE_NOW: 3, PAST_DUE: 3}
_RECURRING_THRESHOLD_DAYS = 3  # distinct overdue days in 7d → recurring_problem

# Fine-grained domain -> enabled WLJ module (so the GuidanceItem surfaces).
_DOMAIN_MODULE = {
    "weight": "health", "sleep": "health", "glucose": "health",
    "workout": "health", "medication": "health", "recommendation": "health",
    "nutrition": "meals", "relationship": "relationships", "faith": "faith",
    "goal": "purpose", "journal": "journal",
}

_PREFIX = "cos_event:"


@dataclass
class CoSEvent:
    """A single Chief-of-Staff event with the mandatory three-part explanation:
    what happened, why it matters, what to do next."""
    category: str
    domain: str
    title: str
    what_happened: str
    why_it_matters: str
    what_to_do: str
    priority: int = 3
    # Optional stable per-item key (operational events). When set, the event is
    # keyed by the ITEM, not the category — so a single notification escalates
    # as the item moves approaching → due_now → past_due → recurring_problem.
    key: str = None
    item_label: str = None

    @property
    def dedupe_key(self):
        if self.key:
            return f"{_PREFIX}{self.key}"
        return f"{_PREFIX}{self.category}:{self.domain}"

    @property
    def message(self):
        return " ".join(p for p in (self.what_happened, self.why_it_matters,
                                    self.what_to_do) if p).strip()

    @property
    def module(self):
        return _DOMAIN_MODULE.get(self.domain, "health")


def _why_decline(domain):
    return {
        "sleep": "Because sleep is a primary constraint on your weight loss and "
                 "energy, a sustained dip raises the risk of a weight-loss "
                 "slowdown.",
        "glucose": "Rising glucose works against your metabolic and weight goals "
                   "and compounds if left unaddressed.",
    }.get(domain, f"A sustained decline in {domain} undermines the progress "
                  f"you've been building.")


def _fix_decline(domain):
    return {
        "sleep": "Protect tonight's sleep — that's the highest-leverage move "
                 "right now.",
        "glucose": "Tighten the levers that move glucose (meal timing, movement) "
                   "this week.",
    }.get(domain, f"Make {domain} this week's focus before it drags other areas.")


def detect_events(user):
    """Run all detectors and return the current list of CoSEvents. Grounded in
    the unified brain + executive signals; never raises."""
    events = []
    try:
        from apps.ai.cos_intelligence import build_cos_intelligence
        intel = build_cos_intelligence(user) or {}
    except Exception:
        intel = {}
    gp = intel.get("goal_pace") or {}
    eff = intel.get("recommendation_effectiveness") or ""

    try:
        from apps.core.cos_briefing.executive_state import (
            build_executive_state_signals, select_executive_lenses)
        picks = select_executive_lenses(build_executive_state_signals(user))
    except Exception:
        picks = {}

    # ── STRATEGIC RISK ──────────────────────────────────────────
    if gp.get("target_passed"):
        events.append(CoSEvent(
            STRATEGIC_RISK, "weight", "Weight goal target date passed",
            what_happened=(f"Your weight target date ({gp.get('target_date')}) "
                           f"has passed and you're still {gp.get('remaining')} lb "
                           f"from goal at ~{gp.get('current_pace_lb_wk')} lb/week."),
            why_it_matters="Without a realistic target the plan loses its anchor "
                           "and momentum drifts.",
            what_to_do="Reset the target date to match your real pace, or tighten "
                       "the plan to hit a date that matters.", priority=2))
    elif gp.get("on_pace") is False and gp.get("required_pace_lb_wk"):
        events.append(CoSEvent(
            STRATEGIC_RISK, "weight", "Weight goal trajectory slipping",
            what_happened=(f"At ~{gp.get('current_pace_lb_wk')} lb/week you're "
                           f"behind your {gp.get('target_date')} target — it needs "
                           f"~{gp.get('required_pace_lb_wk')} lb/week."),
            why_it_matters="At the current rate you won't hit the date, and the "
                           "gap compounds the longer it goes unaddressed.",
            what_to_do="Either lift the rate or move the date so the goal stays "
                       "honest.", priority=2))

    decline = picks.get("biggest_decline")
    if decline and getattr(decline, "domain", None) not in (None, "weight"):
        events.append(CoSEvent(
            STRATEGIC_RISK, decline.domain,
            f"{decline.domain.capitalize()} is trending down",
            what_happened=decline.message or decline.title,
            why_it_matters=_why_decline(decline.domain),
            what_to_do=_fix_decline(decline.domain), priority=2))

    if any(k in eff for k in ("different approach", "wrong way", "change tack")):
        events.append(CoSEvent(
            STRATEGIC_RISK, "recommendation", "Current focus isn't working",
            what_happened=eff,
            why_it_matters="Repeating an approach that isn't moving the metric "
                           "wastes the weeks you have.",
            what_to_do="Switch tactics on this constraint rather than continuing "
                       "the same plan.", priority=2))

    # ── STRATEGIC OPPORTUNITY ───────────────────────────────────
    improvement = picks.get("biggest_improvement")
    if improvement and getattr(improvement, "domain", None):
        events.append(CoSEvent(
            STRATEGIC_OPPORTUNITY, improvement.domain,
            f"{improvement.domain.capitalize()} is improving",
            what_happened=improvement.message or improvement.title,
            why_it_matters="A positive trend is the cheapest momentum you have — "
                           "reinforcing it now compounds.",
            what_to_do=(f"Keep doing what's moving {improvement.domain}; protect "
                        f"the routine that's working."), priority=3))

    if "working" in eff and "isn't working" not in eff and "not working" not in eff:
        events.append(CoSEvent(
            STRATEGIC_OPPORTUNITY, "recommendation", "Your focus is paying off",
            what_happened=eff,
            why_it_matters="Evidence the current focus works is a reason to double "
                           "down, not move on.",
            what_to_do="Stay the course on this constraint for another cycle.",
            priority=3))

    # ── MAJOR WIN ───────────────────────────────────────────────
    win = picks.get("biggest_win")
    if win and getattr(win, "domain", None):
        events.append(CoSEvent(
            MAJOR_WIN, win.domain, win.title or f"{win.domain.capitalize()} win",
            what_happened=win.message or win.title,
            why_it_matters="Naming a win reinforces the behavior that produced it.",
            what_to_do="Acknowledge it and bank the routine that got you here.",
            priority=3))

    if gp.get("remaining") is not None and gp.get("remaining") <= 1.0 \
            and not gp.get("insufficient"):
        events.append(CoSEvent(
            MAJOR_WIN, "goal", "Weight goal reached",
            what_happened=f"You've reached your weight goal of {gp.get('goal')} lb.",
            why_it_matters="This is the outcome the whole plan was built for.",
            what_to_do="Set the next goal — maintenance or a new target — so "
                       "momentum doesn't stall.", priority=2))

    return events


def _op_module(title):
    t = (title or "").lower()
    if any(k in t for k in ("pray", "bible", "devotion", "scripture", "worship")):
        return "faith"
    if "journal" in t:
        return "journal"
    return "health"  # workouts, medication, measurements, routines → always-on


def _op_slug(title):
    import re
    return re.sub(r"[^a-z0-9]+", "-", (title or "item").lower()).strip("-")[:60] or "item"


def _operational_event(category, action):
    title = (action.get("title") or "").strip() or "Scheduled item"
    when = action.get("time_display") or ""
    module = _op_module(title)
    if category == APPROACHING:
        wh = f"{title} is coming up{f' at {when}' if when else ''}."
        why = "Staying ahead of it keeps the rest of the day on track."
        wd = "Plan to handle it shortly."
        pr = 4
    elif category == DUE_NOW:
        wh = f"{title} is due now{f' ({when})' if when else ''}."
        why = "Doing it on time keeps your routine intact."
        wd = "Take care of it now."
        pr = 3
    else:  # PAST_DUE
        wh = f"{title} is overdue{f' (was due {when})' if when else ''}."
        why = "The longer it slips, the harder the day is to recover."
        wd = "Knock it out now, or consciously reschedule it."
        pr = 2 if action.get("is_foundational") else 3
    return CoSEvent(category, module, title, wh, why, wd, priority=pr,
                    key=f"op:{module}:{_op_slug(title)}", item_label=title)


def detect_operational_events(user):
    """Map the canonical execution state (build_execution_state) into operational
    CoSEvents. Returns (events, ok) — ok=False signals detection failed so the
    caller must NOT auto-resolve operational events (avoids false resolution).
    Reuses the same source cos_context uses; no re-derivation of timing."""
    try:
        from apps.core.execution.execution_state import build_execution_state
        es = build_execution_state(user) or {}
    except Exception:
        logger.warning("cos_event: execution_state failed", exc_info=True)
        return [], False

    out = []
    for src_key, cat in (("upcoming_actions", APPROACHING),
                         ("now_actions", DUE_NOW),
                         ("overdue_actions", PAST_DUE)):
        for a in (es.get(src_key) or [])[:_OP_CAPS[cat]]:
            if a.get("completed_today") or a.get("completed"):
                continue
            out.append(_operational_event(cat, a))
    return out, True


def _within_days(iso, now, days):
    from datetime import date
    try:
        return (now.date() - date.fromisoformat(iso)).days <= days
    except Exception:
        return False


def persist_event(user, event):
    """Upsert the event as a GuidanceItem, keyed by dedupe_key. Returns
    (guidance_item, created). Strategic events escalate after ~2 weeks;
    operational past-due events that recur on ≥3 distinct days in a week are
    promoted to recurring_problem."""
    from apps.core.ai_guidance.models import GuidanceItem
    now = timezone.now()
    existing = GuidanceItem.objects.filter(
        user=user, dedupe_key=event.dedupe_key, is_active=True).first()

    meta = dict(existing.metadata or {}) if existing else {}
    meta.update({
        "category": event.category, "domain": event.domain,
        "what_happened": event.what_happened,
        "why_it_matters": event.why_it_matters, "what_to_do": event.what_to_do,
        "last_seen": now.isoformat(),
    })
    meta.setdefault("first_seen",
                    existing.created_at.isoformat() if existing else now.isoformat())
    meta["occurrence_count"] = int(meta.get("occurrence_count", 0)) + 1

    category = event.category
    priority = event.priority
    prefix = ""

    if event.category == PAST_DUE:
        # Track distinct overdue days → promote to recurring_problem.
        dates = set(meta.get("overdue_dates", []))
        dates.add(now.date().isoformat())
        recent = sorted(d for d in dates if _within_days(d, now, 30))
        meta["overdue_dates"] = recent
        last7 = [d for d in recent if _within_days(d, now, 7)]
        if len(last7) >= _RECURRING_THRESHOLD_DAYS:
            category = RECURRING_PROBLEM
            meta["category"] = RECURRING_PROBLEM
            priority = 2
            label = event.item_label or event.title or "this"
            prefix = (f"That's {len(last7)} days in the last week {label} has "
                      f"gone overdue — it's becoming a pattern. ")
    elif existing:
        # Strategic recurrence — escalate framing after ~2 weeks unresolved.
        weeks = max(0, (now - existing.created_at).days) // 7
        if weeks >= 2:
            prefix = (f"I've been flagging this for about {weeks} weeks and it "
                      f"hasn't resolved. ")

    message = prefix + event.message
    guidance_type = f"{_PREFIX}{category}"

    if existing:
        existing.title = event.title
        existing.message = message
        existing.priority = priority
        existing.guidance_type = guidance_type
        existing.metadata = meta
        existing.is_read = False  # resurface
        existing.save(update_fields=["title", "message", "priority",
                                     "guidance_type", "metadata", "is_read",
                                     "updated_at"])
        return existing, False

    item = GuidanceItem.objects.create(
        user=user, title=event.title, message=message, priority=priority,
        guidance_type=guidance_type, source="composite", module=event.module,
        dedupe_key=event.dedupe_key, metadata=meta)
    return item, True


def run_cos_event_engine(user):
    """Detect → persist → auto-resolve. Respects the proactive master switch.
    Returns a summary dict. Never raises per-event."""
    prefs = getattr(user, "preferences", None)
    if prefs and not getattr(prefs, "assistant_proactive_checkins", True):
        return {"created": 0, "updated": 0, "resolved": 0}

    strategic = detect_events(user)
    operational, op_ok = detect_operational_events(user)

    created = updated = 0
    for ev in strategic + operational:
        try:
            _, is_new = persist_event(user, ev)
            created += int(is_new)
            updated += int(not is_new)
        except Exception:
            logger.warning("cos_event: persist failed (%s)", ev.dedupe_key,
                           exc_info=True)

    # Auto-resolve, keeping strategic and operational streams independent so a
    # transient operational-detection failure can't wrongly resolve strategic
    # events (and vice-versa).
    resolved = 0
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        now = timezone.now()
        op_prefix = f"{_PREFIX}op:"

        def _resolve(qs):
            n = 0
            for s in qs:
                meta = s.metadata or {}
                meta["resolved_at"] = now.isoformat()
                s.metadata = meta
                s.is_active = False
                s.save(update_fields=["is_active", "metadata", "updated_at"])
                n += 1
            return n

        strat_keys = {e.dedupe_key for e in strategic}
        resolved += _resolve(GuidanceItem.objects.filter(
            user=user, is_active=True, dedupe_key__startswith=_PREFIX
        ).exclude(dedupe_key__startswith=op_prefix).exclude(
            dedupe_key__in=strat_keys))

        if op_ok:
            op_keys = {e.dedupe_key for e in operational}
            resolved += _resolve(GuidanceItem.objects.filter(
                user=user, is_active=True, dedupe_key__startswith=op_prefix
            ).exclude(dedupe_key__in=op_keys))
    except Exception:
        logger.warning("cos_event: auto-resolve failed", exc_info=True)

    return {"created": created, "updated": updated, "resolved": resolved}


def recent_cos_events(user, limit=5):
    """Active CoS events for the standing read (lightweight, read-only)."""
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        items = GuidanceItem.objects.filter(
            user=user, is_active=True, dedupe_key__startswith=_PREFIX,
            dismissed_at__isnull=True).order_by("priority", "-created_at")[:limit]
    except Exception:
        return []
    out = []
    for g in items:
        meta = g.metadata or {}
        out.append({
            "category": meta.get("category", ""),
            "domain": meta.get("domain", g.module),
            "title": g.title, "message": g.message,
            "occurrence_count": int(meta.get("occurrence_count", 1)),
            "priority": g.priority,
        })
    return out
