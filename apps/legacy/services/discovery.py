"""
Story Discovery Engine (Legacy Phase 2).

Reads a memory's text and proposes everything it understood — people,
relationships, places, human/calendar/relative time, life stage, events,
quotes, artifacts, media references, themes, values, traditions, emotions.

Entirely inside the Legacy domain. It makes ONE direct OpenAI call and does NOT
touch the CoS / Beth / personal_assistant orchestrator. Everything it produces
is proposal-first (MemoryDiscovery rows, status=proposed) — nothing becomes
canonical truth until the user confirms it, at which point person/place
proposals are promoted into real Person/Place graph nodes.
"""

import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# One kind per meaningful category of understanding.
_TEXT_KINDS = {
    "human_time": "human_time",
    "life_stage": "life_stage",
    "relative_time": "relative_time",
    "events": "event",
    "quotes": "quote",
    "artifacts": "artifact",
    "media_refs": "media_ref",
    "themes": "theme",
    "values": "value",
    "traditions": "tradition",
    "emotions": "emotion",
}

SYSTEM_PROMPT = """You are the Story Discovery Engine for a life-preservation app.
A person has written a memory from their life in their own words. Read it the way
a caring family historian would — not like a database. Identify everything worth
preserving, and return ONLY a single JSON object with these keys (every key must
be present; use an empty array if you found nothing for it):

{
  "people":        [{"name": str, "relationship": str, "confidence": 0.0-1.0}],
  "places":        [{"name": str, "confidence": 0.0-1.0}],
  "human_time":    [{"text": str, "confidence": 0.0-1.0}],
  "calendar_time": [{"text": str, "year": int|null, "month": int|null, "precision": "year|month|day|approx", "confidence": 0.0-1.0}],
  "life_stage":    [{"text": str, "confidence": 0.0-1.0}],
  "relative_time": [{"text": str, "confidence": 0.0-1.0}],
  "events":        [{"text": str, "confidence": 0.0-1.0}],
  "quotes":        [{"text": str, "confidence": 0.0-1.0}],
  "artifacts":     [{"text": str, "confidence": 0.0-1.0}],
  "media_refs":    [{"text": str, "confidence": 0.0-1.0}],
  "themes":        [{"text": str, "confidence": 0.0-1.0}],
  "values":        [{"text": str, "confidence": 0.0-1.0}],
  "traditions":    [{"text": str, "confidence": 0.0-1.0}],
  "emotions":      [{"text": str, "confidence": 0.0-1.0}]
}

Guidance:
- people.relationship is the person's relationship to the author when it can be
  inferred (father, mother, grandfather, uncle, friend, coach, pastor, sibling,
  spouse, child, neighbor, teacher). Leave "" if unknown. Do not invent people.
- human_time is how humans actually remember time: "Summer 1969", "Early 1980s",
  "During high school", "Before Haley was born", "After Grandpa died". Preserve
  the phrasing from the story.
- life_stage: infancy, childhood, elementary/middle/high school, college,
  military, early career, marriage, parenthood, retirement, grandparenthood.
- relative_time: "before the move", "after the surgery", "during football season".
- events: fishing, camping, vacation, birthday, graduation, wedding, funeral,
  military service, road trip, holiday, etc.
- quotes: exact meaningful things people said or repeated. Keep them verbatim.
- artifacts: physical objects that carry meaning (a bracelet, a glove, a truck).
- themes/values/traditions/emotions: only when reasonably supported. Do not overreach.
- confidence is 0.0-1.0 for how clearly the text supports each item.
- Extract only what the text supports. Respond with ONLY the JSON, no prose."""


_SUMMARY = {
    "person": ("person", "people"), "place": ("place", "places"),
    "event": ("event", "events"), "quote": ("quote", "quotes"),
    "theme": ("theme", "themes"), "value": ("value", "values"),
    "artifact": ("artifact", "artifacts"), "tradition": ("tradition", "traditions"),
    "emotion": ("emotion", "emotions"), "human_time": ("moment in time", "moments in time"),
    "calendar_time": ("date", "dates"), "life_stage": ("life stage", "life stages"),
    "relative_time": ("moment", "moments"), "media_ref": ("media mention", "media mentions"),
}


def is_available():
    return bool(getattr(settings, "OPENAI_API_KEY", None))


def _person_stats(person):
    if not person:
        return None
    from apps.legacy.models import Media
    stories = person.memories.count()
    photos = Media.objects.filter(
        memories__in=person.memories.all(), media_type="photo").distinct().count()
    return {"stories": stories, "photos": photos}


def _similar(a, b):
    """Loose name similarity for possible-duplicate detection (not exact match)."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return False
    at, bt = set(a.split()), set(b.split())
    if at & bt:                      # shared token (e.g. a surname)
        return True
    if a in b or b in a:             # one contains the other
        return True
    for x in at:                     # nickname/prefix (Marv/Marvin)
        for y in bt:
            if len(x) >= 3 and len(y) >= 3 and (x.startswith(y) or y.startswith(x)):
                return True
    return False


def summary_text(groups):
    parts = []
    for g in groups:
        n = len(g["items"])
        sing, plur = _SUMMARY.get(g["kind"], (g["label"].lower(), g["label"].lower()))
        parts.append(f"{n} {sing if n == 1 else plur}")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _client():
    """A self-contained OpenAI client (no CoS/Beth coupling). None if unconfigured."""
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, timeout=30, max_retries=1)
    except Exception:  # pragma: no cover - import/init failure
        logger.warning("legacy.discovery: OpenAI client unavailable", exc_info=True)
        return None


def _extract(text):
    """Call OpenAI and return the parsed dict, or None on any failure."""
    client = _client()
    if client is None:
        return None
    model = getattr(settings, "LEGACY_DISCOVERY_MODEL", getattr(settings, "OPENAI_MODEL", "gpt-4o"))
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:8000]},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        logger.warning("legacy.discovery: model returned non-JSON", exc_info=True)
        return None
    except Exception:
        logger.error("legacy.discovery: extraction failed", exc_info=True)
        return None


def _conf(value):
    from apps.legacy.models import MemoryDiscovery
    try:
        v = float(value)
    except (TypeError, ValueError):
        return MemoryDiscovery.Confidence.MEDIUM
    if v >= 0.75:
        return MemoryDiscovery.Confidence.HIGH
    if v >= 0.45:
        return MemoryDiscovery.Confidence.MEDIUM
    return MemoryDiscovery.Confidence.LOW


def run_discovery(memory, extractor=None):
    """
    Run discovery on a memory and (re)build its `proposed` discoveries.

    Returns (status, discoveries):
      status in {"ok", "empty", "unavailable", "nothing"}.
    Accepted/rejected discoveries are preserved; only prior `proposed` rows are
    refreshed. `extractor` is injectable for tests (defaults to the OpenAI call).
    """
    from apps.legacy.models import MemoryDiscovery, Person, Place

    text = ("%s\n%s" % (memory.title, memory.body)).strip()
    if len(text) < 12:
        return "empty", []

    if extractor is None:
        if not is_available():
            return "unavailable", []
        extractor = _extract

    data = extractor(text)
    if not data:
        return "unavailable", []

    # Refresh proposals: clear previous undecided ones, keep accepted/rejected.
    MemoryDiscovery.objects.filter(memory=memory, status=MemoryDiscovery.Status.PROPOSED).delete()

    user = memory.user
    existing_people = {p.display_name.lower(): p for p in Person.objects.filter(user=user)}
    existing_places = {p.name.lower(): p for p in Place.objects.filter(user=user)}
    already = {
        (d.kind, d.label.lower())
        for d in MemoryDiscovery.objects.filter(memory=memory).exclude(status=MemoryDiscovery.Status.PROPOSED)
    }

    created = []

    def add(kind, label, confidence, detail=None):
        label = (label or "").strip()
        if not label or (kind, label.lower()) in already:
            return
        already.add((kind, label.lower()))
        created.append(MemoryDiscovery(
            memory=memory, kind=kind, label=label[:500],
            confidence=_conf(confidence), detail=detail or {},
        ))

    for p in data.get("people", []) or []:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        rel = (p.get("relationship") or "").strip()
        match = existing_people.get(name.lower())
        candidates = []
        if not match:
            candidates = [person for lname, person in existing_people.items()
                          if _similar(name, person.display_name)]
        # Relationship stays tied to the person (shown on the person card); we
        # deliberately do not create a separate, redundant relationship row.
        add(MemoryDiscovery.Kind.PERSON, name, p.get("confidence"), {
            "relationship": rel,
            "is_new": match is None and not candidates,
            "matched_person_id": match.id if match else None,
            "matched": _person_stats(match) if match else None,
            "candidates": [dict(id=c.id, name=c.display_name, **_person_stats(c))
                           for c in candidates[:3]],
        })

    for pl in data.get("places", []) or []:
        name = (pl.get("name") or "").strip()
        if not name:
            continue
        match = existing_places.get(name.lower())
        add(MemoryDiscovery.Kind.PLACE, name, pl.get("confidence"), {
            "matched_place_id": match.id if match else None,
            "is_new": match is None,
        })

    for ct in data.get("calendar_time", []) or []:
        label = (ct.get("text") or "").strip()
        if not label and ct.get("year"):
            label = str(ct["year"])
        add(MemoryDiscovery.Kind.CALENDAR_TIME, label, ct.get("confidence"), {
            "year": ct.get("year"), "month": ct.get("month"),
            "precision": ct.get("precision"),
        })

    for key, kind in _TEXT_KINDS.items():
        for item in data.get(key, []) or []:
            label = (item.get("text") or "").strip() if isinstance(item, dict) else str(item)
            conf = item.get("confidence") if isinstance(item, dict) else None
            add(kind, label, conf)

    if created:
        MemoryDiscovery.objects.bulk_create(created)

    proposed = list(MemoryDiscovery.objects.filter(
        memory=memory, status=MemoryDiscovery.Status.PROPOSED))
    return ("ok" if proposed else "nothing"), proposed


def grouped_proposals(memory):
    """Proposed discoveries grouped by kind, in display order, for the review UI."""
    from apps.legacy.models import MemoryDiscovery

    proposals = MemoryDiscovery.objects.filter(
        memory=memory, status=MemoryDiscovery.Status.PROPOSED)
    groups = {}
    for d in proposals:
        groups.setdefault(d.kind, []).append(d)
    order = MemoryDiscovery._ORDER
    headings = {
        "person": "People", "relationship": "Relationships", "place": "Places",
        "human_time": "Human time", "calendar_time": "Calendar time",
        "life_stage": "Life stage", "relative_time": "Relative time",
        "event": "Events", "quote": "Quotes", "artifact": "Artifacts",
        "media_ref": "Media", "theme": "Themes", "value": "Values",
        "tradition": "Traditions", "emotion": "Emotions",
    }
    return [
        {"kind": k, "label": headings.get(k, k.title()), "items": v}
        for k, v in sorted(groups.items(), key=lambda kv: order.get(kv[0], 99))
    ]


def confirm_discoveries(memory, accepted_ids=None, accept_all=False, resolutions=None):
    """
    Promotion gate. Accept the chosen proposals (or all), reject the rest.
    Person/Place acceptances create/link real graph nodes and connect them to
    the memory. `resolutions` maps a person-discovery id -> an existing Person id
    (link to it) or "new" (force-create), for duplicate resolution.
    Returns the number accepted.
    """
    from apps.legacy.models import MemoryDiscovery, Person, Place

    resolutions = resolutions or {}
    accepted_ids = set(int(i) for i in (accepted_ids or []))
    proposals = MemoryDiscovery.objects.filter(
        memory=memory, status=MemoryDiscovery.Status.PROPOSED)
    now = timezone.now()
    user = memory.user
    accepted = 0

    for d in proposals:
        keep = accept_all or (d.id in accepted_ids)
        if not keep:
            d.status = MemoryDiscovery.Status.REJECTED
            d.decided_at = now
            d.save(update_fields=["status", "decided_at"])
            continue

        if d.kind == MemoryDiscovery.Kind.PERSON:
            person = None
            res = resolutions.get(str(d.id)) or resolutions.get(d.id)
            if res and res != "new":
                person = Person.all_objects.filter(pk=res, user=user).first()
            elif res != "new":
                mid = d.detail.get("matched_person_id")
                if mid:
                    person = Person.all_objects.filter(pk=mid, user=user).first()
            if person is None:
                person = Person.objects.create(
                    user=user, display_name=d.label,
                    relationship_label=(d.detail.get("relationship") or "")[:120],
                    created_via=Person.CREATED_VIA_MANUAL,
                )
            elif not person.relationship_label and d.detail.get("relationship"):
                person.relationship_label = d.detail["relationship"][:120]
                person.save(update_fields=["relationship_label", "updated_at"])
            memory.people.add(person)
            d.linked_person = person

        elif d.kind == MemoryDiscovery.Kind.PLACE:
            place = None
            mid = d.detail.get("matched_place_id")
            if mid:
                place = Place.all_objects.filter(pk=mid, user=user).first()
            if place is None:
                place = Place.objects.create(
                    user=user, name=d.label, created_via=Place.CREATED_VIA_MANUAL)
            memory.places.add(place)
            d.linked_place = place

        d.status = MemoryDiscovery.Status.ACCEPTED
        d.decided_at = now
        d.save()
        accepted += 1

    return accepted
