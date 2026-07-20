"""Prayer ↔ Scripture bridge — deterministic, honest connections.

The Chief of Staff connects Reading and Prayer through truth WLJ owns, never by
inventing it. Here that means: given a prayer's category (or a keyword in its
subject), offer a real passage that speaks to it; and given a day's reading,
offer a gentle prayer starting point. Pure functions — safe anywhere.
"""

from __future__ import annotations

from typing import Any, Optional

# Curated, public-domain (World English Bible) Scripture for each prayer theme.
_CATEGORY_VERSES = {
    "family":    ("As for me and my house, we will serve Yahweh.", "Joshua 24:15"),
    "health":    ("He heals the broken in heart, and binds up their wounds.", "Psalm 147:3"),
    "provision": ("My God will supply every need of yours according to his riches in glory in Christ Jesus.", "Philippians 4:19"),
    "guidance":  ("Trust in Yahweh with all your heart, and don't lean on your own understanding. In all your ways acknowledge him, and he will make your paths straight.", "Proverbs 3:5-6"),
    "gratitude": ("In everything give thanks, for this is the will of God in Christ Jesus toward you.", "1 Thessalonians 5:18"),
    "growth":    ("But grow in the grace and knowledge of our Lord and Savior Jesus Christ.", "2 Peter 3:18"),
    "others":    ("Confess your sins to one another and pray for one another, that you may be healed.", "James 5:16"),
}

# Keyword → Scripture, for when no category is set. First match wins.
_KEYWORD_VERSES = [
    (("anxiety", "anxious", "worry", "worried", "stress", "overwhelm"),
     ("Don't be anxious about anything, but in everything, by prayer and petition with thanksgiving, let your requests be made known to God.", "Philippians 4:6")),
    (("fear", "afraid", "scared", "courage"),
     ("Don't be afraid, for I am with you. Don't be dismayed, for I am your God.", "Isaiah 41:10")),
    (("heal", "sick", "illness", "pain", "cancer", "surgery"),
     ("He heals the broken in heart, and binds up their wounds.", "Psalm 147:3")),
    (("grief", "loss", "grieving", "mourning", "death", "died"),
     ("Blessed are those who mourn, for they shall be comforted.", "Matthew 5:4")),
    (("job", "work", "money", "finances", "provision", "provide"),
     ("My God will supply every need of yours according to his riches in glory in Christ Jesus.", "Philippians 4:19")),
    (("wisdom", "decision", "guidance", "direction", "choice"),
     ("If any of you lacks wisdom, let him ask of God, who gives to all liberally.", "James 1:5")),
    (("marriage", "spouse", "husband", "wife", "family", "children", "kids", "dad", "mom", "father", "mother", "son", "daughter"),
     ("Love is patient and is kind. Love bears all things, believes all things, hopes all things, endures all things.", "1 Corinthians 13:4,7")),
    (("thank", "grateful", "gratitude", "praise"),
     ("In everything give thanks, for this is the will of God in Christ Jesus toward you.", "1 Thessalonians 5:18")),
]

_DEFAULT_VERSE = (
    "Cast all your worries on him, because he cares for you.",
    "1 Peter 5:7",
)


def scripture_for_prayer(prayer) -> Optional[dict[str, str]]:
    """A real passage that speaks to this prayer — by category, else by keyword."""
    cat = getattr(prayer, "category", "") or ""
    if cat and cat in _CATEGORY_VERSES:
        text, ref = _CATEGORY_VERSES[cat]
        return {"text": text, "ref": ref}

    hay = " ".join(filter(None, [
        (getattr(prayer, "title", "") or ""),
        (getattr(prayer, "person_or_situation", "") or ""),
        (getattr(prayer, "description_plain", "") or ""),
    ])).lower()
    for keys, (text, ref) in _KEYWORD_VERSES:
        if any(k in hay for k in keys):
            return {"text": text, "ref": ref}

    text, ref = _DEFAULT_VERSE
    return {"text": text, "ref": ref}


def _humanize_span(days: int) -> str:
    """A gentle span like 'a few days' / '6 weeks' / '3 months' / '2 years'."""
    if days <= 1:
        return "a day"
    if days < 14:
        return f"{days} days"
    if days < 60:
        weeks = max(2, round(days / 7))
        return f"{weeks} weeks"
    if days < 365:
        months = max(2, round(days / 30.44))
        return f"{months} months"
    years = round(days / 365.25)
    return "a year" if years == 1 else f"{years} years"


def testimony_for(prayer) -> Optional[dict[str, Any]]:
    """An answered prayer as a testimony, not a record.

    Gathers, deterministically and read-only, the story around an answered
    prayer: how long it was carried, how it was answered, journal entries and
    reading journeys from that season, and a word of Scripture. Bounded, cheap —
    safe on the request path. Returns None for prayers that aren't answered.
    """
    if not getattr(prayer, "is_answered", False):
        return None

    from django.utils import timezone as _tz

    created = getattr(prayer, "created_at", None)
    answered = getattr(prayer, "answered_at", None) or created
    duration = None
    if created and answered:
        duration = _humanize_span(max(0, (answered - created).days))

    journal = []
    journeys = []
    if created and answered:
        start = created.date()
        end = answered.date()
        try:
            from apps.journal.models import JournalEntry
            for e in (
                JournalEntry.objects.filter(
                    user=prayer.user, entry_date__gte=start, entry_date__lte=end,
                ).order_by("entry_date")[:3]
            ):
                excerpt = (getattr(e, "body_plain", "") or "").strip()
                journal.append({
                    "title": e.title or "A journal entry",
                    "when": e.entry_date,
                    "excerpt": (excerpt[:150] + "…") if len(excerpt) > 150 else excerpt,
                })
        except Exception:
            pass
        try:
            from apps.faith.models import UserReadingPlan
            for up in (
                UserReadingPlan.objects.filter(
                    user=prayer.user, plan_status="completed",
                    completed_at__date__gte=start, completed_at__date__lte=end,
                ).select_related("template")[:3]
            ):
                journeys.append({"title": up.template.title})
        except Exception:
            pass

    return {
        "duration": duration,
        "answered_at": answered,
        "answer": (getattr(prayer, "answer_notes_plain", "") or "").strip(),
        "scripture": scripture_for_prayer(prayer),
        "journal": journal,
        "journeys": journeys,
    }


def prayer_prefill_from_reading(refs, arc_name: str = "", key_insight: str = "") -> dict[str, Any]:
    """Gentle starting values for a prayer created from today's reading.

    `refs` is the day's scripture references (list or string). Nothing is
    fabricated — we simply seed the title/description with what the reading was.
    """
    if isinstance(refs, (list, tuple)):
        ref_str = ", ".join(str(r) for r in refs)
    else:
        ref_str = str(refs or "")
    title = "A prayer from today's reading"
    if arc_name:
        title = f"From “{arc_name}”"
    description = ""
    if key_insight:
        description = f"Lord, as I read {ref_str}: {key_insight}"
    elif ref_str:
        description = f"Lord, as I read {ref_str} today…"
    return {"title": title, "description": description, "person_or_situation": ""}
