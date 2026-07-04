"""
Home (the Hearth) data builder.

Builds the Legacy Home context from real canonical data. When the keeper has no
memories yet, returns a curated *sample* set so the Hearth is warm and complete
out of the box (per the brief: cards may use placeholder/demo data initially).
Real data replaces the sample automatically as memories are created.

This is a read-only assembler over the domain — no heavy computation, safe on
the request path.
"""

import datetime

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

    # Real Memory objects so the Hearth renders the SAME canonical story card
    # (templates/legacy/_memory_card.html) used everywhere else — one design.
    resurfaced = list(
        memories.filter(entry_state=Memory.EntryState.LEGACY)
        .select_related("primary_media", "attributed_to").order_by("-created_at")[:4]
    )
    if not resurfaced:
        resurfaced = list(
            memories.select_related("primary_media", "attributed_to")
            .order_by("-created_at")[:4]
        )

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


class _SampleStory:
    """Duck-typed stand-in so the empty-state Hearth renders the SAME canonical
    story card (_memory_card.html) as real memories — never a second design.
    Not persisted; pk is None so the card links to the library and omits actions."""

    pk = None
    status = "active"
    attributed_to = None
    occurred_precision = "exact"

    def __init__(self, title, body, entry_state, entry_type, occurred_on):
        self.title = title
        self.body = body
        self.entry_state = entry_state
        self.entry_type = entry_type
        self.occurred_on = occurred_on
        self.created_at = occurred_on

    def cover_media(self):
        return None


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
            _SampleStory("First Day of School",
                         "A memory from August 1974 that became meaningful again today.",
                         "legacy", "memory", datetime.date(1974, 8, 28)),
            _SampleStory("The Blue Chevy",
                         "You and your brother restored this together.",
                         "legacy", "object", datetime.date(1978, 6, 12)),
            _SampleStory("Pine Lake Cabin",
                         "Many memories live here. Want to explore?",
                         "legacy", "place", datetime.date(1976, 7, 1)),
            _SampleStory("Prom Night",
                         "Lisa found this photo and wanted to share it.",
                         "legacy", "memory", datetime.date(1981, 5, 15)),
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
