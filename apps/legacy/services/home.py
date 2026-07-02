"""
Home (the Hearth) data builder.

Builds the Legacy Home context from real canonical data. When the keeper has no
memories yet, returns a curated *sample* set so the Hearth is warm and complete
out of the box (per the brief: cards may use placeholder/demo data initially).
Real data replaces the sample automatically as memories are created.

This is a read-only assembler over the domain — no heavy computation, safe on
the request path.
"""

from django.utils import timezone


def build_home_context(user):
    from apps.legacy.models import Contributor, Memory

    memories = Memory.objects.filter(user=user)
    has_data = memories.exists()

    if not has_data:
        ctx = _sample_home()
        ctx["is_sample"] = True
        return ctx

    now = timezone.now()
    month_count = memories.filter(created_at__year=now.year, created_at__month=now.month).count()

    resurfaced = [
        _memory_card(m)
        for m in memories.filter(entry_state=Memory.EntryState.LEGACY)
        .order_by("-created_at")[:4]
    ]
    if not resurfaced:
        resurfaced = [_memory_card(m) for m in memories.order_by("-created_at")[:4]]

    draft = memories.filter(entry_state=Memory.EntryState.DRAFT).order_by("-updated_at").first()

    contributions = (
        Contributor.objects.filter(user=user)
        .order_by("-updated_at")[:3]
    )
    highlights = [
        {"who": c.name, "text": f"{c.name} is a contributor", "meta": c.get_permission_level_display(),
         "initial": (c.name or "?")[:1]}
        for c in contributions
    ]

    return {
        "is_sample": False,
        "greeting_name": user.first_name or (user.get_full_name() or "").split(" ")[0] or "",
        "hero_subtitle": "This is your Legacy. Capture it. Cherish it. Share it.",
        "recently_resurfaced": resurfaced,
        "today": _today_card(memories, now),
        "continue": ({
            "title": draft.title or "Untitled memory",
            "state": draft.get_entry_state_display(),
            "meta": "Last edited " + _human_when(draft.updated_at, now),
            "progress": 60,
            "pk": draft.pk,
        } if draft else None),
        "family_highlights": highlights,
        "month_count": month_count,
    }


def _memory_card(m):
    return {
        "pk": m.pk,
        "title": m.title or "Untitled memory",
        "description": (m.body[:90] + "…") if len(m.body) > 90 else m.body,
        "meta_date": _date_label(m),
        "teller": (m.attributed_to.display_name if m.attributed_to else "You"),
        "image_url": (m.primary_media.file.url if (m.primary_media and m.primary_media.file) else None),
        "type": m.entry_type,
    }


def _today_card(memories, now):
    same_day = memories.filter(
        occurred_on__month=now.month, occurred_on__day=now.day
    ).exclude(occurred_on__year=now.year).order_by("occurred_on").first()
    if not same_day:
        return None
    return {
        "date_label": now.strftime("%B %-d, %Y"),
        "title": same_day.title or "A memory",
        "remembered_on": "You remembered this on " + same_day.occurred_on.strftime("%B %-d, %Y"),
        "pk": same_day.pk,
        "image_url": (same_day.primary_media.file.url
                      if (same_day.primary_media and same_day.primary_media.file) else None),
    }


def _date_label(m):
    if not m.occurred_on:
        return ""
    if m.occurred_precision == "year":
        return m.occurred_on.strftime("%Y")
    return m.occurred_on.strftime("%b %-d, %Y")


def _human_when(dt, now):
    delta = now - dt
    if delta.days <= 0:
        return "today"
    if delta.days == 1:
        return "yesterday"
    return f"{delta.days} days ago"


def _sample_home():
    """Curated sample matching the approved mockup — shown until real memories exist."""
    return {
        "greeting_name": "",
        "hero_subtitle": "This is your Legacy. Capture it. Cherish it. Share it.",
        "recently_resurfaced": [
            {"pk": None, "title": "First Day of School",
             "description": "A memory from August 1974 that became meaningful again today.",
             "meta_date": "Aug 28, 1974", "teller": "You", "image_url": None, "type": "memory"},
            {"pk": None, "title": "The Blue Chevy",
             "description": "You and your brother restored this together.",
             "meta_date": "Jun 12, 1978", "teller": "You", "image_url": None, "type": "object"},
            {"pk": None, "title": "Pine Lake Cabin",
             "description": "Many memories live here. Want to explore?",
             "meta_date": "1976 – 1995", "teller": "You", "image_url": None, "type": "place"},
            {"pk": None, "title": "Prom Night",
             "description": "Lisa found this photo and wanted to share it.",
             "meta_date": "May 15, 1981", "teller": "Lisa", "image_url": None, "type": "memory"},
        ],
        "today": {
            "date_label": "Today in Your Legacy",
            "title": "Fishing with Dad",
            "remembered_on": "You remembered this on May 16, 2018",
            "pk": None, "image_url": None,
        },
        "continue": {
            "title": "Summer of '72", "state": "Draft",
            "meta": "Last edited yesterday", "progress": 60, "pk": None,
        },
        "family_highlights": [
            {"who": "Sarah", "text": "Sarah added 3 memories", "meta": "2 hours ago", "initial": "S"},
            {"who": "Dad", "text": "Dad's 90th Birthday — new photos added", "meta": "", "initial": "D"},
            {"who": "Mom", "text": "Mom's Recipe Box — audio memory added", "meta": "", "initial": "M"},
        ],
        "month_count": 24,
    }
