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
import re

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Common words that carry no matching signal when pairing a story with media.
_STOPWORDS = {
    "this", "that", "there", "their", "them", "then", "they", "were", "with",
    "from", "have", "here", "your", "yours", "about", "which", "would", "could",
    "should", "when", "what", "where", "been", "into", "over", "some", "just",
    "like", "made", "make", "back", "very", "much", "more", "most", "only",
    "also", "them", "than", "onto", "upon", "each", "both", "same", "still",
    "after", "before", "again", "because", "while", "these", "those", "being",
    "everything", "something", "nothing", "remember", "memory", "story",
}
# Media captions/filenames often carry generic tokens that shouldn't match.
_MEDIA_STOPWORDS = {
    "photo", "photos", "image", "images", "img", "picture", "pictures", "pic",
    "pics", "scan", "scanned", "video", "clip", "audio", "recording", "file",
    "untitled", "copy", "final", "edit", "edited", "version", "download",
}


def _significant_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
            if w not in _STOPWORDS}


def _suggest_existing_media(memory, user, text, created):
    """Deterministically surface media the user already uploaded that seems to
    belong with this story (caption / filename shares a meaningful word). It is
    only a suggestion — nothing attaches until the user applies, media is never
    duplicated, and media already on this memory is skipped. No AI, no cost."""
    from apps.legacy.models import Media, MemoryDiscovery

    story_words = _significant_words(text)
    if not story_words:
        return
    attached = set(memory.media.values_list("id", flat=True))
    matches = []
    for m in Media.objects.filter(user=user).exclude(id__in=attached):
        hay = " ".join(x for x in (m.caption, m.original_filename) if x)
        tokens = set(re.findall(r"[a-z]{4,}", hay.lower())) - _MEDIA_STOPWORDS
        overlap = tokens & story_words
        if overlap:
            matches.append((len(overlap), m, sorted(overlap)[:4]))
    matches.sort(key=lambda t: t[0], reverse=True)
    for _, m, overlap in matches[:6]:
        is_photo = m.media_type == Media.MediaType.PHOTO
        created.append(MemoryDiscovery(
            memory=memory,
            kind=MemoryDiscovery.Kind.EXISTING_MEDIA,
            label=(m.caption or m.original_filename or m.get_media_type_display())[:500],
            confidence=MemoryDiscovery.Confidence.MEDIUM,
            detail={
                "media_id": m.id,
                "media_type": m.media_type,
                "media_type_display": m.get_media_type_display(),
                "is_photo": is_photo,
                "thumb_url": m.file.url if (is_photo and m.file) else "",
                "matched_on": overlap,
            },
        ))

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
  "places":        [{"name": str, "personal": bool, "official_name": str|null, "line1": str|null, "city": str|null, "state": str|null, "country": str|null, "lat": number|null, "lon": number|null, "place_confidence": "high"|"medium"|"low"|null, "reasoning": str|null, "confidence": 0.0-1.0}],
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
  "emotions":      [{"text": str, "confidence": 0.0-1.0}],
  "milestones":    [{"title": str, "kind": str, "year": int|null, "confidence": 0.0-1.0}],
  "prompts":       [str]
}

Guidance:
- people.relationship is the person's relationship to the author when it can be
  inferred (father, mother, grandfather, uncle, friend, coach, pastor, sibling,
  spouse, child, neighbor, teacher). Leave "" if unknown. Do not invent people.
- places: put the place as the author named it in `name`, then RESOLVE it:
  * PERSONAL/private places (Grandma's house, Dad's shop, the old barn, the
    fishing hole, our cabin) → set "personal": true and DO NOT identify them;
    leave every address/coordinate field null and place_confidence null.
  * PUBLIC places (restaurant, church, school, park, business, landmark) → try to
    identify the real official place using context you ALREADY have, in priority:
    (1) an explicit location named in the story ("Riverside, California");
    (2) another place already in the SAME story ("we left UT Medical Center and
    stopped at Nauti K's" → Nauti K's is near Knoxville); (3) the author's home
    location (provided to you) — prefer a well-known place within ~30-50 miles of
    home when the story names no nearer location.
  * When confident, fill official_name, line1 (street address), city, state,
    country, lat, lon; set place_confidence "high" (very confident) or "medium"
    (plausible but unsure); and give a SHORT reasoning ("A well-known business
    about 15 miles from your home in Maryville, TN").
  * If you cannot confidently identify it, set place_confidence "low" and leave
    address and coordinates null. NEVER fabricate an address or coordinates and
    never guess — a wrong address is far worse than an unresolved place.
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
- milestones: MAJOR life chapters the story marks — marriage, bought first house,
  graduation, military service, first job / started career, retirement, birth of a
  child or grandchild, meeting significant people, moving/relocation, baptism /
  started a church, divorce, a diagnosis or recovery, death of a parent or spouse,
  starting or selling a business, a major vacation. `title` is specific ("Bought
  our first house", "Met Eric and Carrie"). `kind` is one of: marriage, home,
  education, military, career, birth, death, faith, health, relocation, travel,
  business, relationship, other. `year` when the text supports it, else null. Only
  when the story genuinely marks a chapter — most events are NOT milestones.
- confidence is 0.0-1.0 for how clearly the text supports each item.
- prompts: 3-5 SHORT, SPECIFIC, optional preservation suggestions based on what
  this story leaves out. ALWAYS reference something concrete the author actually
  wrote. Good: "You mentioned your grandfather but never described what he was
  like." / "You wrote about the fishing trip but not what happened afterward." /
  "You mentioned Christmas but not who celebrated with you." NEVER generic ("Tell
  me more"), never filler. If the story is already rich, return fewer. These are
  gentle nudges for the author to preserve more — not questions you are asking.
- Extract only what the text supports. Respond with ONLY the JSON, no prose."""


_SUMMARY = {
    "person": ("person", "people"), "place": ("place", "places"),
    "milestone": ("life milestone", "life milestones"),
    "event": ("event", "events"), "quote": ("quote", "quotes"),
    "theme": ("theme", "themes"), "value": ("value", "values"),
    "artifact": ("artifact", "artifacts"), "tradition": ("tradition", "traditions"),
    "emotion": ("emotion", "emotions"), "human_time": ("moment in time", "moments in time"),
    "calendar_time": ("date", "dates"), "life_stage": ("life stage", "life stages"),
    "relative_time": ("moment", "moments"), "media_ref": ("media mention", "media mentions"),
    "existing_media": ("photo you already have", "photos you already have"),
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


def _place_stats(place):
    if not place:
        return None
    from apps.legacy.models import Media
    stories = place.memories.count()
    photos = Media.objects.filter(
        memories__in=place.memories.all(), media_type="photo").distinct().count()
    return {"stories": stories, "photos": photos}


# Generic words that shouldn't, on their own, make two place names "similar"
# ("Grandma's house" vs "The lake house" must NOT match on "house").
_PLACE_GENERIC = {
    "the", "a", "an", "our", "my", "old", "new", "of", "and", "at",
    "house", "home", "place", "house's", "homeplace",
}


def _place_similar(a, b):
    """Place-name similarity that ignores generic words to avoid false matches."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return False
    at = set(a.split()) - _PLACE_GENERIC
    bt = set(b.split()) - _PLACE_GENERIC
    if at & bt:                       # shared meaningful token
        return True
    if len(a) >= 5 and (a in b or b in a):
        return True
    return False


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


def summary_text(sections):
    # Accepts the sectioned proposals (or a flat group list) and flattens to
    # a human count summary.
    parts = []
    for entry in sections:
        for g in entry.get("groups", [entry]):
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


def _extract(text, home=None):
    """Call OpenAI and return the parsed dict, or None on any failure. `home` is
    the author's configured home location, given to the model ONLY to help it
    identify public places when the story names no nearer location."""
    client = _client()
    if client is None:
        return None
    model = getattr(settings, "LEGACY_DISCOVERY_MODEL", getattr(settings, "OPENAI_MODEL", "gpt-4o"))
    user_content = text[:8000]
    if home:
        user_content += (
            "\n\n[Context Legacy already knows — the author's home location is %s. "
            "Use it ONLY to help identify public places when the story names no "
            "nearer location. Do not add it as a discovered place.]" % home)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
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


def run_discovery(memory, extractor=None, place_lookup_fn=None):
    """
    Run discovery on a memory and (re)build its `proposed` discoveries.

    Returns (status, discoveries):
      status in {"ok", "empty", "unavailable", "nothing"}.
    Accepted/rejected discoveries are preserved; only prior `proposed` rows are
    refreshed. `extractor` is injectable for tests (defaults to the OpenAI call);
    `place_lookup_fn` is the place-verification module (defaults to the real one).
    """
    from apps.legacy.models import LifeMilestone, MemoryDiscovery, Person, Place
    if place_lookup_fn is None:
        from apps.legacy.services import place_lookup as place_lookup_fn

    text = ("%s\n%s" % (memory.title, memory.body)).strip()
    if len(text) < 12:
        return "empty", []

    # The user's home location is handed to the same Discovery call so OpenAI can
    # resolve public places with context — no second lookup, no extra request.
    home_ctx = place_lookup_fn.home_location(memory.user)
    home_text = home_ctx["text"] if home_ctx else None

    if extractor is None:
        if not is_available():
            return "unavailable", []
        extractor = lambda t: _extract(t, home=home_text)

    data = extractor(text)
    if not data:
        return "unavailable", []

    # Refresh proposals: clear previous undecided ones, keep accepted/rejected.
    MemoryDiscovery.objects.filter(memory=memory, status=MemoryDiscovery.Status.PROPOSED).delete()

    user = memory.user
    existing_people = {p.display_name.lower(): p for p in Person.objects.filter(user=user)}
    existing_places = {p.name.lower(): p for p in Place.objects.filter(user=user)}
    existing_milestones = {m.title.lower(): m for m in LifeMilestone.objects.filter(user=user)}
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
        d = detail or {}
        # Keep the engine's original proposal so a future version of Legacy can
        # learn from the user's corrections (not implemented now).
        d.setdefault("original_label", label[:500])
        created.append(MemoryDiscovery(
            memory=memory, kind=kind, label=label[:500],
            confidence=_conf(confidence), detail=d,
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

    # Places carry their resolution INLINE from the same Discovery call — OpenAI
    # identified the public place using the story + the home context we supplied.
    # We still search Legacy first (never duplicate) and keep a personal-place
    # safety net. No second lookup, no network request here.
    for pl in data.get("places", []) or []:
        name = (pl.get("name") or "").strip()
        if not name:
            continue
        # Trust the model's personal flag, with the heuristic as a safety net.
        personal = bool(pl.get("personal")) or place_lookup_fn.is_personal_place(name)
        match = existing_places.get(name.lower())
        # Search Legacy first — never duplicate a place you already have. Personal
        # places aren't fuzzy-matched (they'd collide on generic words like "house").
        ex_candidates = []
        if not match and not personal:
            ex_candidates = [p for lname, p in existing_places.items()
                             if _place_similar(name, p.name)]

        pconf = (pl.get("place_confidence") or "").lower()
        reasoning = (pl.get("reasoning") or "").strip()
        lookups, lookup_confidence = [], None
        # Adopt the model's identification only for a confident PUBLIC place we
        # don't already have — and only if it actually gave us a location. Low
        # confidence stays unresolved; we never fabricate an address.
        if not match and not ex_candidates and not personal and pconf in ("high", "medium"):
            if any(pl.get(k) for k in ("line1", "city", "state")):
                lookups = [{
                    "name": (pl.get("official_name") or name)[:200],
                    "line1": (pl.get("line1") or "")[:200],
                    "city": (pl.get("city") or "")[:120],
                    "state": (pl.get("state") or "")[:120],
                    "country": (pl.get("country") or "")[:120],
                    "lat": str(pl.get("lat")) if pl.get("lat") is not None else "",
                    "lon": str(pl.get("lon")) if pl.get("lon") is not None else "",
                    "display": ", ".join(x for x in (
                        pl.get("line1"), pl.get("city"), pl.get("state")) if x),
                }]
                lookup_confidence = "verified" if pconf == "high" else "possible"

        # Internal-only log for debugging/refinement — never shown to the user.
        logger.info(
            "[legacy.place_resolution] mem=%s name=%r personal=%s existing=%s "
            "resolved=%r confidence=%s home=%r reason=%r",
            memory.pk, name, personal, bool(match or ex_candidates),
            (lookups[0]["display"] if lookups else None), pconf or None,
            home_text, reasoning or None)

        add(MemoryDiscovery.Kind.PLACE, name, pl.get("confidence"), {
            "matched_place_id": match.id if match else None,
            "is_new": match is None and not ex_candidates,
            "personal": personal,
            "matched": (dict(name=match.name, **_place_stats(match)) if match else None),
            "existing": [dict(id=p.id, name=p.name, **_place_stats(p))
                         for p in ex_candidates[:3]],
            "lookup": lookups,
            "lookup_confidence": lookup_confidence,
            "reasoning": reasoning if lookups else "",
        })

    for ml in data.get("milestones", []) or []:
        title = (ml.get("title") or "").strip()
        if not title:
            continue
        match = existing_milestones.get(title.lower())
        candidates = []
        if not match:
            candidates = [m for lname, m in existing_milestones.items()
                          if _similar(title, m.title)]
        add(MemoryDiscovery.Kind.MILESTONE, title, ml.get("confidence"), {
            "kind": (ml.get("kind") or "other"),
            "year": ml.get("year"),
            "is_new": match is None and not candidates,
            "matched_milestone_id": match.id if match else None,
            "matched": ({"stories": match.memories.count(), "year": match.year}
                        if match else None),
            "candidates": [dict(id=c.id, title=c.title, year=c.year, stories=c.memories.count())
                           for c in candidates[:3]],
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

    # Existing media the user already uploaded that seems to belong here.
    _suggest_existing_media(memory, user, text, created)

    if created:
        MemoryDiscovery.objects.bulk_create(created)

    # Optional, story-aware memory prompts (never required; suggestions only).
    prompts = [str(p).strip() for p in (data.get("prompts") or []) if str(p).strip()][:5]
    if memory.discovery_prompts != prompts:
        memory.discovery_prompts = prompts
        memory.save(update_fields=["discovery_prompts", "updated_at"])

    proposed = list(MemoryDiscovery.objects.filter(
        memory=memory, status=MemoryDiscovery.Status.PROPOSED))
    return ("ok" if proposed else "nothing"), proposed


# Kind groups gather into a few calm, human super-sections so the panel stays
# readable as Discovery finds more. Order here is the order sections appear in.
_SECTIONS = [
    ("People", {"person", "relationship"}),
    ("Places", {"place"}),
    ("Life", {"milestone"}),
    ("Time", {"human_time", "calendar_time", "life_stage", "relative_time"}),
    ("Meaning", {"event", "quote", "theme", "value", "tradition", "emotion"}),
    ("Media", {"existing_media", "media_ref", "artifact"}),
]


def grouped_proposals(memory):
    """Proposed discoveries grouped by kind and gathered into collapsible
    super-sections (People / Places / Life / Time / Meaning / Media) for the
    review UI. Sections keep the panel readable as understanding grows."""
    from apps.legacy.models import MemoryDiscovery

    proposals = MemoryDiscovery.objects.filter(
        memory=memory, status=MemoryDiscovery.Status.PROPOSED)
    by_kind = {}
    for d in proposals:
        by_kind.setdefault(d.kind, []).append(d)
    order = MemoryDiscovery._ORDER
    headings = {
        "person": "People", "relationship": "Relationships", "place": "Places",
        "milestone": "Life milestones",
        "human_time": "Human time", "calendar_time": "Calendar time",
        "life_stage": "Life stage", "relative_time": "Relative time",
        "event": "Events", "quote": "Quotes", "artifact": "Artifacts",
        "media_ref": "Media", "existing_media": "Photos & media you already have",
        "theme": "Themes", "value": "Values",
        "tradition": "Traditions", "emotion": "Emotions",
    }

    def group_for(kind):
        return {"kind": kind, "label": headings.get(kind, kind.title()),
                "items": by_kind[kind]}

    sections, placed = [], set()
    for title, kinds in _SECTIONS:
        present = sorted((k for k in kinds if k in by_kind),
                         key=lambda k: order.get(k, 99))
        if not present:
            continue
        placed.update(present)
        groups = [group_for(k) for k in present]
        sections.append({
            "title": title, "groups": groups,
            "count": sum(len(g["items"]) for g in groups),
        })
    # Any kind not assigned to a named section still shows, never dropped.
    leftover = sorted((k for k in by_kind if k not in placed),
                      key=lambda k: order.get(k, 99))
    if leftover:
        groups = [group_for(k) for k in leftover]
        sections.append({
            "title": "More", "groups": groups,
            "count": sum(len(g["items"]) for g in groups),
        })
    return sections


def confirm_discoveries(memory, accepted_ids=None, accept_all=False, resolutions=None, edits=None):
    """
    Promotion gate. Accept the chosen proposals (or all), reject the rest.
    Person/Place acceptances create/link real graph nodes and connect them to
    the memory. `resolutions` maps a person-discovery id -> an existing Person id
    (link to it) or "new" (force-create), for duplicate resolution. `edits` maps
    a discovery id -> {label, relationship, location, notes} — inline corrections
    the user made; the engine's original value is preserved on the row for future
    learning. Returns the number accepted.
    """
    from apps.legacy.models import LifeMilestone, MemoryDiscovery, Person, Place

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _dec(v):
        from decimal import Decimal, InvalidOperation
        try:
            return Decimal(str(v)).quantize(Decimal("0.000001"))
        except (TypeError, ValueError, InvalidOperation):
            return None

    valid_kinds = set(LifeMilestone.Kind.values)
    resolutions = resolutions or {}
    edits = edits or {}
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

        # Apply inline edits (preserving the engine's original for future learning).
        e = edits.get(str(d.id)) or edits.get(d.id)
        if e:
            new_label = (e.get("label") or "").strip()
            if new_label and new_label != d.label:
                d.detail.setdefault("original_label", d.label)
                d.detail["edited"] = True
                d.label = new_label[:500]
            if e.get("relationship") is not None:
                rel = (e.get("relationship") or "").strip()
                if rel != (d.detail.get("relationship") or ""):
                    d.detail["edited"] = True
                    d.detail["relationship"] = rel
            if e.get("location"):
                d.detail["location"] = e["location"].strip()
            if e.get("notes"):
                d.detail["notes"] = e["notes"].strip()
            if e.get("year") is not None:
                d.detail["year"] = _int(e.get("year"))

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
                    bio=(d.detail.get("notes") or ""),
                    created_via=Person.CREATED_VIA_MANUAL,
                )
            elif not person.relationship_label and d.detail.get("relationship"):
                person.relationship_label = d.detail["relationship"][:120]
                person.save(update_fields=["relationship_label", "updated_at"])
            memory.people.add(person)
            d.linked_person = person

        elif d.kind == MemoryDiscovery.Kind.PLACE:
            place = None
            choice = resolutions.get(str(d.id)) or resolutions.get(d.id) or ""
            lookups = d.detail.get("lookup") or []
            # 1) Use an existing Legacy place (exact match or a chosen candidate) —
            #    never duplicate a place you already have.
            if choice.startswith("existing:"):
                place = Place.all_objects.filter(pk=choice.split(":", 1)[1], user=user).first()
            elif d.detail.get("matched_place_id") and not choice:
                place = Place.all_objects.filter(pk=d.detail["matched_place_id"], user=user).first()
            # 2) Adopt a verified public place (name + location only).
            if place is None and choice.startswith("lookup:"):
                try:
                    cand = lookups[int(choice.split(":", 1)[1])]
                except (ValueError, IndexError):
                    cand = None
                if cand:
                    place = Place.objects.create(
                        user=user,
                        name=cand.get("name") or d.label,
                        location_text=", ".join(x for x in (
                            cand.get("line1"), cand.get("city"), cand.get("state"),
                            cand.get("country")) if x)[:255],
                        latitude=_dec(cand.get("lat")),
                        longitude=_dec(cand.get("lon")),
                        created_via=Place.CREATED_VIA_MANUAL)
            # 3) Fall back to a personal place — the user's wording, no address.
            if place is None:
                place = Place.objects.create(
                    user=user, name=d.label,
                    location_text=(d.detail.get("location") or ""),
                    created_via=Place.CREATED_VIA_MANUAL)
            memory.places.add(place)
            d.linked_place = place

        elif d.kind == MemoryDiscovery.Kind.MILESTONE:
            milestone = None
            res = resolutions.get(str(d.id)) or resolutions.get(d.id)
            if res and res != "new":
                milestone = LifeMilestone.all_objects.filter(pk=res, user=user).first()
            elif res != "new":
                mid = d.detail.get("matched_milestone_id")
                if mid:
                    milestone = LifeMilestone.all_objects.filter(pk=mid, user=user).first()
            kind = d.detail.get("kind")
            kind = kind if kind in valid_kinds else LifeMilestone.Kind.OTHER
            year = _int(d.detail.get("year"))
            if milestone is None:
                milestone = LifeMilestone.objects.create(
                    user=user, title=d.label[:200], kind=kind, year=year,
                    created_via=LifeMilestone.CREATED_VIA_MANUAL)
            elif year and not milestone.year:
                milestone.year = year
                milestone.save(update_fields=["year", "updated_at"])
            memory.milestones.add(milestone)
            d.linked_milestone = milestone

        elif d.kind == MemoryDiscovery.Kind.EXISTING_MEDIA:
            # Associate an already-uploaded media item — never duplicate it.
            from apps.legacy.models import Media
            mid = d.detail.get("media_id")
            media = Media.all_objects.filter(pk=mid, user=user).first() if mid else None
            if media:
                memory.media.add(media)
                if media.media_type == Media.MediaType.PHOTO and not memory.primary_media_id:
                    memory.primary_media = media
                    memory.save(update_fields=["primary_media", "updated_at"])

        d.status = MemoryDiscovery.Status.ACCEPTED
        d.decided_at = now
        d.save()
        accepted += 1

    return accepted
