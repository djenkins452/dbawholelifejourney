"""build_today(user) — the deterministic payload for the First Light "Today" home.

Everything here is a cheap, read-only projection of truth WLJ already owns
(active journey / reading plan, recent prayers, the Church calendar). No LLM,
no heavy compute — safe to call from the request path.

Design intent (from the approved Formation direction):
  • Presence before information. Most mornings: a stillness verse + one warm step.
  • The companion is OCCASIONAL and GROUNDED. It only speaks when there is real
    truth to speak from (a return after a gap, a recent prayer), otherwise it
    stays silent — the better the companion, the less it interrupts.
  • Grace over guilt. No streak/urgency framing anywhere.
  • Story over percentage. Progress is the journey map of named chapters.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from django.urls import reverse
from django.utils import timezone

from .season import season_note

# Curated stillness / presence verses (World English Bible — public domain).
# A calm, God-ward rotation so the first thing a person meets is Scripture.
_STILL_VERSES = [
    ("Be still, and know that I am God.", "Psalm 46:10"),
    ("Come to me, all you who labor and are heavily burdened, and I will give you rest.", "Matthew 11:28"),
    ("The LORD is my shepherd; I shall lack nothing.", "Psalm 23:1"),
    ("In quietness and in confidence shall be your strength.", "Isaiah 30:15"),
    ("This is the day that the LORD has made. We will rejoice and be glad in it.", "Psalm 118:24"),
    ("His compassions never fail. They are new every morning.", "Lamentations 3:22-23"),
    ("Cast all your worries on him, because he cares for you.", "1 Peter 5:7"),
    ("Wait for the LORD. Be strong, and let your heart take courage.", "Psalm 27:14"),
    ("Peace I leave with you. My peace I give to you.", "John 14:27"),
    ("The LORD is near to all who call on him.", "Psalm 145:18"),
    ("Trust in the LORD with all your heart, and don't lean on your own understanding.", "Proverbs 3:5"),
    ("Draw near to God, and he will draw near to you.", "James 4:8"),
]


def _greeting(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _first_name(user) -> str:
    name = (getattr(user, "first_name", "") or "").strip()
    if name:
        return name
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    if full:
        return full.split()[0]
    return "friend"


def build_today(user) -> dict[str, Any]:
    now = timezone.localtime(timezone.now())
    today = now.date()

    still = _STILL_VERSES[today.timetuple().tm_yday % len(_STILL_VERSES)]
    cont, jmap = _continue_and_map(user)

    return {
        "greeting": _greeting(now.hour),
        "name": _first_name(user),
        "weekday": now.strftime("%A"),
        "season_note": season_note(today),
        "still": {"text": still[0], "ref": still[1]},
        "continue": cont,
        "journey_map": jmap,
        "companion": _companion(user, cont),
        "invitation": _invitation(user, cont),
        "has_started": cont is not None,
    }


# ---------------------------------------------------------------------------
# Continue-as-story + the journey map
# ---------------------------------------------------------------------------

def _continue_and_map(user):
    from apps.faith.journey.dashboard import get_dashboard_card_data
    from apps.faith.journey.services import get_active_journey

    uj = get_active_journey(user)
    if uj is not None:
        jmap = _journey_map(uj)
        card = get_dashboard_card_data(user)  # None if an authored content gap
        if card:
            return {
                "kind": "journey",
                "title": card["journey_name"],
                "arc_name": card["arc_name"],
                "day_number": card["day_number"],
                "total_days": card["total_days"],
                "subtitle": f'{card["arc_name"]} · Day {card["day_number"]}',
                "focus": card.get("focus"),
                "resume_url": reverse("journey:today"),
            }, jmap
        # Journey exists but no resolvable current day — still resumable.
        arc = uj.current_arc
        return {
            "kind": "journey",
            "title": uj.journey_path.name,
            "arc_name": arc.name if arc else "",
            "day_number": uj.current_day_number,
            "total_days": arc.estimated_days if arc else 0,
            "subtitle": arc.name if arc else uj.journey_path.name,
            "focus": None,
            "resume_url": reverse("journey:today"),
        }, jmap

    # Fall back to an active classic reading plan.
    from apps.faith.models import UserReadingPlan

    plan = (
        UserReadingPlan.objects
        .filter(user=user, plan_status="active")
        .select_related("template")
        .first()
    )
    if plan is not None:
        total = plan.template.duration_days or 0
        return {
            "kind": "plan",
            "title": plan.template.title,
            "arc_name": None,
            "day_number": plan.current_day,
            "total_days": total,
            "subtitle": f"Day {plan.current_day} of {total}" if total else f"Day {plan.current_day}",
            "focus": None,
            "resume_url": reverse("faith:reading_plan_progress", args=[plan.pk]),
            "progress_pct": plan.progress_percentage,
        }, None

    return None, None


def _journey_map(uj) -> Optional[dict[str, Any]]:
    """Named chapters walked, current, and ahead — the story of the journey."""
    path = uj.journey_path
    arcs = list(path.arcs.order_by("order").values("name", "order"))
    if not arcs:
        return None
    cur_order = uj.current_arc.order if uj.current_arc else arcs[0]["order"]
    out = []
    done = 0
    for a in arcs:
        if a["order"] < cur_order:
            status = "done"
            done += 1
        elif a["order"] == cur_order:
            status = "current"
        else:
            status = "ahead"
        out.append({"name": a["name"], "status": status})
    return {
        "arcs": out,
        "done": done,
        "total": len(arcs),
        "current_name": uj.current_arc.name if uj.current_arc else "",
    }


# ---------------------------------------------------------------------------
# The companion — occasional and grounded
# ---------------------------------------------------------------------------

def _companion(user, cont) -> Optional[dict[str, Any]]:
    """Return a gentle, grounded question — or None (presence only).

    Only speaks for a real reason: a return after a gap, or a recent prayer to
    carry into today's reading. Most mornings returns None.
    """
    if not cont or cont.get("kind") != "journey":
        return None

    from apps.faith.journey.services import get_active_journey

    uj = get_active_journey(user)

    # 1) Welcome back after a genuine gap (grace, not guilt).
    if uj is not None and uj.last_visited_at:
        gap = (timezone.now() - uj.last_visited_at).days
        if gap >= 3:
            return {
                "reason": None,
                "q": f"It’s been {gap} days — no rush at all. "
                     "Pick up where you left off, or just sit with today’s verse?",
                "choices": [
                    {"label": "Continue where I left off", "sub": cont["subtitle"], "url": cont["resume_url"]},
                    {"label": "Just today’s verse", "sub": None, "url": reverse("faith:todays_verse")},
                ],
            }

    # 2) A recent prayer to carry into the reading.
    subject = _recent_prayer_subject(user)
    if subject:
        return {
            "reason": f"You’ve been praying about {subject}",
            "q": f"Would you like to bring {subject} before God as you read today?",
            "choices": [
                {"label": "Yes, hold it before Him", "sub": None, "url": cont["resume_url"]},
                {"label": "Just the reading today", "sub": None, "url": cont["resume_url"]},
            ],
        }

    return None


def _recent_prayer_subject(user) -> Optional[str]:
    """A short, real subject from a recent unanswered prayer, or None."""
    from apps.faith.models import PrayerRequest

    cutoff = timezone.now() - timedelta(days=21)
    p = (
        PrayerRequest.objects
        .filter(user=user, is_answered=False, created_at__gte=cutoff)
        .order_by("-priority", "-created_at")
        .first()
    )
    if p is None:
        return None
    subject = (getattr(p, "person_or_situation", "") or "").strip() or (p.title or "").strip()
    subject = subject.strip()
    # Keep it short enough to read cleanly inside a sentence.
    if not subject or len(subject) > 40:
        return None
    return subject


# ---------------------------------------------------------------------------
# One honest invitation
# ---------------------------------------------------------------------------

def _invitation(user, cont) -> Optional[dict[str, Any]]:
    """A single, honest next journey.

    v1 surfaces a featured, accessible reading plan with a plain label — no
    fabricated personal reason. (Grounded "because you…" reasons arrive with the
    recommendation phase, which matches plan topics to real prayer/journal truth.)
    """
    from apps.faith.models import ReadingPlanTemplate

    current_plan_title = cont["title"] if (cont and cont.get("kind") == "plan") else None

    candidates = (
        ReadingPlanTemplate.objects
        .filter(is_active=True)
        .order_by("-is_featured", "title")[:20]
    )
    email = (getattr(user, "email", "") or "").lower()
    for plan in candidates:
        allowed = getattr(plan, "allowed_emails", None) or []
        if allowed and email not in [str(e).lower() for e in allowed]:
            continue  # gated (e.g. copyrighted) plan the user can't access
        if current_plan_title and plan.title == current_plan_title:
            continue  # don't suggest the plan they're already reading
        try:
            difficulty = plan.get_difficulty_display()
        except Exception:
            difficulty = getattr(plan, "difficulty", "") or ""
        return {
            "label": "If you have a little more" if cont else "A gentle place to begin",
            "title": plan.title,
            "why": (plan.description or "").strip()[:150],
            "duration_days": plan.duration_days,
            "difficulty": difficulty,
            "url": reverse("faith:reading_plan_detail", args=[plan.slug]),
            "reason": None,
        }
    return None
